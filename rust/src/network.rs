//! Wi-Fi (AP+STA) + servidor HTTP (equivalente a network.c en C).
//! Endpoints idénticos al C: /api/status, /api/sensors, /api/weather,
//! /api/config/interval, /api/config/display, /wifi, /.

use std::sync::{Arc, Mutex};

use embedded_svc::{
    http::Method,
    io::{Read, Write},
};
use esp_idf_svc::{
    eventloop::EspSystemEventLoop,
    hal::modem::WifiModem,
    http::server::{Configuration as HttpServerConfig, EspHttpServer},
    nvs::{EspDefaultNvsPartition, EspNvs, NvsDefault},
    wifi::{
        AccessPointConfiguration, AuthMethod, BlockingWifi, ClientConfiguration,
        Configuration as WifiConfig, EspWifi,
    },
};

use crate::monitor_state::{
    MonitorData, MonitorState, DISPLAY_FIELD_BATTERY, DISPLAY_FIELD_DHT, DISPLAY_FIELD_GPS,
    DISPLAY_FIELD_MOON, DISPLAY_FIELD_PRESSURE, DISPLAY_FIELD_WEATHER, SENSOR_INTERVAL_MAX_SECS,
    SENSOR_INTERVAL_MIN_SECS,
};
use crate::moon_image::render_bmp;
use crate::weather::start_weather_task;

const PORTAL_SSID: &str = "ESP32-Monitor-Setup";
const PORTAL_AP_CODE: &str = "monitor1234";
const NVS_NAMESPACE: &str = "mon_wifi";

