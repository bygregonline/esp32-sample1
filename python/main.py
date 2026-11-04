"""Monitor ESP32 — MicroPython.

Equivalente completo al C/ESP-IDF:
  - Sensores: DHT22, GPS NEO-6M, ADC batería
  - Displays: LCD ST7789V2 (170×320), OLED SSD1306 (128×64)
  - Wi-Fi STA + AP de configuración
  - Servidor HTTP embebido (usocket no bloqueante)
  - Pronóstico Open-Meteo via urequests/HTTPS
  - Ajuste horario NTP

Endpoints:
  GET  /                     — página HTML
  GET  /api/status           — snapshot completo
  GET  /api/sensors          — última lectura de sensores
  GET  /api/weather          — solo datos de clima
  POST /api/config/interval  — cambia ciclo (5-300 s)
  POST /api/config/display   — oculta/muestra secciones
  POST /wifi                 — guarda credenciales Wi-Fi

Ejemplo curl:
  curl -X POST http://<ip>/api/config/interval \\
       -H 'Content-Type: application/json' \\
       -d '{"interval_seconds": 30}'
"""

import json
import time
import network as net_hw
import ntptime
import urequests
import usocket as socket

from machine import ADC, I2C, Pin, SPI, UART
from time import sleep_ms, ticks_diff, ticks_ms
import dht

import config
from gps import NMEAParser
from ssd1306 import SSD1306_I2C
from st7789 import ST7789


# ── Colores RGB565 ─────────────────────────────────────────────────────────
BLACK  = 0x0000
WHITE  = 0xFFFF
CYAN   = 0x07FF
GREEN  = 0x07E0
YELLOW = 0xFFE0
ORANGE = 0xFC60
DIM    = 0x2965

# ── Estado global ──────────────────────────────────────────────────────────
_state = {
    # sensores
    "battery_v":          0.0,
    "temperature_c":      None,
    "humidity_percent":   None,
    "dht_valid":          False,
    # gps
    "gps_fix":            False,
    "latitude":           None,
    "longitude":          None,
    "satellites":         None,
    # red
    "wifi_connected":     False,
    "wifi_ssid":          "",
    "ip_address":         "",
    # clima
    "weather": {
        "valid":                     False,
        "weather_code":              None,
        "summary":                   "SIN DATOS",
        "current_temperature_c":     None,
        "current_humidity_percent":  None,
        "minimum_temperature_c":     None,
        "maximum_temperature_c":     None,
        "precipitation_probability": None,
        "updated_ms":                0,
    },
    # ciclo
    "last_read_ms":       0,
    "sensor_interval_s":  config.SENSOR_INTERVAL_DEFAULT_S,
    "next_refresh_ms":    0,  # para el countdown de clima (equivale a next_refresh_us en C)
    "refresh_interval_s": config.WEATHER_REFRESH_INTERVAL_S,
    # display
    "display_mask": 0x0F,
    # interno
    "_last_display_ms":   0,
    "_last_dht_ms":       0,
    "_last_weather_lat":  None,
    "_last_weather_lon":  None,
}


# ── Hardware ───────────────────────────────────────────────────────────────

def make_lcd():
    spi = SPI(
        config.LCD_SPI_ID,
        baudrate=config.LCD_SPI_BAUDRATE,
        polarity=0, phase=0,
        sck=Pin(config.LCD_SCK_PIN),
        mosi=Pin(config.LCD_MOSI_PIN),
        miso=None,
    )
    bl = Pin(config.LCD_BL_PIN, Pin.OUT) if config.LCD_BL_PIN is not None else None
    lcd = ST7789(
        spi, config.LCD_WIDTH, config.LCD_HEIGHT,
        Pin(config.LCD_CS_PIN, Pin.OUT),
        Pin(config.LCD_DC_PIN, Pin.OUT),
        Pin(config.LCD_RST_PIN, Pin.OUT),
        bl, config.LCD_X_OFFSET, config.LCD_Y_OFFSET,
    )
    lcd.init()
    lcd.fill(BLACK)
    return lcd


def make_oled():
    i2c = I2C(config.OLED_I2C_ID,
              scl=Pin(config.OLED_SCL_PIN),
              sda=Pin(config.OLED_SDA_PIN),
              freq=config.OLED_I2C_FREQ)
    if config.OLED_I2C_ADDRESS not in i2c.scan():
        print("OLED no encontrado; continuando solo con LCD.")
        return None
    return SSD1306_I2C(config.OLED_WIDTH, config.OLED_HEIGHT,
                       i2c, config.OLED_I2C_ADDRESS)


