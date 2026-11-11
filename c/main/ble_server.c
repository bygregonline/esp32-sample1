#include "ble_server.h"

#include <stdio.h>
#include <inttypes.h>
#include <string.h>
#include <time.h>

#include "cJSON.h"
#include "esp_log.h"
#include "esp_check.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "host/ble_hs.h"
#include "host/ble_uuid.h"
#include "nimble/nimble_port.h"
#include "nimble/nimble_port_freertos.h"
#include "services/gap/ble_svc_gap.h"
#include "services/gatt/ble_svc_gatt.h"
#include "monitor_state.h"

static const char *TAG = "monitor_ble";
static monitor_state_t *s_state;
static uint16_t s_value_handles[4];
static const ble_uuid16_t s_service_uuid = BLE_UUID16_INIT(0xFFA0);
static const ble_uuid16_t s_format_uuids[4] = {
    BLE_UUID16_INIT(0xFFA1), BLE_UUID16_INIT(0xFFA2),
    BLE_UUID16_INIT(0xFFA3), BLE_UUID16_INIT(0xFFA4),
};

static void xml_escape(const char *src, char *dst, size_t cap) {
    dst[0] = '\0';
    for (; *src && strlen(dst) + 1 < cap; ++src) {
        const char *replacement = NULL;
        switch (*src) {
        case '&': replacement = "&amp;"; break;
        case '<': replacement = "&lt;"; break;
        case '>': replacement = "&gt;"; break;
        case '\"': replacement = "&quot;"; break;
        case '\'': replacement = "&apos;"; break;
        default: break;
        }
        if (replacement) {
            if (strlen(dst) + strlen(replacement) + 1 >= cap) break;
            strlcat(dst, replacement, cap);
        } else {
            const size_t len = strlen(dst);
            dst[len] = *src; dst[len + 1] = '\0';
        }
    }
}

static void host_task(void *arg) { (void)arg; nimble_port_run(); nimble_port_freertos_deinit(); }
static void advertise(void);
static void on_sync(void) { advertise(); }
static int gap_event(struct ble_gap_event *event, void *arg) {
    (void)arg;
    if (event->type == BLE_GAP_EVENT_DISCONNECT) advertise();
    return 0;
}

