#pragma once

#include <stddef.h>
#include <stdint.h>

#define MOON_BMP_WIDTH 64
#define MOON_BMP_HEADER_SIZE 1078
#define MOON_BMP_SIZE (MOON_BMP_HEADER_SIZE + MOON_BMP_WIDTH * MOON_BMP_WIDTH)

/* Render one grayscale, 8-bit BMP moon phase into a caller-owned buffer. */
void moon_image_render_bmp(float phase, uint8_t *buffer, size_t buffer_size);
