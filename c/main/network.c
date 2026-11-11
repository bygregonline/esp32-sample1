#include "network.h"

#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "cJSON.h"
#include "esp_check.h"
#include "esp_event.h"
#include "esp_http_server.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_netif_sntp.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "moon_image.h"
#include "nvs.h"
#include "nvs_flash.h"
#include "weather.h"
#ifndef CONFIG_MONITOR_WOKWI_SIMULATION
#include "ble_server.h"
#endif

static const char *TAG = "network";
#ifndef CONFIG_MONITOR_WOKWI_SIMULATION
static const char *PORTAL_SSID    = "ESP32-Monitor-Setup";
static const char *PORTAL_AP_CODE = "monitor1234";
static const char *NVS_NAMESPACE  = "monitor_wifi";
#endif

static monitor_state_t *s_state;
static httpd_handle_t s_server;
static bool s_have_credentials;
static bool s_sntp_started;
static char s_saved_ssid[33];
static uint8_t s_moon_image_buffer[MOON_BMP_SIZE];
static SemaphoreHandle_t s_moon_image_mutex;

/* ── Página HTML principal ──────────────────────────────────────────────── */
static const char INDEX_HTML[] =
    "<!doctype html><html lang='es'><meta charset='utf-8'>"
    "<meta name='viewport' content='width=device-width,initial-scale=1'>"
    "<title>ESP32 Monitor</title>"
    "<style>"
    "body{font:15px system-ui;max-width:1000px;margin:30px auto;padding:0 18px;"
    "background:radial-gradient(ellipse at 50% -20%,#172c49 0,#0a101b 48%,#080c13 100%);"
    "color:#e8f0fc;min-height:100vh}"
    "h1{font-size:1.65rem;margin:0 0 4px;color:#f1f6ff;letter-spacing:-.03em}"
    ".hero{padding-right:70px;min-height:60px;margin-bottom:18px}"
    ".eyebrow{font-size:.7rem;color:#78b8ff;text-transform:uppercase;letter-spacing:.18em;margin:0 0 4px}"
    ".refresh-badge{position:fixed;z-index:5;top:12px;right:12px;left:auto;width:54px;height:54px;"
    "display:grid;place-items:center;border:1px solid #29415d;border-radius:16px;"
    "background:#101a29eF;box-shadow:0 8px 30px #0008;backdrop-filter:blur(8px)}"
    ".refresh-badge svg{position:absolute;width:42px;height:42px;transform:rotate(-90deg)}"
    ".ring-track,.ring-progress{fill:none;stroke-width:3.5}.ring-track{stroke:#24364b}"
    ".ring-progress{stroke:#54d6c7;stroke-linecap:round;stroke-dasharray:100;stroke-dashoffset:0;transition:stroke-dashoffset .5s}"
    "#refresh-time{font:600 10px ui-monospace,monospace;color:#e8f0fc}"
    "h2{font-size:1rem;margin:0 0 8px;color:#79c0ff}"
    "section{background:#161b22;padding:14px 16px;border-radius:10px;margin:10px 0;"
    "border:1px solid #21262d}"
    "label{display:block;margin:8px 0 3px;font-size:.85rem;color:#8b949e}"
    "input,button{font:inherit;padding:9px 12px;width:100%;box-sizing:border-box;"
    "border-radius:6px;border:1px solid #30363d;background:#0d1117;color:#e6edf3}"
    "button{margin-top:10px;background:#238636;color:#fff;border-color:#2ea043}"
    "button:hover{background:#2ea043}"
    ".grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px}"
    ".card{background:#0b1420;border-radius:11px;padding:13px 14px;border:1px solid #1e3043;min-width:0}"
    ".lbl{font-size:.75rem;color:#8b949e;text-transform:uppercase;letter-spacing:.05em}"
    ".val{font-size:1.15rem;font-weight:600;margin-top:2px}"
    ".moon-card{display:flex;align-items:center;gap:12px;min-height:82px}"
    ".moon-card img{width:68px;height:68px;flex:0 0 68px;border-radius:50%;background:#03070c;"
    "box-shadow:0 0 22px #79a9d455;border:1px solid #61778d;object-fit:cover}"
    ".moon-title{font-size:1.05rem;font-weight:650}"
    ".ok{color:#3fb950}.warn{color:#d29922}.err{color:#f85149}"
    ".muted{color:#8b949e;font-size:.85rem}"
    "pre{white-space:pre-wrap;font-size:.8rem;color:#8b949e}"
    "#msg{margin-top:8px;font-size:.85rem}"
    "</style>"
    "<div class='refresh-badge' aria-label='Sensor refresh countdown'><svg viewBox='0 0 40 40'>"
    "<circle class='ring-track' cx='20' cy='20' r='16'/><circle id='refresh-ring' class='ring-progress' cx='20' cy='20' r='16'/></svg>"
    "<span id='refresh-time'>--</span></div>"
    "<header class='hero'><p class='eyebrow'>LIVE SENSOR STATION</p><h1>ESP32 Monitor</h1></header>"

    "<section><div class='grid'>"
    "<div class='card'><div class='lbl'>Hora local</div><div class='val' id='cv-clock'>--</div></div>"
    "<div class='card'><div class='lbl'>IP address</div><div class='val' id='cv-ip'>--</div></div>"
    "</div></section>"

    /* Tarjetas de sensores */
    "<section>"
    "<h2>Lecturas</h2>"
    "<div class='grid' id='cards'>"
    "<div class='card'><div class='lbl'>Bateria</div><div class='val' id='cv-bat'>--</div></div>"
    "<div class='card'><div class='lbl'>Temperatura</div><div class='val' "
    "id='cv-temp'>--</div></div>"
    "<div class='card'><div class='lbl'>Humedad</div><div class='val' id='cv-hum'>--</div></div>"
    "<div class='card'><div class='lbl'>Pressure</div><div class='val' id='cv-pressure'>--</div></div>"
    "<div class='card'><div class='lbl'>Latitude</div><div class='val' id='cv-lat'>--</div></div>"
    "<div class='card'><div class='lbl'>Longitude</div><div class='val' id='cv-lon'>--</div></div>"
    "<div class='card'><div class='lbl'>Weather forecast</div><div class='val' id='cv-wx'>--</div></div>"
    "<div class='card moon-card'><img id='moon-photo' alt='Current moon phase' src='/moon.bmp'>"
    "<div><div class='lbl'>Lunar phase</div><div class='moon-title' id='cv-moon'>--</div>"
    "<div class='muted' id='cv-moon-illum'>Moon illumination</div></div></div>"
    "<div class='card'><div class='lbl'>Ciclo / prox.</div><div class='val' "
    "id='cv-upd'>--</div></div>"
    "</div>"
    "</section>"

    "<section><h2>System log</h2><pre id='cv-events'>Waiting for events...</pre></section>"

    /* Configuracion de ciclo */
    "<section>"
    "<h2>Ciclo de sensores</h2>"
    "<p class='muted'>Intervalo entre lecturas. Rango: 5 – 300 s.</p>"
    "<label>Intervalo (segundos)</label>"
    "<input id='iv' type='number' min='5' max='300' value='10'>"
    "<button onclick='setInterval_()'>Aplicar</button>"
    "<div id='msg'></div>"
    "</section>"

