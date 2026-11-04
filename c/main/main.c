#include <math.h>
#include <stdio.h>
#include <string.h>

#include "config.h"
#include "display.h"
#include "driver/gpio.h"
#include "driver/uart.h"
#include "esp_adc/adc_cali.h"
#include "esp_adc/adc_cali_scheme.h"
#include "esp_adc/adc_oneshot.h"
#include "esp_check.h"
#include "esp_err.h"
#include "esp_log.h"
#include "esp_rom_sys.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "gps.h"
#include "monitor_state.h"
#include "network.h"

static const char *TAG = "monitor";

typedef struct {
    float temperature;
    float humidity;
} dht_reading_t;

/* ── DHT22 bit-bang ─────────────────────────────────────────────────────── */

static bool wait_level(int level, int64_t timeout_us) {
    const int64_t start = esp_timer_get_time();
    while (gpio_get_level(DHT_GPIO) != level) {
        if (esp_timer_get_time() - start >= timeout_us) {
            return false;
        }
    }
    return true;
}

static esp_err_t dht_read(dht_reading_t *reading) {
    gpio_set_direction(DHT_GPIO, GPIO_MODE_OUTPUT_OD);
    gpio_set_level(DHT_GPIO, 0);
    esp_rom_delay_us(1200);
    gpio_set_level(DHT_GPIO, 1);
    esp_rom_delay_us(30);
    gpio_set_direction(DHT_GPIO, GPIO_MODE_INPUT_OUTPUT_OD);

    if (!wait_level(0, 120) || !wait_level(1, 120) || !wait_level(0, 120)) {
        return ESP_ERR_TIMEOUT;
    }

    uint8_t bytes[5] = {0};
    for (int bit = 0; bit < 40; ++bit) {
        if (!wait_level(1, 100)) {
            return ESP_ERR_TIMEOUT;
        }
        const int64_t high_start = esp_timer_get_time();
        if (!wait_level(0, 120)) {
            return ESP_ERR_TIMEOUT;
        }
        const int64_t high_time = esp_timer_get_time() - high_start;
        bytes[bit / 8] <<= 1;
        if (high_time > 40) {
            bytes[bit / 8] |= 1;
        }
    }

    if ((uint8_t)(bytes[0] + bytes[1] + bytes[2] + bytes[3]) != bytes[4]) {
        return ESP_ERR_INVALID_CRC;
    }
    const uint16_t humidity_raw    = (uint16_t)((bytes[0] << 8) | bytes[1]);
    const uint16_t temperature_raw = (uint16_t)(((bytes[2] & 0x7f) << 8) | bytes[3]);
    reading->humidity              = humidity_raw / 10.0f;
    reading->temperature           = temperature_raw / 10.0f;
    if ((bytes[2] & 0x80) != 0) {
        reading->temperature = -reading->temperature;
    }
    return ESP_OK;
}

/* ── ADC (tensión de batería) ───────────────────────────────────────────── */

static esp_err_t configure_adc(adc_oneshot_unit_handle_t *adc, adc_cali_handle_t *calibration) {
    const adc_oneshot_unit_init_cfg_t unit_config = {.unit_id = VOLTAGE_ADC_UNIT};
    ESP_RETURN_ON_ERROR(adc_oneshot_new_unit(&unit_config, adc), TAG, "ADC oneshot init failed");
    const adc_oneshot_chan_cfg_t channel_config = {
        .atten    = ADC_ATTEN_DB_12,
        .bitwidth = ADC_BITWIDTH_DEFAULT,
    };
    ESP_RETURN_ON_ERROR(adc_oneshot_config_channel(*adc, VOLTAGE_ADC_CHANNEL, &channel_config), TAG,
                        "ADC GPIO34 configuration failed");

#if ADC_CALI_SCHEME_LINE_FITTING_SUPPORTED
    const adc_cali_line_fitting_config_t cali_config = {
        .unit_id  = VOLTAGE_ADC_UNIT,
        .atten    = ADC_ATTEN_DB_12,
        .bitwidth = ADC_BITWIDTH_DEFAULT,
    };
    if (adc_cali_create_scheme_line_fitting(&cali_config, calibration) != ESP_OK) {
        *calibration = NULL;
        ESP_LOGW(TAG, "ADC calibration unavailable; using approximate conversion");
    }
#else
    *calibration = NULL;
    ESP_LOGW(TAG, "ADC calibration scheme unavailable in this ESP-IDF build");
#endif
    return ESP_OK;
}

static float read_battery_voltage(adc_oneshot_unit_handle_t adc, adc_cali_handle_t calibration) {
    int raw_total     = 0;
    const int samples = 8;
    for (int i = 0; i < samples; ++i) {
        int raw = 0;
        if (adc_oneshot_read(adc, VOLTAGE_ADC_CHANNEL, &raw) == ESP_OK) {
            raw_total += raw;
        }
    }
    const int raw_avg = raw_total / samples;

    int millivolts = 0;
    if (calibration != NULL &&
        adc_cali_raw_to_voltage(calibration, raw_avg, &millivolts) == ESP_OK) {
        return millivolts / 1000.0f * ADC_EXTERNAL_DIVIDER_RATIO * VOLTAGE_SENSOR_RATIO *
               VOLTAGE_CALIBRATION;
    }
    /* Aproximación sin calibración: 2.45 V a escala completa. */
    const float adc_volts = raw_avg * 2.45f / 4095.0f;
    return adc_volts * ADC_EXTERNAL_DIVIDER_RATIO * VOLTAGE_SENSOR_RATIO * VOLTAGE_CALIBRATION;
}

