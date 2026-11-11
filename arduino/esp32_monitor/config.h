#pragma once

// ESP32-S3 DevKitC-1 compatible, módulo N16R8 (16 MB flash, 8 MB PSRAM).

// LCD Waveshare 170x320 ST7789V2 por SPI
#define LCD_SCK_PIN 12
#define LCD_MOSI_PIN 11
#define LCD_CS_PIN 10
#define LCD_DC_PIN 13
#define LCD_RST_PIN 14
#define LCD_WIDTH 170
#define LCD_HEIGHT 320
#define LCD_X_OFFSET 35
#define LCD_Y_OFFSET 0

// OLED SSD1306 128x64 por I2C
#define OLED_SDA_PIN 8
#define OLED_SCL_PIN 9
#define OLED_I2C_ADDRESS 0x3C
#define OLED_WIDTH 128
#define OLED_HEIGHT 64

// Sensores
#define DHT_PIN 6
#define GPS_RX_PIN 18
#define GPS_TX_PIN 17
#define GPS_BAUD_RATE 9600
#define VOLTAGE_ADC_PIN 4

// Módulo de voltaje 0-25 V y divisor externo de 12 kΩ / 10 kΩ.
#define VOLTAGE_SENSOR_RATIO 5.0f
#define ADC_EXTERNAL_DIVIDER_RATIO 2.2f
#define VOLTAGE_CALIBRATION 1.0f

#define DHT_READ_INTERVAL_MS 2500UL
#define DISPLAY_UPDATE_INTERVAL_MS 1000UL
#define GPS_FIX_TIMEOUT_MS 5000UL