/* Configuración Wi-Fi */
#ifdef CONFIG_MONITOR_WOKWI_SIMULATION
    "<section><h2>Simulacion Wokwi</h2>"
    "<p class='muted'>Conectado a Wokwi-GUEST; GPS fijo de prueba.</p></section>"
#else
    "<section>"
    "<h2>Conectar a Wi-Fi</h2>"
    "<p class='muted'>Las credenciales se guardan en el dispositivo.</p>"
    "<form id='wifi'>"
    "<label>Red Wi-Fi</label><input name='ssid' maxlength='32' required autocomplete='off'>"
    "<label>Contrasena</label><input name='password' type='password' maxlength='64'"
    " autocomplete='new-password'>"
    "<button>Guardar y conectar</button>"
    "</form>"
    "<p id='wres'></p>"
    "</section>"
#endif

    /* JSON links */
    "<p class='muted'>Endpoints: "
    "<a href='/api/status'>/api/status</a> &middot; "
    "<a href='/api/sensors'>/api/sensors</a> &middot; "
    "<a href='/api/weather'>/api/weather</a> &middot; "
    "POST <code>/api/config/interval</code>"
    "</p>"

    "<script>"
    /* Actualizar tarjetas */
    "async function refresh(){"
    "try{"
    "const d=await(await fetch('/api/status',{cache:'no-store'})).json();"
    "const s=d.sensors,g=d.gps,w=d.weather,r=d.refresh;"
    "set('cv-clock',d.local_time||'--');set('cv-ip',d.wifi.ip||'192.168.4.1');"
    "set('cv-bat', s.battery_v.toFixed(2)+' V',"
    "  s.battery_v>3.5?'ok':'warn');"
    "set('cv-temp',s.temperature_c!=null?s.temperature_c.toFixed(1)+' C':'--',"
    "  s.temperature_c!=null?'ok':'warn');"
    "set('cv-hum',s.humidity_percent!=null?s.humidity_percent.toFixed(0)+' %':'--',"
    "  s.humidity_percent!=null?'ok':'warn');"
    "set('cv-pressure',s.pressure_hpa!=null?s.pressure_hpa.toFixed(1)+' hPa':'Sensor unavailable',s.bmp280_valid?'ok':'muted');"
    "set('cv-lat',g.fix?g.latitude.toFixed(5):'--',g.fix?'ok':'warn');"
    "set('cv-lon',g.fix?g.longitude.toFixed(5):'--',g.fix?'ok':'warn');"
    "set('cv-wx',w.available?(w.summary+' '+w.current_temperature_c.toFixed(1)+'C · '+w.minimum_temperature_c.toFixed(0)+'/'+w.maximum_temperature_c.toFixed(0)+'C · rain '+w.precipitation_probability+'%'):'Sin datos',"
    "  w.available?'ok':'muted');"
    "set('cv-moon',w.moon_phase!=null?moonName(w.moon_phase):'--');"
    "set('cv-moon-illum',w.moon_illumination_percent!=null?w.moon_illumination_percent+'% illuminated':'Moon data unavailable','muted');"
    "if(w.moon_phase!=null){const k=Math.floor(w.moon_phase*255),im=document.querySelector('#moon-photo');"
    "if(im.dataset.phase!==String(k)){im.dataset.phase=String(k);im.src='/moon.bmp?v='+k;}}"
    "document.querySelector('#cv-events').textContent=(d.events||[]).join('\\n')||'No events yet';"
    "const rem=r.remaining_seconds;const iv=r.interval_seconds||1;"
    "document.querySelector('#refresh-time').textContent=rem>=0?"
    "(String(Math.floor(rem/60)).padStart(2,'0')+':'+String(rem%60).padStart(2,'0')):'--:--';"
    "document.querySelector('#refresh-ring').style.strokeDashoffset=String(100*(1-Math.max(0,Math.min(1,rem/iv))));"
    "set('cv-upd',r.interval_seconds+'s / '+(rem>=0?rem+'s restantes':'esperando'),"
    "  rem>=0?(rem/r.interval_seconds>0.3?'ok':'warn'):'muted');"
    "document.querySelector('#iv').value=r.interval_seconds;"
    "}catch(e){}"
    "}"
    "function set(id,v,cls){"
    "const el=document.querySelector('#'+id);"
    "el.textContent=v; el.className='val '+(cls||'');"
    "}"
    "function moonName(p){return p<.035||p>=.965?'New moon':p<.22?'Waxing crescent':"
    "p<.28?'First quarter':p<.47?'Waxing gibbous':p<.53?'Full moon':p<.72?"
    "'Waning gibbous':p<.78?'Last quarter':'Waning crescent';}"
    "setInterval(refresh,2000);refresh();"

    /* Cambiar intervalo */
    "async function setInterval_(){"
    "const v=parseInt(document.querySelector('#iv').value,10);"
    "if(isNaN(v)||v<5||v>300){"
    "document.querySelector('#msg').textContent='Valor fuera de rango (5-300 s).';"
    "return;}"
    "try{"
    "const r=await fetch('/api/config/interval',{"
    "method:'POST',"
    "headers:{'Content-Type':'application/json'},"
    "body:JSON.stringify({interval_seconds:v})});"
    "const j=await r.json();"
    "document.querySelector('#msg').textContent="
    "j.ok?'Intervalo actualizado a '+j.interval_seconds+' s.':'Error: '+j.error;"
    "}catch(e){document.querySelector('#msg').textContent='Error de red.';}"
    "}"

    /* Wi-Fi form */
    "const wf=document.querySelector('#wifi');"
    "if(wf)wf.onsubmit=async e=>{"
    "e.preventDefault();"
    "const r=await fetch('/wifi',{method:'POST',body:new URLSearchParams(new FormData(e.target))});"
    "document.querySelector('#wres').textContent=await r.text();"
    "};"
    "</script></html>";

