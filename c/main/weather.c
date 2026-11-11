#include "weather.h"

#include <math.h>
#include <stdio.h>
#include <string.h>
#include <time.h>

#include "cJSON.h"
#include "esp_crt_bundle.h"
#include "esp_http_client.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "weather";
#define WEATHER_RESPONSE_MAX 4096
#define GPS_RELOCATION_THRESHOLD_DEGREES 0.005

typedef struct {
    char body[WEATHER_RESPONSE_MAX];
    size_t length;
    bool overflow;
} weather_http_response_t;

static esp_err_t weather_http_event(esp_http_client_event_t *event) {
    weather_http_response_t *response = event->user_data;
    if (event->event_id == HTTP_EVENT_ON_DATA && event->data_len > 0) {
        const size_t available = sizeof(response->body) - response->length - 1;
        const size_t copy_length =
            (size_t)event->data_len < available ? (size_t)event->data_len : available;
        memcpy(response->body + response->length, event->data, copy_length);
        response->length += copy_length;
        response->body[response->length] = '\0';
        if (copy_length != (size_t)event->data_len) {
            response->overflow = true;
        }
    }
    return ESP_OK;
}

static const cJSON *object_item(const cJSON *object, const char *name) {
    return cJSON_GetObjectItemCaseSensitive(object, name);
}

static bool number_value(const cJSON *object, const char *name, double *value) {
    const cJSON *item = object_item(object, name);
    if (!cJSON_IsNumber(item) || !isfinite(item->valuedouble)) {
        return false;
    }
    *value = item->valuedouble;
    return true;
}

static bool first_array_number(const cJSON *object, const char *name, double *value) {
    const cJSON *array = object_item(object, name);
    if (!cJSON_IsArray(array) || cJSON_GetArraySize(array) == 0) {
        return false;
    }
    const cJSON *item = cJSON_GetArrayItem(array, 0);
    if (!cJSON_IsNumber(item) || !isfinite(item->valuedouble)) {
        return false;
    }
    *value = item->valuedouble;
    return true;
}

static const char *weather_summary(int code) {
    if (code == 0)
        return "SOLEADO";
    if (code <= 2)
        return "PARC NUBLADO";
    if (code == 3)
        return "NUBLADO";
    if (code == 45 || code == 48)
        return "NEBLINA";
    if (code <= 57 && code >= 51)
        return "LLOVIZNA";
    if (code <= 67 && code >= 61)
        return "LLUVIA";
    if (code >= 71 && code <= 77)
        return "NIEVE";
    if (code >= 80 && code <= 82)
        return "CHUBASCOS";
    if (code >= 85 && code <= 86)
        return "NIEVE";
    if (code >= 95)
        return "TORMENTA";
    return "SIN DESCRIPCION";
}

static bool parse_weather_response(const weather_http_response_t *response,
                                   weather_data_t *weather) {
    cJSON *root = cJSON_ParseWithLength(response->body, response->length);
    if (root == NULL) {
        return false;
    }

    const cJSON *current = object_item(root, "current");
    const cJSON *daily   = object_item(root, "daily");
    double current_temperature;
    double current_humidity;
    double current_code;
    double minimum;
    double maximum;
    double precipitation;
    double moon_phase = 0;
    const bool valid = cJSON_IsObject(current) && cJSON_IsObject(daily) &&
                       number_value(current, "temperature_2m", &current_temperature) &&
                       number_value(current, "relative_humidity_2m", &current_humidity) &&
                       number_value(current, "weather_code", &current_code) &&
                       first_array_number(daily, "temperature_2m_min", &minimum) &&
                       first_array_number(daily, "temperature_2m_max", &maximum) &&
                       first_array_number(daily, "precipitation_probability_max", &precipitation);
    const bool moon_ok = first_array_number(daily, "moon_phase", &moon_phase);
    if (valid) {
        memset(weather, 0, sizeof(*weather));
        weather->valid                     = true;
        weather->weather_code              = (int)current_code;
        weather->current_temperature_c     = (float)current_temperature;
        weather->current_humidity_percent  = (float)current_humidity;
        weather->minimum_temperature_c     = (float)minimum;
        weather->maximum_temperature_c     = (float)maximum;
        weather->precipitation_probability = (int)precipitation;
        weather->moon_phase = (float)moon_phase;
        weather->moon_illumination_percent =
            (int)lroundf((1.0f - cosf((float)moon_phase * 6.28318530718f)) * 50.0f);
        weather->moon_phase_valid = moon_ok;
        snprintf(weather->summary, sizeof(weather->summary), "%s",
                 weather_summary(weather->weather_code));
        weather->updated_ms = (uint32_t)(esp_timer_get_time() / 1000);
    }
    cJSON_Delete(root);
    return valid;
}

