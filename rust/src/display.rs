//! Render LCD (ST7789V2 170×320) y OLED (SSD1306 128×64).
//! Layout y colores idénticos a display.c en C.

use core::fmt::Write as FmtWrite;
use embedded_graphics::{
    mono_font::{ascii::FONT_6X10, MonoTextStyle},
    pixelcolor::{BinaryColor, Rgb565},
    prelude::{DrawTarget, Point, RgbColor},
    primitives::{Line, Primitive, PrimitiveStyle},
    text::{Baseline, Text},
    Drawable,
};
use heapless::String;

use crate::monitor_state::{
    MonitorData, DISPLAY_FIELD_BATTERY, DISPLAY_FIELD_DHT, DISPLAY_FIELD_GPS, DISPLAY_FIELD_WEATHER,
};

// ── Colores ────────────────────────────────────────────────────────────────
const C_TITLE: Rgb565 = Rgb565::new(10, 27, 28); // azul claro
const C_LABEL: Rgb565 = Rgb565::new(0, 24, 25); // cian
const C_VALUE: Rgb565 = Rgb565::WHITE;
const C_OK: Rgb565 = Rgb565::new(3, 26, 12); // verde
const C_WARN: Rgb565 = Rgb565::new(31, 23, 0); // amarillo
const C_DIM: Rgb565 = Rgb565::new(5, 7, 8); // gris oscuro
const C_WEATHER: Rgb565 = Rgb565::new(31, 18, 0); // naranja

// ── LCD render ────────────────────────────────────────────────────────────
pub fn render_lcd<D>(display: &mut D, data: &MonitorData, _now_us: i64, remaining: i32)
where
    D: DrawTarget<Color = Rgb565>,
{
    let _ = display.clear(Rgb565::BLACK);
    let mask = data.display_mask;

    // Título
    lcd_text(display, "ESP32 MONITOR", 4, 4, C_TITLE);
    lcd_hline(display, 14, C_DIM);

    // Wi-Fi
    if data.wifi_connected {
        let mut s: String<64> = String::new();
        let _ = write!(
            s,
            "WIFI {}  {}",
            &data.wifi_ssid[..data.wifi_ssid.len().min(12)],
            data.ip_address
        );
        lcd_text(display, s.as_str(), 4, 20, C_OK);
    } else {
        lcd_text(display, "WIFI SIN CONEXION  AP:192.168.4.1", 4, 20, C_WARN);
    }

    // Batería
    if mask & DISPLAY_FIELD_BATTERY != 0 {
        lcd_text(display, "BAT", 4, 36, C_LABEL);
        let mut s: String<16> = String::new();
        let _ = write!(s, "{:.2}V", data.battery_voltage);
        lcd_text(
            display,
            s.as_str(),
            28,
            36,
            if data.battery_voltage > 3.5 {
                C_OK
            } else {
                C_WARN
            },
        );
    }
    lcd_hline(display, 46, C_DIM);

    // Temperatura / Humedad
    if mask & DISPLAY_FIELD_DHT != 0 {
        lcd_text(display, "TEMP", 4, 52, C_LABEL);
        if data.dht_valid {
            let mut t: String<16> = String::new();
            let mut h: String<16> = String::new();
            let _ = write!(t, "{:.1}C", data.temperature_c);
            let _ = write!(h, "{:.0}%", data.humidity_percent);
            lcd_text(display, t.as_str(), 34, 52, C_VALUE);
            lcd_text(display, "HUM", 82, 52, C_LABEL);
            lcd_text(display, h.as_str(), 106, 52, C_VALUE);
        } else {
            lcd_text(display, "DHT22 SIN DATOS", 34, 52, C_WARN);
        }
    }
    lcd_hline(display, 62, C_DIM);

    // GPS
    if mask & DISPLAY_FIELD_GPS != 0 {
        lcd_text(display, "GPS", 4, 68, C_LABEL);
        if data.gps_fix {
            let mut s: String<24> = String::new();
            let sats = if data.gps_has_satellites {
                data.satellites
            } else {
                0
            };
            let _ = write!(s, "FIX  SAT {}", sats);
            lcd_text(display, s.as_str(), 28, 68, C_OK);
            let mut lat: String<24> = String::new();
            let mut lon: String<24> = String::new();
            let _ = write!(lat, "LAT {:.5}", data.latitude);
            let _ = write!(lon, "LON {:.5}", data.longitude);
            lcd_text(display, lat.as_str(), 4, 80, C_VALUE);
            lcd_text(display, lon.as_str(), 4, 92, C_VALUE);
        } else {
            lcd_text(display, "BUSCANDO SENAL", 28, 68, C_WARN);
            lcd_text(display, "LAT ---.-----", 4, 80, C_DIM);
            lcd_text(display, "LON ---.-----", 4, 92, C_DIM);
        }
    }
    lcd_hline(display, 104, C_DIM);

    // Clima
    if mask & DISPLAY_FIELD_WEATHER != 0 {
        lcd_text(display, "CLIMA", 4, 110, C_LABEL);
        let w = &data.weather;
        if w.valid {
            let mut s: String<32> = String::new();
            let _ = write!(s, "{:.14}  {:.1}C", w.summary, w.current_temperature_c);
            lcd_text(display, s.as_str(), 4, 122, C_WEATHER);
            let mut minmax: String<32> = String::new();
            let _ = write!(
                minmax,
                "MIN {:.1}  MAX {:.1}C",
                w.minimum_temperature_c, w.maximum_temperature_c
            );
            lcd_text(display, minmax.as_str(), 4, 134, C_VALUE);
            let mut pp: String<16> = String::new();
            let _ = write!(pp, "LLUVIA {}%", w.precipitation_probability);
            lcd_text(display, pp.as_str(), 4, 146, C_WARN);
        } else {
            lcd_text(
                display,
                if data.wifi_connected {
                    "ESPERANDO GPS/CLIMA"
                } else {
                    "ESPERANDO WIFI/GPS"
                },
                4,
                122,
                C_DIM,
            );
            lcd_text(display, "MIN --  MAX --  P --", 4, 134, C_DIM);
        }
    }
    lcd_hline(display, 158, C_DIM);

    // UPDATE + countdown
    lcd_text(display, "UPDATE", 4, 164, C_LABEL);
    let mut iv: String<16> = String::new();
    let _ = write!(iv, "{}s", data.sensor_interval_secs);
    lcd_text(display, iv.as_str(), 52, 164, C_VALUE);

    let rem = remaining.max(0) as u32;
    let mut cd: String<16> = String::new();
    let _ = write!(cd, "PROX {:02}:{:02}", rem / 60, rem % 60);
    let rem_color = if remaining >= 0 && rem > data.sensor_interval_secs / 3 {
        C_OK
    } else {
        C_WARN
    };
    lcd_text(display, cd.as_str(), 76, 164, rem_color);
}