/* ── Helpers JSON ────────────────────────────────────────────────────────── */
static void add_number_or_null(cJSON *obj, const char *key, bool valid, double v) {
    if (valid)
        cJSON_AddNumberToObject(obj, key, v);
    else
        cJSON_AddNullToObject(obj, key);
}

static void add_local_time(cJSON *obj) {
    time_t epoch = time(NULL);
    struct tm local = {0};
    char value[32] = "TIME SYNCING";
    if (epoch > 1700000000 && localtime_r(&epoch, &local))
        strftime(value, sizeof(value), "%a %d %b %H:%M", &local);
    cJSON_AddStringToObject(obj, "local_time", value);
}

static cJSON *weather_json(const monitor_data_t *data, uint32_t now_ms) {
    cJSON *w = cJSON_CreateObject();
    if (!w)
        return NULL;
    cJSON_AddBoolToObject(w, "available", data->weather.valid);
    cJSON_AddStringToObject(w, "summary",
                            data->weather.valid ? data->weather.summary : "SIN DATOS");
    add_number_or_null(w, "weather_code", data->weather.valid, data->weather.weather_code);
    add_number_or_null(w, "current_temperature_c", data->weather.valid,
                       data->weather.current_temperature_c);
    add_number_or_null(w, "current_humidity_percent", data->weather.valid,
                       data->weather.current_humidity_percent);
    add_number_or_null(w, "minimum_temperature_c", data->weather.valid,
                       data->weather.minimum_temperature_c);
    add_number_or_null(w, "maximum_temperature_c", data->weather.valid,
                       data->weather.maximum_temperature_c);
    add_number_or_null(w, "precipitation_probability", data->weather.valid,
                       data->weather.precipitation_probability);
    add_number_or_null(w, "moon_phase", data->weather.moon_phase_valid, data->weather.moon_phase);
    add_number_or_null(w, "moon_illumination_percent", data->weather.moon_phase_valid,
                       data->weather.moon_illumination_percent);
    const uint32_t age =
        data->weather.valid ? (uint32_t)(now_ms - data->weather.updated_ms) / 1000 : 0;
    cJSON_AddNumberToObject(w, "age_seconds", age);
    cJSON_AddBoolToObject(w, "stale",
                          data->weather.valid && age > data->refresh_interval_seconds * 2);
    return w;
}

static esp_err_t send_json(httpd_req_t *req, cJSON *root) {
    if (!root) {
        httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "No hay memoria para crear JSON");
        return ESP_FAIL;
    }
    char *body = cJSON_PrintUnformatted(root);
    cJSON_Delete(root);
    if (!body) {
        httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR,
                            "No hay memoria para serializar JSON");
        return ESP_FAIL;
    }
    httpd_resp_set_type(req, "application/json; charset=utf-8");
    httpd_resp_set_hdr(req, "Cache-Control", "no-store");
    const esp_err_t r = httpd_resp_sendstr(req, body);
    free(body);
    return r;
}