static esp_err_t fetch_weather(double latitude, double longitude, weather_data_t *weather) {
    char url[320];
    snprintf(url, sizeof(url),
             "https://api.open-meteo.com/v1/forecast?latitude=%.6f&longitude=%.6f"
             "&current=temperature_2m,relative_humidity_2m,weather_code"
             "&daily=temperature_2m_min,temperature_2m_max,precipitation_probability_max,moon_phase"
             "&forecast_days=1&timezone=auto",
             latitude, longitude);

    weather_http_response_t response      = {0};
    const esp_http_client_config_t config = {
        .url               = url,
        .event_handler     = weather_http_event,
        .user_data         = &response,
        .timeout_ms        = 15000,
        .buffer_size       = 1024,
        .crt_bundle_attach = esp_crt_bundle_attach,
    };
    esp_http_client_handle_t client = esp_http_client_init(&config);
    if (client == NULL) {
        return ESP_ERR_NO_MEM;
    }

    esp_err_t result      = esp_http_client_perform(client);
    const int status_code = esp_http_client_get_status_code(client);
    esp_http_client_cleanup(client);
    if (result != ESP_OK) {
        ESP_LOGW(TAG, "No se pudo consultar Open-Meteo: %s", esp_err_to_name(result));
        return result;
    }
    if (status_code != 200 || response.overflow) {
        ESP_LOGW(TAG, "Open-Meteo respondio HTTP %d%s", status_code,
                 response.overflow ? " (respuesta demasiado grande)" : "");
        return ESP_FAIL;
    }
    if (!parse_weather_response(&response, weather)) {
        ESP_LOGW(TAG, "Respuesta de pronostico invalida o incompleta");
        return ESP_ERR_INVALID_RESPONSE;
    }
    return ESP_OK;
}

static void weather_task(void *argument) {
    monitor_state_t *state = argument;
    bool observed_location = false;
    double last_latitude   = 0;
    double last_longitude  = 0;

    while (true) {
        monitor_data_t snapshot;
        monitor_state_snapshot(state, &snapshot);
        const int64_t now_us = esp_timer_get_time();
        const bool location_changed =
            !observed_location ||
            fabs(snapshot.latitude - last_latitude) > GPS_RELOCATION_THRESHOLD_DEGREES ||
            fabs(snapshot.longitude - last_longitude) > GPS_RELOCATION_THRESHOLD_DEGREES;
        const bool refresh_due =
            snapshot.next_refresh_us <= 0 || now_us >= snapshot.next_refresh_us;

        // TLS valida fechas de certificados; espera a que SNTP ajuste el reloj.
        if (snapshot.wifi_connected && snapshot.gps_fix && time(NULL) > 1700000000 &&
            (refresh_due || location_changed)) {
            const int64_t next_refresh =
                now_us + (int64_t)WEATHER_REFRESH_INTERVAL_SECONDS * 1000000;
            monitor_state_set_refresh_deadline(state, next_refresh);
            observed_location = true;
            last_latitude     = snapshot.latitude;
            last_longitude    = snapshot.longitude;
            ESP_LOGI(TAG, "Consultando pronostico para %.5f, %.5f", snapshot.latitude,
                     snapshot.longitude);

            weather_data_t weather;
            if (fetch_weather(snapshot.latitude, snapshot.longitude, &weather) == ESP_OK) {
                monitor_state_set_weather(state, &weather);
                ESP_LOGI(TAG, "Pronostico actualizado: %s, %.1f C", weather.summary,
                         weather.current_temperature_c);
            }
        }
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}

esp_err_t weather_start(monitor_state_t *state) {
    if (xTaskCreate(weather_task, "weather", 10240, state, 4, NULL) != pdPASS) {
        return ESP_ERR_NO_MEM;
    }
    return ESP_OK;
}
