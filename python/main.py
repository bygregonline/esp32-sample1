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
try:
    import bluetooth
except ImportError:
    bluetooth = None

from machine import ADC, I2C, Pin, SPI, UART
from time import sleep_ms, ticks_diff, ticks_ms
import dht

import config
from gps import NMEAParser
from bmp280 import BMP280
from moon_image import update as moon_image_update
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
    "pressure_hpa":       None,
    "bmp280_valid":       False,
    "moon_phase":         None,
    "moon_phase_valid":   False,
    "moon_illumination_percent": None,
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
        "moon_phase": None,
        "moon_illumination_percent": None,
        "moon_phase_valid": False,
        "updated_ms":                0,
    },
    # ciclo
    "last_read_ms":       0,
    "sensor_interval_s":  config.SENSOR_INTERVAL_DEFAULT_S,
    "next_refresh_ms":    0,  # para el countdown de clima (equivale a next_refresh_us en C)
    "refresh_interval_s": config.WEATHER_REFRESH_INTERVAL_S,
    # display
    "display_mask": 0x3F,
    # interno
    "_last_display_ms":   0,
    "_last_dht_ms":       0,
    "_last_weather_lat":  None,
    "_last_weather_lon":  None,
}
_events = []

def local_datetime():
    return time.localtime(time.time() + config.TIMEZONE_OFFSET_HOURS * 3600)

def clock_text():
    if time.time() < 1700000000:
        return "TIME SYNCING"
    lt = local_datetime()
    weekdays = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
    months = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
    return "%s %02d %s %02d:%02d" % (weekdays[lt[6]],lt[2],months[lt[1]-1],lt[3],lt[4])

def log_event(message):
    try:
        lt = local_datetime()
        stamp = "%02d:%02d:%02d" % (lt[3], lt[4], lt[5]) if lt[0] >= 2024 else "--:--:--"
    except Exception:
        stamp = "--:--:--"
    _events.append("%s %s" % (stamp, message))
    if len(_events) > 4:
        del _events[0]


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
        oled = None
    else:
        oled = SSD1306_I2C(config.OLED_WIDTH, config.OLED_HEIGHT,
                           i2c, config.OLED_I2C_ADDRESS)
    return i2c, oled


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
    log_event("Setup AP ready")

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
            log_event("Wi-Fi connected %s" % ip)
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
            log_event("Wi-Fi connection failed")

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

def moon_phase_name(phase):
    if phase is None: return "--"
    if phase < .035 or phase >= .965: return "NEW"
    if phase < .22: return "WAX CRES"
    if phase < .28: return "FIRST Q"
    if phase < .47: return "WAX GIB"
    if phase < .53: return "FULL"
    if phase < .72: return "WAN GIB"
    if phase < .78: return "LAST Q"
    return "WAN CRES"