/* Lee el body completo de la petición (hasta max_len bytes). */
static esp_err_t read_body(httpd_req_t *req, char *buf, size_t max_len) {
    if (req->content_len == 0 || req->content_len >= max_len) {
        return ESP_ERR_INVALID_SIZE;
    }
    size_t received = 0;
    while (received < (size_t)req->content_len) {
        const int n = httpd_req_recv(req, buf + received, req->content_len - received);
        if (n <= 0)
            return ESP_ERR_TIMEOUT;
        received += (size_t)n;
    }
    buf[received] = '\0';
    return ESP_OK;
}

/* ── Manejadores HTTP ────────────────────────────────────────────────────── */

/* GET / */
static esp_err_t index_handler(httpd_req_t *req) {
    httpd_resp_set_type(req, "text/html; charset=utf-8");
    httpd_resp_set_hdr(req, "Cache-Control", "no-store");
    return httpd_resp_sendstr(req, INDEX_HTML);
}

/* GET /moon.bmp — imagen pequeña, generada y almacenada en RAM por fase. */
static esp_err_t moon_image_handler(httpd_req_t *req) {
    monitor_data_t data;
    monitor_state_snapshot(s_state, &data);
    if (s_moon_image_mutex == NULL ||
        xSemaphoreTake(s_moon_image_mutex, portMAX_DELAY) != pdTRUE) {
        return httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR,
                                   "Moon image buffer unavailable");
    }
    moon_image_render_bmp(data.moon_phase_valid ? data.moon_phase : 0.0f,
                          s_moon_image_buffer, sizeof(s_moon_image_buffer));
    httpd_resp_set_type(req, "image/bmp");
    httpd_resp_set_hdr(req, "Cache-Control", "private, max-age=3600");
    const esp_err_t result = httpd_resp_send(req, (const char *)s_moon_image_buffer,
                                             sizeof(s_moon_image_buffer));
    xSemaphoreGive(s_moon_image_mutex);
    return result;
}

/* GET /api/status — snapshot completo del monitor */
static esp_err_t status_handler(httpd_req_t *req) {
    monitor_data_t data;
    monitor_state_snapshot(s_state, &data);
    const uint32_t now_ms = (uint32_t)(esp_timer_get_time() / 1000);
    const int remaining   = monitor_seconds_until_refresh(&data, esp_timer_get_time());

    cJSON *root    = cJSON_CreateObject();
    cJSON *sensors = root ? cJSON_AddObjectToObject(root, "sensors") : NULL;
    cJSON *gps     = root ? cJSON_AddObjectToObject(root, "gps") : NULL;
    cJSON *wifi    = root ? cJSON_AddObjectToObject(root, "wifi") : NULL;
    cJSON *refresh = root ? cJSON_AddObjectToObject(root, "refresh") : NULL;

    if (!root || !sensors || !gps || !wifi || !refresh) {
        cJSON_Delete(root);
        return send_json(req, NULL);
    }

    /* sensors */
    cJSON_AddNumberToObject(sensors, "battery_v", data.battery_voltage);
    add_number_or_null(sensors, "temperature_c", data.dht_valid, data.temperature_c);
    add_number_or_null(sensors, "humidity_percent", data.dht_valid, data.humidity_percent);
    add_number_or_null(sensors, "pressure_hpa", data.bmp280_valid, data.pressure_hpa);
    cJSON_AddBoolToObject(sensors, "bmp280_valid", data.bmp280_valid);
    add_number_or_null(sensors, "moon_phase", data.moon_phase_valid, data.moon_phase);
    add_number_or_null(sensors, "moon_illumination_percent", data.moon_phase_valid,
                       data.moon_illumination_percent);
    cJSON_AddBoolToObject(sensors, "dht_valid", data.dht_valid);
    cJSON_AddNumberToObject(sensors, "last_read_ms", data.last_sensor_read_ms);

    /* gps */
    cJSON_AddBoolToObject(gps, "fix", data.gps_fix);
    add_number_or_null(gps, "latitude", data.gps_fix, data.latitude);
    add_number_or_null(gps, "longitude", data.gps_fix, data.longitude);
    if (data.gps_fix && data.gps_has_satellites)
        cJSON_AddNumberToObject(gps, "satellites", data.satellites);
    else
        cJSON_AddNullToObject(gps, "satellites");

    /* wifi */
    cJSON_AddBoolToObject(wifi, "connected", data.wifi_connected);
    cJSON_AddStringToObject(wifi, "ssid", data.wifi_ssid);
    cJSON_AddStringToObject(wifi, "ip", data.ip_address);

    /* refresh / ciclo */
    cJSON_AddNumberToObject(refresh, "interval_seconds", data.sensor_interval_seconds);
    cJSON_AddNumberToObject(refresh, "weather_interval_seconds", data.refresh_interval_seconds);
    cJSON_AddNumberToObject(refresh, "remaining_seconds", remaining >= 0 ? remaining : -1);

    /* display mask */
    cJSON_AddNumberToObject(root, "display_mask", data.display_fields_mask);
    add_local_time(root);

    /* weather */
    cJSON *w = weather_json(&data, now_ms);
    if (!w) {
        cJSON_Delete(root);
        return send_json(req, NULL);
    }
    cJSON_AddItemToObject(root, "weather", w);
    cJSON *events = cJSON_AddArrayToObject(root, "events");
    for (uint8_t i = 0; events && i < data.event_log_count; ++i)
        cJSON_AddItemToArray(events, cJSON_CreateString(data.event_log[i]));

    return send_json(req, root);
}

