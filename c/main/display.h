#pragma once

#include <stdbool.h>

#include "driver/i2c.h"
#include "driver/spi_master.h"
#include "esp_err.h"
#include "monitor_state.h"

typedef struct {
    spi_device_handle_t lcd;
    uint8_t oled_buffer[1024];
} display_t;

esp_err_t display_init(display_t *display);
void display_render(display_t *display, const monitor_data_t *data, uint32_t now_ms);
