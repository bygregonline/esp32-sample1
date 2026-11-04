#pragma once

#include <stdbool.h>
#include <stdint.h>

#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "gps.h"

#define WEATHER_REFRESH_INTERVAL_SECONDS 300

/* Límites para el intervalo de ciclo de sensores (segundos). */
#define SENSOR_INTERVAL_MIN_SECONDS 5
#define SENSOR_INTERVAL_MAX_SECONDS 300
#define SENSOR_INTERVAL_DEFAULT_SECONDS 10

typedef struct {
    bool valid;
    int weather_code;
    float current_temperature_c;
    float current_humidity_percent;
    float minimum_temperature_c;
    float maximum_temperature_c;
    int precipitation_probability;
    uint32_t updated_ms;
    char summary[16];
} weather_data_t;

typedef struct {
    float battery_voltage;
    float temperature_c;
    float humidity_percent;
    bool dht_valid;

    bool gps_fix;
    bool gps_has_satellites;
    double latitude;
    double longitude;
    int satellites;

    bool wifi_connected;
    char wifi_ssid[33];
    char ip_address[16];

    weather_data_t weather;
    int64_t next_refresh_us;
    uint32_t refresh_interval_seconds;

    /* Intervalo de ciclo de sensores configurable vía API (segundos). */
    uint32_t sensor_interval_seconds;

    /* Timestamp del último ciclo de sensores (ms desde boot). */
    uint32_t last_sensor_read_ms;

    /* Visibilidad de campos en el display (bitmask). */
    uint8_t display_fields_mask;
} monitor_data_t;

/* Bits para display_fields_mask. */
#define DISPLAY_FIELD_BATTERY (1u << 0)
#define DISPLAY_FIELD_DHT (1u << 1)
#define DISPLAY_FIELD_GPS (1u << 2)
#define DISPLAY_FIELD_WEATHER (1u << 3)
#define DISPLAY_FIELDS_ALL 0x0Fu

typedef struct {
    monitor_data_t data;
    SemaphoreHandle_t mutex;
} monitor_state_t;

void monitor_state_init(monitor_state_t *state);
void monitor_state_set_sensors(monitor_state_t *state, float battery_voltage, float temperature_c,
                               float humidity_percent, bool dht_valid, uint32_t now_ms);
void monitor_state_set_gps(monitor_state_t *state, const gps_state_t *gps, uint32_t now_ms);
void monitor_state_set_wifi(monitor_state_t *state, bool connected, const char *ssid,
                            const char *ip_address);
void monitor_state_set_weather(monitor_state_t *state, const weather_data_t *weather);
void monitor_state_set_refresh_deadline(monitor_state_t *state, int64_t deadline_us);
void monitor_state_set_sensor_interval(monitor_state_t *state, uint32_t interval_seconds);
void monitor_state_set_display_mask(monitor_state_t *state, uint8_t mask);
void monitor_state_snapshot(monitor_state_t *state, monitor_data_t *snapshot);
int monitor_seconds_until_refresh(const monitor_data_t *snapshot, int64_t now_us);
