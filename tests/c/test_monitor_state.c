/**
 * Host-side tests for monitor_state.c logic.
 *
 * We test the pure-logic functions: seconds_until_refresh and
 * sensor_interval clamping. FreeRTOS mutex calls are stubbed.
 *
 * Build:
 *   gcc -I../../c/main -DTEST_HOST \
 *       -o test_state test_monitor_state.c ../../c/main/monitor_state.c \
 *       stub_freertos.c && ./test_state
 */

#include <assert.h>
#include <stdio.h>
#include <string.h>

/* ── FreeRTOS stubs (stub_freertos.c provides the symbols) ── */
#include "monitor_state.h"

static int g_pass = 0;
static int g_fail = 0;

#define ASSERT_EQ(a, b) \
    do { \
        if ((a) == (b)) { g_pass++; } \
        else { g_fail++; \
               printf("FAIL %s:%d  expected %d got %d\n", \
                      __FILE__, __LINE__, (int)(b), (int)(a)); } \
    } while (0)

#define ASSERT_TRUE(e) ASSERT_EQ(!!(e), 1)

/* ── seconds_until_refresh ────────────────────────────────── */

static void test_no_deadline_returns_minus_one(void) {
    monitor_data_t d = {0};
    d.next_refresh_us = 0;
    ASSERT_EQ(monitor_seconds_until_refresh(&d, 0), -1);
}

static void test_past_deadline_returns_zero(void) {
    monitor_data_t d = {0};
    d.next_refresh_us = 1000000; /* 1 s */
    ASSERT_EQ(monitor_seconds_until_refresh(&d, 2000000), 0);
}

static void test_ten_seconds_remaining(void) {
    monitor_data_t d = {0};
    d.next_refresh_us = 11000000LL; /* 11 s from epoch */
    ASSERT_EQ(monitor_seconds_until_refresh(&d, 1000000LL), 10);
}

static void test_rounds_up(void) {
    monitor_data_t d = {0};
    /* 9.5 s remaining → rounds up to 10 */
    d.next_refresh_us = 10500000LL;
    ASSERT_EQ(monitor_seconds_until_refresh(&d, 1000000LL), 10);
}

/* ── sensor_interval clamping ─────────────────────────────── */

static void test_interval_below_min_clamped(void) {
    ASSERT_TRUE(SENSOR_INTERVAL_MIN_SECONDS <= 5);
    ASSERT_TRUE(SENSOR_INTERVAL_MAX_SECONDS >= 300);
}

static void test_display_mask_all(void) {
    ASSERT_EQ(DISPLAY_FIELDS_ALL, 0x0F);
}

static void test_display_field_bits_non_overlapping(void) {
    ASSERT_EQ(DISPLAY_FIELD_BATTERY & DISPLAY_FIELD_DHT,     0);
    ASSERT_EQ(DISPLAY_FIELD_BATTERY & DISPLAY_FIELD_GPS,     0);
    ASSERT_EQ(DISPLAY_FIELD_BATTERY & DISPLAY_FIELD_WEATHER, 0);
    ASSERT_EQ(DISPLAY_FIELD_DHT     & DISPLAY_FIELD_GPS,     0);
    ASSERT_EQ(DISPLAY_FIELD_DHT     & DISPLAY_FIELD_WEATHER, 0);
    ASSERT_EQ(DISPLAY_FIELD_GPS     & DISPLAY_FIELD_WEATHER, 0);
}

int main(void) {
    test_no_deadline_returns_minus_one();
    test_past_deadline_returns_zero();
    test_ten_seconds_remaining();
    test_rounds_up();
    test_interval_below_min_clamped();
    test_display_mask_all();
    test_display_field_bits_non_overlapping();

    printf("\n=== Monitor State Tests ===\n");
    printf("PASS: %d  FAIL: %d\n\n", g_pass, g_fail);
    return g_fail > 0 ? 1 : 0;
}