// ── HTML ───────────────────────────────────────────────────────────────────
const INDEX_HTML: &str = concat!(
    "<!doctype html><html lang='es'><meta charset='utf-8'>",
    "<meta name='viewport' content='width=device-width,initial-scale=1'>",
    "<title>ESP32 Monitor</title>",
    "<style>",
    "body{font:15px system-ui;max-width:1000px;margin:30px auto;padding:0 18px;",
    "background:radial-gradient(ellipse at 50% -20%,#172c49 0,#0a101b 48%,#080c13 100%);",
    "color:#e8f0fc;min-height:100vh}",
    "h1{font-size:1.65rem;margin:0 0 4px;color:#f1f6ff;letter-spacing:-.03em}",
    ".hero{padding-right:70px;min-height:60px;margin-bottom:18px}",
    ".eyebrow{font-size:.7rem;color:#78b8ff;text-transform:uppercase;letter-spacing:.18em;margin:0 0 4px}",
    ".refresh-badge{position:fixed;z-index:5;top:12px;right:12px;left:auto;width:54px;height:54px;",
    "display:grid;place-items:center;border:1px solid #29415d;border-radius:16px;",
    "background:#101a29ef;box-shadow:0 8px 30px #0008;backdrop-filter:blur(8px)}",
    ".refresh-badge svg{position:absolute;width:42px;height:42px;transform:rotate(-90deg)}",
    ".ring-track,.ring-progress{fill:none;stroke-width:3.5}.ring-track{stroke:#24364b}",
    ".ring-progress{stroke:#54d6c7;stroke-linecap:round;stroke-dasharray:100;stroke-dashoffset:0;transition:stroke-dashoffset .5s}",
    "#refresh-time{font:600 10px ui-monospace,monospace;color:#e8f0fc}",
    "h1{color:#58a6ff;font-size:1.4rem}h2{color:#79c0ff;font-size:1rem;margin:0 0 8px}",
    "section{background:#161b22;padding:14px 16px;border-radius:10px;margin:10px 0;",
    "border:1px solid #21262d}",
    ".grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px}",
    ".card{background:#0b1420;border-radius:11px;padding:13px 14px;border:1px solid #1e3043;min-width:0}",
    ".lbl{font-size:.75rem;color:#8b949e;text-transform:uppercase;letter-spacing:.05em}",
    ".val{font-size:1.15rem;font-weight:600;margin-top:2px}",
    ".moon-card{display:flex;align-items:center;gap:12px;min-height:82px}",
    ".moon-card img{width:68px;height:68px;flex:0 0 68px;border-radius:50%;background:#03070c;",
    "box-shadow:0 0 22px #79a9d455;border:1px solid #61778d;object-fit:cover}",
    ".moon-title{font-size:1.05rem;font-weight:650}",
    ".ok{color:#3fb950}.warn{color:#d29922}.muted{color:#8b949e;font-size:.85rem}",
    "label{display:block;margin:8px 0 3px;font-size:.85rem;color:#8b949e}",
    "input,button{font:inherit;padding:9px 12px;width:100%;box-sizing:border-box;",
    "border-radius:6px;border:1px solid #30363d;background:#0d1117;color:#e6edf3}",
    "button{margin-top:10px;background:#238636;color:#fff;border:none}",
    "#msg,#wres{margin-top:8px;font-size:.85rem;color:#8b949e}",
    "</style>",
    "<div class='refresh-badge' aria-label='Sensor refresh countdown'><svg viewBox='0 0 40 40'>",
    "<circle class='ring-track' cx='20' cy='20' r='16'/><circle id='refresh-ring' class='ring-progress' cx='20' cy='20' r='16'/></svg>",
    "<span id='refresh-time'>--</span></div>",
    "<header class='hero'><p class='eyebrow'>LIVE SENSOR STATION</p><h1>ESP32 Monitor</h1></header>",
    "<section><div class='grid'>",
    "<div class='card'><div class='lbl'>Hora local</div><div class='val' id='clock'>--</div></div>",
    "<div class='card'><div class='lbl'>IP address</div><div class='val' id='ip'>--</div></div>",
    "</div></section>",
    "<section><h2>Lecturas</h2><div class='grid'>",
    "<div class='card'><div class='lbl'>Bateria</div><div class='val' id='bat'>--</div></div>",
    "<div class='card'><div class='lbl'>Temperatura</div><div class='val' id='temp'>--</div></div>",
    "<div class='card'><div class='lbl'>Humedad</div><div class='val' id='hum'>--</div></div>",
    "<div class='card'><div class='lbl'>Pressure</div><div class='val' id='pressure'>--</div></div>",
    "<div class='card'><div class='lbl'>Latitude</div><div class='val' id='lat'>--</div></div>",
    "<div class='card'><div class='lbl'>Longitude</div><div class='val' id='lon'>--</div></div>",
    "<div class='card'><div class='lbl'>Weather forecast</div><div class='val' id='wx'>--</div></div>",
    "<div class='card moon-card'><img id='moon-photo' alt='Current moon phase' src='/moon.bmp'>",
    "<div><div class='lbl'>Lunar phase</div><div class='moon-title' id='moon'>--</div>",
    "<div class='muted' id='moon-illum'>Moon illumination</div></div></div>",
    "<div class='card'><div class='lbl'>Ciclo / prox.</div><div class='val' id='upd'>--</div></div>",
    "</div></section>",
    "<section><h2>System log</h2><pre id='events'>Waiting for events...</pre></section>",
    "<section><h2>Ciclo de sensores</h2>",
    "<p class='muted'>Intervalo entre lecturas (5–300 s).</p>",
    "<label>Segundos</label><input id='iv' type='number' min='5' max='300' value='10'>",
    "<button onclick='setIv()'>Aplicar</button><div id='msg'></div></section>",
    "<section><h2>Conectar a Wi-Fi</h2>",
    "<p class='muted'>Se guarda en el dispositivo.</p>",
    "<form id='wf'><label>Red</label><input name='ssid' maxlength='32' required>",
    "<label>Contrasena</label><input name='password' type='password' maxlength='64'>",
    "<button>Guardar y conectar</button></form><p id='wres'></p></section>",
    "<p class='muted'>",
    "<a href='/api/status'>/api/status</a> &middot; ",
    "<a href='/api/sensors'>/api/sensors</a> &middot; ",
    "<a href='/api/weather'>/api/weather</a> &middot; ",
    "POST <code>/api/config/interval</code> &middot; ",
    "POST <code>/api/config/display</code></p>",
    "<script>",
    "async function r(){try{",
    "const d=await(await fetch('/api/status',{cache:'no-store'})).json();",
    "const s=d.sensors,g=d.gps,w=d.weather,rf=d.refresh;",
    "set('clock',d.local_time||'--');set('ip',d.wifi.ip||'192.168.4.1');",
    "set('bat',s.battery_v.toFixed(2)+' V',s.battery_v>3.5?'ok':'warn');",
    "set('temp',s.temperature_c!=null?s.temperature_c.toFixed(1)+' C':'--',s.temperature_c!=null?'ok':'warn');",
    "set('hum',s.humidity_percent!=null?s.humidity_percent.toFixed(0)+' %':'--',s.humidity_percent!=null?'ok':'warn');",
    "set('pressure',s.pressure_hpa!=null?s.pressure_hpa.toFixed(1)+' hPa':'Sensor unavailable',s.bmp280_valid?'ok':'muted');",
    "set('lat',g.fix?g.latitude.toFixed(5):'--',g.fix?'ok':'warn');set('lon',g.fix?g.longitude.toFixed(5):'--',g.fix?'ok':'warn');",
    "set('wx',w.available?w.summary+' '+w.current_temperature_c.toFixed(1)+'C · '+w.minimum_temperature_c.toFixed(0)+'/'+w.maximum_temperature_c.toFixed(0)+'C · rain '+w.precipitation_probability+'%':'Sin datos',w.available?'ok':'muted');",
    "set('moon',w.moon_phase!=null?moonName(w.moon_phase):'--');",
    "set('moon-illum',w.moon_illumination_percent!=null?w.moon_illumination_percent+'% illuminated':'Moon data unavailable','muted');",
    "if(w.moon_phase!=null){const k=Math.floor(w.moon_phase*255),im=document.getElementById('moon-photo');",
    "if(im.dataset.phase!==String(k)){im.dataset.phase=String(k);im.src='/moon.bmp?v='+k;}}",
    "document.getElementById('events').textContent=(d.events||[]).join('\\n')||'No events yet';",
    "set('upd',rf.interval_seconds+'s / '+(rf.remaining_seconds>=0?rf.remaining_seconds+'s':'esperando'),'ok');",
    "document.getElementById('refresh-time').textContent=rf.remaining_seconds>=0?",
    "(String(Math.floor(rf.remaining_seconds/60)).padStart(2,'0')+':'+String(rf.remaining_seconds%60).padStart(2,'0')):'--:--';",
    "document.getElementById('refresh-ring').style.strokeDashoffset=String(100*(1-Math.max(0,Math.min(1,rf.remaining_seconds/(rf.interval_seconds||1)))));",
    "document.getElementById('iv').value=rf.interval_seconds;",
    "}catch(e){}}",
    "function set(id,v,c){const e=document.getElementById(id);e.textContent=v;e.className='val '+(c||'');}",
    "function moonName(p){return p<.035||p>=.965?'New moon':p<.22?'Waxing crescent':p<.28?'First quarter':p<.47?'Waxing gibbous':p<.53?'Full moon':p<.72?'Waning gibbous':p<.78?'Last quarter':'Waning crescent';}",
    "setInterval(r,2000);r();",
    "async function setIv(){const v=parseInt(document.getElementById('iv').value,10);",
    "if(isNaN(v)||v<5||v>300){document.getElementById('msg').textContent='Rango 5-300';return;}",
    "const j=await(await fetch('/api/config/interval',{method:'POST',",
    "headers:{'Content-Type':'application/json'},body:JSON.stringify({interval_seconds:v})})).json();",
    "document.getElementById('msg').textContent=j.ok?'Aplicado: '+j.interval_seconds+'s':'Error';}",
    "document.getElementById('wf').onsubmit=async e=>{e.preventDefault();",
    "const res=await fetch('/wifi',{method:'POST',body:new URLSearchParams(new FormData(e.target))});",
    "document.getElementById('wres').textContent=await res.text();};",
    "</script></html>"
);