// ── OLED render ───────────────────────────────────────────────────────────
pub fn render_oled<D>(display: &mut D, data: &MonitorData, remaining: i32)
where
    D: DrawTarget<Color = BinaryColor>,
{
    let _ = display.clear(BinaryColor::Off);
    let mask = data.display_mask;

    // Línea 0: título + wifi
    oled_text(
        display,
        if data.wifi_connected {
            "WIFI OK"
        } else {
            "WIFI CONFIG"
        },
        0,
    );

    // Línea 1: batería
    if mask & DISPLAY_FIELD_BATTERY != 0 {
        let mut s: String<24> = String::new();
        let _ = write!(s, "BAT {:.2}V", data.battery_voltage);
        oled_text(display, s.as_str(), 10);
    }

    // Línea 2: DHT22
    if mask & DISPLAY_FIELD_DHT != 0 {
        let mut s: String<32> = String::new();
        if data.dht_valid {
            let _ = write!(
                s,
                "T {:.1}C H {:.0}%",
                data.temperature_c, data.humidity_percent
            );
        } else {
            let _ = s.push_str("DHT22 SIN DATOS");
        }
        oled_text(display, s.as_str(), 20);
    }

    // Líneas 3-4: GPS
    if mask & DISPLAY_FIELD_GPS != 0 {
        if data.gps_fix {
            let mut lat: String<24> = String::new();
            let mut lon: String<24> = String::new();
            let _ = write!(lat, "LAT {:.4}", data.latitude);
            let _ = write!(lon, "LON {:.4}", data.longitude);
            oled_text(display, lat.as_str(), 30);
            oled_text(display, lon.as_str(), 40);
        } else {
            oled_text(display, "GPS BUSCANDO", 30);
            oled_text(display, "LAT/LON --", 40);
        }
    }

    // Líneas 5-6: Clima
    if mask & DISPLAY_FIELD_WEATHER != 0 {
        let w = &data.weather;
        if w.valid {
            let mut s: String<24> = String::new();
            let _ = write!(s, "{:.8} {:.0}C", w.summary, w.current_temperature_c);
            oled_text(
                display,
                s.as_str(),
                30 + if mask & DISPLAY_FIELD_GPS != 0 { 16 } else { 0 },
            );
            let mut mm: String<24> = String::new();
            let _ = write!(
                mm,
                "{:.0}/{:.0}C P{}%",
                w.minimum_temperature_c, w.maximum_temperature_c, w.precipitation_probability
            );
            oled_text(
                display,
                mm.as_str(),
                40 + if mask & DISPLAY_FIELD_GPS != 0 { 16 } else { 0 },
            );
        }
    }

    // Línea 7: UPDATE + countdown
    let rem = remaining.max(0) as u32;
    let mut s: String<32> = String::new();
    let _ = write!(
        s,
        "UPD {}s  {:02}:{:02}",
        data.sensor_interval_secs,
        rem / 60,
        rem % 60
    );
    oled_text(display, s.as_str(), 54);
}

// ── Primitivas ────────────────────────────────────────────────────────────
pub fn lcd_text<D>(display: &mut D, text: &str, x: i32, y: i32, color: Rgb565)
where
    D: DrawTarget<Color = Rgb565>,
{
    let style = MonoTextStyle::new(&FONT_6X10, color);
    let _ = Text::with_baseline(text, Point::new(x, y), style, Baseline::Top).draw(display);
}

pub fn lcd_hline<D>(display: &mut D, y: i32, color: Rgb565)
where
    D: DrawTarget<Color = Rgb565>,
{
    let style = PrimitiveStyle::with_stroke(color, 1);
    let _ = Line::new(Point::new(0, y), Point::new(169, y))
        .into_styled(style)
        .draw(display);
}

pub fn oled_text<D>(display: &mut D, text: &str, y: i32)
where
    D: DrawTarget<Color = BinaryColor>,
{
    let style = MonoTextStyle::new(&FONT_6X10, BinaryColor::On);
    let _ = Text::with_baseline(text, Point::new(0, y), style, Baseline::Top).draw(display);
}
