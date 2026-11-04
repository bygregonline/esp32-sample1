idf_component_register(
    SRCS "main.c" "display.c" "gps.c" "monitor_state.c" "network.c" "weather.c"
    INCLUDE_DIRS "."
    REQUIRES driver esp_adc
    PRIV_REQUIRES esp_timer esp_wifi esp_event esp_netif nvs_flash
                  esp_http_server esp_http_client esp-tls mbedtls json
)