// ── Helpers JSON ───────────────────────────────────────────────────────────

fn num_or_null(valid: bool, val: f64) -> String {
    if valid {
        format!("{:.6}", val)
            .trim_end_matches('0')
            .trim_end_matches('.')
            .to_string()
    } else {
        "null".to_string()
    }
}

fn weather_json(data: &MonitorData, now_ms: u64) -> String {
    let w = &data.weather;
    let age = if w.valid && w.updated_ms > 0 {
        (now_ms - w.updated_ms) / 1000
    } else {
        0
    };
    let stale = w.valid && age > data.refresh_interval_secs as u64 * 2;
    format!(
        r#"{{"available":{av},"summary":"{sum}","weather_code":{code},"current_temperature_c":{ct},"current_humidity_percent":{ch},"minimum_temperature_c":{mn},"maximum_temperature_c":{mx},"precipitation_probability":{pp},"moon_phase":{phase},"moon_illumination_percent":{illum},"age_seconds":{age},"stale":{stale}}}"#,
        av = w.valid,
        sum = if w.valid { &w.summary } else { "SIN DATOS" },
        code = if w.valid {
            w.weather_code.to_string()
        } else {
            "null".to_string()
        },
        ct = num_or_null(w.valid, w.current_temperature_c as f64),
        ch = num_or_null(w.valid, w.current_humidity_percent as f64),
        mn = num_or_null(w.valid, w.minimum_temperature_c as f64),
        mx = num_or_null(w.valid, w.maximum_temperature_c as f64),
        pp = if w.valid {
            w.precipitation_probability.to_string()
        } else {
            "null".to_string()
        },
        phase = num_or_null(w.moon_phase_valid, w.moon_phase as f64),
        illum = if w.moon_phase_valid {
            w.moon_illumination_percent.to_string()
        } else {
            "null".to_string()
        },
        age = age,
        stale = stale,
    )
}