static void format_value(const monitor_data_t *d, int format, char *out, size_t cap) {
    char clock_text[32] = "unknown";
    time_t now = time(NULL); struct tm local;
    if (localtime_r(&now, &local)) strftime(clock_text, sizeof(clock_text), "%Y-%m-%d %H:%M:%S", &local);
    char temperature[16] = "null", humidity[16] = "null", pressure[16] = "null";
    char latitude[24] = "null", longitude[24] = "null", moon[16] = "null", illumination[16] = "null";
    char weather_temp[16] = "null", weather_humidity[16] = "null";
    char weather_min[16] = "null", weather_max[16] = "null", rain[16] = "null";
    char forecast_yaml[80] = "null", ip_xml[64], ssid_xml[40], forecast_xml[80], event_xml[100];
    const char *event = d->event_log_count ? d->event_log[d->event_log_count - 1] : "none";
    xml_escape(d->ip_address, ip_xml, sizeof(ip_xml));
    xml_escape(d->wifi_ssid, ssid_xml, sizeof(ssid_xml));
    xml_escape(d->weather.valid ? d->weather.summary : "", forecast_xml, sizeof(forecast_xml));
    xml_escape(event, event_xml, sizeof(event_xml));
    if (d->dht_valid) { snprintf(temperature,sizeof(temperature),"%.1f",d->temperature_c); snprintf(humidity,sizeof(humidity),"%.1f",d->humidity_percent); }
    if (d->bmp280_valid) snprintf(pressure,sizeof(pressure),"%.1f",d->pressure_hpa);
    if (d->gps_fix) { snprintf(latitude,sizeof(latitude),"%.6f",d->latitude); snprintf(longitude,sizeof(longitude),"%.6f",d->longitude); }
    if (d->moon_phase_valid) { snprintf(moon,sizeof(moon),"%.3f",d->moon_phase); snprintf(illumination,sizeof(illumination),"%d",d->moon_illumination_percent); }
    if (d->weather.valid) {
        snprintf(weather_temp,sizeof(weather_temp),"%.1f",d->weather.current_temperature_c);
        snprintf(weather_humidity,sizeof(weather_humidity),"%.1f",d->weather.current_humidity_percent);
        snprintf(weather_min,sizeof(weather_min),"%.1f",d->weather.minimum_temperature_c);
        snprintf(weather_max,sizeof(weather_max),"%.1f",d->weather.maximum_temperature_c);
        snprintf(rain,sizeof(rain),"%d",d->weather.precipitation_probability);
        snprintf(forecast_yaml,sizeof(forecast_yaml),"\"%.32s\"",d->weather.summary);
    }
    const uint64_t elapsed = ((uint64_t)esp_timer_get_time() / 1000000U) > (d->last_sensor_read_ms / 1000U)
        ? ((uint64_t)esp_timer_get_time() / 1000000U - d->last_sensor_read_ms / 1000U) : 0;
    const int remaining = elapsed >= d->sensor_interval_seconds ? 0 : (int)(d->sensor_interval_seconds - elapsed);
    char json[512];
    cJSON *root = cJSON_CreateObject();
    if (root) {
        cJSON_AddStringToObject(root, "time", clock_text);
        cJSON_AddStringToObject(root, "ip", d->ip_address);
        cJSON_AddBoolToObject(root, "wifi", d->wifi_connected);
        cJSON_AddStringToObject(root, "ssid", d->wifi_ssid);
        cJSON_AddNumberToObject(root, "battery_v", d->battery_voltage);
        if (d->dht_valid) { cJSON_AddNumberToObject(root, "temp_c", d->temperature_c); cJSON_AddNumberToObject(root, "hum_pct", d->humidity_percent); }
        else { cJSON_AddNullToObject(root, "temp_c"); cJSON_AddNullToObject(root, "hum_pct"); }
        if (d->bmp280_valid) cJSON_AddNumberToObject(root, "pressure_hpa", d->pressure_hpa); else cJSON_AddNullToObject(root, "pressure_hpa");
        if (d->gps_fix) { cJSON_AddNumberToObject(root, "lat", d->latitude); cJSON_AddNumberToObject(root, "lon", d->longitude); }
        else { cJSON_AddNullToObject(root, "lat"); cJSON_AddNullToObject(root, "lon"); }
        if (d->weather.valid) cJSON_AddStringToObject(root, "forecast", d->weather.summary); else cJSON_AddNullToObject(root, "forecast");
        if (d->weather.valid) {
            cJSON_AddNumberToObject(root, "wx_c", d->weather.current_temperature_c);
            cJSON_AddNumberToObject(root, "wx_hum_pct", d->weather.current_humidity_percent);
            cJSON_AddNumberToObject(root, "wx_min_c", d->weather.minimum_temperature_c);
            cJSON_AddNumberToObject(root, "wx_max_c", d->weather.maximum_temperature_c);
            cJSON_AddNumberToObject(root, "rain_pct", d->weather.precipitation_probability);
        } else {
            cJSON_AddNullToObject(root, "wx_c"); cJSON_AddNullToObject(root, "wx_hum_pct");
            cJSON_AddNullToObject(root, "wx_min_c"); cJSON_AddNullToObject(root, "wx_max_c");
            cJSON_AddNullToObject(root, "rain_pct");
        }
        if (d->moon_phase_valid) { cJSON_AddNumberToObject(root, "moon", d->moon_phase); cJSON_AddNumberToObject(root, "moon_illum_pct", d->moon_illumination_percent); }
        else { cJSON_AddNullToObject(root, "moon"); cJSON_AddNullToObject(root, "moon_illum_pct"); }
        cJSON_AddNumberToObject(root, "interval_s", d->sensor_interval_seconds);
        cJSON_AddNumberToObject(root, "remaining_s", remaining);
        cJSON_AddStringToObject(root, "event", d->event_log_count ? d->event_log[d->event_log_count - 1] : "none");
        char *printed = cJSON_PrintUnformatted(root);
        if (printed) { strlcpy(json, printed, sizeof(json)); cJSON_free(printed); } else json[0] = '\0';
        cJSON_Delete(root);
    } else json[0] = '\0';
    if (format == 0) { strlcpy(out, json, cap); return; }
    if (format == 1) {
        snprintf(out, cap, "time=%s\nip=%s\nwifi=%s\nssid=%s\nbattery_v=%.3f\ntemp_c=%s\nhum_pct=%s\npressure_hpa=%s\nlat=%s\nlon=%s\nforecast=%s\nwx_c=%s\nwx_hum_pct=%s\nwx_min_c=%s\nwx_max_c=%s\nrain_pct=%s\nmoon=%s\nmoon_illum_pct=%s\ninterval_s=%" PRIu32 "\nremaining_s=%d\nevent=%s",
          clock_text,d->ip_address,d->wifi_connected?"true":"false",d->wifi_ssid,d->battery_voltage,
          temperature,humidity,pressure,latitude,longitude,d->weather.valid?d->weather.summary:"unavailable",
          weather_temp,weather_humidity,weather_min,weather_max,rain,moon,illumination,
          d->sensor_interval_seconds,remaining,d->event_log_count?d->event_log[d->event_log_count-1]:"none");
    } else if (format == 2) {
        snprintf(out, cap, "time: \"%s\"\nip: \"%s\"\nwifi: %s\nssid: \"%.32s\"\nbattery_v: %.3f\ntemp_c: %s\nhum_pct: %s\npressure_hpa: %s\nlat: %s\nlon: %s\nforecast: %s\nwx_c: %s\nwx_hum_pct: %s\nwx_min_c: %s\nwx_max_c: %s\nrain_pct: %s\nmoon: %s\nmoon_illum_pct: %s\ninterval_s: %" PRIu32 "\nremaining_s: %d\nevent: \"%.60s\"",
          clock_text,d->ip_address,d->wifi_connected?"true":"false",d->wifi_ssid,d->battery_voltage,
          temperature,humidity,pressure,latitude,longitude,
          forecast_yaml,moon,illumination,
          weather_temp,weather_humidity,weather_min,weather_max,rain,
          d->sensor_interval_seconds,remaining,
          d->event_log_count?d->event_log[d->event_log_count-1]:"none");
    } else {
        snprintf(out, cap, "<monitor time=\"%s\" ip=\"%s\" wifi=\"%s\" ssid=\"%s\" battery_v=\"%.3f\" temp_c=\"%s\" hum_pct=\"%s\" pressure_hpa=\"%s\" lat=\"%s\" lon=\"%s\" forecast=\"%s\" wx_c=\"%s\" wx_hum_pct=\"%s\" wx_min_c=\"%s\" wx_max_c=\"%s\" rain_pct=\"%s\" moon=\"%s\" moon_illum_pct=\"%s\" interval_s=\"%" PRIu32 "\" remaining_s=\"%d\" event=\"%s\"/>",clock_text,ip_xml,d->wifi_connected?"true":"false",ssid_xml,d->battery_voltage,temperature,humidity,pressure,latitude,longitude,forecast_xml,weather_temp,weather_humidity,weather_min,weather_max,rain,moon,illumination,d->sensor_interval_seconds,remaining,event_xml);
    }
}