/* GET /api/sensors — último snapshot sólo de sensores (sin clima ni GPS) */
static esp_err_t sensors_handler(httpd_req_t *req) {
    monitor_data_t data;
    monitor_state_snapshot(s_state, &data);

    cJSON *root = cJSON_CreateObject();
    if (!root)
        return send_json(req, NULL);

    cJSON_AddNumberToObject(root, "battery_v", data.battery_voltage);
    add_number_or_null(root, "temperature_c", data.dht_valid, data.temperature_c);
    add_number_or_null(root, "humidity_percent", data.dht_valid, data.humidity_percent);
    add_number_or_null(root, "pressure_hpa", data.bmp280_valid, data.pressure_hpa);
    cJSON_AddBoolToObject(root, "bmp280_valid", data.bmp280_valid);
    add_number_or_null(root, "moon_phase", data.moon_phase_valid, data.moon_phase);
    add_number_or_null(root, "moon_illumination_percent", data.moon_phase_valid,
                       data.moon_illumination_percent);
    cJSON_AddBoolToObject(root, "dht_valid", data.dht_valid);
    cJSON_AddBoolToObject(root, "gps_fix", data.gps_fix);
    add_number_or_null(root, "latitude", data.gps_fix, data.latitude);
    add_number_or_null(root, "longitude", data.gps_fix, data.longitude);
    cJSON_AddNumberToObject(root, "last_read_ms", data.last_sensor_read_ms);
    cJSON_AddNumberToObject(root, "interval_seconds", data.sensor_interval_seconds);
    add_local_time(root);
    return send_json(req, root);
}

/* GET /api/weather */
static esp_err_t weather_handler(httpd_req_t *req) {
    monitor_data_t data;
    monitor_state_snapshot(s_state, &data);
    return send_json(req, weather_json(&data, (uint32_t)(esp_timer_get_time() / 1000)));
}

/*
 * POST /api/config/interval
 * Body JSON: {"interval_seconds": <5-300>}
 * También acepta query string: /api/config/interval?seconds=30
 *
 * Respuesta: {"ok":true,"interval_seconds":<n>}
 *
 * Ejemplo curl:
 *   curl -X POST http://<ip>/api/config/interval \
 *        -H "Content-Type: application/json" \
 *        -d '{"interval_seconds":30}'
 */
static esp_err_t config_interval_handler(httpd_req_t *req) {
    uint32_t new_interval = 0;
    bool parsed           = false;

    /* Intentar leer del body JSON */
    if (req->content_len > 0 && req->content_len < 128) {
        char body[128];
        if (read_body(req, body, sizeof(body)) == ESP_OK) {
            cJSON *json = cJSON_ParseWithLength(body, strlen(body));
            if (json) {
                const cJSON *iv = cJSON_GetObjectItemCaseSensitive(json, "interval_seconds");
                if (cJSON_IsNumber(iv) && iv->valuedouble >= 1) {
                    new_interval = (uint32_t)iv->valuedouble;
                    parsed       = true;
                }
                cJSON_Delete(json);
            }
        }
    }

    /* Fallback: query string ?seconds=<n> */
    if (!parsed) {
        char qs[32] = {0};
        if (httpd_req_get_url_query_str(req, qs, sizeof(qs)) == ESP_OK) {
            char val[16] = {0};
            if (httpd_query_key_value(qs, "seconds", val, sizeof(val)) == ESP_OK) {
                const long v = strtol(val, NULL, 10);
                if (v > 0) {
                    new_interval = (uint32_t)v;
                    parsed       = true;
                }
            }
        }
    }

    if (!parsed || new_interval < SENSOR_INTERVAL_MIN_SECONDS ||
        new_interval > SENSOR_INTERVAL_MAX_SECONDS) {
        cJSON *err = cJSON_CreateObject();
        cJSON_AddBoolToObject(err, "ok", false);
        cJSON_AddStringToObject(err, "error", "interval_seconds fuera de rango (5-300)");
        return send_json(req, err);
    }

    monitor_state_set_sensor_interval(s_state, new_interval);

    monitor_data_t snap;
    monitor_state_snapshot(s_state, &snap);

    cJSON *resp = cJSON_CreateObject();
    cJSON_AddBoolToObject(resp, "ok", true);
    cJSON_AddNumberToObject(resp, "interval_seconds", snap.sensor_interval_seconds);
    ESP_LOGI(TAG, "Ciclo de sensores actualizado a %u s", (unsigned)snap.sensor_interval_seconds);
    return send_json(req, resp);
}

/*
 * POST /api/config/display
 * Body JSON: {"battery":true,"dht":true,"gps":true,"weather":true}
 * Controla qué secciones se muestran en los displays.
 *
 * Ejemplo curl:
 *   curl -X POST http://<ip>/api/config/display \
 *        -H "Content-Type: application/json" \
 *        -d '{"battery":true,"dht":true,"gps":false,"weather":false}'
 */