fn events_json(data: &MonitorData) -> String {
    format!(
        "[{}]",
        data.events
            .iter()
            .map(|e| format!("\"{}\"", e))
            .collect::<Vec<_>>()
            .join(",")
    )
}

fn status_json(data: &MonitorData, now_ms: u64, remaining: i32) -> String {
    let clock = crate::display::clock_text();
    format!(
        r#"{{"sensors":{{"battery_v":{bv:.3},"temperature_c":{tc},"humidity_percent":{hp},"dht_valid":{dv},"pressure_hpa":{pressure},"bmp280_valid":{bmp},"moon_phase":{phase},"moon_illumination_percent":{illum},"last_read_ms":{lr}}},"gps":{{"fix":{gf},"latitude":{lat},"longitude":{lon},"satellites":{sat}}},"wifi":{{"connected":{wc},"ssid":"{ssid}","ip":"{ip}"}},"refresh":{{"interval_seconds":{iv},"weather_interval_seconds":{wiv},"remaining_seconds":{rem}}},"display_mask":{dm},"weather":{wx},"events":{events},"local_time":"{clock}"}}"#,
        bv = data.battery_voltage,
        tc = num_or_null(data.dht_valid, data.temperature_c as f64),
        hp = num_or_null(data.dht_valid, data.humidity_percent as f64),
        dv = data.dht_valid,
        pressure = num_or_null(data.bmp280_valid, data.pressure_hpa as f64),
        bmp = data.bmp280_valid,
        phase = num_or_null(data.moon_phase_valid, data.moon_phase as f64),
        illum = if data.moon_phase_valid {
            data.moon_illumination_percent.to_string()
        } else {
            "null".to_string()
        },
        lr = data.last_sensor_read_ms,
        gf = data.gps_fix,
        lat = num_or_null(data.gps_fix, data.latitude),
        lon = num_or_null(data.gps_fix, data.longitude),
        sat = if data.gps_fix && data.gps_has_satellites {
            data.satellites.to_string()
        } else {
            "null".to_string()
        },
        wc = data.wifi_connected,
        ssid = data.wifi_ssid,
        ip = data.ip_address,
        iv = data.sensor_interval_secs,
        wiv = data.refresh_interval_secs,
        rem = remaining,
        dm = data.display_mask,
        wx = weather_json(data, now_ms),
        events = events_json(data),
        clock = clock.as_str(),
    )
}

