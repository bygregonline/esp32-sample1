#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <Arduino_GFX_Library.h>
#include <DHT.h>
#include <TinyGPS++.h>
#include <Wire.h>

#include <math.h>
#include <stdio.h>

#include "config.h"

constexpr uint16_t COLOR_BLACK = 0x0000;
constexpr uint16_t COLOR_WHITE = 0xFFFF;
constexpr uint16_t COLOR_CYAN = 0x07FF;
constexpr uint16_t COLOR_GREEN = 0x07E0;
constexpr uint16_t COLOR_YELLOW = 0xFFE0;

Arduino_DataBus *lcdBus = new Arduino_ESP32SPI(
    LCD_DC_PIN, LCD_CS_PIN, LCD_SCK_PIN, LCD_MOSI_PIN, GFX_NOT_DEFINED);
Arduino_GFX *lcd = new Arduino_ST7789(
    lcdBus, LCD_RST_PIN, 0, true, LCD_WIDTH, LCD_HEIGHT,
    LCD_X_OFFSET, LCD_Y_OFFSET, LCD_X_OFFSET, LCD_Y_OFFSET);

Adafruit_SSD1306 oled(OLED_WIDTH, OLED_HEIGHT, &Wire, -1);
DHT dht(DHT_PIN, DHT22);
HardwareSerial gpsSerial(1);
TinyGPSPlus gps;

bool oledAvailable = false;
float temperatureC = NAN;
float humidityPercent = NAN;
float batteryVoltage = 0.0f;
uint32_t lastDhtReadMs = 0;
uint32_t lastDisplayUpdateMs = 0;

bool i2cDevicePresent(uint8_t address) {
    Wire.beginTransmission(address);
    return Wire.endTransmission() == 0;
}

float readBatteryVoltage() {
    constexpr int samples = 8;
    uint32_t millivoltsTotal = 0;

    for (int i = 0; i < samples; ++i) {
        millivoltsTotal += analogReadMilliVolts(VOLTAGE_ADC_PIN);
        delay(2);
    }

    const float adcVolts = millivoltsTotal / (1000.0f * samples);
    return adcVolts * ADC_EXTERNAL_DIVIDER_RATIO * VOLTAGE_SENSOR_RATIO *
           VOLTAGE_CALIBRATION;
}

bool gpsHasRecentFix() {
    return gps.location.isValid() && gps.location.age() < GPS_FIX_TIMEOUT_MS;
}

void drawLcdLine(const char *text, int16_t y, uint16_t color) {
    lcd->setTextColor(color);
    lcd->setCursor(4, y);
    lcd->print(text);
}

void renderLcd() {
    lcd->fillScreen(COLOR_BLACK);
    lcd->setTextSize(1);
    drawLcdLine("ESP32 - TELEMETRIA", 4, COLOR_WHITE);
    drawLcdLine("BATERIA", 24, COLOR_CYAN);

    char line[32];
    snprintf(line, sizeof(line), "%.2f V", batteryVoltage);
    drawLcdLine(line, 36, batteryVoltage > 0.0f ? COLOR_GREEN : COLOR_YELLOW);

    drawLcdLine("TEMPERATURA / HUMEDAD", 64, COLOR_CYAN);
    if (isnan(temperatureC) || isnan(humidityPercent)) {
        drawLcdLine("DHT22: --", 76, COLOR_YELLOW);
    } else {
        snprintf(line, sizeof(line), "Temp: %.1f C", temperatureC);
        drawLcdLine(line, 76, COLOR_WHITE);
        snprintf(line, sizeof(line), "Hum:  %.1f %%", humidityPercent);
        drawLcdLine(line, 88, COLOR_WHITE);
    }

    drawLcdLine("GPS / COORDENADAS", 120, COLOR_CYAN);
    if (gpsHasRecentFix()) {
        drawLcdLine("FIX: SI", 132, COLOR_GREEN);
        snprintf(line, sizeof(line), "LAT: %.6f", gps.location.lat());
        drawLcdLine(line, 144, COLOR_WHITE);
        snprintf(line, sizeof(line), "LON: %.6f", gps.location.lng());
        drawLcdLine(line, 156, COLOR_WHITE);
        if (gps.satellites.isValid()) {
            snprintf(line, sizeof(line), "SAT: %lu",
                     static_cast<unsigned long>(gps.satellites.value()));
        } else {
            snprintf(line, sizeof(line), "SAT: --");
        }
        drawLcdLine(line, 168, COLOR_WHITE);
    } else {
        drawLcdLine("GPS: BUSCANDO SENAL", 132, COLOR_YELLOW);
        drawLcdLine("LAT: --", 144, COLOR_WHITE);
        drawLcdLine("LON: --", 156, COLOR_WHITE);
    }
}

