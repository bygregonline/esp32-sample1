#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef struct {
    double latitude;
    double longitude;
    int satellites;
    bool has_position;
    bool has_satellites;
    uint32_t last_fix_ms;
    char line[128];
    size_t line_length;
} gps_state_t;

void gps_init(gps_state_t *gps);
void gps_feed(gps_state_t *gps, const uint8_t *data, size_t length, uint32_t now_ms);
bool gps_has_recent_fix(const gps_state_t *gps, uint32_t now_ms);