fn sensors_json(data: &MonitorData, now_ms: u64) -> String {
    let clock = crate::display::clock_text();
    let elapsed = if now_ms > data.last_sensor_read_ms {
        (now_ms - data.last_sensor_read_ms) / 1000
    } else {
        0
    };
    let remaining = data.sensor_interval_secs.saturating_sub(elapsed as u32);
    format!(
        r#"{{"battery_v":{bv:.3},"temperature_c":{tc},"humidity_percent":{hp},"dht_valid":{dv},"pressure_hpa":{pressure},"bmp280_valid":{bmp},"moon_phase":{phase},"moon_illumination_percent":{illum},"gps_fix":{gf},"latitude":{lat},"longitude":{lon},"satellites":{sat},"last_read_ms":{lr},"interval_seconds":{iv},"remaining_seconds":{rem},"local_time":"{clock}"}}"#,
        bv = data.battery_voltage,
        tc = num_or_null(data.dht_valid, data.temperature_c as f64),
        hp = num_or_null(data.dht_valid, data.humidity_percent as f64),
        dv = data.dht_valid,
        pressure = num_or_null(data.bmp280_valid, data.pressure_hpa as f64),
        bmp = data.bmp280_valid,
        phase = num_or_null(data.moon_phase_valid, data.moon_phase as f64),
        illum = if data.moon_phase_valid {
            data.moon_illumination_percent.to_string()
        } else {
            "null".to_string()
        },
        gf = data.gps_fix,
        lat = num_or_null(data.gps_fix, data.latitude),
        lon = num_or_null(data.gps_fix, data.longitude),
        sat = if data.gps_fix && data.gps_has_satellites {
            data.satellites.to_string()
        } else {
            "null".to_string()
        },
        lr = data.last_sensor_read_ms,
        iv = data.sensor_interval_secs,
        rem = remaining,
        clock = clock.as_str(),
    )
}

fn now_ms() -> u64 {
    esp_idf_svc::systime::EspSystemTime {}.now().as_millis() as u64
}
fn now_us() -> i64 {
    esp_idf_svc::systime::EspSystemTime {}.now().as_micros() as i64
}

fn send_json(resp: &mut impl Write, body: &str) {
    let header = format!(
        "HTTP/1.1 200 OK\r\nContent-Type: application/json; charset=utf-8\r\nCache-Control: no-store\r\nContent-Length: {}\r\n\r\n",
        body.len()
    );
    let _ = resp.write_all(header.as_bytes());
    let _ = resp.write_all(body.as_bytes());
}

fn read_body(req: &mut impl Read, max: usize) -> Vec<u8> {
    let mut buf = vec![0u8; max];
    let mut total = 0;
    loop {
        match req.read(&mut buf[total..]) {
            Ok(0) => break,
            Ok(n) => total += n,
            Err(_) => break,
        }
        if total >= max {
            break;
        }
    }
    buf.truncate(total);
    buf
}

