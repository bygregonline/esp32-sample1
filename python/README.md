# Monitor ESP32 con MicroPython

Proyecto para un ESP32 DevKit/WROOM-32 que presenta voltaje de batería, temperatura, humedad y posición GPS en dos pantallas:

- Waveshare LCD de 1.9 pulgadas, 170 × 320, ST7789V2 por SPI.
- OLED de 0.96 pulgadas, 128 × 64, SSD1306 por I2C.

Los controladores de pantalla y el parser GPS están incluidos. No hay paquetes de terceros que instalar en la placa.

## Pines predeterminados

Los pines corresponden a un ESP32 DevKit/WROOM-32 común. Si tu placa es otra variante, revisa su pinout y cambia `config.py`.

| Módulo | Pin del módulo | ESP32 |
|---|---|---|
| LCD Waveshare | DIN / MOSI | GPIO23 |
| LCD Waveshare | CLK / SCK | GPIO18 |
| LCD Waveshare | CS | GPIO13 |
| LCD Waveshare | DC | GPIO27 |
| LCD Waveshare | RST | GPIO26 |
| LCD Waveshare | BL | 3V3 (luz fija) |
| LCD Waveshare | VCC / GND | 3V3 / GND |
| OLED SSD1306 | SDA / SCL | GPIO21 / GPIO22 |
| OLED SSD1306 | VCC / GND | 3V3 / GND |
| DHT22 | DATA | GPIO33 |
| DHT22 | VCC / GND | 3V3 / GND |
| GPS NEO-6M | TX | GPIO16 (RX del ESP32) |
| GPS NEO-6M | RX (opcional) | GPIO17 (TX del ESP32) |
| GPS NEO-6M | VCC / GND | Según el módulo / GND común |
| Sensor de voltaje | S / salida analógica | A través del divisor adicional a GPIO34 |

El ESP32, el GPS y los sensores deben compartir GND. El pin TX del GPS se conecta al RX del ESP32, y viceversa. Para recibir coordenadas basta conectar TX del GPS a GPIO16; RX del GPS puede quedar desconectado.

## Conexión segura del sensor de voltaje

El módulo económico típico de 0–25 V usa un divisor 5:1. Eso puede producir 5 V en su salida analógica al medir 25 V; el GPIO del ESP32 no admite esa tensión. El proyecto agrega un segundo divisor para limitar la entrada ADC a unos 2.27 V con 25 V en la batería:

1. Batería positiva y negativa a las entradas `IN+` e `IN-` del módulo medidor.
2. Salida `S` del medidor a una resistencia de **12 kΩ**.
3. El otro extremo de 12 kΩ va al nodo de GPIO34.
4. Conecta una resistencia de **10 kΩ** entre GPIO34 y GND.
5. Une el GND del medidor, del divisor y del ESP32.
6. Si el conector de tres pines del medidor tiene `+`, `-` y `S`, conecta `-` a GND y `+` a 3V3 cuando el modelo lo requiera; `S` es la señal medida.

Comprueba el pinout de tu placa de voltaje antes de alimentarlo: existen variantes. No conectes directamente la batería ni una salida de 5 V al GPIO34. Si la batería puede superar 25 V, este divisor no es adecuado. La lectura se calibra con `VOLTAGE_CALIBRATION` en `config.py` comparándola con un multímetro.

El módulo medidor solo mide; no alimenta al ESP32. Alimenta el ESP32 desde la batería con un regulador DC-DC apropiado para la entrada de tu placa. Nunca conectes una batería directamente al pin 3V3.

## DHT22 y GPS

El DHT22 se consulta cada 2.5 segundos, como requiere este sensor. En un DHT22 sin placa adaptadora, agrega una resistencia pull-up de 4.7–10 kΩ entre DATA y 3V3. Muchos módulos de tres pines ya la incluyen.

El GPS NEO-6M usa UART2 a 9600 baudios, una configuración común de fábrica. La primera posición puede tardar y la antena suele necesitar vista despejada del cielo. Hasta que haya una posición reciente, ambas pantallas indican que el GPS está buscando señal.

## Preparar y cargar por CLI

1. Instala firmware MicroPython para tu modelo exacto de ESP32 si todavía no lo tiene. `dht`, `framebuf` y `machine` deben estar disponibles en el firmware.
2. Crea el entorno local con Python 3.12 e instala `mpremote` usando `uv`:

   ```sh
   ./scripts/install-deps.sh
   ```

3. Conecta la placa por USB y revisa el puerto con `mpremote connect list`.
4. Desde esta carpeta, prepara el paquete e instala los archivos en la placa:

   ```sh
   ./scripts/build.sh
   ./scripts/deploy.sh
   ```

`install-deps.sh` ejecuta `uv sync --project .. --python 3.12`; crea el entorno compartido en la raíz del repositorio (`.venv/`) y usa el `pyproject.toml` y `uv.lock` que también están en la raíz. Las dependencias host (por ahora `mpremote`) se instalan ahí; el firmware MicroPython de la placa solo usa módulos incluidos (`machine`, `dht`, etc.). `build.sh` reúne los módulos en `dist/esp32-monitor-python/`; MicroPython es interpretado, así que ese paquete es el artefacto de despliegue y no un ejecutable nativo. `deploy.sh` usa `mpremote` para copiar los archivos y reiniciar la placa. De forma predeterminada selecciona el primer dispositivo detectado. Para elegir uno, define `ESP32_PORT`, por ejemplo `ESP32_PORT=port:/dev/cu.usbserial-0001 ./scripts/deploy.sh`.

La placa ejecutará `main.py` al arrancar. Para ver mensajes y abrir la consola serial:

```sh
mpremote connect auto repl
```

Si tienes más de un dispositivo serial, cambia `auto` por el puerto indicado por `mpremote connect list`, por ejemplo `port:/dev/ttyUSB0`.

## Ajustes

- Cambia pines, dirección I2C y factores del divisor en `config.py`.
- El OLED se busca en `0x3C`; muchas placas también permiten `0x3D`.
- El área visible del LCD 170 × 320 empieza en el desplazamiento X 35 del controlador; si tu revisión muestra imagen corrida, ajusta `LCD_X_OFFSET`.
- La precisión del ADC varía entre placas. Ajusta `VOLTAGE_CALIBRATION` con una medición real.
