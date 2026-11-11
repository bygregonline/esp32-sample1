cmake_minimum_required(VERSION 3.16)

set(EXTRA_COMPONENT_DIRS "${CMAKE_CURRENT_LIST_DIR}/../components/tflm_demo")
if(NOT DEFINED ENV{MONITOR_TZ})
    set(ENV{MONITOR_TZ} "CST6")
endif()
add_compile_definitions(MONITOR_TIMEZONE="$ENV{MONITOR_TZ}")
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(esp32_monitor_c)