static esp_err_t config_display_handler(httpd_req_t *req) {
    if (req->content_len == 0 || req->content_len >= 256) {
        cJSON *err = cJSON_CreateObject();
        cJSON_AddBoolToObject(err, "ok", false);
        cJSON_AddStringToObject(err, "error", "body vacio o demasiado grande");
        return send_json(req, err);
    }
    char body[256];
    if (read_body(req, body, sizeof(body)) != ESP_OK) {
        cJSON *err = cJSON_CreateObject();
        cJSON_AddBoolToObject(err, "ok", false);
        cJSON_AddStringToObject(err, "error", "no se pudo leer el body");
        return send_json(req, err);
    }

    cJSON *json = cJSON_ParseWithLength(body, strlen(body));
    if (!json) {
        cJSON *err = cJSON_CreateObject();
        cJSON_AddBoolToObject(err, "ok", false);
        cJSON_AddStringToObject(err, "error", "JSON invalido");
        return send_json(req, err);
    }

    /* Leer el estado actual como base */
    monitor_data_t snap;
    monitor_state_snapshot(s_state, &snap);
    uint8_t mask = snap.display_fields_mask;

#define APPLY_BIT(key, bit)                                            \
    do {                                                               \
        const cJSON *_f = cJSON_GetObjectItemCaseSensitive(json, key); \
        if (cJSON_IsBool(_f)) {                                        \
            if (cJSON_IsTrue(_f))                                      \
                mask |= (bit);                                         \
            else                                                       \
                mask &= (uint8_t) ~(bit);                              \
        }                                                              \
    } while (0)

    APPLY_BIT("battery", DISPLAY_FIELD_BATTERY);
    APPLY_BIT("dht", DISPLAY_FIELD_DHT);
    APPLY_BIT("gps", DISPLAY_FIELD_GPS);
    APPLY_BIT("weather", DISPLAY_FIELD_WEATHER);
    APPLY_BIT("pressure", DISPLAY_FIELD_PRESSURE);
    APPLY_BIT("moon", DISPLAY_FIELD_MOON);
#undef APPLY_BIT

    cJSON_Delete(json);
    monitor_state_set_display_mask(s_state, mask);

    cJSON *resp = cJSON_CreateObject();
    cJSON_AddBoolToObject(resp, "ok", true);
    cJSON_AddNumberToObject(resp, "display_mask", mask);
    cJSON_AddBoolToObject(resp, "battery", (mask & DISPLAY_FIELD_BATTERY) != 0);
    cJSON_AddBoolToObject(resp, "dht", (mask & DISPLAY_FIELD_DHT) != 0);
    cJSON_AddBoolToObject(resp, "gps", (mask & DISPLAY_FIELD_GPS) != 0);
    cJSON_AddBoolToObject(resp, "weather", (mask & DISPLAY_FIELD_WEATHER) != 0);
    cJSON_AddBoolToObject(resp, "pressure", (mask & DISPLAY_FIELD_PRESSURE) != 0);
    cJSON_AddBoolToObject(resp, "moon", (mask & DISPLAY_FIELD_MOON) != 0);
    ESP_LOGI(TAG, "Display mask actualizado a 0x%02x", mask);
    return send_json(req, resp);
}

/* ── Wi-Fi form (POST /wifi) ─────────────────────────────────────────────── */

#ifndef CONFIG_MONITOR_WOKWI_SIMULATION
static int hex_value(char c) {
    if (c >= '0' && c <= '9')
        return c - '0';
    c = (char)tolower((unsigned char)c);
    if (c >= 'a' && c <= 'f')
        return c - 'a' + 10;
    return -1;
}

static bool decode_form_value(const char *enc, char *out, size_t cap) {
    size_t n = 0;
    while (*enc) {
        char v = *enc++;
        if (v == '+') {
            v = ' ';
        } else if (v == '%') {
            const int hi = hex_value(enc[0]);
            const int lo = enc[0] ? hex_value(enc[1]) : -1;
            if (hi < 0 || lo < 0)
                return false;
            v = (char)((hi << 4) | lo);
            enc += 2;
        }
        if ((unsigned char)v < 0x20 || (unsigned char)v == 0x7f || n + 1 >= cap)
            return false;
        out[n++] = v;
    }
    out[n] = '\0';
    return true;
}

static bool parse_form_field(char *body, const char *key, char *out, size_t cap) {
    char *save = NULL;
    for (char *f = strtok_r(body, "&", &save); f; f = strtok_r(NULL, "&", &save)) {
        char *eq = strchr(f, '=');
        if (!eq)
            continue;
        *eq = '\0';
        if (strcmp(f, key) == 0)
            return decode_form_value(eq + 1, out, cap);
    }
    return false;
}

static void save_wifi_credentials(const char *ssid, const char *pw) {
    nvs_handle_t h;
    ESP_ERROR_CHECK(nvs_open(NVS_NAMESPACE, NVS_READWRITE, &h));
    ESP_ERROR_CHECK(nvs_set_str(h, "ssid", ssid));
    ESP_ERROR_CHECK(nvs_set_str(h, "password", pw));
    ESP_ERROR_CHECK(nvs_commit(h));
    nvs_close(h);
}
#endif

