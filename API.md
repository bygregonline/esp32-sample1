# ESP32 Monitor — API Reference

Guía completa de endpoints HTTP disponibles en las implementaciones
**C/ESP-IDF**, **Python/MicroPython** y **Rust/ESP-IDF** del monitor.
La implementación **Rust/ESP-IDF** expone exactamente los mismos endpoints.

Reemplaza `<IP>` con la dirección IP del dispositivo.

La página en `/` actualiza estas lecturas cada dos segundos. La interfaz BLE
GATT también ofrece snapshots en JSON, texto, YAML y XML; consulta
[docs/ble.md](docs/ble.md) para los UUID y el contrato de datos.

- En red local: la que muestra el display (ej. `192.168.1.42`)
- Desde el AP de configuración: `192.168.4.1`

---

## Resumen de endpoints

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/` | Página HTML de configuración |
| GET | `/moon.bmp` | Imagen BMP de la fase lunar actual |
| GET | `/api/status` | Snapshot completo del monitor |
| GET | `/api/sensors` | Última lectura de sensores |
| GET | `/api/weather` | Solo datos de clima |
| POST | `/api/config/interval` | Cambia el ciclo de sensores |
| POST | `/api/config/display` | Oculta/muestra secciones del display |
| POST | `/wifi` | Guarda credenciales Wi-Fi |

---

## GET `/api/status`

Snapshot completo: sensores, GPS, Wi-Fi, clima y configuración.

```bash
curl http://<IP>/api/status
```

**Respuesta:**

```json
{
  "sensors": {
    "battery_v": 12.34,
    "temperature_c": 24.1,
    "humidity_percent": 55.0,
    "dht_valid": true,
    "pressure_hpa": 1013.2,
    "bmp280_valid": true,
    "moon_phase": 0.25,
    "moon_illumination_percent": 50,
    "last_read_ms": 45000
  },
  "gps": {
    "fix": true,
    "latitude": 19.4326,
    "longitude": -99.1332,
    "satellites": 9
  },
  "wifi": {
    "connected": true,
    "ssid": "MiRed",
    "ip": "192.168.1.42"
  },
  "refresh": {
    "interval_seconds": 10,
    "weather_interval_seconds": 300,
    "remaining_seconds": 7
  },
  "display_mask": 63,
  "events": ["Setup AP ready", "BMP280 pressure updated"],
  "local_time": "Tue 10 Nov 13:54",
  "weather": {
    "available": true,
    "summary": "SOLEADO",
    "weather_code": 0,
    "current_temperature_c": 22.5,
    "current_humidity_percent": 48.0,
    "minimum_temperature_c": 15.0,
    "maximum_temperature_c": 28.0,
    "precipitation_probability": 5,
    "moon_phase": 0.25,
    "moon_illumination_percent": 50,
    "age_seconds": 120,
    "stale": false
  }
}
```

---

## GET `/api/sensors`

Solo la última lectura de sensores con el tiempo restante hasta el próximo ciclo.

```bash
curl http://<IP>/api/sensors
```

**Respuesta:**

```json
{
  "battery_v": 12.34,
  "temperature_c": 24.1,
  "humidity_percent": 55.0,
  "dht_valid": true,
  "pressure_hpa": 1013.2,
  "bmp280_valid": true,
  "moon_phase": 0.25,
  "moon_illumination_percent": 50,
  "gps_fix": true,
  "latitude": 19.4326,
  "longitude": -99.1332,
  "satellites": 9,
  "last_read_ms": 45000,
  "interval_seconds": 10,
  "remaining_seconds": 7,
  "local_time": "Tue 10 Nov 13:54"
}
```

---

## GET `/api/weather`

Solo datos de pronóstico del tiempo.

```bash
curl http://<IP>/api/weather
```

**Respuesta:**

```json
{
  "available": true,
  "summary": "LLUVIA",
  "weather_code": 61,
  "current_temperature_c": 18.2,
  "current_humidity_percent": 82.0,
  "minimum_temperature_c": 14.0,
  "maximum_temperature_c": 21.0,
  "precipitation_probability": 80,
  "moon_phase": 0.75,
  "moon_illumination_percent": 50,
  "age_seconds": 45,
  "stale": false
}
```

---

## POST `/api/config/interval`

Cambia el intervalo de ciclo de sensores en tiempo real.
**Rango válido: 5 – 300 segundos.**
El cambio es inmediato: el próximo ciclo usará el nuevo intervalo.

### Cambiar a 30 segundos

```bash
curl -X POST http://<IP>/api/config/interval \
     -H "Content-Type: application/json" \
     -d '{"interval_seconds": 30}'
```

### Cambiar a 60 segundos

```bash
curl -X POST http://<IP>/api/config/interval \
     -H "Content-Type: application/json" \
     -d '{"interval_seconds": 60}'
```

### Cambiar a 5 segundos (mínimo)

```bash
curl -X POST http://<IP>/api/config/interval \
     -H "Content-Type: application/json" \
     -d '{"interval_seconds": 5}'
```

### Cambiar a 5 minutos (máximo útil)

```bash
curl -X POST http://<IP>/api/config/interval \
     -H "Content-Type: application/json" \
     -d '{"interval_seconds": 300}'
