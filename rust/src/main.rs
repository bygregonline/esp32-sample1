//! ESP32 Monitor — Rust/ESP-IDF (std)
//!
//! Equivalente completo al C: sensores DHT22, GPS NEO-6M, ADC batería,
//! LCD ST7789V2, OLED SSD1306, Wi-Fi AP+STA, servidor HTTP, clima Open-Meteo.
//!
//! Endpoints idénticos a la implementación C:
//!   GET  /api/status           — snapshot completo
//!   GET  /api/sensors          — última lectura de sensores
//!   GET  /api/weather          — datos de clima
//!   POST /api/config/interval  — cambia ciclo de sensores (5-300 s)
//!   POST /api/config/display   — oculta/muestra secciones del display
//!   POST /wifi                 — guarda credenciales Wi-Fi
//!   GET  /                     — página HTML

mod display;
mod gps;
mod monitor_state;
mod network;
mod weather;

use std::{thread, time::Duration};

use esp_idf_svc::hal::adc::oneshot::config::AdcChannelConfig;
use esp_idf_svc::{
    hal::{
        adc::{attenuation, oneshot::*},
        delay::FreeRtos,
        gpio::{PinDriver, Pull},
        i2c::{I2cConfig, I2cDriver},
        peripherals::Peripherals,
        spi::{config::Config as SpiConfig, SpiDeviceDriver, SpiDriver, SpiDriverConfig},
        uart::{config::Config as UartConfig, UartDriver},
        units::Hertz,
    },
    log::EspLogger,
    systime::EspSystemTime,
};

use dht_sensor::dht22;
use mipidsi::{interface::SpiInterface, models::ST7789, options::ColorOrder, Builder};
use ssd1306::{
    mode::{BufferedGraphicsMode, DisplayConfig},
    prelude::{DisplayRotation, DisplaySize128x64},
    I2CDisplayInterface, Ssd1306,
};

use monitor_state::{MonitorState, SENSOR_INTERVAL_DEFAULT_SECS};

// ── Constantes ADC ────────────────────────────────────────────────────────
const ADC_EXTERNAL_DIVIDER: f32 = 2.2;
const VOLTAGE_SENSOR_RATIO: f32 = 5.0;
const VOLTAGE_CALIBRATION: f32 = 1.0;
const ADC_FULL_SCALE_VOLTS: f32 = 2.45;
const ADC_FULL_SCALE_COUNTS: f32 = 4_095.0;