# ── Wi-Fi ──────────────────────────────────────────────────────────────────

def _load_wifi_credentials():
    """Lee SSID/password del archivo de credenciales si existe."""
    try:
        with open("wifi_creds.json") as f:
            return json.load(f)
    except Exception:
        return None


def _save_wifi_credentials(ssid, password):
    with open("wifi_creds.json", "w") as f:
        json.dump({"ssid": ssid, "password": password}, f)


def start_wifi():
    """Inicia Wi-Fi: STA con credenciales guardadas + AP de configuración."""
    sta = net_hw.WLAN(net_hw.STA_IF)
    ap  = net_hw.WLAN(net_hw.AP_IF)

    # AP siempre activo (equivalente al APSTA de ESP-IDF)
    ap.active(True)
    ap.config(
        essid=config.PORTAL_SSID,
        password=config.PORTAL_AP_CODE,
        authmode=net_hw.AUTH_WPA2_PSK,
    )
    print("AP activo:", config.PORTAL_SSID, "/ http://192.168.4.1")

    # STA con credenciales guardadas
    creds = _load_wifi_credentials()
    if creds:
        sta.active(True)
        sta.connect(creds["ssid"], creds["password"])
        # Esperar conexión hasta 10 s
        for _ in range(100):
            if sta.isconnected():
                break
            sleep_ms(100)

        if sta.isconnected():
            ip = sta.ifconfig()[0]
            _state["wifi_connected"] = True
            _state["wifi_ssid"]      = creds["ssid"]
            _state["ip_address"]     = ip
            print("Wi-Fi conectado:", creds["ssid"], "/", ip)
            # Sincronizar NTP
            try:
                ntptime.settime()
                print("NTP sincronizado")
            except Exception as e:
                print("NTP error:", e)
        else:
            print("Wi-Fi: no se pudo conectar a", creds["ssid"])
            _state["wifi_connected"] = False
            _state["wifi_ssid"]      = creds["ssid"]

    return sta, ap


# ── Clima (Open-Meteo) ─────────────────────────────────────────────────────

WEATHER_SUMMARIES = {
    0:  "SOLEADO",
    1:  "PARC NUBLADO", 2: "PARC NUBLADO",
    3:  "NUBLADO",
    45: "NEBLINA", 48: "NEBLINA",
    51: "LLOVIZNA", 53: "LLOVIZNA", 55: "LLOVIZNA",
    61: "LLUVIA",  63: "LLUVIA",  65: "LLUVIA",
    71: "NIEVE",   73: "NIEVE",   75: "NIEVE",
    77: "NIEVE",
    80: "CHUBASCOS", 81: "CHUBASCOS", 82: "CHUBASCOS",
    85: "NIEVE",   86: "NIEVE",
    95: "TORMENTA",
}

def _weather_summary(code):
    if code in WEATHER_SUMMARIES:
        return WEATHER_SUMMARIES[code]
    if code >= 95:
        return "TORMENTA"
    return "SIN DATOS"


def fetch_weather(lat, lon):
    url = (
        "https://api.open-meteo.com/v1/forecast"
        "?latitude={:.6f}&longitude={:.6f}"
        "&current=temperature_2m,relative_humidity_2m,weather_code"
        "&daily=temperature_2m_min,temperature_2m_max,precipitation_probability_max"
        "&forecast_days=1&timezone=auto"
    ).format(lat, lon)

    try:
        r = urequests.get(url, timeout=15)
        if r.status_code != 200:
            print("Clima HTTP", r.status_code)
            r.close()
            return None
        data = r.json()
        r.close()

        cur   = data.get("current", {})
        daily = data.get("daily", {})
        code  = int(cur.get("weather_code", 0))
        return {
            "valid":                     True,
            "weather_code":              code,
            "summary":                   _weather_summary(code),
            "current_temperature_c":     cur.get("temperature_2m"),
            "current_humidity_percent":  cur.get("relative_humidity_2m"),
            "minimum_temperature_c":     (daily.get("temperature_2m_min") or [None])[0],
            "maximum_temperature_c":     (daily.get("temperature_2m_max") or [None])[0],
            "precipitation_probability": (daily.get("precipitation_probability_max") or [None])[0],
            "updated_ms":                ticks_ms(),
        }
    except Exception as e:
        print("Error clima:", e)
        return None


