"""Pin configuration for ESP32-S3 DevKitC-1 compatible N16R8 board."""

# Offset local de Mexico Central respecto a UTC. Ajustar en instalaciones distintas.
TIMEZONE_OFFSET_HOURS = -6

# LCD Waveshare 1.9in, ST7789V2, SPI
LCD_SPI_ID       = 1
LCD_SCK_PIN      = 12
LCD_MOSI_PIN     = 11
LCD_CS_PIN       = 10
LCD_DC_PIN       = 13
LCD_RST_PIN      = 14
LCD_BL_PIN       = None   # BL directo a 3V3
LCD_SPI_BAUDRATE = 20_000_000
LCD_WIDTH        = 170
LCD_HEIGHT       = 320
LCD_X_OFFSET     = 35
LCD_Y_OFFSET     = 0

# OLED SSD1306 128x64, I2C
OLED_SDA_PIN     = 8
OLED_SCL_PIN     = 9
OLED_I2C_ID      = 0
OLED_I2C_FREQ    = 400_000
OLED_I2C_ADDRESS = 0x3C

# BMP280 on a separate I2C controller/bus
BMP280_I2C_ID      = 1
BMP280_SDA_PIN     = 1
BMP280_SCL_PIN     = 2
BMP280_I2C_FREQ    = 400_000
OLED_WIDTH       = 128
OLED_HEIGHT      = 64

# Sensores
DHT_PIN          = 6
GPS_UART_ID      = 2
GPS_RX_PIN       = 18
GPS_TX_PIN       = 17
GPS_BAUDRATE     = 9600
VOLTAGE_ADC_PIN  = 4

# Divisor de voltaje
VOLTAGE_SENSOR_RATIO       = 5.0
ADC_EXTERNAL_DIVIDER_RATIO = 2.2
VOLTAGE_CALIBRATION        = 1.0

# Intervalos
DHT_READ_INTERVAL_MS       = 2500
DISPLAY_UPDATE_INTERVAL_MS = 1000
SENSOR_INTERVAL_DEFAULT_S  = 10
SENSOR_INTERVAL_MIN_S      = 5
SENSOR_INTERVAL_MAX_S      = 300
WEATHER_REFRESH_INTERVAL_S = 300

# Wi-Fi de configuración
PORTAL_SSID      = "ESP32-Monitor-Setup"
PORTAL_AP_CODE   = "monitor1234"
WEB_SERVER_PORT  = 80