fn main() -> anyhow::Result<()> {
    // Inicializar logger y link patches de ESP-IDF
    esp_idf_svc::sys::link_patches();
    EspLogger::initialize_default();

    log::info!("Iniciando ESP32 Monitor (Rust/std)");

    let peripherals = Peripherals::take()?;
    let state = MonitorState::new();

    // ── LCD ST7789V2 170×320 via SPI2 ────────────────────────────────────
    let spi_driver = SpiDriver::new(
        peripherals.spi2,
        peripherals.pins.gpio18, // SCK
        peripherals.pins.gpio23, // MOSI
        None::<esp_idf_svc::hal::gpio::AnyIOPin>,
        &SpiDriverConfig::default(),
    )?;
    let spi_device = SpiDeviceDriver::new(
        spi_driver,
        Some(peripherals.pins.gpio13), // CS
        &SpiConfig::new().baudrate(Hertz(20_000_000)),
    )?;
    let lcd_dc = PinDriver::output(peripherals.pins.gpio27)?;
    let lcd_reset = PinDriver::output(peripherals.pins.gpio26)?;
    let mut spi_buf = [0u8; 512];
    let iface = SpiInterface::new(spi_device, lcd_dc, &mut spi_buf);
    let mut delay = FreeRtos;
    let mut lcd = Builder::new(ST7789, iface)
        .reset_pin(lcd_reset)
        .display_size(170, 320)
        .display_offset(35, 0)
        .color_order(ColorOrder::Rgb)
        .init(&mut delay)
        .map_err(|error| anyhow::anyhow!("LCD init failed: {error:?}"))?;

    // ── OLED SSD1306 128×64 via I2C ──────────────────────────────────────
    let i2c = I2cDriver::new(
        peripherals.i2c0,
        peripherals.pins.gpio21, // SDA
        peripherals.pins.gpio22, // SCL
        &I2cConfig::default().baudrate(Hertz(400_000)),
    )?;
    let mut oled: Ssd1306<_, DisplaySize128x64, BufferedGraphicsMode<DisplaySize128x64>> =
        Ssd1306::new(
            I2CDisplayInterface::new(i2c),
            DisplaySize128x64,
            DisplayRotation::Rotate0,
        )
        .into_buffered_graphics_mode();
    oled.init()
        .map_err(|error| anyhow::anyhow!("OLED init failed: {error:?}"))?;

    // ── DHT22 GPIO33 (open-drain + pull-up) ──────────────────────────────
    let mut dht_pin = PinDriver::input_output_od(peripherals.pins.gpio33, Pull::Up)?;
    dht_pin.set_high()?;

    // ── GPS NEO-6M UART1 (RX=16, TX=17) 9600 baud ────────────────────────
    let gps_uart = UartDriver::new(
        peripherals.uart1,
        peripherals.pins.gpio17, // TX del ESP → RX del GPS
        peripherals.pins.gpio16, // RX del ESP ← TX del GPS
        None::<esp_idf_svc::hal::gpio::AnyIOPin>,
        None::<esp_idf_svc::hal::gpio::AnyIOPin>,
        &UartConfig::default().baudrate(Hertz(9600)),
    )?;
    let mut gps = gps::NmeaParser::new();

    // ── ADC batería GPIO34 ────────────────────────────────────────────────
    let adc_driver = AdcDriver::new(peripherals.adc1)?;
    let adc_channel_config = AdcChannelConfig {
        attenuation: attenuation::DB_12,
        ..Default::default()
    };
    let mut adc_pin =
        AdcChannelDriver::new(&adc_driver, peripherals.pins.gpio34, &adc_channel_config)?;

    // ── Red (Wi-Fi + HTTP + Weather) ──────────────────────────────────────
    network::start_network(state.clone())?;

    // ── Contadores de tiempo ──────────────────────────────────────────────
    let mut dht_last_ms: u64 = 0;
    let mut screen_last_ms: u64 = 0;

    let now_ms = || EspSystemTime {}.now().as_millis() as u64;
    let now_us = || EspSystemTime {}.now().as_micros() as i64;

    // Forzar primer ciclo inmediato
    let first_run_offset = SENSOR_INTERVAL_DEFAULT_SECS as u64 * 1000;
    let mut sensor_last_ms = now_ms().saturating_sub(first_run_offset);

    let mut temperature: Option<f32> = None;
    let mut humidity: Option<f32> = None;

    loop {
        let t = now_ms();

        // ── GPS ───────────────────────────────────────────────────────────
        let mut buf = [0u8; 64];
        let n = gps_uart.read(&mut buf, 0).unwrap_or(0);
        if n > 0 {
            gps.feed(&buf[..n], t as u32);
        }
        let fix = gps.has_recent_fix(t as u32);
        state.set_gps(
            fix,
            gps.satellites.is_some(),
            gps.latitude.unwrap_or(0.0) as f64,
            gps.longitude.unwrap_or(0.0) as f64,
            gps.satellites.unwrap_or(0) as i32,
        );

        // ── Ciclo de sensores ─────────────────────────────────────────────
        let interval_ms = state.snapshot().sensor_interval_secs as u64 * 1000;
        if t.saturating_sub(sensor_last_ms) >= interval_ms {
            sensor_last_ms = t;

            // DHT22 — mínimo 2.5 s entre lecturas
            if t.saturating_sub(dht_last_ms) >= 2500 {
                dht_last_ms = t;
                match dht22::blocking::read(&mut delay, &mut dht_pin) {
                    Ok(r) => {
                        temperature = Some(r.temperature);
                        humidity = Some(r.relative_humidity);
                    }
                    Err(e) => {
                        log::warn!("DHT22 error: {:?}", e);
                        temperature = None;
                        humidity = None;
                    }
                }
            }

            // ADC batería — 8 muestras promediadas
            let mut raw_sum: u32 = 0;
            for _ in 0..8 {
                raw_sum += adc_pin.read_raw().unwrap_or(0) as u32;
            }
            let raw_avg = raw_sum / 8;
            let adc_volts = raw_avg as f32 * ADC_FULL_SCALE_VOLTS / ADC_FULL_SCALE_COUNTS;
            let battery_voltage =
                adc_volts * ADC_EXTERNAL_DIVIDER * VOLTAGE_SENSOR_RATIO * VOLTAGE_CALIBRATION;

            state.set_sensors(
                battery_voltage,
                temperature.unwrap_or(0.0),
                humidity.unwrap_or(0.0),
                temperature.is_some() && humidity.is_some(),
                t,
            );

            log::info!(
                "Bat {:.2}V | T {:?}C | H {:?}% | GPS {} | ciclo {}s",
                battery_voltage,
                temperature,
                humidity,
                if fix { "FIX" } else { "sin fix" },
                state.snapshot().sensor_interval_secs,
            );
        }

        // ── Display (cada 1 s) ────────────────────────────────────────────
        if t.saturating_sub(screen_last_ms) >= 1000 {
            screen_last_ms = t;
            let snap = state.snapshot();
            let remaining = MonitorState::seconds_until_refresh(&snap, now_us());

            display::render_lcd(&mut lcd, &snap, now_us(), remaining);
            display::render_oled(&mut oled, &snap, remaining);
            let _ = oled.flush();
        }

        thread::sleep(Duration::from_millis(20));
    }
}
