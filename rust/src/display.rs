//! Render LCD (ST7789V2 170×320) y OLED (SSD1306 128×64).
//! Layout y colores idénticos a display.c en C.

use core::fmt::Write as FmtWrite;
use embedded_graphics::{
    mono_font::{
        ascii::{FONT_5X8, FONT_6X10},
        MonoTextStyle,
    },
    pixelcolor::{BinaryColor, Rgb565},
    prelude::{DrawTarget, Pixel, Point, RgbColor},
    primitives::{Circle, Line, Primitive, PrimitiveStyle},
    text::{Baseline, Text},
    Drawable,
};
use heapless::String;

use crate::monitor_state::{
    MonitorData, DISPLAY_FIELD_BATTERY, DISPLAY_FIELD_DHT, DISPLAY_FIELD_GPS, DISPLAY_FIELD_MOON,
    DISPLAY_FIELD_PRESSURE, DISPLAY_FIELD_WEATHER,
};

#[repr(C)]
struct Tm {
    sec: i32,
    min: i32,
    hour: i32,
    mday: i32,
    mon: i32,
    year: i32,
    wday: i32,
    yday: i32,
    isdst: i32,
    gmtoff: i32,
    zone: *const i8,
}
unsafe extern "C" {
    fn time(out: *mut i64) -> i64;
    fn localtime_r(t: *const i64, out: *mut Tm) -> *mut Tm;
}
pub(crate) fn clock_text() -> String<24> {
    let mut out = String::new();
    let mut epoch = 0i64;
    let mut tm = Tm {
        sec: 0,
        min: 0,
        hour: 0,
        mday: 0,
        mon: 0,
        year: 0,
        wday: 0,
        yday: 0,
        isdst: 0,
        gmtoff: 0,
        zone: core::ptr::null(),
    };
    unsafe {
        time(&mut epoch);
        if epoch > 1_700_000_000 && !localtime_r(&epoch, &mut tm).is_null() {
            let days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
            let months = [
                "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
            ];
            let _ = write!(
                out,
                "{} {:02} {} {:02}:{:02}",
                days[tm.wday.clamp(0, 6) as usize],
                tm.mday,
                months[tm.mon.clamp(0, 11) as usize],
                tm.hour,
                tm.min
            );
        } else {
            let _ = write!(out, "TIME SYNCING");
        }
    }
    out
}

// ── Colores ────────────────────────────────────────────────────────────────
const C_TITLE: Rgb565 = Rgb565::new(10, 27, 28); // azul claro
const C_LABEL: Rgb565 = Rgb565::new(0, 24, 25); // cian
const C_VALUE: Rgb565 = Rgb565::WHITE;
const C_OK: Rgb565 = Rgb565::new(3, 26, 12); // verde
const C_WARN: Rgb565 = Rgb565::new(31, 23, 0); // amarillo
const C_DIM: Rgb565 = Rgb565::new(5, 7, 8); // gris oscuro
const C_WEATHER: Rgb565 = Rgb565::new(31, 18, 0); // naranja

fn moon_phase_name(phase: f32, valid: bool) -> &'static str {
    if !valid {
        "--"
    } else if !(0.035..0.965).contains(&phase) {
        "NEW"
    } else if phase < 0.22 {
        "WAX CRES"
    } else if phase < 0.28 {
        "FIRST Q"
    } else if phase < 0.47 {
        "WAX GIB"
    } else if phase < 0.53 {
        "FULL"
    } else if phase < 0.72 {
        "WAN GIB"
    } else if phase < 0.78 {
        "LAST Q"
    } else {
        "WAN CRES"
    }
}

