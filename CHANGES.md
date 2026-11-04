# ESP32 Monitor — Registro de cambios

Resumen completo de todo lo implementado en esta sesión.
Fuente de verdad: **C/ESP-IDF**. Replicado a **Python/MicroPython** y **Rust/ESP-IDF (std)**.

---

## 1. C/ESP-IDF (`c/`)

### `monitor_state.h` / `monitor_state.c`

- Campo `sensor_interval_seconds` — intervalo de ciclo de sensores (default 10 s, rango 5–300 s).
- Campo `last_sensor_read_ms` — timestamp de la última lectura para calcular countdown.
- Campo `display_fields_mask` — bitmask de visibilidad de secciones en ambos displays:
  - `bit 0` = batería, `bit 1` = DHT22, `bit 2` = GPS, `bit 3` = clima
- `monitor_state_set_sensor_interval()` — valida y aplica el nuevo intervalo.
- `monitor_state_set_display_mask()` — actualiza la máscara de visibilidad.
- `monitor_state_set_sensors()` ahora recibe `now_ms` para registrar timestamp.

### `main.c`

- El bucle respeta `sensor_interval_seconds`: solo lee DHT22 y ADC cuando toca.
- DHT22 mantiene su restricción interna de mínimo 2.5 s entre lecturas.
- Log incluye el ciclo activo en segundos.

### `display.c` — Layout rediseñado

**LCD 170×320 (separadores + paleta de colores consistente):**

| y (px) | Contenido | Color |
|--------|-----------|-------|
| 4 | ESP32 MONITOR | Azul claro |
| 14 | ─── separador | Gris |
| 20 | WIFI ssid  ip | Verde / Amarillo |
| 36 | BAT x.xxV | Verde/Amarillo |
| 46 | ─── separador | |
| 52 | TEMP xx.xC   HUM xx% | Cian + Blanco |
| 62 | ─── separador | |
| 68 | GPS FIX SAT n / BUSCANDO | Verde/Amarillo |
| 80 | LAT xx.xxxxx | Blanco |
| 92 | LON xx.xxxxx | Blanco |
| 104 | ─── separador | |
| 110 | CLIMA | Cian |
| 122 | resumen xx.xC | Naranja |
| 134 | MIN / MAX °C | Blanco |
| 146 | LLUVIA xx% | Amarillo |
| 158 | ─── separador | |
| 164 | UPDATE xxs   PROX MM:SS | Cian + Verde/Amarillo |
| 220 | Anillo de countdown (radio 38) | Verde→Amarillo→Rojo |

**OLED 128×64:**

| px | Contenido |
|----|-----------|
| 0 | WIFI OK / WIFI CONFIG |
| 8 | BAT x.xxV |
| 16 | T xx.xC H xx% |
| 24 | LAT x.xxxx |
| 32 | LON x.xxxx |
| 40 | clima resumen xxC |
| 48 | MIN/MAX/P% |
| 56 | UPD xxs  MM:SS |

Ambos displays respetan `display_fields_mask`.