def maybe_update_weather():
    """Llama al API de clima si toca (equivale a weather_task en C)."""
    s = _state
    if not s["wifi_connected"] or not s["gps_fix"]:
        return
    lat, lon = s["latitude"], s["longitude"]
    if lat is None or lon is None:
        return

    now = ticks_ms()
    refresh_due = (s["next_refresh_ms"] == 0 or
                   ticks_diff(now, s["next_refresh_ms"]) >= 0)

    last_lat = s["_last_weather_lat"]
    last_lon = s["_last_weather_lon"]
    loc_changed = (last_lat is None or
                   abs(lat - last_lat) > 0.005 or
                   abs(lon - last_lon) > 0.005)

    if not (refresh_due or loc_changed):
        return

    # Programar próxima actualización antes de llamar (igual que C)
    s["next_refresh_ms"] = ticks_ms() + s["refresh_interval_s"] * 1000
    s["_last_weather_lat"] = lat
    s["_last_weather_lon"] = lon

    print("Consultando clima para %.5f, %.5f" % (lat, lon))
    result = fetch_weather(lat, lon)
    if result:
        s["weather"] = result
        print("Clima:", result["summary"], result["current_temperature_c"], "C")


# ── ADC batería ────────────────────────────────────────────────────────────

def read_battery_voltage(adc):
    total_uv = 0
    for _ in range(8):
        try:
            total_uv += adc.read_uv()
        except AttributeError:
            total_uv += int(adc.read_u16() * 2_450_000 // 65_535)
    adc_v = total_uv / 8 / 1_000_000
    return (adc_v
            * config.ADC_EXTERNAL_DIVIDER_RATIO
            * config.VOLTAGE_SENSOR_RATIO
            * config.VOLTAGE_CALIBRATION)


# ── Display LCD ────────────────────────────────────────────────────────────

def _hline(lcd, y):
    lcd.hline(0, y, config.LCD_WIDTH, DIM)


def render_lcd(lcd, st):
    mask = st["display_mask"]
    now  = ticks_ms()

    lcd.fill(BLACK)
    lcd.text("ESP32 MONITOR", 4, 4, WHITE)
    _hline(lcd, 14)

    # Wi-Fi
    if st["wifi_connected"]:
        lcd.text("WIFI %-12s  %s" % (st["wifi_ssid"][:12], st["ip_address"]), 4, 20, GREEN)
    else:
        lcd.text("WIFI SIN CONEXION  AP:192.168.4.1", 4, 20, YELLOW)

    # Batería
    if mask & 0x01:
        lcd.text("BAT", 4, 36, CYAN)
        v = st["battery_v"]
        lcd.text("%.2fV" % v, 28, 36, GREEN if v > 3.5 else YELLOW)
    _hline(lcd, 46)

    # Temperatura / Humedad
    if mask & 0x02:
        lcd.text("TEMP", 4, 52, CYAN)
        if st["dht_valid"]:
            lcd.text("%.1fC" % st["temperature_c"], 34, 52, WHITE)
            lcd.text("HUM", 82, 52, CYAN)
            lcd.text("%.0f%%" % st["humidity_percent"], 106, 52, WHITE)
        else:
            lcd.text("DHT22 SIN DATOS", 34, 52, YELLOW)
    _hline(lcd, 62)

    # GPS
    if mask & 0x04:
        lcd.text("GPS", 4, 68, CYAN)
        if st["gps_fix"]:
            sats = st["satellites"]
            lcd.text("FIX  SAT %s" % (str(sats) if sats is not None else "--"),
                     28, 68, GREEN)
            lcd.text("LAT %.5f" % st["latitude"],  4, 80, WHITE)
            lcd.text("LON %.5f" % st["longitude"], 4, 92, WHITE)
        else:
            lcd.text("BUSCANDO SENAL", 28, 68, YELLOW)
            lcd.text("LAT ---.-----", 4, 80, DIM)
            lcd.text("LON ---.-----", 4, 92, DIM)
    _hline(lcd, 104)

    # Clima
    if mask & 0x08:
        lcd.text("CLIMA", 4, 110, CYAN)
        w = st["weather"]
        if w["valid"]:
            lcd.text("%-14s %.1fC" % (w["summary"][:14], w["current_temperature_c"]),
                     4, 122, ORANGE)
            lcd.text("MIN %.1f  MAX %.1fC" % (
                w["minimum_temperature_c"],
                w["maximum_temperature_c"]), 4, 134, WHITE)
            lcd.text("LLUVIA %d%%" % w["precipitation_probability"], 4, 146, YELLOW)
        else:
            lcd.text("ESPERANDO GPS/CLIMA" if st["wifi_connected"]
                     else "ESPERANDO WIFI/GPS", 4, 122, DIM)
            lcd.text("MIN --  MAX --  P --", 4, 134, DIM)
    _hline(lcd, 158)

    # UPDATE + countdown
    iv  = st["sensor_interval_s"]
    elapsed = ticks_diff(now, st["last_read_ms"]) // 1000
    rem     = max(0, iv - elapsed)
    lcd.text("UPDATE", 4, 164, CYAN)
    lcd.text("%ds" % iv, 52, 164, WHITE)
    lcd.text("PROX %02d:%02d" % (rem // 60, rem % 60), 82, 164,
             GREEN if rem > iv // 3 else YELLOW)


def render_oled(oled, st):
    if oled is None:
        return
    mask = st["display_mask"]
    now  = ticks_ms()
    iv   = st["sensor_interval_s"]
    elapsed = ticks_diff(now, st["last_read_ms"]) // 1000
    rem     = max(0, iv - elapsed)

    oled.fill(0)
    row = 0

    # Título / Wi-Fi
    oled.text("WIFI OK" if st["wifi_connected"] else "WIFI CONFIG", 0, row)
    row += 8

    # Batería
    if mask & 0x01:
        oled.text("BAT %.2fV" % st["battery_v"], 0, row)
        row += 8

    # DHT22
    if mask & 0x02:
        if st["dht_valid"]:
            oled.text("T %.1fC H %.0f%%" % (
                st["temperature_c"], st["humidity_percent"]), 0, row)
        else:
            oled.text("DHT22 SIN DATOS", 0, row)
        row += 8

    # GPS
    if mask & 0x04:
        if st["gps_fix"]:
            oled.text("LAT %.4f" % st["latitude"],  0, row);     row += 8
            oled.text("LON %.4f" % st["longitude"], 0, min(row, 48)); row += 8
        else:
            oled.text("GPS BUSCANDO", 0, row);  row += 8
            oled.text("LAT/LON --",   0, min(row, 48)); row += 8

    # Clima
    if mask & 0x08:
        w = st["weather"]
        if w["valid"] and row <= 40:
            oled.text("%-8s %.0fC" % (w["summary"][:8],
                                       w["current_temperature_c"]), 0, row)
            row += 8

    # UPDATE + countdown (siempre en fila 56)
    oled.text("UPD %ds  %02d:%02d" % (iv, rem // 60, rem % 60), 0, 56)
    oled.show()


# ── Servidor web ───────────────────────────────────────────────────────────

HTML_PAGE = """\
<!doctype html><html lang='es'><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>ESP32 Monitor</title>
<style>
body{font:15px system-ui;max-width:720px;margin:24px auto;padding:0 16px;
background:#0d1117;color:#e6edf3}
h1{color:#58a6ff;font-size:1.4rem}h2{color:#79c0ff;font-size:1rem;margin:0 0 8px}
section{background:#161b22;padding:14px 16px;border-radius:10px;margin:10px 0;
border:1px solid #21262d}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.card{background:#0d1117;border-radius:8px;padding:10px 12px;border:1px solid #21262d}
.lbl{font-size:.75rem;color:#8b949e;text-transform:uppercase;letter-spacing:.05em}
.val{font-size:1.15rem;font-weight:600;margin-top:2px}
.ok{color:#3fb950}.warn{color:#d29922}.muted{color:#8b949e;font-size:.85rem}
label{display:block;margin:8px 0 3px;font-size:.85rem;color:#8b949e}
input,button{font:inherit;padding:9px 12px;width:100%;box-sizing:border-box;
border-radius:6px;border:1px solid #30363d;background:#0d1117;color:#e6edf3}
button{margin-top:10px;background:#238636;color:#fff;border:none}
#msg,#wres{margin-top:8px;font-size:.85rem;color:#8b949e}
</style>
<h1>ESP32 Monitor</h1>
<section><h2>Lecturas</h2><div class='grid'>
<div class='card'><div class='lbl'>Bateria</div><div class='val' id='bat'>--</div></div>
<div class='card'><div class='lbl'>Temperatura</div><div class='val' id='temp'>--</div></div>
<div class='card'><div class='lbl'>Humedad</div><div class='val' id='hum'>--</div></div>
<div class='card'><div class='lbl'>GPS</div><div class='val' id='gps'>--</div></div>
<div class='card'><div class='lbl'>Clima</div><div class='val' id='wx'>--</div></div>
<div class='card'><div class='lbl'>Ciclo / prox.</div><div class='val' id='upd'>--</div></div>
</div></section>
<section><h2>Ciclo de sensores</h2>
<p class='muted'>Intervalo entre lecturas (5-300 s).</p>
<label>Segundos</label><input id='iv' type='number' min='5' max='300' value='10'>
<button onclick='setIv()'>Aplicar</button><div id='msg'></div></section>
<section><h2>Conectar a Wi-Fi</h2>
<p class='muted'>Se guarda en el dispositivo.</p>
<form id='wf'>
<label>Red Wi-Fi</label><input name='ssid' maxlength='32' required autocomplete='off'>
<label>Contrasena</label><input name='password' type='password' maxlength='64'>
<button>Guardar y conectar</button></form><p id='wres'></p></section>
<p class='muted'>
<a href='/api/status'>/api/status</a> &middot;
<a href='/api/sensors'>/api/sensors</a> &middot;
<a href='/api/weather'>/api/weather</a> &middot;
POST <code>/api/config/interval</code> &middot;
POST <code>/api/config/display</code></p>
<script>
async function r(){try{
const d=await(await fetch('/api/status',{cache:'no-store'})).json();
const s=d.sensors,g=d.gps,w=d.weather,rf=d.refresh;
set('bat',s.battery_v.toFixed(2)+' V',s.battery_v>3.5?'ok':'warn');
set('temp',s.temperature_c!=null?s.temperature_c.toFixed(1)+' C':'--',s.temperature_c!=null?'ok':'warn');
set('hum',s.humidity_percent!=null?s.humidity_percent.toFixed(0)+' %':'--',s.humidity_percent!=null?'ok':'warn');
set('gps',g.fix?(g.latitude.toFixed(4)+', '+g.longitude.toFixed(4)):'Buscando',g.fix?'ok':'warn');
set('wx',w.available?w.summary+' '+w.current_temperature_c.toFixed(1)+'C':'Sin datos',w.available?'ok':'muted');
set('upd',rf.interval_seconds+'s / '+(rf.remaining_seconds>=0?rf.remaining_seconds+'s':'esperando'),'ok');
document.getElementById('iv').value=rf.interval_seconds;
}catch(e){}}
function set(id,v,c){const e=document.getElementById(id);e.textContent=v;e.className='val '+(c||'');}
setInterval(r,2000);r();
async function setIv(){const v=parseInt(document.getElementById('iv').value,10);
if(isNaN(v)||v<5||v>300){document.getElementById('msg').textContent='Rango 5-300';return;}
const j=await(await fetch('/api/config/interval',{method:'POST',
headers:{'Content-Type':'application/json'},body:JSON.stringify({interval_seconds:v})})).json();
document.getElementById('msg').textContent=j.ok?'Aplicado: '+j.interval_seconds+'s':'Error';}
document.getElementById('wf').onsubmit=async e=>{e.preventDefault();
const res=await fetch('/wifi',{method:'POST',
headers:{'Content-Type':'application/x-www-form-urlencoded'},
body:new URLSearchParams(new FormData(e.target))});
document.getElementById('wres').textContent=await res.text();};
</script>
"""


def _send(conn, status, ctype, body):
    if isinstance(body, str):
        body = body.encode("utf-8")
    hdr = ("HTTP/1.0 %s\r\nContent-Type: %s\r\n"
           "Cache-Control: no-store\r\nContent-Length: %d\r\n\r\n"
           % (status, ctype, len(body)))
    conn.sendall(hdr.encode())
    conn.sendall(body)


def _read_body(conn, content_length, max_len=512):
    if content_length <= 0 or content_length > max_len:
        return b""
    buf = b""
    remaining = content_length
    conn.settimeout(3.0)
    try:
        while remaining > 0:
            chunk = conn.recv(min(remaining, 256))
            if not chunk:
                break
            buf += chunk
            remaining -= len(chunk)
    except Exception:
        pass
    return buf


def _weather_json(st, now_ms_val):
    w = st["weather"]
    age = (now_ms_val - w["updated_ms"]) // 1000 if w["valid"] and w["updated_ms"] else 0
    stale = w["valid"] and age > st["refresh_interval_s"] * 2

    def nv(v):
        return ("null" if v is None else
                str(round(v, 6)).rstrip('0').rstrip('.'))

    return json.dumps({
        "available":                w["valid"],
        "summary":                  w["summary"],
        "weather_code":             w["weather_code"],
        "current_temperature_c":    w["current_temperature_c"],
        "current_humidity_percent": w["current_humidity_percent"],
        "minimum_temperature_c":    w["minimum_temperature_c"],
        "maximum_temperature_c":    w["maximum_temperature_c"],
        "precipitation_probability": w["precipitation_probability"],
        "age_seconds":              age,
        "stale":                    stale,
    })


def _seconds_until_refresh(st):
    """Equivalente a monitor_seconds_until_refresh en C."""
    now  = ticks_ms()
    nrm  = st["next_refresh_ms"]
    if nrm == 0:
        return -1
    rem = ticks_diff(nrm, now) // 1000
    return max(0, rem)


def _status_json(st):
    now_ms_val = ticks_ms()
    elapsed    = ticks_diff(now_ms_val, st["last_read_ms"]) // 1000
    remaining  = max(0, st["sensor_interval_s"] - elapsed)
    wx_rem     = _seconds_until_refresh(st)
    return json.dumps({
        "sensors": {
            "battery_v":       round(st["battery_v"], 3),
            "temperature_c":   round(st["temperature_c"], 1) if st["dht_valid"] else None,
            "humidity_percent": round(st["humidity_percent"], 1) if st["dht_valid"] else None,
            "dht_valid":        st["dht_valid"],
            "last_read_ms":     st["last_read_ms"],
        },
        "gps": {
            "fix":        st["gps_fix"],
            "latitude":   round(st["latitude"],  6) if st["gps_fix"] else None,
            "longitude":  round(st["longitude"], 6) if st["gps_fix"] else None,
            "satellites": st["satellites"],
        },
        "wifi": {
            "connected": st["wifi_connected"],
            "ssid":      st["wifi_ssid"],
            "ip":        st["ip_address"],
        },
        "refresh": {
            "interval_seconds":         st["sensor_interval_s"],
            "weather_interval_seconds": st["refresh_interval_s"],
            "remaining_seconds":        remaining,
        },
        "display_mask": st["display_mask"],
        "weather": json.loads(_weather_json(st, now_ms_val)),
    })


def _sensors_json(st):
    now_ms_val = ticks_ms()
    elapsed    = ticks_diff(now_ms_val, st["last_read_ms"]) // 1000
    remaining  = max(0, st["sensor_interval_s"] - elapsed)
    return json.dumps({
        "battery_v":         round(st["battery_v"], 3),
        "temperature_c":     round(st["temperature_c"], 1) if st["dht_valid"] else None,
        "humidity_percent":  round(st["humidity_percent"], 1) if st["dht_valid"] else None,
        "dht_valid":         st["dht_valid"],
        "gps_fix":           st["gps_fix"],
        "latitude":          round(st["latitude"],  6) if st["gps_fix"] else None,
        "longitude":         round(st["longitude"], 6) if st["gps_fix"] else None,
        "satellites":        st["satellites"],
        "last_read_ms":      st["last_read_ms"],
        "interval_seconds":  st["sensor_interval_s"],
        "remaining_seconds": remaining,
    })


def _url_decode(s):
    out = []
    i = 0
    while i < len(s):
        if s[i] == '+':
            out.append(' '); i += 1
        elif s[i] == '%' and i + 2 < len(s):
            try:
                out.append(chr(int(s[i+1:i+3], 16))); i += 3
            except Exception:
                out.append('%'); i += 1
        else:
            out.append(s[i]); i += 1
    return ''.join(out)


def _form_value(body_str, key):
    for part in body_str.split('&'):
        if '=' in part:
            k, v = part.split('=', 1)
            if _url_decode(k) == key:
                return _url_decode(v)
    return ''


def handle_request(conn, addr, sta):
    try:
        raw = b""
        conn.settimeout(2.0)
        while True:
            try:
                chunk = conn.recv(1024)
                if not chunk:
                    break
                raw += chunk
                if b"\r\n\r\n" in raw:
                    break
            except Exception:
                break
    except Exception:
        return

    try:
        text = raw.decode("utf-8", "ignore")
    except Exception:
        return

    lines = text.split("\r\n")
    if not lines:
        return
    parts = lines[0].split(" ")
    if len(parts) < 2:
        return
    method = parts[0]
    path   = parts[1].split("?")[0]

    # Content-Length
    content_length = 0
    for line in lines[1:]:
        if line.lower().startswith("content-length:"):
            try:
                content_length = int(line.split(":", 1)[1].strip())
            except Exception:
                pass

    # Body
    body_bytes = b""
    if "\r\n\r\n" in text:
        pre, post = text.split("\r\n\r\n", 1)
        body_bytes = post.encode("utf-8") if post else b""
    if content_length > len(body_bytes):
        body_bytes += _read_body(conn, content_length - len(body_bytes))
    body_str = body_bytes.decode("utf-8", "ignore")

    # ── Enrutamiento ────────────────────────────────────────────────────
    if method == "GET" and path in ("/", "/index.html",
                                     "/generate_204", "/hotspot-detect.html"):
        _send(conn, "200 OK", "text/html; charset=utf-8", HTML_PAGE)

    elif method == "GET" and path == "/api/status":
        _send(conn, "200 OK", "application/json", _status_json(_state))

    elif method == "GET" and path == "/api/sensors":
        _send(conn, "200 OK", "application/json", _sensors_json(_state))

    elif method == "GET" and path == "/api/weather":
        _send(conn, "200 OK", "application/json",
              _weather_json(_state, ticks_ms()))

    elif method == "POST" and path == "/api/config/interval":
        ok = False
        new_iv = None
        try:
            data = json.loads(body_str)
            v = int(data.get("interval_seconds", 0))
            if config.SENSOR_INTERVAL_MIN_S <= v <= config.SENSOR_INTERVAL_MAX_S:
                _state["sensor_interval_s"] = v
                new_iv = v
                ok = True
        except Exception:
            pass
        if ok:
            _send(conn, "200 OK", "application/json",
                  json.dumps({"ok": True, "interval_seconds": new_iv}))
        else:
            _send(conn, "400 Bad Request", "application/json",
                  json.dumps({"ok": False,
                               "error": "interval_seconds fuera de rango (5-300)"}))

    elif method == "POST" and path == "/api/config/display":
        try:
            data = json.loads(body_str)
            mask = _state["display_mask"]
            for key, bit in (("battery", 0x01), ("dht", 0x02),
                              ("gps", 0x04), ("weather", 0x08)):
                if key in data:
                    if data[key]:
                        mask |= bit
                    else:
                        mask &= ~bit & 0xFF
            _state["display_mask"] = mask
            _send(conn, "200 OK", "application/json",
                  json.dumps({
                      "ok": True, "display_mask": mask,
                      "battery": bool(mask & 0x01),
                      "dht":     bool(mask & 0x02),
                      "gps":     bool(mask & 0x04),
                      "weather": bool(mask & 0x08),
                  }))
        except Exception as e:
            _send(conn, "400 Bad Request", "application/json",
                  json.dumps({"ok": False, "error": str(e)}))

    elif method == "POST" and path == "/wifi":
        ssid = _form_value(body_str, "ssid")
        pw   = _form_value(body_str, "password")
        if ssid:
            _save_wifi_credentials(ssid, pw)
            _state["wifi_ssid"] = ssid
            # Intentar reconexión
            try:
                sta.connect(ssid, pw)
                for _ in range(100):
                    if sta.isconnected():
                        break
                    sleep_ms(100)
                if sta.isconnected():
                    ip = sta.ifconfig()[0]
                    _state["wifi_connected"] = True
                    _state["ip_address"]     = ip
            except Exception:
                pass
            _send(conn, "200 OK", "text/plain",
                  "Guardadas. Reconectando...")
        else:
            _send(conn, "400 Bad Request", "text/plain", "SSID vacio")

    else:
        _send(conn, "404 Not Found", "text/plain", "Not found")


def start_server():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("", config.WEB_SERVER_PORT))
    srv.listen(2)
    srv.setblocking(False)
    print("Servidor HTTP en puerto", config.WEB_SERVER_PORT)
    return srv


def poll_server(srv, sta):
    try:
        conn, addr = srv.accept()
        conn.settimeout(2.0)
        handle_request(conn, addr, sta)
        conn.close()
    except OSError:
        pass


# ── Bucle principal ────────────────────────────────────────────────────────

def main():
    print("Iniciando ESP32 Monitor (MicroPython)...")

    lcd  = make_lcd()
    oled = make_oled()

    dht_sensor = dht.DHT22(Pin(config.DHT_PIN, Pin.IN, Pin.PULL_UP))
    gps_uart   = UART(config.GPS_UART_ID, baudrate=config.GPS_BAUDRATE,
                      bits=8, parity=None, stop=1,
                      tx=Pin(config.GPS_TX_PIN), rx=Pin(config.GPS_RX_PIN))
    gps = NMEAParser()

    adc = ADC(Pin(config.VOLTAGE_ADC_PIN), atten=ADC.ATTN_11DB)
    try:
        adc.width(ADC.WIDTH_12BIT)
    except AttributeError:
        pass

    # Wi-Fi
    sta, ap = start_wifi()

    # Servidor HTTP
    srv = None
    try:
        srv = start_server()
    except Exception as e:
        print("Servidor web no disponible:", e)

    last_read_ms = ticks_ms() - _state["sensor_interval_s"] * 1000

    while True:
        now = ticks_ms()

        # ── GPS ──────────────────────────────────────────────────────────
        incoming = gps_uart.read()
        if incoming:
            gps.feed(incoming)
        _state["gps_fix"]   = gps.has_recent_fix()
        _state["latitude"]  = gps.latitude
        _state["longitude"] = gps.longitude
        _state["satellites"]= gps.satellites

        # ── Ciclo de sensores ─────────────────────────────────────────────
        sensor_interval_ms = _state["sensor_interval_s"] * 1000
        if ticks_diff(now, last_read_ms) >= sensor_interval_ms:
            last_read_ms = now
            _state["last_read_ms"] = now

            # DHT22 — mínimo 2.5 s entre lecturas
            if ticks_diff(now, _state["_last_dht_ms"]) >= config.DHT_READ_INTERVAL_MS:
                _state["_last_dht_ms"] = now
                try:
                    dht_sensor.measure()
                    _state["temperature_c"]    = dht_sensor.temperature()
                    _state["humidity_percent"] = dht_sensor.humidity()
                    _state["dht_valid"]        = True
                except OSError as e:
                    print("DHT22 error:", e)
                    _state["dht_valid"] = False

            _state["battery_v"] = read_battery_voltage(adc)

            # Clima
            maybe_update_weather()

            print("Bat %.2fV | T %s | H %s | GPS %s | ciclo %ds" % (
                _state["battery_v"],
                "--" if not _state["dht_valid"] else "%.1fC" % _state["temperature_c"],
                "--" if not _state["dht_valid"] else "%.0f%%" % _state["humidity_percent"],
                "FIX" if _state["gps_fix"] else "sin fix",
                _state["sensor_interval_s"],
            ))

        # ── Wi-Fi estado ──────────────────────────────────────────────────
        connected = sta.isconnected()
        if connected and not _state["wifi_connected"]:
            ip = sta.ifconfig()[0]
            _state["wifi_connected"] = True
            _state["ip_address"]     = ip
            print("Wi-Fi reconectado:", ip)
        elif not connected and _state["wifi_connected"]:
            _state["wifi_connected"] = False
            _state["ip_address"]     = ""

        # ── Display ───────────────────────────────────────────────────────
        if ticks_diff(now, _state["_last_display_ms"]) >= config.DISPLAY_UPDATE_INTERVAL_MS:
            _state["_last_display_ms"] = now
            render_lcd(lcd, _state)
            render_oled(oled, _state)

        # ── Servidor HTTP ─────────────────────────────────────────────────
        if srv is not None:
            poll_server(srv, sta)

        sleep_ms(20)


if __name__ == "__main__":
    main()
