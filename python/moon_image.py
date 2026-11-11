"""Reusable 64x64 grayscale BMP image buffer for the current moon phase."""

import math

WIDTH = 64
HEADER_SIZE = 1078
BMP_SIZE = HEADER_SIZE + WIDTH * WIDTH
_buffer = bytearray(BMP_SIZE)
_cached_phase_key = None
_CRATERS = ((-.35, -.30, .12), (.30, -.42, .09), (.42, .12, .14),
            (-.22, .36, .10), (.02, -.04, .08), (-.48, .12, .07))


def _put_u16(offset, value):
    _buffer[offset] = value & 0xff
    _buffer[offset + 1] = (value >> 8) & 0xff


def _put_u32(offset, value):
    for index in range(4):
        _buffer[offset + index] = (value >> (index * 8)) & 0xff


def update(phase):
    """Update the module-owned BMP buffer when its 8-bit phase changes."""
    global _cached_phase_key
    if phase is None:
        phase = 0.0
    try:
        phase = float(phase) % 1.0
    except Exception:
        phase = 0.0
    key = int(phase * 255.0)
    if key == _cached_phase_key:
        return _buffer
    _cached_phase_key = key
    for i in range(BMP_SIZE):
        _buffer[i] = 0
    _buffer[0:2] = b"BM"
    _put_u32(2, BMP_SIZE)
    _put_u32(10, HEADER_SIZE)
    _put_u32(14, 40)
    _put_u32(18, WIDTH)
    _put_u32(22, WIDTH)
    _put_u16(26, 1)
    _put_u16(28, 8)
    _put_u32(34, WIDTH * WIDTH)
    _put_u32(46, 256)
    for value in range(256):
        offset = 54 + value * 4
        _buffer[offset:offset + 3] = bytes((value, value, value))

    angle = phase * math.pi * 2.0
    sun_x, sun_z = math.sin(angle), -math.cos(angle)
    center, radius = (WIDTH - 1) * 0.5, 28.5
    for y in range(WIDTH):
        for x in range(WIDTH):
            nx, ny = (x - center) / radius, (y - center) / radius
            r2 = nx * nx + ny * ny
            if r2 > 1.0:
                continue
            nz = math.sqrt(1.0 - r2)
            light = nx * sun_x + nz * sun_z
            noise = math.sin(nx * 31 + ny * 19) * 4 + math.cos(nx * 17 - ny * 29) * 3
            surface = 176 + nz * 14 + noise if light > 0 else 14 + noise * 0.15
            for cx, cy, crater_r in _CRATERS:
                dx, dy = nx - cx, ny - cy
                d2 = dx * dx + dy * dy
                if d2 < crater_r * crater_r:
                    surface += 18 if math.sqrt(d2) / crater_r > .78 else -22
            offset = HEADER_SIZE + (WIDTH - 1 - y) * WIDTH + x
            _buffer[offset] = max(0, min(255, int(surface)))
    return _buffer
