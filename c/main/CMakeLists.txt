set(MONITOR_SOURCES "main.c" "display.c" "gps.c" "monitor_state.c" "moon_image.c" "network.c" "weather.c")
set(MONITOR_PRIVATE_REQUIRES esp_timer esp_wifi esp_event esp_netif nvs_flash
                             esp_http_server esp_http_client esp-tls mbedtls json tflm_demo bmp280)
if(NOT CONFIG_MONITOR_WOKWI_SIMULATION)
    list(APPEND MONITOR_SOURCES "ble_server.c")
    list(APPEND MONITOR_PRIVATE_REQUIRES bt)
endif()

idf_component_register(
    SRCS ${MONITOR_SOURCES}
    INCLUDE_DIRS "."
    REQUIRES driver esp_adc
    PRIV_REQUIRES ${MONITOR_PRIVATE_REQUIRES}
)