def fetch_weather(lat, lon):
    url = (
        "https://api.open-meteo.com/v1/forecast"
        "?latitude={:.6f}&longitude={:.6f}"
        "&current=temperature_2m,relative_humidity_2m,weather_code"
        "&daily=temperature_2m_min,temperature_2m_max,precipitation_probability_max,moon_phase"
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
            "moon_phase": (daily.get("moon_phase") or [None])[0],
            "moon_illumination_percent": int((1 - __import__("math").cos(((daily.get("moon_phase") or [0])[0] or 0) * 6.2831853)) * 50),
            "moon_phase_valid": bool(daily.get("moon_phase") and daily["moon_phase"][0] is not None),
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
        log_event("Weather updated")
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
    iv = st["sensor_interval_s"]
    elapsed = ticks_diff(now, st["last_read_ms"]) // 1000
    rem = max(0, iv - elapsed)

    lcd.fill(BLACK)
    lcd.text(clock_text(), 4, 4, WHITE)

    # Keep date and IP together in the top status band.
    if st["wifi_connected"]:
        lcd.text("IP %s" % st["ip_address"], 4, 20, GREEN)
    else:
        lcd.text("IP 192.168.4.1", 4, 20, YELLOW)

    # Batería
    if mask & 0x01:
        lcd.text("BAT", 4, 36, CYAN)
        v = st["battery_v"]
        lcd.text("%.2fV" % v, 28, 36, GREEN if v > 3.5 else YELLOW)
    _hline(lcd, 46)
    # Refresh ring sits at the far right of the clock/IP header.
    fraction = rem / iv if iv else 0
    ring_color = GREEN if fraction > 0.5 else YELLOW if fraction > 0.2 else 0xF800
    lcd.countdown_ring(149, 23, 20, rem, iv, DIM, ring_color)
    lcd.mini_timer(149, 23, "%02d:%02d" % (rem // 60, rem % 60))

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
            lcd.text("GPS FIX", 28, 68, GREEN)
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
    if mask & 0x10:
        lcd.text("PRESS %.1f hPa" % st["pressure_hpa"] if st["bmp280_valid"] else "PRESS -- hPa",
                 4, 158, CYAN if st["bmp280_valid"] else DIM)
    if mask & 0x20:
        phase = st["weather"].get("moon_phase")
        illumination = st["weather"].get("moon_illumination_percent") if st["weather"].get("moon_phase_valid") else None
        lcd.text("MOON %s %s%%" % (moon_phase_name(phase),
                 str(illumination) if illumination is not None else "--"), 4, 170, WHITE)
        lcd.moon_icon(151, 171, phase if phase is not None else 0.0,
                      st["weather"].get("moon_phase_valid", False))

    # Sensor interval; the remaining-time ring is above.
    lcd.text("UPDATE", 4, 188, CYAN)
    lcd.text("%ds" % iv, 52, 188, WHITE)
    lcd.text("SYSTEM LOG", 4, 220, CYAN)
    for i, event in enumerate(_events[-3:]):
        lcd.text(event[:27], 4, 232 + i * 10, WHITE)


def render_oled(oled, st):
    if oled is None:
        return
    mask = st["display_mask"]
    now  = ticks_ms()
    iv   = st["sensor_interval_s"]
    elapsed = ticks_diff(now, st["last_read_ms"]) // 1000
    rem     = max(0, iv - elapsed)

    oled.fill(0)
    oled.text(clock_text(), 0, 0)
    oled.text("IP %s" % (st["ip_address"] or "192.168.4.1"), 0, 8)
    oled.text("T%s H%s BAT%.1f" % ("--" if not st["dht_valid"] else "%.0f"%st["temperature_c"],
              "--" if not st["dht_valid"] else "%.0f"%st["humidity_percent"],st["battery_v"]),0,16)
    if mask & 0x10:
        oled.text("P %s hPa" % ("%.1f"%st["pressure_hpa"] if st["bmp280_valid"] else "--"),0,24)
    oled.text("LAT %.4f" % st["latitude"] if st["gps_fix"] else "LAT --",0,32)
    oled.text("LON %.4f" % st["longitude"] if st["gps_fix"] else "LON --",0,40)
    if mask & 0x08:
        weather = st["weather"]
        oled.text("WX %-8s %.0fC" % (weather["summary"][:8], weather["current_temperature_c"])
                  if weather["valid"] else "WEATHER WAITING", 0, 48)
    # UPDATE + countdown (siempre en fila 56)
    oled.text("UPD %ds  %02d:%02d" % (iv, rem // 60, rem % 60), 0, 56)
    oled.show()


# ── Servidor web ───────────────────────────────────────────────────────────

HTML_PAGE = """\
<!doctype html><html lang='es'><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>ESP32 Monitor</title>
<style>
body{font:15px system-ui;max-width:1000px;margin:30px auto;padding:0 18px;
background:radial-gradient(ellipse at 50% -20%,#172c49 0,#0a101b 48%,#080c13 100%);
color:#e8f0fc;min-height:100vh}
h1{font-size:1.65rem;margin:0 0 4px;color:#f1f6ff;letter-spacing:-.03em}h2{color:#79c0ff;font-size:1rem;margin:0 0 8px}
.hero{padding-right:70px;min-height:60px;margin-bottom:18px}
.eyebrow{font-size:.7rem;color:#78b8ff;text-transform:uppercase;letter-spacing:.18em;margin:0 0 4px}
.refresh-badge{position:fixed;z-index:5;top:12px;right:12px;left:auto;width:54px;height:54px;
display:grid;place-items:center;border:1px solid #29415d;border-radius:16px;
background:#101a29ef;box-shadow:0 8px 30px #0008;backdrop-filter:blur(8px)}
.refresh-badge svg{position:absolute;width:42px;height:42px;transform:rotate(-90deg)}
.ring-track,.ring-progress{fill:none;stroke-width:3.5}.ring-track{stroke:#24364b}
.ring-progress{stroke:#54d6c7;stroke-linecap:round;stroke-dasharray:100;stroke-dashoffset:0;transition:stroke-dashoffset .5s}
#refresh-time{font:600 10px ui-monospace,monospace;color:#e8f0fc}
section{background:linear-gradient(145deg,#111d2c,#0e1724);padding:16px 18px;border-radius:14px;margin:12px 0;
border:1px solid #25364b;box-shadow:0 10px 30px #0002}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px}
.card{background:#0b1420;border-radius:11px;padding:13px 14px;border:1px solid #1e3043;min-width:0}
.lbl{font-size:.75rem;color:#8b949e;text-transform:uppercase;letter-spacing:.05em}
.val{font-size:1.15rem;font-weight:600;margin-top:2px}
.moon-card{display:flex;align-items:center;gap:12px;min-height:82px}
.moon-card img{width:68px;height:68px;flex:0 0 68px;border-radius:50%;background:#03070c;
box-shadow:0 0 22px #79a9d455;border:1px solid #61778d;object-fit:cover}
.moon-title{font-size:1.05rem;font-weight:650}
.ok{color:#3fb950}.warn{color:#d29922}.muted{color:#8b949e;font-size:.85rem}
label{display:block;margin:8px 0 3px;font-size:.85rem;color:#8b949e}
input,button{font:inherit;padding:9px 12px;width:100%;box-sizing:border-box;
border-radius:6px;border:1px solid #30363d;background:#0d1117;color:#e6edf3}
button{margin-top:10px;background:#238636;color:#fff;border:none}
#msg,#wres{margin-top:8px;font-size:.85rem;color:#8b949e}
pre{white-space:pre-wrap;font-size:.85rem;color:#c9d1d9}
</style>
<div class='refresh-badge' aria-label='Sensor refresh countdown'><svg viewBox='0 0 40 40'>
<circle class='ring-track' cx='20' cy='20' r='16'/><circle id='refresh-ring' class='ring-progress' cx='20' cy='20' r='16'/></svg>
<span id='refresh-time'>--</span></div>
<header class='hero'><p class='eyebrow'>LIVE SENSOR STATION</p><h1>ESP32 Monitor</h1></header>
<section><div class='grid'>
<div class='card'><div class='lbl'>Hora local</div><div class='val' id='clock'>--</div></div>
<div class='card'><div class='lbl'>IP address</div><div class='val' id='ip'>--</div></div>
</div></section>
<section><h2>Lecturas</h2><div class='grid'>
<div class='card'><div class='lbl'>Bateria</div><div class='val' id='bat'>--</div></div>
<div class='card'><div class='lbl'>Temperatura</div><div class='val' id='temp'>--</div></div>
<div class='card'><div class='lbl'>Humedad</div><div class='val' id='hum'>--</div></div>
<div class='card'><div class='lbl'>Pressure</div><div class='val' id='pressure'>--</div></div>
<div class='card'><div class='lbl'>Latitude</div><div class='val' id='lat'>--</div></div>
<div class='card'><div class='lbl'>Longitude</div><div class='val' id='lon'>--</div></div>
<div class='card'><div class='lbl'>Weather forecast</div><div class='val' id='wx'>--</div></div>
<div class='card moon-card'><img id='moon-photo' alt='Current moon phase' src='/moon.bmp'>
<div><div class='lbl'>Lunar phase</div><div class='moon-title' id='moon'>--</div>
<div class='muted' id='moon-illum'>Moon illumination</div></div></div>
<div class='card'><div class='lbl'>Ciclo / prox.</div><div class='val' id='upd'>--</div></div>
</div></section>
<section><h2>System log</h2><pre id='events'>Waiting for events...</pre></section>
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
set('clock',d.local_time||'--');set('ip',d.wifi.ip||'192.168.4.1');
set('bat',s.battery_v.toFixed(2)+' V',s.battery_v>3.5?'ok':'warn');
set('temp',s.temperature_c!=null?s.temperature_c.toFixed(1)+' C':'--',s.temperature_c!=null?'ok':'warn');
set('hum',s.humidity_percent!=null?s.humidity_percent.toFixed(0)+' %':'--',s.humidity_percent!=null?'ok':'warn');
set('pressure',s.pressure_hpa!=null?s.pressure_hpa.toFixed(1)+' hPa':'Sensor unavailable',s.bmp280_valid?'ok':'muted');
set('lat',g.fix?g.latitude.toFixed(5):'--',g.fix?'ok':'warn');
set('lon',g.fix?g.longitude.toFixed(5):'--',g.fix?'ok':'warn');
set('wx',w.available?w.summary+' '+w.current_temperature_c.toFixed(1)+'C · '+w.minimum_temperature_c.toFixed(0)+'/'+w.maximum_temperature_c.toFixed(0)+'C · rain '+w.precipitation_probability+'%':'Sin datos',w.available?'ok':'muted');
set('moon',w.moon_phase!=null?moonName(w.moon_phase):'--');
set('moon-illum',w.moon_illumination_percent!=null?w.moon_illumination_percent+'% illuminated':'Moon data unavailable','muted');
if(w.moon_phase!=null){const k=Math.floor(w.moon_phase*255),im=document.getElementById('moon-photo');
if(im.dataset.phase!==String(k)){im.dataset.phase=String(k);im.src='/moon.bmp?v='+k;}}
document.getElementById('events').textContent=(d.events||[]).join('\\n')||'No events yet';
set('upd',rf.interval_seconds+'s / '+(rf.remaining_seconds>=0?rf.remaining_seconds+'s':'esperando'),'ok');
document.getElementById('refresh-time').textContent=rf.remaining_seconds>=0?
(String(Math.floor(rf.remaining_seconds/60)).padStart(2,'0')+':'+String(rf.remaining_seconds%60).padStart(2,'0')):'--:--';
document.getElementById('refresh-ring').style.strokeDashoffset=String(100*(1-Math.max(0,Math.min(1,rf.remaining_seconds/(rf.interval_seconds||1)))));
document.getElementById('iv').value=rf.interval_seconds;
}catch(e){}}
function set(id,v,c){const e=document.getElementById(id);e.textContent=v;e.className='val '+(c||'');}
function moonName(p){return p<.035||p>=.965?'New moon':p<.22?'Waxing crescent':p<.28?'First quarter':p<.47?'Waxing gibbous':p<.53?'Full moon':p<.72?'Waning gibbous':p<.78?'Last quarter':'Waning crescent';}
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
        "moon_phase":              w.get("moon_phase") if w.get("moon_phase_valid") else None,
        "moon_illumination_percent": w.get("moon_illumination_percent") if w.get("moon_phase_valid") else None,
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
        "pressure_hpa":     st["pressure_hpa"] if st["bmp280_valid"] else None,
        "bmp280_valid":     st["bmp280_valid"],
        "moon_phase":       st["weather"].get("moon_phase") if st["weather"].get("moon_phase_valid") else None,
        "moon_illumination_percent": st["weather"].get("moon_illumination_percent") if st["weather"].get("moon_phase_valid") else None,
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
        "events": list(_events),
        "local_time": clock_text(),
        "utc_offset_hours": config.TIMEZONE_OFFSET_HOURS,
    })


def _ble_representations(st):
    w = st["weather"]
    data = {
        "time": clock_text(), "ip": st["ip_address"], "wifi": st["wifi_connected"],
        "ssid": st["wifi_ssid"], "battery_v": round(st["battery_v"], 3),
        "temp_c": round(st["temperature_c"], 1) if st["dht_valid"] else None,
        "hum_pct": round(st["humidity_percent"], 1) if st["dht_valid"] else None,
        "pressure_hpa": round(st["pressure_hpa"], 1) if st["bmp280_valid"] else None,
        "lat": round(st["latitude"], 6) if st["gps_fix"] else None,
        "lon": round(st["longitude"], 6) if st["gps_fix"] else None,
        "forecast": w["summary"] if w["valid"] else None,
        "wx_c": w["current_temperature_c"] if w["valid"] else None,
        "wx_hum_pct": w["current_humidity_percent"] if w["valid"] else None,
        "wx_min_c": w["minimum_temperature_c"] if w["valid"] else None,
        "wx_max_c": w["maximum_temperature_c"] if w["valid"] else None,
        "rain_pct": w["precipitation_probability"] if w["valid"] else None,
        "moon": w.get("moon_phase") if w.get("moon_phase_valid") else None,
        "moon_illum_pct": w.get("moon_illumination_percent") if w.get("moon_phase_valid") else None,
        "interval_s": st["sensor_interval_s"],
        "remaining_s": max(0, st["sensor_interval_s"] - ticks_diff(ticks_ms(), st["last_read_ms"]) // 1000),
        "event": _events[-1] if _events else "none",
    }
    compact_json = json.dumps(data, separators=(",", ":"))
    text = "\n".join("%s: %s" % (k, "unavailable" if v is None else str(v)) for k, v in data.items() if k != "events")
    yaml = "\n".join("%s: %s" % (k, json.dumps(v) if isinstance(v, str) else ("null" if v is None else str(v))) for k, v in data.items())
    xml_values = " ".join("%s=\"%s\"" % (k, "" if v is None else str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&apos;")) for k, v in data.items())
    xml = "<monitor " + xml_values + "/>"
    return compact_json, text, yaml, xml


class MonitorBle:
    """Read-only snapshot GATT: one readable characteristic per wire format."""
    def __init__(self):
        if bluetooth is None:
            raise RuntimeError("MicroPython firmware lacks the bluetooth module")
        self.ble = bluetooth.BLE()
        self.ble.active(True)
        self.adv_data = bytes((2, 1, 6, 15, 9)) + b"ESP32-Monitor"
        self.ble.irq(self._irq)
        uuids = tuple(bluetooth.UUID(value) for value in (0xFFA1, 0xFFA2, 0xFFA3, 0xFFA4))
        chars = tuple((uuid, bluetooth.FLAG_READ) for uuid in uuids)
        self.handles = self.ble.gatts_register_services(((bluetooth.UUID(0xFFA0), chars),))[0]
        for handle in self.handles:
            self.ble.gatts_set_buffer(handle, 512)
        self.ble.gap_advertise(250000, adv_data=self.adv_data)
    def _irq(self, event, data):
        if event == bluetooth._IRQ_CENTRAL_DISCONNECT:
            self.ble.gap_advertise(250000, adv_data=self.adv_data)
    def update(self, st):
        for handle, value in zip(self.handles, _ble_representations(st)):
            self.ble.gatts_write(handle, value.encode()[:512])


def _sensors_json(st):
    now_ms_val = ticks_ms()
    elapsed    = ticks_diff(now_ms_val, st["last_read_ms"]) // 1000
    remaining  = max(0, st["sensor_interval_s"] - elapsed)
    return json.dumps({
        "battery_v":         round(st["battery_v"], 3),
        "temperature_c":     round(st["temperature_c"], 1) if st["dht_valid"] else None,
        "humidity_percent":  round(st["humidity_percent"], 1) if st["dht_valid"] else None,
        "dht_valid":         st["dht_valid"],
        "pressure_hpa":      st["pressure_hpa"] if st["bmp280_valid"] else None,
        "bmp280_valid":      st["bmp280_valid"],
        "moon_phase":        st["weather"].get("moon_phase") if st["weather"].get("moon_phase_valid") else None,
        "moon_illumination_percent": st["weather"].get("moon_illumination_percent") if st["weather"].get("moon_phase_valid") else None,
        "gps_fix":           st["gps_fix"],
        "latitude":          round(st["latitude"],  6) if st["gps_fix"] else None,
        "longitude":         round(st["longitude"], 6) if st["gps_fix"] else None,
        "satellites":        st["satellites"],
        "last_read_ms":      st["last_read_ms"],
        "interval_seconds":  st["sensor_interval_s"],
        "remaining_seconds": remaining,
        "events": list(_events),
        "local_time": clock_text(),
        "utc_offset_hours": config.TIMEZONE_OFFSET_HOURS,
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

    elif method == "GET" and path == "/moon.bmp":
        wx = _state["weather"]
        phase = wx.get("moon_phase") if wx.get("moon_phase_valid") else 0.0
        _send(conn, "200 OK", "image/bmp", moon_image_update(phase))

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
                              ("gps", 0x04), ("weather", 0x08),
                              ("pressure", 0x10), ("moon", 0x20)):
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
                      "pressure": bool(mask & 0x10),
                      "moon":     bool(mask & 0x20),
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
    log_event("Booting firmware")

    lcd  = make_lcd()
    i2c, oled = make_oled()
    bmp = None
    bmp_i2c = I2C(config.BMP280_I2C_ID, scl=Pin(config.BMP280_SCL_PIN),
                   sda=Pin(config.BMP280_SDA_PIN), freq=config.BMP280_I2C_FREQ)
    for address in (0x76, 0x77):
        if address in bmp_i2c.scan():
            try:
                bmp = BMP280(bmp_i2c, address)
                print("BMP280 detectado en 0x%02x" % address)
                log_event("BMP280 detected")
                break
            except OSError as exc:
                print("BMP280 no inicializado:", exc)
    if bmp is None:
        log_event("BMP280 unavailable")

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

    ble = None
    try:
        ble = MonitorBle()
        log_event("BLE GATT advertising as ESP32-Monitor")
    except Exception as e:
        print("BLE no disponible:", e)
        log_event("BLE unavailable")
    ble_last_ms = 0

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
        if _state["gps_fix"] and not _state.get("_gps_logged", False):
            log_event("GPS fix acquired")
            _state["_gps_logged"] = True
        elif not _state["gps_fix"]:
            if _state.get("_gps_logged", False):
                log_event("GPS fix lost")
            _state["_gps_logged"] = False

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
                    log_event("DHT22 read OK")
                except OSError as e:
                    print("DHT22 error:", e)
                    _state["dht_valid"] = False
                    log_event("DHT22 unavailable")

            _state["battery_v"] = read_battery_voltage(adc)
            try:
                _state["pressure_hpa"] = bmp.pressure_hpa() if bmp else None
                _state["bmp280_valid"] = _state["pressure_hpa"] is not None
                if _state["bmp280_valid"]:
                    log_event("BMP280 pressure updated")
            except OSError as exc:
                _state["bmp280_valid"] = False
                print("BMP280 read error:", exc)
                log_event("BMP280 read error")

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
            log_event("Wi-Fi connected %s" % ip)
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

        if ble is not None and ticks_diff(now, ble_last_ms) >= 2000:
            ble_last_ms = now
            try:
                ble.update(_state)
            except Exception as e:
                print("BLE snapshot update error:", e)

        sleep_ms(20)


if __name__ == "__main__":
    main()
