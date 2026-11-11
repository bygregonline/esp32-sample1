#pragma once
#include <stdbool.h>
#ifdef __cplusplus
extern "C" {
#endif
bool monitor_bmp280_init(void);
bool monitor_bmp280_read(float *pressure_hpa);
#ifdef __cplusplus
}
#endif