```

### Alternativa — query string

```bash
curl -X POST "http://<IP>/api/config/interval?seconds=45"
```

**Respuesta exitosa:**

```json
{ "ok": true, "interval_seconds": 30 }
```

**Respuesta con error:**

```json
{ "ok": false, "error": "interval_seconds fuera de rango (5-300)" }
```

> El display muestra el nuevo intervalo en la sección **UPDATE** inmediatamente.
> El anillo de countdown (LCD) y el texto `UPD xs  MM:SS` (OLED) se actualizan
> en el siguiente ciclo de render (≈ 1 segundo).

---

## POST `/api/config/display`

Oculta o muestra secciones del display sin reiniciar el dispositivo.
Los campos no incluidos en el body mantienen su estado actual.

### Mostrar todo

```bash
curl -X POST http://<IP>/api/config/display \
     -H "Content-Type: application/json" \
     -d '{"battery": true, "dht": true, "gps": true, "weather": true}'
```

### Ocultar GPS y clima (modo simple)

```bash
curl -X POST http://<IP>/api/config/display \
     -H "Content-Type: application/json" \
     -d '{"gps": false, "weather": false}'
```

### Solo batería y temperatura

```bash
curl -X POST http://<IP>/api/config/display \
     -H "Content-Type: application/json" \
     -d '{"battery": true, "dht": true, "gps": false, "weather": false, "pressure": false, "moon": false}'
```

### Solo GPS (modo navegación)

```bash
curl -X POST http://<IP>/api/config/display \
     -H "Content-Type: application/json" \
     -d '{"battery": false, "dht": false, "gps": true, "weather": false, "pressure": false, "moon": false}'
```

### Ocultar todo (display en blanco excepto Wi-Fi y UPDATE)

```bash
curl -X POST http://<IP>/api/config/display \
     -H "Content-Type: application/json" \
     -d '{"battery": false, "dht": false, "gps": false, "weather": false, "pressure": false, "moon": false}'
```

**Respuesta:**

```json
{
  "ok": true,
  "display_mask": 3,
  "battery": true,
  "dht": true,
  "gps": false,
  "weather": false,
  "pressure": false,
  "moon": false
}
```

> `display_mask` es el bitmask resultante:
> bit 0 = batería, bit 1 = DHT22, bit 2 = GPS, bit 3 = clima, bit 4 = presión, bit 5 = fase lunar.
> `0x3F` (63) = todo visible. `0x00` = todo oculto.

---

## POST `/wifi`

Guarda credenciales Wi-Fi y reconecta. Las credenciales se persisten en NVS
(C/Rust) o en archivo `wifi_creds.json` (Python) y sobreviven reinicios.

```bash
curl -X POST http://<IP>/wifi \
     -H "Content-Type: application/x-www-form-urlencoded" \
     -d "ssid=MiRedWiFi&password=YOUR_WIFI_PASSWORD"
```

**Respuesta (texto plano):**

```text
Guardadas. El dispositivo se reconectara.
```

> Después de guardar, el dispositivo intenta conectarse a la red indicada.
> Si la red no está disponible, lo reintentará cuando esté al alcance.
> El AP de configuración (`ESP32-Monitor-Setup`) permanece activo siempre.

---

## Flujo típico de configuración

```bash
# 1. Conectarse al AP del ESP32: "ESP32-Monitor-Setup" / "monitor1234"

# 2. Configurar la red Wi-Fi doméstica
curl -X POST http://192.168.4.1/wifi \
     -H "Content-Type: application/x-www-form-urlencoded" \
     -d "ssid=MiRed&password=MiClave"

# 3. Esperar ~10s y verificar que se conectó (la IP aparece en el display)
curl http://192.168.1.42/api/status | python3 -m json.tool

# 4. Ajustar ciclo de sensores a 20 segundos
curl -X POST http://192.168.1.42/api/config/interval \
     -H "Content-Type: application/json" \
     -d '{"interval_seconds": 20}'

# 5. Verificar lectura actual
curl http://192.168.1.42/api/sensors

# 6. Ver el clima
curl http://192.168.1.42/api/weather

# 7. Configurar display para modo compacto (sin clima, sin GPS)
curl -X POST http://192.168.1.42/api/config/display \
     -H "Content-Type: application/json" \
     -d '{"battery": true, "dht": true, "gps": false, "weather": false}'
```

---

## Monitoreo continuo con watch

```bash
# Actualizar cada 5 segundos
watch -n 5 'curl -s http://<IP>/api/sensors | python3 -m json.tool'

# Solo temperatura y batería
watch -n 10 'curl -s http://<IP>/api/sensors | python3 -c \
  "import json,sys; d=json.load(sys.stdin); \
   print(\"Bat:\", d[\"battery_v\"], \"V | T:\", d[\"temperature_c\"], \"C\")"'
```

---

## Página web

Abre en el navegador:

```text
http://<IP>/
```

Muestra tarjetas con todas las lecturas actualizadas cada 2 s, un campo para
cambiar el intervalo de ciclo, y un formulario para configurar Wi-Fi.