void renderOled() {
    if (!oledAvailable) {
        return;
    }

    oled.clearDisplay();
    oled.setTextSize(1);
    oled.setTextColor(SSD1306_WHITE);
    oled.setCursor(0, 0);
    oled.println("ESP32 TELEMETRIA");

    char line[32];
    snprintf(line, sizeof(line), "BAT %.2f V", batteryVoltage);
    oled.setCursor(0, 10);
    oled.println(line);

    oled.setCursor(0, 20);
    if (isnan(temperatureC) || isnan(humidityPercent)) {
        oled.println("DHT22: --");
    } else {
        snprintf(line, sizeof(line), "T %.1fC H %.0f%%", temperatureC,
                 humidityPercent);
        oled.println(line);
    }

    if (gpsHasRecentFix()) {
        oled.setCursor(0, 32);
        oled.println("GPS: FIX");
        snprintf(line, sizeof(line), "LAT %.4f", gps.location.lat());
        oled.setCursor(0, 42);
        oled.println(line);
        snprintf(line, sizeof(line), "LON %.4f", gps.location.lng());
        oled.setCursor(0, 52);
        oled.println(line);
    } else {
        oled.setCursor(0, 32);
        oled.println("GPS: BUSCANDO");
        oled.setCursor(0, 42);
        oled.println("LAT --");
        oled.setCursor(0, 52);
        oled.println("LON --");
    }
    oled.display();
}

void readDhtIfDue(uint32_t nowMs) {
    if (nowMs - lastDhtReadMs < DHT_READ_INTERVAL_MS) {
        return;
    }

    lastDhtReadMs = nowMs;
    const float newHumidity = dht.readHumidity();
    const float newTemperature = dht.readTemperature();
    if (isnan(newHumidity) || isnan(newTemperature)) {
        temperatureC = NAN;
        humidityPercent = NAN;
        Serial.println("Error leyendo DHT22");
        return;
    }

    temperatureC = newTemperature;
    humidityPercent = newHumidity;
}

void setup() {
    Serial.begin(115200);
    delay(300);
    Serial.println("Iniciando monitor ESP32 con Arduino");

    if (!lcd->begin()) {
        Serial.println("No se pudo iniciar el LCD ST7789");
        while (true) {
            delay(1000);
        }
    }
    lcd->setRotation(0);
    lcd->fillScreen(COLOR_BLACK);

    Wire.begin(OLED_SDA_PIN, OLED_SCL_PIN);
    Wire.setClock(400000);
    if (i2cDevicePresent(OLED_I2C_ADDRESS)) {
        oledAvailable = oled.begin(SSD1306_SWITCHCAPVCC, OLED_I2C_ADDRESS,
                                   true, false);
    }
    if (!oledAvailable) {
        Serial.println("OLED no encontrado; se continúa con el LCD");
    }

    dht.begin();
    gpsSerial.begin(GPS_BAUD_RATE, SERIAL_8N1, GPS_RX_PIN, GPS_TX_PIN);

    analogReadResolution(12);
    analogSetPinAttenuation(VOLTAGE_ADC_PIN, ADC_11db);

    lastDhtReadMs = millis() - DHT_READ_INTERVAL_MS;
    lastDisplayUpdateMs = millis() - DISPLAY_UPDATE_INTERVAL_MS;
}

void loop() {
    while (gpsSerial.available() > 0) {
        gps.encode(gpsSerial.read());
    }

    const uint32_t nowMs = millis();
    readDhtIfDue(nowMs);

    if (nowMs - lastDisplayUpdateMs >= DISPLAY_UPDATE_INTERVAL_MS) {
        lastDisplayUpdateMs = nowMs;
        batteryVoltage = readBatteryVoltage();
        renderLcd();
        renderOled();

        Serial.printf("Bateria: %.2f V | T: %.1f C | H: %.1f %% | GPS fix: %s\n",
                      batteryVoltage, temperatureC, humidityPercent,
                      gpsHasRecentFix() ? "si" : "no");
    }

    delay(10);
}
