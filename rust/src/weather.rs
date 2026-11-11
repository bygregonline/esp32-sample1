//! Tarea de pronóstico Open-Meteo (equivalente a weather.c en C).

use std::{thread, time::Duration};

use embedded_svc::http::{client::Client as HttpClient, Method};
use esp_idf_svc::http::client::{Configuration as HttpConfig, EspHttpConnection};

use crate::monitor_state::{MonitorState, WeatherData, WEATHER_REFRESH_INTERVAL_SECS};

const GPS_RELOCATION_THRESHOLD: f64 = 0.005;
const MAX_RESPONSE_BYTES: usize = 4096;

fn weather_summary(code: i32) -> &'static str {
    match code {
        0 => "SOLEADO",
        1..=2 => "PARC NUBLADO",
        3 => "NUBLADO",
        45 | 48 => "NEBLINA",
        51..=57 => "LLOVIZNA",
        61..=67 => "LLUVIA",
        71..=77 => "NIEVE",
        80..=82 => "CHUBASCOS",
        85..=86 => "NIEVE",
        95..=i32::MAX => "TORMENTA",
        _ => "SIN DATOS",
    }
}

fn fetch_weather(lat: f64, lon: f64) -> anyhow::Result<WeatherData> {
    let url = format!(
        "https://api.open-meteo.com/v1/forecast\
         ?latitude={:.6}&longitude={:.6}\
         &current=temperature_2m,relative_humidity_2m,weather_code\
         &daily=temperature_2m_min,temperature_2m_max,precipitation_probability_max,moon_phase\
         &forecast_days=1&timezone=auto",
        lat, lon
    );

    let config = HttpConfig {
        use_global_ca_store: true,
        crt_bundle_attach: Some(esp_idf_svc::sys::esp_crt_bundle_attach),
        ..Default::default()
    };
    let conn = EspHttpConnection::new(&config)?;
    let mut client = HttpClient::wrap(conn);

    let headers = [("Accept", "application/json")];
    let request = client.request(Method::Get, &url, &headers)?;
    let mut response = request.submit()?;

    if response.status() != 200 {
        anyhow::bail!("HTTP {}", response.status());
    }

    let mut body = Vec::with_capacity(MAX_RESPONSE_BYTES);
    let mut buf = [0u8; 512];
    loop {
        let n = response.read(&mut buf)?;
        if n == 0 {
            break;
        }
        if body.len() + n > MAX_RESPONSE_BYTES {
            anyhow::bail!("Respuesta demasiado grande");
        }
        body.extend_from_slice(&buf[..n]);
    }

    parse_weather_response(&body)
}

fn parse_weather_response(body: &[u8]) -> anyhow::Result<WeatherData> {
    let text = std::str::from_utf8(body)?;
    // Parser JSON minimal sin serde para evitar dependencias extra.
    // Extrae los campos necesarios con búsqueda de patrones.
    let current_temp = json_f64(text, "\"temperature_2m\"")?;
    let current_hum = json_f64(text, "\"relative_humidity_2m\"")?;
    let weather_code = json_f64(text, "\"weather_code\"")?;
    let min_temp = json_array_first_f64(text, "\"temperature_2m_min\"")?;
    let max_temp = json_array_first_f64(text, "\"temperature_2m_max\"")?;
    let precip = json_array_first_f64(text, "\"precipitation_probability_max\"")?;
    let moon_phase_result = json_array_first_f64(text, "\"moon_phase\"");
    let moon_phase_valid = moon_phase_result.is_ok();
    let moon_phase = moon_phase_result.unwrap_or(0.0);

    let code = weather_code as i32;
    Ok(WeatherData {
        valid: true,
        weather_code: code,
        current_temperature_c: current_temp as f32,
        current_humidity_percent: current_hum as f32,
        minimum_temperature_c: min_temp as f32,
        maximum_temperature_c: max_temp as f32,
        precipitation_probability: precip as i32,
        moon_phase: moon_phase as f32,
        moon_illumination_percent: ((1.0 - (moon_phase * core::f64::consts::TAU).cos()) * 50.0)
            .round() as i32,
        moon_phase_valid,
        updated_ms: esp_idf_svc::systime::EspSystemTime {}.now().as_millis() as u64,
        summary: weather_summary(code).to_string(),
    })
}

/// Extrae el primer valor numérico de `"key": <number>` en JSON plano.
fn json_f64(text: &str, key: &str) -> anyhow::Result<f64> {
    let pos = text
        .find(key)
        .ok_or_else(|| anyhow::anyhow!("key {} not found", key))?;
    let rest = &text[pos + key.len()..];
    let colon = rest
        .find(':')
        .ok_or_else(|| anyhow::anyhow!("no colon after {}", key))?;
    let after = rest[colon + 1..].trim_start_matches(' ');
    let end = after
        .find(|c: char| !c.is_ascii_digit() && c != '.' && c != '-')
        .unwrap_or(after.len());
    Ok(after[..end].parse::<f64>()?)
}

/// Extrae el primer elemento de un array JSON `"key": [<number>, ...]`.
fn json_array_first_f64(text: &str, key: &str) -> anyhow::Result<f64> {
    let pos = text
        .find(key)
        .ok_or_else(|| anyhow::anyhow!("key {} not found", key))?;
    let rest = &text[pos + key.len()..];
    let bracket = rest
        .find('[')
        .ok_or_else(|| anyhow::anyhow!("no array for {}", key))?;
    let after = rest[bracket + 1..].trim_start_matches(' ');
    let end = after
        .find(|c: char| !c.is_ascii_digit() && c != '.' && c != '-')
        .unwrap_or(after.len());
    Ok(after[..end].parse::<f64>()?)
}

/// Lanza la tarea de clima en un thread separado (equivalente a weather_task en C).
pub fn start_weather_task(state: MonitorState) {
    thread::Builder::new()
        .name("weather".to_string())
        .stack_size(8192)
        .spawn(move || {
            let mut observed_lat = 0f64;
            let mut observed_lon = 0f64;
            let mut observed = false;

            loop {
                thread::sleep(Duration::from_secs(1));

                let snap = state.snapshot();
                let now_us = esp_idf_svc::systime::EspSystemTime {}.now().as_micros() as i64;

                let location_changed = !observed
                    || (snap.latitude - observed_lat).abs() > GPS_RELOCATION_THRESHOLD
                    || (snap.longitude - observed_lon).abs() > GPS_RELOCATION_THRESHOLD;

                let refresh_due = snap.next_refresh_us <= 0 || now_us >= snap.next_refresh_us;

                // Esperar a que Wi-Fi esté activo y GPS tenga fix
                if !snap.wifi_connected || !snap.gps_fix {
                    continue;
                }

                if refresh_due || location_changed {
                    let next = now_us + (WEATHER_REFRESH_INTERVAL_SECS as i64 * 1_000_000);
                    state.set_refresh_deadline(next);
                    observed = true;
                    observed_lat = snap.latitude;
                    observed_lon = snap.longitude;

                    log::info!(
                        "Consultando pronostico para {:.5}, {:.5}",
                        snap.latitude,
                        snap.longitude
                    );

                    match fetch_weather(snap.latitude, snap.longitude) {
                        Ok(w) => {
                            log::info!("Pronostico: {} {:.1}C", w.summary, w.current_temperature_c);
                            state.set_weather(w);
                        }
                        Err(e) => log::warn!("Error clima: {}", e),
                    }
                }
            }
        })
        .unwrap();
}
