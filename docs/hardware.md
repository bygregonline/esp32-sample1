# Hardware and wiring

The ESP32 DevKit/WROOM-32 reads a DHT22, NEO-6M GPS, and a 0–25 V battery voltage module. It drives a 170 × 320 ST7789V2 color LCD and a 128 × 64 SSD1306 OLED.

## Breadboard assembly

![ESP32 between two breadboard sections](visuals/diagrama-conexiones-esp32-protoboard.png)

The two breadboard sections keep equal-numbered rows isolated. Power rails connect vertically; each five-hole strip connects horizontally. Colored jumpers join the sides only at the shown endpoints.

## Wiring overview

![ESP32 wiring overview](visuals/diagrama-conexiones-esp32.png)

The voltage module's `S` output passes through a 12 kΩ resistor before GPIO34. A 10 kΩ resistor connects the GPIO34 node to ground. The DHT22 DATA line has a 4.7 kΩ pull-up to 3V3 when the sensor module does not include one.

## Display layout

![LCD and OLED display preview](visuals/mockup-displays-esp32.png)

See the [pin map and exact breadboard rows](https://github.com/bygregonline/esp32-sample1#pin-map) in the repository README before assembling hardware.