### `network.c` — Nuevos endpoints

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/` | Página HTML (tarjetas + control ciclo + Wi-Fi form) |
| GET | `/api/status` | Snapshot completo |
| GET | `/api/sensors` | **Nuevo** — última lectura de sensores |
| GET | `/api/weather` | Solo datos de clima |
| POST | `/api/config/interval` | **Nuevo** — cambia ciclo 5–300 s |
| POST | `/api/config/display` | **Nuevo** — oculta/muestra secciones |
| POST | `/wifi` | Guarda credenciales Wi-Fi en NVS |

---

## 2. Python/MicroPython (`python/`) — Paridad completa con C

### `config.py`

Nuevas constantes: `SENSOR_INTERVAL_DEFAULT_S`, `SENSOR_INTERVAL_MIN_S`, `SENSOR_INTERVAL_MAX_S`, `WEATHER_REFRESH_INTERVAL_S`, `PORTAL_SSID`, `PORTAL_PASSWORD`, `WEB_SERVER_PORT`.

### `main.py` — Reescrito con paridad total

- **Wi-Fi STA + AP** simultáneos (`network.WLAN`). AP siempre activo como portal de configuración.
- **NTP** via `ntptime.settime()` al conectar.
- **Clima Open-Meteo** via `urequests` con HTTPS. Misma lógica de refresco que C: cada 300 s o si el GPS se mueve > 0.005°.
- **Servidor HTTP** no bloqueante (`usocket`), mismos 7 endpoints que C.
- **Estado global** `_state` centraliza todos los valores, mutable en runtime.
- Credenciales Wi-Fi persistidas en `wifi_creds.json`.
- Display LCD y OLED con mismo layout que C, respeta `display_mask`.
- Ciclo de sensores respeta `sensor_interval_s` configurable por API.

---

## 3. Rust — Migración completa a `std` / ESP-IDF

### Arquitectura anterior (abandonada)

`no_std` + `esp-hal` → sin Wi-Fi, sin HTTP, sin TLS, sin std.

### Arquitectura nueva

`std` + `esp-idf-svc` → paridad completa con C.

### Archivos nuevos/reescritos

| Archivo | Descripción |
|---------|-------------|
| `Cargo.toml` | Migrado a `esp-idf-svc`, `esp-idf-sys`, `embedded-svc` |
| `.cargo/config.toml` | Target `xtensa-esp32-espidf` (std) |
| `build.rs` | `embuild::espidf::sysenv::output()` |
| `src/monitor_state.rs` | Equivalente a `monitor_state.h/c` — `Arc<Mutex<MonitorData>>` |
| `src/weather.rs` | Tarea de clima en thread separado, fetch HTTPS a Open-Meteo |
| `src/network.rs` | Wi-Fi AP+STA, NVS, servidor HTTP, todos los endpoints |
| `src/display.rs` | Render LCD y OLED con mismo layout y colores que C |
| `src/main.rs` | Bucle principal con std, FreeRTOS threads, misma lógica que C |
| `src/gps.rs` | Sin cambios (parser NMEA ya funcionaba) |

### Paridad de endpoints Rust vs C

| Endpoint | C | Python | Rust |
|----------|---|--------|------|
| GET `/api/status` | ✅ | ✅ | ✅ |
| GET `/api/sensors` | ✅ | ✅ | ✅ |
| GET `/api/weather` | ✅ | ✅ | ✅ |
| POST `/api/config/interval` | ✅ | ✅ | ✅ |
| POST `/api/config/display` | ✅ | ✅ | ✅ |
| POST `/wifi` | ✅ | ✅ | ✅ |
| GET `/` (HTML) | ✅ | ✅ | ✅ |

---

## 4. Paridad completa entre las tres implementaciones

| Feature | C | Python | Rust |
|---------|---|--------|------|
| DHT22 (temperatura/humedad) | ✅ | ✅ | ✅ |
| GPS NEO-6M (NMEA RMC+GGA) | ✅ | ✅ | ✅ |
| ADC batería (8 muestras) | ✅ | ✅ | ✅ |
| LCD ST7789V2 render | ✅ | ✅ | ✅ |
| OLED SSD1306 render | ✅ | ✅ | ✅ |
| Layout idéntico con separadores | ✅ | ✅ | ✅ |
| Paleta de colores consistente | ✅ | ✅ | ✅ |
| Countdown UPDATE en display | ✅ anillo+texto | ✅ texto | ✅ texto |
| display_fields_mask | ✅ | ✅ | ✅ |
| Ciclo de sensores configurable | ✅ | ✅ | ✅ |
| Wi-Fi AP+STA | ✅ APSTA | ✅ dual WLAN | ✅ Mixed |
| Credenciales persistentes | ✅ NVS | ✅ JSON file | ✅ NVS |
| NTP / SNTP | ✅ | ✅ | ✅ |
| Servidor HTTP | ✅ | ✅ usocket | ✅ |
| Open-Meteo HTTPS | ✅ | ✅ urequests | ✅ |
| JSON idéntico `/api/status` | ✅ | ✅ | ✅ |
| GET `/api/sensors` | ✅ | ✅ | ✅ |
| POST `/api/config/interval` | ✅ | ✅ | ✅ |
| POST `/api/config/display` | ✅ | ✅ | ✅ |

---

## 5. API.md

Creado `API.md` en la raíz con la referencia completa de curl:

- Todos los endpoints con ejemplos
- Flujo completo de configuración desde cero
- Monitoreo continuo con `watch`
- Descripción exacta de cada campo JSON de respuesta
