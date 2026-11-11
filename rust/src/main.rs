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

mod ble;
mod bmp280;
pub(crate) mod display;
mod gps;
mod ml_demo;
mod monitor_state;
mod moon_image;
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
    std::env::set_var("TZ", option_env!("MONITOR_TZ").unwrap_or("CST6"));
    unsafe {
        esp_idf_sys::tzset();
    }

    log::info!("Iniciando ESP32 Monitor (Rust/std)");

    let peripherals = Peripherals::take()?;
    let state = MonitorState::new();
    state.log_event("Booting firmware");
    let bmp_i2c = I2cDriver::new(
        peripherals.i2c1,
        peripherals.pins.gpio1,
        peripherals.pins.gpio2,
        &I2cConfig::default().baudrate(Hertz(400_000)),
    )?;
    let mut bmp = match bmp280::Bmp280::new(bmp_i2c) {
        Ok(sensor) => {
            log::info!("BMP280 detected");
            state.log_event("BMP280 detected");
            Some(sensor)
        }
        Err(error) => {
            log::warn!("BMP280 unavailable: {error}");
            state.log_event("BMP280 unavailable");
            None
        }
    };

    // ── LCD ST7789V2 170×320 via SPI2 ────────────────────────────────────
    let spi_driver = SpiDriver::new(
        peripherals.spi2,
        peripherals.pins.gpio12, // SCK
        peripherals.pins.gpio11, // MOSI
        None::<esp_idf_svc::hal::gpio::AnyIOPin>,
        &SpiDriverConfig::default(),
    )?;
    let spi_device = SpiDeviceDriver::new(
        spi_driver,
        Some(peripherals.pins.gpio10), // CS
        &SpiConfig::new().baudrate(Hertz(20_000_000)),
    )?;
    let lcd_dc = PinDriver::output(peripherals.pins.gpio13)?;
    let lcd_reset = PinDriver::output(peripherals.pins.gpio14)?;
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
        peripherals.pins.gpio8, // SDA
        peripherals.pins.gpio9, // SCL
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

    // ── DHT22 GPIO6 (open-drain + pull-up) ───────────────────────────────
    let mut dht_pin = PinDriver::input_output_od(peripherals.pins.gpio6, Pull::Up)?;
    dht_pin.set_high()?;

    // ── GPS NEO-6M UART1 (RX=18, TX=17) 9600 baud ────────────────────────
    let gps_uart = UartDriver::new(
        peripherals.uart1,
        peripherals.pins.gpio17, // TX del ESP → RX del GPS
        peripherals.pins.gpio18, // RX del ESP ← TX del GPS
        None::<esp_idf_svc::hal::gpio::AnyIOPin>,
        None::<esp_idf_svc::hal::gpio::AnyIOPin>,
        &UartConfig::default().baudrate(Hertz(9600)),
    )?;
    let mut gps = gps::NmeaParser::new();

    // ── ADC batería GPIO4 (ADC1_CH3) ─────────────────────────────────────
    let adc_driver = AdcDriver::new(peripherals.adc1)?;
    let adc_channel_config = AdcChannelConfig {
        attenuation: attenuation::DB_12,
        ..Default::default()
    };
    let mut adc_pin =
        AdcChannelDriver::new(&adc_driver, peripherals.pins.gpio4, &adc_channel_config)?;

    // ── Red (Wi-Fi + HTTP + Weather) ──────────────────────────────────────
    let (wifi_modem, bluetooth_modem) = peripherals.modem.split();
    network::start_network(state.clone(), wifi_modem)?;
    ble::start(bluetooth_modem, state.clone())?;
    let _sntp = esp_idf_svc::sntp::EspSntp::new_default()?;
    let ml_ready = ml_demo::init();
    if !ml_ready {
        log::warn!("TensorFlow Lite Micro demo is unavailable");
    }

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
                        state.log_event("DHT22 read OK");
                    }
                    Err(e) => {
                        log::warn!("DHT22 error: {:?}", e);
                        state.log_event("DHT22 unavailable");
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

            match bmp.as_mut().map(|sensor| sensor.pressure_hpa()) {
                Some(Ok(p)) => state.set_bmp280(p, true),
                _ => state.set_bmp280(0.0, false),
            }

            state.set_sensors(
                battery_voltage,
                temperature.unwrap_or(0.0),
                humidity.unwrap_or(0.0),
                temperature.is_some() && humidity.is_some(),
                t,
            );

            if ml_ready {
                if let (Some(temperature_c), Some(humidity_percent)) = (temperature, humidity) {
                    // The published demo model expects one float in [0, 2π] per inference.
                    ml_demo::log_prediction("DHT22 temperature", (temperature_c + 40.0) / 120.0);
                    ml_demo::log_prediction("DHT22 humidity", humidity_percent / 100.0);
                } else {
                    ml_demo::log_prediction("battery voltage", battery_voltage / 5.0);
                }
            }

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