fn draw_countdown_ring<D>(display: &mut D, remaining: i32, interval: u32)
where
    D: DrawTarget<Color = Rgb565>,
{
    let cx = 149;
    let cy = 23;
    let radius = 20.0f32;
    let ratio = if remaining < 0 || interval == 0 {
        0.0
    } else {
        (remaining as f32 / interval as f32).min(1.0)
    };
    let arc_color = if ratio > 0.5 {
        C_OK
    } else if ratio > 0.2 {
        C_WARN
    } else {
        Rgb565::new(31, 8, 8)
    };
    let _ = Circle::new(Point::new(cx - 20, cy - 20), 41)
        .into_styled(PrimitiveStyle::with_stroke(C_DIM, 3))
        .draw(display);
    let steps = (120.0 * ratio).ceil() as i32;
    for step in 0..steps {
        let a0 = -core::f32::consts::FRAC_PI_2 + (step as f32) * core::f32::consts::TAU / 120.0;
        let a1 =
            -core::f32::consts::FRAC_PI_2 + ((step + 1) as f32) * core::f32::consts::TAU / 120.0;
        let p0 = Point::new(
            cx + (radius * a0.cos()) as i32,
            cy + (radius * a0.sin()) as i32,
        );
        let p1 = Point::new(
            cx + (radius * a1.cos()) as i32,
            cy + (radius * a1.sin()) as i32,
        );
        let _ = Line::new(p0, p1)
            .into_styled(PrimitiveStyle::with_stroke(arc_color, 3))
            .draw(display);
    }
}

fn draw_moon_icon<D>(display: &mut D, phase: f32, valid: bool)
where
    D: DrawTarget<Color = Rgb565>,
{
    let radius = 10;
    let center_x = 151;
    let center_y = 171;
    let angle = (if valid { phase } else { 0.0 }) * core::f32::consts::TAU;
    let (sun_x, sun_z) = (angle.sin(), -angle.cos());
    let mut row = [Pixel(Point::new(0, 0), Rgb565::BLACK); 21];
    for dy in -radius..=radius {
        for dx in -radius..=radius {
            let nx = dx as f32 / radius as f32;
            let ny = dy as f32 / radius as f32;
            let r2 = nx * nx + ny * ny;
            let color = if r2 <= 1.0 {
                let nz = (1.0 - r2).sqrt();
                let light = nx * sun_x + nz * sun_z;
                if light > 0.0 {
                    let shade = (175.0 + nz * 65.0) as u8;
                    Rgb565::new(shade >> 3, shade >> 2, (shade + 5) >> 3)
                } else {
                    Rgb565::new(2, 3, 5)
                }
            } else {
                Rgb565::BLACK
            };
            row[(dx + radius) as usize] = Pixel(Point::new(center_x + dx, center_y + dy), color);
        }
        let _ = display.draw_iter(row);
    }
}

