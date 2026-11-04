#include "monitor_state.h"

#include <stdio.h>
#include <string.h>

void monitor_state_init(monitor_state_t *state) {
    memset(state, 0, sizeof(*state));
    state->mutex = xSemaphoreCreateMutex();
    configASSERT(state->mutex != NULL);
    state->data.refresh_interval_seconds = WEATHER_REFRESH_INTERVAL_SECONDS;
    state->data.sensor_interval_seconds  = SENSOR_INTERVAL_DEFAULT_SECONDS;
    state->data.display_fields_mask      = DISPLAY_FIELDS_ALL;
}

void monitor_state_set_sensors(monitor_state_t *state, float battery_voltage, float temperature_c,
                               float humidity_percent, bool dht_valid, uint32_t now_ms) {
    xSemaphoreTake(state->mutex, portMAX_DELAY);
    state->data.battery_voltage     = battery_voltage;
    state->data.temperature_c       = temperature_c;
    state->data.humidity_percent    = humidity_percent;
    state->data.dht_valid           = dht_valid;
    state->data.last_sensor_read_ms = now_ms;
    xSemaphoreGive(state->mutex);
}

void monitor_state_set_gps(monitor_state_t *state, const gps_state_t *gps, uint32_t now_ms) {
    xSemaphoreTake(state->mutex, portMAX_DELAY);
    state->data.gps_fix            = gps_has_recent_fix(gps, now_ms);
    state->data.latitude           = gps->latitude;
    state->data.longitude          = gps->longitude;
    state->data.gps_has_satellites = gps->has_satellites;
    state->data.satellites         = gps->satellites;
    xSemaphoreGive(state->mutex);
}

void monitor_state_set_wifi(monitor_state_t *state, bool connected, const char *ssid,
                            const char *ip_address) {
    xSemaphoreTake(state->mutex, portMAX_DELAY);
    state->data.wifi_connected = connected;
    snprintf(state->data.wifi_ssid, sizeof(state->data.wifi_ssid), "%s", ssid != NULL ? ssid : "");
    snprintf(state->data.ip_address, sizeof(state->data.ip_address), "%s",
             ip_address != NULL ? ip_address : "");
    xSemaphoreGive(state->mutex);
}

void monitor_state_set_weather(monitor_state_t *state, const weather_data_t *weather) {
    xSemaphoreTake(state->mutex, portMAX_DELAY);
    state->data.weather = *weather;
    xSemaphoreGive(state->mutex);
}

void monitor_state_set_refresh_deadline(monitor_state_t *state, int64_t deadline_us) {
    xSemaphoreTake(state->mutex, portMAX_DELAY);
    state->data.next_refresh_us = deadline_us;
    xSemaphoreGive(state->mutex);
}

void monitor_state_set_sensor_interval(monitor_state_t *state, uint32_t interval_seconds) {
    if (interval_seconds < SENSOR_INTERVAL_MIN_SECONDS) {
        interval_seconds = SENSOR_INTERVAL_MIN_SECONDS;
    }
    if (interval_seconds > SENSOR_INTERVAL_MAX_SECONDS) {
        interval_seconds = SENSOR_INTERVAL_MAX_SECONDS;
    }
    xSemaphoreTake(state->mutex, portMAX_DELAY);
    state->data.sensor_interval_seconds = interval_seconds;
    xSemaphoreGive(state->mutex);
}

void monitor_state_set_display_mask(monitor_state_t *state, uint8_t mask) {
    xSemaphoreTake(state->mutex, portMAX_DELAY);
    state->data.display_fields_mask = mask & DISPLAY_FIELDS_ALL;
    xSemaphoreGive(state->mutex);
}

void monitor_state_snapshot(monitor_state_t *state, monitor_data_t *snapshot) {
    xSemaphoreTake(state->mutex, portMAX_DELAY);
    *snapshot = state->data;
    xSemaphoreGive(state->mutex);
}

int monitor_seconds_until_refresh(const monitor_data_t *snapshot, int64_t now_us) {
    if (snapshot->next_refresh_us <= 0) {
        return -1;
    }
    const int64_t remaining_us = snapshot->next_refresh_us - now_us;
    if (remaining_us <= 0) {
        return 0;
    }
    return (int)((remaining_us + 999999) / 1000000);
}