/* ── GPS UART ───────────────────────────────────────────────────────────── */

#ifndef CONFIG_MONITOR_WOKWI_SIMULATION
static void configure_gps(void) {
    const uart_config_t uart_config = {
        .baud_rate  = GPS_BAUD,
        .data_bits  = UART_DATA_8_BITS,
        .parity     = UART_PARITY_DISABLE,
        .stop_bits  = UART_STOP_BITS_1,
        .flow_ctrl  = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };
    ESP_ERROR_CHECK(uart_driver_install(GPS_UART_PORT, 2048, 0, 0, NULL, 0));
    ESP_ERROR_CHECK(uart_param_config(GPS_UART_PORT, &uart_config));
    ESP_ERROR_CHECK(uart_set_pin(GPS_UART_PORT, GPS_TX_GPIO, GPS_RX_GPIO, UART_PIN_NO_CHANGE,
                                 UART_PIN_NO_CHANGE));
}
#endif

/* ── Bucle principal ────────────────────────────────────────────────────── */

void app_main(void) {
    ESP_LOGI(TAG, "Iniciando monitor de bateria, sensores y GPS");

    monitor_state_t state;
    monitor_state_init(&state);

    display_t display;
    ESP_ERROR_CHECK(display_init(&display));

    const gpio_config_t dht_config = {
        .pin_bit_mask = 1ULL << DHT_GPIO,
        .mode         = GPIO_MODE_INPUT_OUTPUT_OD,
        .pull_up_en   = GPIO_PULLUP_ENABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type    = GPIO_INTR_DISABLE,
    };
    ESP_ERROR_CHECK(gpio_config(&dht_config));
    gpio_set_level(DHT_GPIO, 1);

    gps_state_t gps;
    gps_init(&gps);
#ifndef CONFIG_MONITOR_WOKWI_SIMULATION
    configure_gps();
#endif

    adc_oneshot_unit_handle_t adc     = NULL;
    adc_cali_handle_t adc_calibration = NULL;
    ESP_ERROR_CHECK(configure_adc(&adc, &adc_calibration));
    ESP_ERROR_CHECK(network_start(&state));

    dht_reading_t dht    = {0};
    bool dht_ok          = false;
    int64_t last_dht_ms  = -(int64_t)SENSOR_INTERVAL_DEFAULT_SECONDS * 1000;
    int64_t last_read_ms = -(int64_t)SENSOR_INTERVAL_DEFAULT_SECONDS * 1000;
#ifndef CONFIG_MONITOR_WOKWI_SIMULATION
    uint8_t gps_bytes[128];
#endif
    char log_line[160];

    while (true) {
        const int64_t now_us  = esp_timer_get_time();
        const uint32_t now_ms = (uint32_t)(now_us / 1000);

        /* ── GPS ── */
#ifdef CONFIG_MONITOR_WOKWI_SIMULATION
        gps.has_position   = true;
        gps.latitude       = 19.4326;
        gps.longitude      = -99.1332;
        gps.has_satellites = true;
        gps.satellites     = 9;
        gps.last_fix_ms    = now_ms;
#else
        const int received = uart_read_bytes(GPS_UART_PORT, gps_bytes, sizeof(gps_bytes), 0);
        if (received > 0) {
            gps_feed(&gps, gps_bytes, (size_t)received, now_ms);
        }
#endif

        /* ── DHT22 + batería: sólo cuando toca según el intervalo ── */
        monitor_data_t cfg_snap;
        monitor_state_snapshot(&state, &cfg_snap);
        const int64_t sensor_interval_ms = (int64_t)cfg_snap.sensor_interval_seconds * 1000;

        if (now_ms - (uint32_t)last_read_ms >= (uint32_t)sensor_interval_ms) {
            last_read_ms = now_ms;

            /* DHT22: requiere mínimo 2.5 s entre lecturas */
            if (now_ms - (uint32_t)last_dht_ms >= 2500) {
                last_dht_ms = now_ms;
                dht_ok      = dht_read(&dht) == ESP_OK;
#ifdef CONFIG_MONITOR_WOKWI_SIMULATION
                if (!dht_ok) {
                    dht.temperature = 24.0f;
                    dht.humidity    = 45.0f;
                    dht_ok          = true;
                    ESP_LOGW(TAG, "DHT22 simulado: valores de respaldo");
                }
#endif
                if (!dht_ok) {
                    ESP_LOGW(TAG, "No se pudo leer el DHT22");
                }
            }

            const float battery_voltage = read_battery_voltage(adc, adc_calibration);
            monitor_state_set_sensors(&state, battery_voltage, dht.temperature, dht.humidity,
                                      dht_ok, now_ms);
        }

        monitor_state_set_gps(&state, &gps, now_ms);

        monitor_data_t snapshot;
        monitor_state_snapshot(&state, &snapshot);
        display_render(&display, &snapshot, now_ms);

        snprintf(log_line, sizeof(log_line),
                 "Bat %.2fV | T %.1fC | H %.1f%% | GPS %s | Wi-Fi %s | ciclo %us",
                 snapshot.battery_voltage, dht_ok ? dht.temperature : NAN,
                 dht_ok ? dht.humidity : NAN, snapshot.gps_fix ? "FIX" : "sin fix",
                 snapshot.wifi_connected ? snapshot.ip_address : "sin conectar",
                 (unsigned)snapshot.sensor_interval_seconds);
        ESP_LOGI(TAG, "%s", log_line);

        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}
