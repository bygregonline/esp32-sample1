//! Estado compartido del monitor (equivalente a monitor_state.h/c en C).
//! Protegido con Mutex de ESP-IDF para acceso seguro entre tareas.

use std::sync::{Arc, Mutex};

// ── Constantes ─────────────────────────────────────────────────────────────
pub const WEATHER_REFRESH_INTERVAL_SECS: u32 = 300;
pub const SENSOR_INTERVAL_MIN_SECS: u32 = 5;
pub const SENSOR_INTERVAL_MAX_SECS: u32 = 300;
pub const SENSOR_INTERVAL_DEFAULT_SECS: u32 = 10;

// Bits de display_mask
pub const DISPLAY_FIELD_BATTERY: u8 = 1 << 0;
pub const DISPLAY_FIELD_DHT: u8 = 1 << 1;
pub const DISPLAY_FIELD_GPS: u8 = 1 << 2;
pub const DISPLAY_FIELD_WEATHER: u8 = 1 << 3;
pub const DISPLAY_FIELD_PRESSURE: u8 = 1 << 4;
pub const DISPLAY_FIELD_MOON: u8 = 1 << 5;
pub const DISPLAY_FIELDS_ALL: u8 = 0x3F;

// ── Datos de clima ──────────────────────────────────────────────────────────
#[derive(Clone, Default)]
pub struct WeatherData {
    pub valid: bool,
    pub weather_code: i32,
    pub current_temperature_c: f32,
    pub current_humidity_percent: f32,
    pub minimum_temperature_c: f32,
    pub maximum_temperature_c: f32,
    pub precipitation_probability: i32,
    pub moon_phase: f32,
    pub moon_illumination_percent: i32,
    pub moon_phase_valid: bool,
    pub updated_ms: u64,
    pub summary: String,
}

// ── Snapshot del monitor ────────────────────────────────────────────────────
#[derive(Clone, Default)]
pub struct MonitorData {
    pub battery_voltage: f32,
    pub temperature_c: f32,
    pub humidity_percent: f32,
    pub dht_valid: bool,
    pub pressure_hpa: f32,
    pub bmp280_valid: bool,
    pub moon_phase: f32,
    pub moon_phase_valid: bool,
    pub moon_illumination_percent: i32,

    pub gps_fix: bool,
    pub gps_has_satellites: bool,
    pub latitude: f64,
    pub longitude: f64,
    pub satellites: i32,

    pub wifi_connected: bool,
    pub wifi_ssid: String,
    pub ip_address: String,

    pub weather: WeatherData,
    pub next_refresh_us: i64,
    pub refresh_interval_secs: u32,

    pub sensor_interval_secs: u32,
    pub last_sensor_read_ms: u64,
    pub display_mask: u8,
    pub events: Vec<String>,
}

// ── Estado compartido (Arc<Mutex<>>) ────────────────────────────────────────
#[derive(Clone)]
pub struct MonitorState(Arc<Mutex<MonitorData>>);

impl MonitorState {
    pub fn new() -> Self {
        let data = MonitorData {
            refresh_interval_secs: WEATHER_REFRESH_INTERVAL_SECS,
            sensor_interval_secs: SENSOR_INTERVAL_DEFAULT_SECS,
            display_mask: DISPLAY_FIELDS_ALL,
            ..Default::default()
        };
        Self(Arc::new(Mutex::new(data)))
    }

    pub fn snapshot(&self) -> MonitorData {
        self.0.lock().unwrap().clone()
    }

    pub fn set_sensors(
        &self,
        battery_v: f32,
        temp_c: f32,
        hum_pct: f32,
        dht_valid: bool,
        now_ms: u64,
    ) {
        let mut d = self.0.lock().unwrap();
        d.battery_voltage = battery_v;
        d.temperature_c = temp_c;
        d.humidity_percent = hum_pct;
        d.dht_valid = dht_valid;
        d.last_sensor_read_ms = now_ms;
    }

    pub fn set_bmp280(&self, pressure_hpa: f32, valid: bool) {
        let mut d = self.0.lock().unwrap();
        d.pressure_hpa = pressure_hpa;
        d.bmp280_valid = valid;
        if valid {
            push_event(&mut d, "BMP280 pressure updated");
        }
    }

    pub fn set_gps(&self, fix: bool, has_sats: bool, lat: f64, lon: f64, sats: i32) {
        let mut d = self.0.lock().unwrap();
        if fix != d.gps_fix {
            push_event(
                &mut d,
                if fix {
                    "GPS fix acquired"
                } else {
                    "GPS fix lost"
                },
            );
        }
        d.gps_fix = fix;
        d.gps_has_satellites = has_sats;
        d.latitude = lat;
        d.longitude = lon;
        d.satellites = sats;
    }

    pub fn set_wifi(&self, connected: bool, ssid: &str, ip: &str) {
        let mut d = self.0.lock().unwrap();
        if connected && !d.wifi_connected {
            push_event(&mut d, "Wi-Fi connected");
        }
        if !connected && d.wifi_connected {
            push_event(&mut d, "Wi-Fi disconnected");
        }
        d.wifi_connected = connected;
        d.wifi_ssid = ssid.to_string();
        d.ip_address = ip.to_string();
    }

    pub fn set_weather(&self, w: WeatherData) {
        let mut d = self.0.lock().unwrap();
        d.moon_phase = w.moon_phase;
        d.moon_illumination_percent = w.moon_illumination_percent;
        d.moon_phase_valid = w.moon_phase_valid;
        if w.valid {
            push_event(&mut d, "Weather updated");
        }
        d.weather = w;
    }

    pub fn set_refresh_deadline(&self, deadline_us: i64) {
        self.0.lock().unwrap().next_refresh_us = deadline_us;
    }

    pub fn set_sensor_interval(&self, secs: u32) {
        let secs = secs.clamp(SENSOR_INTERVAL_MIN_SECS, SENSOR_INTERVAL_MAX_SECS);
        self.0.lock().unwrap().sensor_interval_secs = secs;
    }

    pub fn set_display_mask(&self, mask: u8) {
        self.0.lock().unwrap().display_mask = mask & DISPLAY_FIELDS_ALL;
    }

    pub fn seconds_until_refresh(data: &MonitorData, now_us: i64) -> i32 {
        if data.next_refresh_us <= 0 {
            return -1;
        }
        let rem = data.next_refresh_us - now_us;
        if rem <= 0 {
            0
        } else {
            ((rem + 999_999) / 1_000_000) as i32
        }
    }
}

impl MonitorState {
    pub fn log_event(&self, message: &str) {
        push_event(&mut self.0.lock().unwrap(), message);
    }
}

fn push_event(data: &mut MonitorData, message: &str) {
    if data.events.len() == 3 {
        data.events.remove(0);
    }
    data.events.push(message.to_string());
}
