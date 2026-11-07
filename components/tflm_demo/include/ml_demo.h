#pragma once

#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

bool ml_demo_init(void);
bool ml_demo_infer(float input, float *prediction);

#ifdef __cplusplus
}
#endif
