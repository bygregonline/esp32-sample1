#include "gps.h"

#include <stdlib.h>
#include <string.h>

#define GPS_FIX_TIMEOUT_MS 10000u

static bool parse_coordinate(const char *value, const char *hemisphere, double *result) {
    if (value == NULL || hemisphere == NULL || value[0] == '\0' || hemisphere[0] == '\0') {
        return false;
    }

    const double raw  = strtod(value, NULL);
    const int degrees = (int)(raw / 100.0);
    double decimal    = degrees + (raw - degrees * 100.0) / 60.0;
    if (hemisphere[0] == 'S' || hemisphere[0] == 'W') {
        decimal = -decimal;
    }
    *result = decimal;
    return true;
}

static size_t split_fields(char *line, char **fields, size_t capacity) {
    size_t count = 0;
    if (capacity == 0) {
        return 0;
    }
    fields[count++] = line;
    for (char *cursor = line; *cursor != '\0' && count < capacity; ++cursor) {
        if (*cursor == ',') {
            *cursor         = '\0';
            fields[count++] = cursor + 1;
        } else if (*cursor == '*') {
            *cursor = '\0';
            break;
        }
    }
    return count;
}

static bool checksum_valid(const char *line) {
    if (line[0] != '$') {
        return false;
    }
    const char *star = strchr(line, '*');
    if (star == NULL || star[1] == '\0' || star[2] == '\0') {
        return false;
    }
    unsigned char checksum = 0;
    for (const char *cursor = line + 1; cursor < star; ++cursor) {
        checksum ^= (unsigned char)*cursor;
    }
    char *end           = NULL;
    const long expected = strtol(star + 1, &end, 16);
    return end != star + 1 && checksum == (unsigned char)expected;
}

static void parse_sentence(gps_state_t *gps, const char *input, uint32_t now_ms) {
    if (!checksum_valid(input)) {
        return;
    }

    char sentence[128];
    strncpy(sentence, input, sizeof(sentence) - 1);
    sentence[sizeof(sentence) - 1] = '\0';
    char *fields[20]               = {0};
    const size_t count             = split_fields(sentence, fields, 20);
    if (count == 0) {
        return;
    }

    const char *type = fields[0] + 3;  // GPRMC/GNRMC -> RMC; GPGGA/GNGGA -> GGA
    if (strcmp(type, "RMC") == 0 && count > 6 && fields[2][0] == 'A') {
        double latitude;
        double longitude;
        if (parse_coordinate(fields[3], fields[4], &latitude) &&
            parse_coordinate(fields[5], fields[6], &longitude)) {
            gps->latitude     = latitude;
            gps->longitude    = longitude;
            gps->has_position = true;
            gps->last_fix_ms  = now_ms;
        }
    } else if (strcmp(type, "GGA") == 0 && count > 7 && fields[6][0] != '0' &&
               fields[6][0] != '\0') {
        gps->satellites     = atoi(fields[7]);
        gps->has_satellites = true;
        double latitude;
        double longitude;
        if (parse_coordinate(fields[2], fields[3], &latitude) &&
            parse_coordinate(fields[4], fields[5], &longitude)) {
            gps->latitude     = latitude;
            gps->longitude    = longitude;
            gps->has_position = true;
            gps->last_fix_ms  = now_ms;
        }
    }
}

void gps_init(gps_state_t *gps) {
    memset(gps, 0, sizeof(*gps));
}

void gps_feed(gps_state_t *gps, const uint8_t *data, size_t length, uint32_t now_ms) {
    for (size_t i = 0; i < length; ++i) {
        const char value = (char)data[i];
        if (value == '\n') {
            gps->line[gps->line_length] = '\0';
            parse_sentence(gps, gps->line, now_ms);
            gps->line_length = 0;
        } else if (value != '\r') {
            if (gps->line_length + 1 < sizeof(gps->line)) {
                gps->line[gps->line_length++] = value;
            } else {
                gps->line_length = 0;
            }
        }
    }
}

bool gps_has_recent_fix(const gps_state_t *gps, uint32_t now_ms) {
    return gps->has_position && (uint32_t)(now_ms - gps->last_fix_ms) <= GPS_FIX_TIMEOUT_MS;
}
