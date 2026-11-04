/**
 * Host-side tests for the NMEA GPS parser (c/main/gps.c).
 *
 * Compiled with plain gcc — no ESP32 toolchain needed.
 * Build: gcc -I../../c/main -o test_nmea test_nmea_parser.c ../../c/main/gps.c && ./test_nmea
 */

#include <assert.h>
#include <math.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "gps.h"

/* ── Test helpers ─────────────────────────────────────────── */
static int g_pass = 0;
static int g_fail = 0;

#define TEST(name) \
    static void name(void); \
    __attribute__((constructor)) static void _reg_##name(void) { name(); } \
    static void name(void)

#define ASSERT_TRUE(expr) \
    do { \
        if (expr) { g_pass++; } \
        else { g_fail++; \
               printf("FAIL %s:%d  %s\n", __FILE__, __LINE__, #expr); } \
    } while (0)

#define ASSERT_FALSE(expr) ASSERT_TRUE(!(expr))

#define ASSERT_NEAR(a, b, tol) \
    ASSERT_TRUE(fabs((double)(a) - (double)(b)) < (tol))

static void feed(gps_state_t *g, const char *sentence, uint32_t now_ms) {
    gps_feed(g, (const uint8_t *)sentence, strlen(sentence), now_ms);
}

/* ── Tests ────────────────────────────────────────────────── */

TEST(test_rmc_valid_sets_fix) {
    gps_state_t g; gps_init(&g);
    feed(&g, "$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A\r\n", 0);
    ASSERT_TRUE(g.has_position);
    ASSERT_TRUE(gps_has_recent_fix(&g, 100));
}

TEST(test_rmc_latitude_conversion) {
    gps_state_t g; gps_init(&g);
    feed(&g, "$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A\r\n", 0);
    /* 48°07.038′ N → 48 + 7.038/60 ≈ 48.11730 */
    ASSERT_NEAR(g.latitude, 48.11730, 0.0001);
}

TEST(test_rmc_longitude_conversion) {
    gps_state_t g; gps_init(&g);
    feed(&g, "$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A\r\n", 0);
    /* 011°31.000′ E → 11 + 31/60 ≈ 11.5167 */
    ASSERT_NEAR(g.longitude, 11.5167, 0.0001);
}

TEST(test_rmc_south_negative) {
    gps_state_t g; gps_init(&g);
    feed(&g, "$GPRMC,000000,A,1926.556,S,09908.000,W,0,0,010101,,*11\r\n", 0);
    ASSERT_TRUE(g.latitude < 0.0);
    ASSERT_TRUE(g.longitude < 0.0);
}

TEST(test_rmc_void_status_no_fix) {
    gps_state_t g; gps_init(&g);
    feed(&g, "$GPRMC,000000,V,,,,,,,010101,,*25\r\n", 0);
    ASSERT_FALSE(g.has_position);
}

TEST(test_rmc_bad_checksum_ignored) {
    gps_state_t g; gps_init(&g);
    feed(&g, "$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*FF\r\n", 0);
    ASSERT_FALSE(g.has_position);
}

TEST(test_gga_sets_satellites) {
    gps_state_t g; gps_init(&g);
    feed(&g, "$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47\r\n", 0);
    ASSERT_TRUE(g.has_satellites);
    ASSERT_TRUE(g.satellites == 8);
}

TEST(test_gga_quality_zero_no_fix) {
    gps_state_t g; gps_init(&g);
    feed(&g, "$GPGGA,123519,4807.038,N,01131.000,E,0,00,,,,,,,*66\r\n", 0);
    ASSERT_FALSE(g.has_position);
}

TEST(test_gnrmc_also_parsed) {
    gps_state_t g; gps_init(&g);
    feed(&g, "$GNRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*74\r\n", 0);
    ASSERT_TRUE(g.has_position);
}

TEST(test_fix_timeout_expired) {
    gps_state_t g; gps_init(&g);
    feed(&g, "$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A\r\n", 0);
    /* 10001 ms later — past the 10 000 ms timeout */
    ASSERT_FALSE(gps_has_recent_fix(&g, 10001));
}

TEST(test_fix_within_timeout) {
    gps_state_t g; gps_init(&g);
    feed(&g, "$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A\r\n", 1000);
    ASSERT_TRUE(gps_has_recent_fix(&g, 5000));
}

TEST(test_partial_sentence_buffered) {
    gps_state_t g; gps_init(&g);
    const char *s = "$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A\r\n";
    size_t mid = strlen(s) / 2;
    gps_feed(&g, (const uint8_t *)s, mid, 0);
    ASSERT_FALSE(g.has_position);  /* incomplete — no fix yet */
    gps_feed(&g, (const uint8_t *)(s + mid), strlen(s) - mid, 0);
    ASSERT_TRUE(g.has_position);
}

/* ── Runner ───────────────────────────────────────────────── */
int main(void) {
    printf("\n=== NMEA Parser Tests ===\n");
    printf("PASS: %d  FAIL: %d\n\n", g_pass, g_fail);
    return g_fail > 0 ? 1 : 0;
}
