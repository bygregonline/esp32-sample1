cmake_minimum_required(VERSION 3.16)
project(esp32_monitor_c_tests C)

set(CMAKE_C_STANDARD 11)
set(C_MAIN ${CMAKE_SOURCE_DIR}/../../c/main)

include_directories(${C_MAIN})
include_directories(${CMAKE_SOURCE_DIR}/stubs)

# Stub GPS parser dependencies (no ESP-IDF headers needed for host build)
add_compile_definitions(TEST_HOST)

# ── NMEA parser tests ──────────────────────────────────────────────────────
add_executable(test_nmea
    test_nmea_parser.c
    ${C_MAIN}/gps.c
)
target_link_libraries(test_nmea m)

# ── Monitor state tests ────────────────────────────────────────────────────
add_executable(test_state
    test_monitor_state.c
    stub_freertos.c
    ${C_MAIN}/monitor_state.c
    ${C_MAIN}/gps.c   # monitor_state.c includes gps.h
)
target_link_libraries(test_state m)

enable_testing()
add_test(NAME nmea_parser   COMMAND test_nmea)
add_test(NAME monitor_state COMMAND test_state)