static esp_err_t wifi_form_handler(httpd_req_t *req) {
#ifdef CONFIG_MONITOR_WOKWI_SIMULATION
    return httpd_resp_send_err(req, HTTPD_403_FORBIDDEN, "Wi-Fi auto-configurado en Wokwi");
#else
    char body[512] = {0};
    char ssid[33]  = {0};
    char pw[65]    = {0};

    if (req->content_len <= 0 || req->content_len >= (int)sizeof(body)) {
        return httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST,
                                   "Formulario vacio o demasiado grande");
    }
    size_t recv = 0;
    while (recv < (size_t)req->content_len) {
        const int n = httpd_req_recv(req, body + recv, req->content_len - (int)recv);
        if (n <= 0)
            return httpd_resp_send_err(req, HTTPD_408_REQ_TIMEOUT, "Timeout");
        recv += (size_t)n;
    }
    body[recv] = '\0';

    char body2[sizeof(body)];
    memcpy(body2, body, recv + 1);

    if (!parse_form_field(body, "ssid", ssid, sizeof(ssid)) || !ssid[0] ||
        !parse_form_field(body2, "password", pw, sizeof(pw))) {
        return httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "SSID o contrasena invalida");
    }

    save_wifi_credentials(ssid, pw);
    wifi_config_t sta = {0};
    memcpy(sta.sta.ssid, ssid, strlen(ssid));
    memcpy(sta.sta.password, pw, strlen(pw));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &sta));
    snprintf(s_saved_ssid, sizeof(s_saved_ssid), "%s", ssid);
    s_have_credentials = true;
    monitor_state_set_wifi(s_state, false, ssid, "");
    (void)esp_wifi_disconnect();
    esp_wifi_connect();

    httpd_resp_set_type(req, "text/plain; charset=utf-8");
    return httpd_resp_sendstr(req, "Guardadas. Reconectando... actualiza en unos segundos.");
#endif
}

/* ── SNTP ────────────────────────────────────────────────────────────────── */
static void start_sntp_once(void) {
    if (!s_sntp_started) {
        const esp_sntp_config_t cfg = ESP_NETIF_SNTP_DEFAULT_CONFIG("pool.ntp.org");
        if (esp_netif_sntp_init(&cfg) == ESP_OK) {
            s_sntp_started = true;
            ESP_LOGI(TAG, "SNTP iniciado");
        }
    }
}

/* ── Eventos Wi-Fi ───────────────────────────────────────────────────────── */
static void wifi_event_handler(void *arg, esp_event_base_t base, int32_t id, void *data) {
    (void)arg;
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_START && s_have_credentials) {
        esp_wifi_connect();
    } else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        monitor_state_set_wifi(s_state, false, s_saved_ssid, "");
        if (s_have_credentials)
            esp_wifi_connect();
    } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        const ip_event_got_ip_t *ev = data;
        char ip[16];
        snprintf(ip, sizeof(ip), IPSTR, IP2STR(&ev->ip_info.ip));
        monitor_state_set_wifi(s_state, true, s_saved_ssid, ip);
        ESP_LOGI(TAG, "Wi-Fi OK: %s", ip);
        start_sntp_once();
    }
}

/* ── Servidor HTTP ───────────────────────────────────────────────────────── */
static esp_err_t start_web_server(void) {
    httpd_config_t cfg   = HTTPD_DEFAULT_CONFIG();
    cfg.max_uri_handlers = 12;
    cfg.stack_size       = 8192;
    cfg.lru_purge_enable = true;

    ESP_RETURN_ON_ERROR(httpd_start(&s_server, &cfg), TAG, "No se pudo iniciar el servidor HTTP");

    const httpd_uri_t routes[] = {
        /* Pagina principal */
        {"/", HTTP_GET, index_handler, NULL},
        {"/moon.bmp", HTTP_GET, moon_image_handler, NULL},
        /* Datos */
        {"/api/status", HTTP_GET, status_handler, NULL},
        {"/api/sensors", HTTP_GET, sensors_handler, NULL},
        {"/api/weather", HTTP_GET, weather_handler, NULL},
        /* Configuracion */
        {"/api/config/interval", HTTP_POST, config_interval_handler, NULL},
        {"/api/config/display", HTTP_POST, config_display_handler, NULL},
        /* Wi-Fi */
        {"/wifi", HTTP_POST, wifi_form_handler, NULL},
        /* Captive portal helpers */
        {"/generate_204", HTTP_GET, index_handler, NULL},
        {"/hotspot-detect.html", HTTP_GET, index_handler, NULL},
    };
    for (size_t i = 0; i < sizeof(routes) / sizeof(routes[0]); ++i) {
        const esp_err_t r = httpd_register_uri_handler(s_server, &routes[i]);
        if (r != ESP_OK) {
            httpd_stop(s_server);
            s_server = NULL;
            return r;
        }
    }
    return ESP_OK;
}