// ── Lanzar el servidor ─────────────────────────────────────────────────────
pub fn start_network(state: MonitorState, modem: WifiModem<'static>) -> anyhow::Result<()> {
    // --- NVS para credenciales ---
    let nvs_partition = EspDefaultNvsPartition::take()?;
    let nvs: Arc<Mutex<EspNvs<NvsDefault>>> = Arc::new(Mutex::new(EspNvs::new(
        nvs_partition.clone(),
        NVS_NAMESPACE,
        true,
    )?));

    let saved_ssid = {
        let mut buf = [0u8; 33];
        let nvs_g = nvs.lock().unwrap();
        nvs_g
            .get_str("ssid", &mut buf)
            .ok()
            .flatten()
            .unwrap_or("")
            .to_string()
    };
    let saved_pw = {
        let mut buf = [0u8; 65];
        let nvs_g = nvs.lock().unwrap();
        nvs_g
            .get_str("pw", &mut buf)
            .ok()
            .flatten()
            .unwrap_or("")
            .to_string()
    };
    let have_creds = !saved_ssid.is_empty() && !saved_pw.is_empty();

    // --- Wi-Fi ---
    let sys_loop = EspSystemEventLoop::take()?;
    let mut wifi = BlockingWifi::wrap(
        EspWifi::new(modem, sys_loop.clone(), Some(nvs_partition))?,
        sys_loop.clone(),
    )?;

    let ap_cfg = AccessPointConfiguration {
        ssid: PORTAL_SSID.try_into().unwrap(),
        password: PORTAL_AP_CODE.try_into().unwrap(),
        auth_method: AuthMethod::WPA2Personal,
        max_connections: 4,
        ..Default::default()
    };

    let sta_cfg = if have_creds {
        ClientConfiguration {
            ssid: saved_ssid.as_str().try_into().unwrap_or_default(),
            password: saved_pw.as_str().try_into().unwrap_or_default(),
            ..Default::default()
        }
    } else {
        ClientConfiguration::default()
    };

    wifi.set_configuration(&WifiConfig::Mixed(sta_cfg, ap_cfg))?;
    wifi.start()?;
    if have_creds {
        if let Err(e) = wifi.connect() {
            log::warn!("Wi-Fi connect error (se reintentara): {:?}", e);
        }
        if let Ok(ip_info) = wifi.wifi().sta_netif().get_ip_info() {
            let ip = ip_info.ip.to_string();
            state.set_wifi(true, &saved_ssid, &ip);
            log::info!("Wi-Fi conectado: {} / {}", saved_ssid, ip);
        }
    }
    state.set_wifi(false, &saved_ssid, "");
    log::info!(
        "AP activo: {} / {} | http://192.168.4.1",
        PORTAL_SSID,
        PORTAL_AP_CODE
    );
    state.log_event("Setup AP ready");

    // Mantener wifi vivo en un Arc para que no se droppe
    let _wifi = Arc::new(Mutex::new(wifi));

    // --- Tarea de clima ---
    start_weather_task(state.clone());

    // --- Servidor HTTP ---
    let server_config = HttpServerConfig {
        http_port: 80,
        stack_size: 8192,
        max_uri_handlers: 12,
        ..Default::default()
    };
    let mut server = EspHttpServer::new(&server_config)?;

    // GET /moon.bmp — small phase image generated into a response buffer.
    {
        let s = state.clone();
        server.fn_handler::<anyhow::Error, _>("/moon.bmp", Method::Get, move |req| {
            let data = s.snapshot();
            let bmp = render_bmp(if data.moon_phase_valid {
                data.moon_phase
            } else {
                0.0
            });
            let mut resp = req.into_response(
                200,
                None,
                &[
                    ("Content-Type", "image/bmp"),
                    ("Cache-Control", "private, max-age=3600"),
                ],
            )?;
            resp.write_all(&bmp)?;
            Ok(())
        })?;
    }

    // GET /
    {
        server.fn_handler::<anyhow::Error, _>("/", Method::Get, |req| {
            let mut resp = req.into_response(
                200,
                None,
                &[
                    ("Content-Type", "text/html; charset=utf-8"),
                    ("Cache-Control", "no-store"),
                ],
            )?;
            resp.write_all(INDEX_HTML.as_bytes())?;
            Ok(())
        })?;
    }

    // Clonar estado para cada handler
    macro_rules! state_clone {
        () => {
            state.clone()
        };
    }

    // GET /api/status
    {
        let s = state_clone!();
        server.fn_handler::<anyhow::Error, _>("/api/status", Method::Get, move |req| {
            let data = s.snapshot();
            let ms = now_ms();
            let rem = MonitorState::seconds_until_refresh(&data, now_us());
            let body = status_json(&data, ms, rem);
            send_json(&mut req.into_ok_response()?, &body);
            Ok(())
        })?;
    }

    // GET /api/sensors
    {
        let s = state_clone!();
        server.fn_handler::<anyhow::Error, _>("/api/sensors", Method::Get, move |req| {
            let data = s.snapshot();
            let body = sensors_json(&data, now_ms());
            send_json(&mut req.into_ok_response()?, &body);
            Ok(())
        })?;
    }

    // GET /api/weather
    {
        let s = state_clone!();
        server.fn_handler::<anyhow::Error, _>("/api/weather", Method::Get, move |req| {
            let data = s.snapshot();
            let body = weather_json(&data, now_ms());
            send_json(&mut req.into_ok_response()?, &body);
            Ok(())
        })?;
    }

    // POST /api/config/interval
    {
        let s = state_clone!();
        server.fn_handler::<anyhow::Error, _>(
            "/api/config/interval",
            Method::Post,
            move |mut req| {
                let body = read_body(&mut req, 256);
                let text = std::str::from_utf8(&body).unwrap_or("");

                // Parsear JSON minimal: {"interval_seconds": N}
                let new_iv: Option<u32> = (|| {
                    let key = "\"interval_seconds\"";
                    let pos = text.find(key)?;
                    let rest = &text[pos + key.len()..];
                    let colon = rest.find(':')?;
                    let after = rest[colon + 1..].trim_start_matches(' ');
                    let end = after
                        .find(|c: char| !c.is_ascii_digit())
                        .unwrap_or(after.len());
                    after[..end].parse::<u32>().ok()
                })();

                let mut resp = req.into_ok_response()?;
                match new_iv {
                    Some(v)
                        if (SENSOR_INTERVAL_MIN_SECS..=SENSOR_INTERVAL_MAX_SECS).contains(&v) =>
                    {
                        s.set_sensor_interval(v);
                        let actual = s.snapshot().sensor_interval_secs;
                        log::info!("Ciclo actualizado a {}s", actual);
                        send_json(
                            &mut resp,
                            &format!(r#"{{"ok":true,"interval_seconds":{}}}"#, actual),
                        );
                    }
                    _ => {
                        send_json(
                            &mut resp,
                            r#"{"ok":false,"error":"interval_seconds fuera de rango (5-300)"}"#,
                        );
                    }
                }
                Ok(())
            },
        )?;
    }

    // POST /api/config/display
    {
        let s = state_clone!();
        server.fn_handler::<anyhow::Error, _>("/api/config/display", Method::Post, move |mut req| {
            let body = read_body(&mut req, 256);
            let text = std::str::from_utf8(&body).unwrap_or("");

            let cur_mask = s.snapshot().display_mask;
            let mut mask = cur_mask;

            for (key, bit) in &[
                ("\"battery\"", DISPLAY_FIELD_BATTERY),
                ("\"dht\"",     DISPLAY_FIELD_DHT),
                ("\"gps\"",     DISPLAY_FIELD_GPS),
                ("\"weather\"", DISPLAY_FIELD_WEATHER),
                ("\"pressure\"", DISPLAY_FIELD_PRESSURE),
                ("\"moon\"", DISPLAY_FIELD_MOON),
            ] {
                if let Some(pos) = text.find(key) {
                    let rest = &text[pos + key.len()..];
                    if let Some(colon) = rest.find(':') {
                        let after = rest[colon+1..].trim_start_matches(' ');
                        if after.starts_with("true")  { mask |= bit; }
                        if after.starts_with("false") { mask &= !bit; }
                    }
                }
            }

            s.set_display_mask(mask);
            let snap = s.snapshot();
            let m = snap.display_mask;
            log::info!("Display mask: 0x{:02x}", m);
            send_json(&mut req.into_ok_response()?,
                      &format!(
                          r#"{{"ok":true,"display_mask":{m},"battery":{b},"dht":{d},"gps":{g},"weather":{w},"pressure":{p},"moon":{moon}}}"#,
                          m = m,
                          b = (m & DISPLAY_FIELD_BATTERY) != 0,
                          d = (m & DISPLAY_FIELD_DHT)     != 0,
                          g = (m & DISPLAY_FIELD_GPS)     != 0,
                          w = (m & DISPLAY_FIELD_WEATHER) != 0,
                          p = (m & DISPLAY_FIELD_PRESSURE) != 0,
                          moon = (m & DISPLAY_FIELD_MOON) != 0,
                      ));
            Ok(())
        })?;
    }

    // POST /wifi
    {
        let s = state_clone!();
        let nvs_c = nvs.clone();
        server.fn_handler::<anyhow::Error, _>("/wifi", Method::Post, move |mut req| {
            let body = read_body(&mut req, 512);
            let text = std::str::from_utf8(&body).unwrap_or("");

            // URL-decode form fields
            let ssid = form_value(text, "ssid");
            let pw = form_value(text, "password");

            let mut resp = req.into_ok_response()?;
            if ssid.is_empty() {
                resp.write_all(b"SSID vacio")?;
                return Ok(());
            }

            // Guardar en NVS
            {
                let nvs_g = nvs_c.lock().unwrap();
                let _ = nvs_g.set_str("ssid", &ssid);
                let _ = nvs_g.set_str("pw", &pw);
            }
            s.set_wifi(false, &ssid, "");
            log::info!("Credenciales Wi-Fi guardadas para {}", ssid);
            resp.write_all(b"Guardadas. El dispositivo se reconectara.")?;
            Ok(())
        })?;
    }

    // Captive portal helpers
    server.fn_handler::<anyhow::Error, _>("/generate_204", Method::Get, |req| {
        req.into_response(200, None, &[("Content-Type", "text/html")])?
            .write_all(INDEX_HTML.as_bytes())?;
        Ok(())
    })?;
    server.fn_handler::<anyhow::Error, _>("/hotspot-detect.html", Method::Get, |req| {
        req.into_response(200, None, &[("Content-Type", "text/html")])?
            .write_all(INDEX_HTML.as_bytes())?;
        Ok(())
    })?;

    // Mantener el servidor vivo
    std::mem::forget(server);
    Ok(())
}

// ── URL-decode simple ──────────────────────────────────────────────────────
fn form_value(body: &str, key: &str) -> String {
    for part in body.split('&') {
        if let Some((k, v)) = part.split_once('=') {
            if k == key {
                return url_decode(v);
            }
        }
    }
    String::new()
}

fn url_decode(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    let bytes = s.as_bytes();
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'+' {
            out.push(' ');
            i += 1;
        } else if bytes[i] == b'%' && i + 2 < bytes.len() {
            if let (Some(h), Some(l)) = (hex_val(bytes[i + 1]), hex_val(bytes[i + 2])) {
                out.push((h << 4 | l) as char);
                i += 3;
            } else {
                out.push('%');
                i += 1;
            }
        } else {
            out.push(bytes[i] as char);
            i += 1;
        }
    }
    out
}

fn hex_val(b: u8) -> Option<u8> {
    match b {
        b'0'..=b'9' => Some(b - b'0'),
        b'A'..=b'F' => Some(b - b'A' + 10),
        b'a'..=b'f' => Some(b - b'a' + 10),
        _ => None,
    }
}
