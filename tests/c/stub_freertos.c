/**
 * Minimal FreeRTOS stubs so monitor_state.c compiles on host.
 * Only the mutex functions are needed; everything else is unused.
 */
#include <stdlib.h>

#include "freertos/semphr.h"

SemaphoreHandle_t xSemaphoreCreateMutex(void)  { return malloc(1); }
BaseType_t xSemaphoreTake(SemaphoreHandle_t h, TickType_t t) { (void)h; (void)t; return pdTRUE; }
BaseType_t xSemaphoreGive(SemaphoreHandle_t h) { (void)h; return pdTRUE; }
void configASSERT_stub(int v) { (void)v; }
