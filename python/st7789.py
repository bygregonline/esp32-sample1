"""Controlador ST7789V2 sencillo: texto de 8x8 y relleno para el TFT 170x320."""

import framebuf
import math
from time import sleep_ms


class ST7789:
    def __init__(
        self,
        spi,
        width,
        height,
        cs,
        dc,
        reset,
        backlight=None,
        x_offset=35,
        y_offset=0,
    ):
        self.spi = spi
        self.width = width
        self.height = height
        self.cs = cs
        self.dc = dc
        self.reset = reset
        self.backlight = backlight
        self.x_offset = x_offset
        self.y_offset = y_offset
        self._fill_tile = bytearray(width * 8 * 2)
        self._moon_row = bytearray(21 * 2)
        self._timer_row = bytearray(20 * 2)
        self.cs.value(1)
        self.dc.value(1)

    @staticmethod
    def color565(red, green, blue):
        return ((red & 0xF8) << 8) | ((green & 0xFC) << 3) | (blue >> 3)

    def _command(self, command, data=None):
        self.cs.value(0)
        self.dc.value(0)
        self.spi.write(bytes((command,)))
        if data:
            self.dc.value(1)
            self.spi.write(data)
        self.cs.value(1)

    def _set_window(self, x, y, width, height):
        x0 = x + self.x_offset
        x1 = x0 + width - 1
        y0 = y + self.y_offset
        y1 = y0 + height - 1
        self._command(0x2A, bytes((x0 >> 8, x0 & 0xFF, x1 >> 8, x1 & 0xFF)))
        self._command(0x2B, bytes((y0 >> 8, y0 & 0xFF, y1 >> 8, y1 & 0xFF)))
        self._command(0x2C)

    def init(self):
        if self.backlight is not None:
            self.backlight.value(1)
        self.reset.value(1)
        sleep_ms(10)
        self.reset.value(0)
        sleep_ms(20)
        self.reset.value(1)
        sleep_ms(120)
        self._command(0x01)  # Software reset
        sleep_ms(150)
        self._command(0x11)  # Sleep out
        sleep_ms(120)
        self._command(0x36, b"\x00")  # Rotacion vertical, RGB
        self._command(0x3A, b"\x55")  # RGB565
        self._command(0xB2, b"\x0c\x0c\x00\x33\x33")
        self._command(0xB7, b"\x35")
        self._command(0xBB, b"\x19")
        self._command(0xC0, b"\x2c")
        self._command(0xC2, b"\x01")
        self._command(0xC3, b"\x12")
        self._command(0xC4, b"\x20")
        self._command(0xC6, b"\x0f")
        self._command(0xD0, b"\xa4\xa1")
        self._command(
            0xE0,
            b"\xd0\x04\x0d\x11\x13\x2b\x3f\x54\x4c\x18\x0d\x0b\x1f\x23",
        )
        self._command(
            0xE1,
            b"\xd0\x04\x0c\x11\x13\x2c\x3f\x44\x51\x2f\x1f\x1f\x20\x23",
        )
        self._command(0x21)  # Inversion on
        self._command(0x13)  # Normal display mode
        self._command(0x29)  # Display on
        sleep_ms(100)

    def fill(self, color):
        high = (color >> 8) & 0xFF
        low = color & 0xFF
        for offset in range(0, len(self._fill_tile), 2):
            self._fill_tile[offset] = high
            self._fill_tile[offset + 1] = low
        self._set_window(0, 0, self.width, self.height)
        self.cs.value(0)
        self.dc.value(1)
        full_tiles = self.height // 8
        for _ in range(full_tiles):
            self.spi.write(self._fill_tile)
        remaining = self.height % 8
        if remaining:
            self.spi.write(memoryview(self._fill_tile)[:self.width * remaining * 2])
        self.cs.value(1)

    def text(self, value, x, y, color, background=0x0000):
        if y < 0 or y + 8 > self.height:
            return
        buffer = bytearray(self.width * 8 * 2)
        fb = framebuf.FrameBuffer(buffer, self.width, 8, framebuf.RGB565)
        fb.fill(background)
        fb.text(str(value), x, 0, color)
        # FrameBuffer stores RGB565 little-endian; ST7789 expects high byte first.
        for offset in range(0, len(buffer), 2):
            buffer[offset], buffer[offset + 1] = buffer[offset + 1], buffer[offset]
        self._set_window(0, y, self.width, 8)
        self.cs.value(0)
        self.dc.value(1)
        self.spi.write(buffer)
        self.cs.value(1)

    def countdown_ring(self, cx, cy, radius, remaining, interval, track, progress_color):
        """Draw a shrinking circular countdown using one small scanline buffer."""
        inner = radius - 4
        fraction = max(0.0, min(1.0, remaining / interval)) if interval else 0.0
        end_angle = fraction * math.pi * 2
        diameter = radius * 2 + 1
        row = bytearray(diameter * 2)
        self.cs.value(1)
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                distance = dx * dx + dy * dy
                color = 0
                if inner * inner <= distance <= radius * radius:
                    angle = math.atan2(dx, -dy)
                    if angle < 0:
                        angle += math.pi * 2
                    color = progress_color if angle <= end_angle else track
                pos = (dx + radius) * 2
                row[pos] = (color >> 8) & 0xFF
                row[pos + 1] = color & 0xFF
            self._set_window(cx - radius, cy + dy, diameter, 1)
            self.cs.value(0)
            self.dc.value(1)
            self.spi.write(row)
            self.cs.value(1)

    def moon_icon(self, cx, cy, phase, valid=True):
        """Draw a small textured moon disk with the current illuminated side."""
        radius = 10
        angle = (phase if valid else 0.0) * math.pi * 2
        sun_x, sun_z = math.sin(angle), -math.cos(angle)
        self.cs.value(1)
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                nx, ny = dx / radius, dy / radius
                r2 = nx * nx + ny * ny
                color = 0
                if r2 <= 1.0:
                    nz = math.sqrt(1.0 - r2)
                    light = nx * sun_x + nz * sun_z
                    shade = int(175 + nz * 65) if light > 0 else 19
                    c1x, c1y = nx - .28, ny + .25
                    c2x, c2y = nx + .35, ny - .20
                    if light > 0 and (c1x * c1x + c1y * c1y < .025 or
                                      c2x * c2x + c2y * c2y < .018):
                        shade = max(0, shade - 35)
                    color = self.color565(shade, shade, min(255, shade + 5))
                offset = (dx + radius) * 2
                self._moon_row[offset] = (color >> 8) & 0xff
                self._moon_row[offset + 1] = color & 0xff
            self._set_window(cx - radius, cy + dy, radius * 2 + 1, 1)
            self.cs.value(0)
            self.dc.value(1)
            self.spi.write(self._moon_row)
            self.cs.value(1)

    def mini_timer(self, cx, cy, value):
        """Render MM:SS in a compact five-row font inside the small ring."""
        glyphs = {
            "0": (7, 5, 5, 5, 7), "1": (2, 6, 2, 2, 7),
            "2": (7, 1, 7, 4, 7), "3": (7, 1, 7, 1, 7),
            "4": (5, 5, 7, 1, 1), "5": (7, 4, 7, 1, 7),
            "6": (7, 4, 7, 5, 7), "7": (7, 1, 1, 1, 1),
            "8": (7, 5, 7, 5, 7), "9": (7, 5, 7, 1, 7),
            ":": (0, 2, 0, 2, 0), "-": (0, 0, 7, 0, 0),
        }
        text = str(value)[:5].rjust(5, "-")
        left, top = cx - 10, cy - 2
        for row_index in range(5):
            for char_index, char in enumerate(text):
                bits = glyphs.get(char, glyphs["-"])[row_index]
                for col in range(3):
                    offset = (char_index * 4 + col) * 2
                    color = 0xFFFF if bits & (1 << (2 - col)) else 0
                    self._timer_row[offset] = (color >> 8) & 0xff
                    self._timer_row[offset + 1] = color & 0xff
            self._set_window(left, top + row_index, 20, 1)
            self.cs.value(0)
            self.dc.value(1)
            self.spi.write(self._timer_row)
            self.cs.value(1)
