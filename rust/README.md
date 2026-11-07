# Firmware Rust para ESP32

Versión Rust del monitor de batería, DHT22 y GPS para las pantallas Waveshare ST7789V2 170 × 320 y SSD1306 128 × 64. Está configurada para el chip **ESP32 clásico** de una placa DevKit/WROOM-32 y usa ESP-IDF con Rust `std` mediante `esp-idf-svc`.

## Diagramas y pantallas

### Montaje con protoboard

![Montaje del ESP32 centrado entre dos secciones de protoboard](../docs/visuals/diagrama-conexiones-esp32-protoboard.png)

### Diagrama general de conexiones

![Diagrama de conexiones del ESP32](../docs/visuals/diagrama-conexiones-esp32.png)

### Vista de las pantallas

![Vista esperada de las pantallas LCD y OLED](../docs/visuals/mockup-displays-esp32.png)

El montaje muestra las pantallas a la izquierda del ESP32 y los sensores a la derecha. El [README principal](../README.md#wiring-diagrams-and-display-mockup) describe las filas y resistencias; los GPIO de esta versión se declaran en `src/main.rs`.

## Pines

| Función | GPIO |
|---|---:|
| LCD SPI SCK / MOSI | 18 / 23 |
| LCD CS / DC / RST | 13 / 27 / 26 |
| LCD BL | 3V3, luz fija |
| OLED I2C SDA / SCL | 21 / 22 |
| DHT22 DATA | 33 |
| GPS UART RX / TX | 16 / 17 |
| Voltaje ADC1 | 34 |

El GPS se configura a 9600 baudios. El OLED usa I2C `0x3C`; el LCD usa un desplazamiento X de 35 píxeles.

## Documentación

Desde la raíz del repositorio, `./scripts/build_docs.sh` genera el sitio MkDocs. Para añadir la referencia nativa de los módulos Rust, ejecuta `./scripts/build_docs.sh --rust-api`; usa `cargo doc` y requiere el entorno Xtensa preparado por `rust/scripts/install-deps.sh`. El HTML queda en `site/api/rust/` y se ignora en Git.

## Entrada de batería

El módulo típico 0–25 V entrega hasta 5 V en su salida. Para limitar la entrada del ESP32, conecta `S` del módulo a GPIO34 mediante una resistencia de 12 kΩ y conecta otra resistencia de 10 kΩ entre GPIO34 y GND. Comparte GND entre ESP32, sensor de voltaje y batería. El cálculo usa la relación 5:1 del módulo más el divisor adicional 12 kΩ/10 kΩ; calibra `VOLTAGE_CALIBRATION` en `src/main.rs` con multímetro. No conectes la batería directamente al GPIO ni al pin 3V3.

## TensorFlow Lite Micro: prueba float32

Rust ejecuta el mismo modelo de demostración `hello_world` que C mediante el componente nativo compartido [`components/tflm_demo/`](../components/tflm_demo/). Usamos TensorFlow Lite Micro para ejercitar inferencia `float32` en el CPU/FPU del ESP32 clásico. Este chip tiene FPU, no TPU; la prueba valida la integración del runtime, no es una prueba de TPU ni un benchmark. El modelo aproxima `sin(x)`; el firmware normaliza temperatura y humedad del DHT22 y las ejecuta en llamadas separadas. Si el DHT22 no está disponible, usa el voltaje de batería. Las predicciones aparecen en el monitor serial bajo `TFLM demo`; no son pronósticos ambientales ni alteran el API.

El proyecto Rust declara el componente compartido en `Cargo.toml`; ESP-IDF Component Manager descarga `espressif/esp-tflite-micro` al compilar. La interfaz C se consume mediante FFI desde [`src/ml_demo.rs`](src/ml_demo.rs).

## Compilar y desplegar

Para este chip Xtensa se requiere el compilador de Espressif, instalado por `espup`, además de `espflash` y `ldproxy` para generar y cargar una imagen. El proyecto usa ESP-IDF 5.4.2, igual que la versión C. La herramienta oficial se configura desde la [guía Rust on ESP](https://docs.espressif.com/projects/rust/book/getting-started/toolchain.html). Ejecuta el script una vez en la computadora de desarrollo; instala las herramientas en el perfil de usuario con Cargo y descarga las crates declaradas en `Cargo.toml`:

```sh
./scripts/install-deps.sh
```

El script genera el archivo de entorno como `rust/export-esp.sh`, lo ignora en Git y lo carga automáticamente al compilar. En otras terminales puedes cargarlo manualmente con `. ./export-esp.sh` desde `rust/`.

## Actualizar dependencias

Desde `rust/`, ejecuta `./scripts/update-deps.sh` para actualizar las crates permitidas por `Cargo.toml` y descargar las versiones resueltas. El script actualiza `Cargo.lock`; revisa ese diff y compila después con `./scripts/build.sh`. Las versiones de componentes ESP-IDF se resuelven aparte desde `components/tflm_demo/idf_component.yml` y se fijan en `components_esp32.lock`.

## Compilar sin placa y cargar cuando esté disponible

Desde `rust/`, ejecuta:

```sh
./scripts/build.sh
```

El ELF queda en `target/xtensa-esp32-espidf/release/esp32-monitor-rust` y la imagen de aplicación queda en `firmware.bin`. No hace falta conectar la placa para compilarlos. Cuando esté conectada por USB, ejecuta `./scripts/deploy.sh`. Para fijar el puerto serial, usa `ESP32_PORT=/dev/cu.usbserial-0001 ./scripts/deploy.sh`. El script vuelve a compilar y flashea el ELF con `espflash`; `firmware.bin` queda como artefacto separado para transferir o archivar. La referencia del flasher está en la [guía oficial de espflash](https://docs.espressif.com/projects/rust/book/getting-started/tooling/espflash.html).
