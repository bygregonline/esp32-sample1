#include "moon_image.h"

#include <math.h>
#include <string.h>

static void put_u16(uint8_t *p, uint16_t value) {
    p[0] = (uint8_t)value;
    p[1] = (uint8_t)(value >> 8);
}

static void put_u32(uint8_t *p, uint32_t value) {
    p[0] = (uint8_t)value;
    p[1] = (uint8_t)(value >> 8);
    p[2] = (uint8_t)(value >> 16);
    p[3] = (uint8_t)(value >> 24);
}

void moon_image_render_bmp(float phase, uint8_t *buffer, size_t buffer_size) {
    if (buffer == NULL || buffer_size < MOON_BMP_SIZE) {
        return;
    }

    memset(buffer, 0, MOON_BMP_SIZE);
    buffer[0] = 'B';
    buffer[1] = 'M';
    put_u32(buffer + 2, MOON_BMP_SIZE);
    put_u32(buffer + 10, MOON_BMP_HEADER_SIZE);
    put_u32(buffer + 14, 40);
    put_u32(buffer + 18, MOON_BMP_WIDTH);
    put_u32(buffer + 22, MOON_BMP_WIDTH);
    put_u16(buffer + 26, 1);
    put_u16(buffer + 28, 8);
    put_u32(buffer + 34, MOON_BMP_WIDTH * MOON_BMP_WIDTH);
    put_u32(buffer + 46, 256);
    for (int i = 0; i < 256; ++i) {
        uint8_t *entry = buffer + 54 + i * 4;
        entry[0] = (uint8_t)i;
        entry[1] = (uint8_t)i;
        entry[2] = (uint8_t)i;
    }

    if (!isfinite(phase)) {
        phase = 0.0f;
    }
    phase -= floorf(phase);
    const float angle = phase * 6.28318530718f;
    const float sun_x = sinf(angle);
    const float sun_z = -cosf(angle);
    const float center = (MOON_BMP_WIDTH - 1) * 0.5f;
    const float radius = 28.5f;
    static const float craters[][3] = {
        {-0.35f, -0.30f, 0.12f}, {0.30f, -0.42f, 0.09f},
        {0.42f, 0.12f, 0.14f}, {-0.22f, 0.36f, 0.10f},
        {0.02f, -0.04f, 0.08f}, {-0.48f, 0.12f, 0.07f},
    };

    for (int y = 0; y < MOON_BMP_WIDTH; ++y) {
        for (int x = 0; x < MOON_BMP_WIDTH; ++x) {
            const float nx = (x - center) / radius;
            const float ny = (y - center) / radius;
            const float r2 = nx * nx + ny * ny;
            if (r2 > 1.0f) {
                continue;
            }
            const float nz = sqrtf(1.0f - r2);
            const float light = nx * sun_x + nz * sun_z;
            const float noise = sinf(nx * 31.0f + ny * 19.0f) * 4.0f +
                                cosf(nx * 17.0f - ny * 29.0f) * 3.0f;
            float surface = light > 0.0f ? 176.0f + nz * 14.0f + noise : 14.0f + noise * 0.15f;
            for (size_t c = 0; c < sizeof(craters) / sizeof(craters[0]); ++c) {
                const float dx = nx - craters[c][0];
                const float dy = ny - craters[c][1];
                const float d2 = dx * dx + dy * dy;
                const float crater_r = craters[c][2];
                if (d2 < crater_r * crater_r) {
                    const float edge = sqrtf(d2) / crater_r;
                    surface += edge > 0.78f ? 18.0f : -22.0f;
                }
            }
            if (surface < 0.0f) surface = 0.0f;
            if (surface > 255.0f) surface = 255.0f;
            const size_t offset = MOON_BMP_HEADER_SIZE +
                                  (MOON_BMP_WIDTH - 1 - y) * MOON_BMP_WIDTH + x;
            buffer[offset] = (uint8_t)surface;
        }
    }
}
