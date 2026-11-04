#pragma once

#include <assert.h>

typedef int BaseType_t;
typedef unsigned long TickType_t;

#define pdTRUE 1
#define pdFALSE 0
#define portMAX_DELAY 0xFFFFFFFFUL
#define configASSERT(expression) assert(expression)