/* ── Punto de entrada ────────────────────────────────────────────────────── */
esp_err_t network_start(monitor_state_t *state) {
    s_state = state;
    if (s_moon_image_mutex == NULL) {
        s_moon_image_mutex = xSemaphoreCreateMutex();
        if (s_moon_image_mutex == NULL) {
            return ESP_ERR_NO_MEM;
        }
    }

    esp_err_t r = nvs_flash_init();
    if (r == ESP_ERR_NVS_NO_FREE_PAGES || r == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_RETURN_ON_ERROR(nvs_flash_erase(), TAG, "No se pudo limpiar NVS");
        ESP_RETURN_ON_ERROR(nvs_flash_init(), TAG, "No se pudo iniciar NVS");
    } else if (r != ESP_OK) {
        return r;
    }

#ifdef CONFIG_MONITOR_WOKWI_SIMULATION
    snprintf(s_saved_ssid, sizeof(s_saved_ssid), "Wokwi-GUEST");
    s_have_credentials = true;
#else
    size_t ssid_len   = sizeof(s_saved_ssid);
    size_t pw_len     = 65;
    char saved_pw[65] = {0};
    nvs_handle_t cred;
    if (nvs_open(NVS_NAMESPACE, NVS_READONLY, &cred) == ESP_OK) {
        const esp_err_t rs = nvs_get_str(cred, "ssid", s_saved_ssid, &ssid_len);
        const esp_err_t rp = nvs_get_str(cred, "password", saved_pw, &pw_len);
        s_have_credentials = (rs == ESP_OK && s_saved_ssid[0] != '\0' && rp == ESP_OK);
        nvs_close(cred);
    }
#endif

    ESP_RETURN_ON_ERROR(esp_netif_init(), TAG, "No se pudo inicializar TCP/IP");
    ESP_RETURN_ON_ERROR(esp_event_loop_create_default(), TAG, "No se pudo crear event loop");
    esp_netif_create_default_wifi_sta();
#ifndef CONFIG_MONITOR_WOKWI_SIMULATION
    esp_netif_create_default_wifi_ap();
#endif

    const wifi_init_config_t wifi_init = WIFI_INIT_CONFIG_DEFAULT();
    ESP_RETURN_ON_ERROR(esp_wifi_init(&wifi_init), TAG, "No se pudo iniciar Wi-Fi");
    ESP_RETURN_ON_ERROR(
        esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, wifi_event_handler, NULL), TAG,
        "Registro evento Wi-Fi");
    ESP_RETURN_ON_ERROR(
        esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, wifi_event_handler, NULL), TAG,
        "Registro evento IP");

#ifndef CONFIG_MONITOR_WOKWI_SIMULATION
    wifi_config_t ap = {0};
    snprintf((char *)ap.ap.ssid, sizeof(ap.ap.ssid), "%s", PORTAL_SSID);
    snprintf((char *)ap.ap.password, sizeof(ap.ap.password), "%s", PORTAL_AP_CODE);
    ap.ap.ssid_len       = (uint8_t)strlen(PORTAL_SSID);
    ap.ap.channel        = 1;
    ap.ap.max_connection = 4;
    ap.ap.authmode       = WIFI_AUTH_WPA2_PSK;
#endif

    wifi_config_t sta = {0};
#ifdef CONFIG_MONITOR_WOKWI_SIMULATION
    snprintf((char *)sta.sta.ssid, sizeof(sta.sta.ssid), "Wokwi-GUEST");
    sta.sta.channel            = 6;
    sta.sta.threshold.authmode = WIFI_AUTH_OPEN;
#else
    if (s_have_credentials) {
        memcpy(sta.sta.ssid, s_saved_ssid, strlen(s_saved_ssid));
        memcpy(sta.sta.password, saved_pw, strlen(saved_pw));
    }
#endif

    ESP_RETURN_ON_ERROR(esp_wifi_set_storage(WIFI_STORAGE_RAM), TAG, "wifi storage");
    ESP_RETURN_ON_ERROR(esp_wifi_set_mode(
#ifdef CONFIG_MONITOR_WOKWI_SIMULATION
                            WIFI_MODE_STA
#else
                            WIFI_MODE_APSTA
#endif
                            ),
                        TAG, "wifi mode");

#ifndef CONFIG_MONITOR_WOKWI_SIMULATION
    ESP_RETURN_ON_ERROR(esp_wifi_set_config(WIFI_IF_AP, &ap), TAG, "AP config");
#endif
    if (s_have_credentials) {
        ESP_RETURN_ON_ERROR(esp_wifi_set_config(WIFI_IF_STA, &sta), TAG, "STA config");
        monitor_state_set_wifi(state, false, s_saved_ssid, "");
    }

    ESP_RETURN_ON_ERROR(esp_wifi_start(), TAG, "wifi start");
    ESP_RETURN_ON_ERROR(start_web_server(), TAG, "web server");
    ESP_RETURN_ON_ERROR(weather_start(state), TAG, "weather task");
#ifndef CONFIG_MONITOR_WOKWI_SIMULATION
    ESP_RETURN_ON_ERROR(ble_server_start(state), TAG, "BLE GATT server");
#endif

#ifdef CONFIG_MONITOR_WOKWI_SIMULATION
    ESP_LOGI(TAG, "Wokwi: STA Wokwi-GUEST | servidor en puerto 80");
#else
    ESP_LOGI(TAG, "AP: %s / %s  |  http://192.168.4.1", PORTAL_SSID, PORTAL_AP_CODE);
    monitor_state_log_event(state, "Setup AP ready");
#endif
    return ESP_OK;
}