// ── LCD render ────────────────────────────────────────────────────────────
pub fn render_lcd<D>(display: &mut D, data: &MonitorData, _now_us: i64, remaining: i32)
where
    D: DrawTarget<Color = Rgb565>,
{
    let _ = display.clear(Rgb565::BLACK);
    let mask = data.display_mask;

    // Título
    let clock = clock_text();
    lcd_text(display, clock.as_str(), 4, 4, C_TITLE);

    // Keep date and IP together in the top status band.
    if data.wifi_connected {
        let mut s: String<24> = String::new();
        let _ = write!(s, "IP {}", data.ip_address);
        lcd_text(display, s.as_str(), 4, 20, C_OK);
    } else {
        lcd_text(display, "IP 192.168.4.1", 4, 20, C_WARN);
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
    draw_countdown_ring(display, remaining, data.sensor_interval_secs);
    let mut countdown: String<8> = String::new();
    if remaining >= 0 {
        let _ = write!(countdown, "{:02}:{:02}", remaining / 60, remaining % 60);
    } else {
        let _ = write!(countdown, "--:--");
    }
    lcd_text(display, countdown.as_str(), 134, 18, C_VALUE);

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
            let _ = write!(s, "GPS FIX");
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
    if mask & DISPLAY_FIELD_PRESSURE != 0 {
        let mut p: String<24> = String::new();
        if data.bmp280_valid {
            let _ = write!(p, "PRESS {:.1} hPa", data.pressure_hpa);
        } else {
            let _ = write!(p, "PRESS -- hPa");
        }
        lcd_text(
            display,
            p.as_str(),
            4,
            160,
            if data.bmp280_valid { C_OK } else { C_DIM },
        );
    }
    if mask & DISPLAY_FIELD_MOON != 0 {
        let phase = moon_phase_name(data.moon_phase, data.moon_phase_valid);
        let mut m: String<32> = String::new();
        let _ = write!(m, "MOON {} {}%", phase, data.moon_illumination_percent);
        lcd_text(display, m.as_str(), 4, 172, C_WEATHER);
        draw_moon_icon(display, data.moon_phase, data.moon_phase_valid);
    }
    lcd_hline(display, 184, C_DIM);

    // UPDATE + countdown
    lcd_text(display, "UPDATE", 4, 188, C_LABEL);
    let mut iv: String<16> = String::new();
    let _ = write!(iv, "{}s", data.sensor_interval_secs);
    lcd_text(display, iv.as_str(), 52, 188, C_VALUE);

    lcd_hline(display, 216, C_DIM);
    lcd_text(display, "SYSTEM LOG", 4, 220, C_LABEL);
    for (i, event) in data.events.iter().rev().take(2).enumerate() {
        lcd_text(display, event, 4, 232 + (i as i32) * 12, C_VALUE);
    }
}

// ── OLED render ───────────────────────────────────────────────────────────
pub fn render_oled<D>(display: &mut D, data: &MonitorData, remaining: i32)
where
    D: DrawTarget<Color = BinaryColor>,
{
    let _ = display.clear(BinaryColor::Off);
    let clock = clock_text();
    oled_text(display, clock.as_str(), 0);
    let mut ip: String<24> = String::new();
    let _ = write!(
        ip,
        "IP {}",
        if data.ip_address.is_empty() {
            "192.168.4.1"
        } else {
            &data.ip_address
        }
    );
    oled_text(display, ip.as_str(), 8);
    if data.display_mask & DISPLAY_FIELD_DHT != 0 {
        let mut dht: String<24> = String::new();
        if data.dht_valid {
            let _ = write!(
                dht,
                "T{:.0} H{:.0} BAT{:.1}",
                data.temperature_c, data.humidity_percent, data.battery_voltage
            );
        } else {
            let _ = write!(dht, "DHT -- BAT{:.1}", data.battery_voltage);
        }
        oled_text(display, dht.as_str(), 16);
    }
    if data.display_mask & DISPLAY_FIELD_PRESSURE != 0 {
        let mut p: String<24> = String::new();
        if data.bmp280_valid {
            let _ = write!(p, "PRESS {:.1} hPa", data.pressure_hpa);
        } else {
            let _ = write!(p, "PRESS -- hPa");
        }
        oled_text(display, p.as_str(), 24);
    }
    if data.display_mask & DISPLAY_FIELD_GPS != 0 {
        if data.gps_fix {
            let mut lat: String<24> = String::new();
            let mut lon: String<24> = String::new();
            let _ = write!(lat, "LAT {:.4}", data.latitude);
            let _ = write!(lon, "LON {:.4}", data.longitude);
            oled_text(display, lat.as_str(), 32);
            oled_text(display, lon.as_str(), 40);
        } else {
            oled_text(display, "GPS SEARCHING", 32);
            oled_text(display, "LAT/LON --", 40);
        }
    }
    if data.display_mask & DISPLAY_FIELD_WEATHER != 0 {
        let mut wx: String<24> = String::new();
        if data.weather.valid {
            let _ = write!(
                wx,
                "WX {:.8} {:.0}C",
                data.weather.summary, data.weather.current_temperature_c
            );
        } else {
            let _ = write!(wx, "WEATHER WAITING");
        }
        oled_text(display, wx.as_str(), 48);
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
    oled_text(display, s.as_str(), 56);
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
    let style = MonoTextStyle::new(&FONT_5X8, BinaryColor::On);
    let _ = Text::with_baseline(text, Point::new(0, y), style, Baseline::Top).draw(display);
}