static int access_cb(uint16_t conn, uint16_t attr, struct ble_gatt_access_ctxt *ctxt, void *arg) {
    (void)conn; (void)arg;
    if (ctxt->op != BLE_GATT_ACCESS_OP_READ_CHR) return BLE_ATT_ERR_UNLIKELY;
    int index = -1;
    for (int i=0;i<4;i++) if (s_value_handles[i] == attr) index=i;
    if (index < 0) return BLE_ATT_ERR_UNLIKELY;
    monitor_data_t data; monitor_state_snapshot(s_state, &data);
    char payload[512]; format_value(&data,index,payload,sizeof(payload));
    return os_mbuf_append(ctxt->om,payload,strlen(payload)) == 0 ? 0 : BLE_ATT_ERR_INSUFFICIENT_RES;
}

static const struct ble_gatt_svc_def s_services[] = {
  {.type=BLE_GATT_SVC_TYPE_PRIMARY,.uuid=&s_service_uuid.u,.characteristics=(struct ble_gatt_chr_def[]){
    {.uuid=&s_format_uuids[0].u,.access_cb=access_cb,.flags=BLE_GATT_CHR_F_READ,.val_handle=&s_value_handles[0]},
    {.uuid=&s_format_uuids[1].u,.access_cb=access_cb,.flags=BLE_GATT_CHR_F_READ,.val_handle=&s_value_handles[1]},
    {.uuid=&s_format_uuids[2].u,.access_cb=access_cb,.flags=BLE_GATT_CHR_F_READ,.val_handle=&s_value_handles[2]},
    {.uuid=&s_format_uuids[3].u,.access_cb=access_cb,.flags=BLE_GATT_CHR_F_READ,.val_handle=&s_value_handles[3]}, {0}}}, {0}};

static void advertise(void) {
    uint8_t addr_type; ble_hs_id_infer_auto(0,&addr_type);
    struct ble_hs_adv_fields fields = {0}; fields.flags = BLE_HS_ADV_F_DISC_GEN | BLE_HS_ADV_F_BREDR_UNSUP;
    const char *name="ESP32-Monitor"; fields.name=(uint8_t *)name; fields.name_len=strlen(name); fields.name_is_complete=1;
    ble_gap_adv_set_fields(&fields);
    struct ble_gap_adv_params params={0}; params.conn_mode=BLE_GAP_CONN_MODE_UND; params.disc_mode=BLE_GAP_DISC_MODE_GEN;
    ble_gap_adv_start(addr_type,NULL,BLE_HS_FOREVER,&params,gap_event,NULL);
}

esp_err_t ble_server_start(monitor_state_t *state) {
    s_state=state;
    ESP_RETURN_ON_ERROR(nimble_port_init(), TAG, "NimBLE init failed");
    ble_svc_gap_init(); ble_svc_gatt_init();
    ble_svc_gap_device_name_set("ESP32-Monitor");
    int rc=ble_gatts_count_cfg(s_services); if (rc) return ESP_FAIL;
    rc=ble_gatts_add_svcs(s_services); if (rc) return ESP_FAIL;
    ble_hs_cfg.sync_cb=on_sync;
    nimble_port_freertos_init(host_task);
    ESP_LOGI(TAG,"GATT service ready (JSON/TEXT/YAML/XML)");
    return ESP_OK;
}
