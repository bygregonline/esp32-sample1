"""Controlador SSD1306 I2C minimo para MicroPython y pantallas 128x64."""

import framebuf


class SSD1306_I2C:
    def __init__(self, width, height, i2c, address=0x3C):
        self.width = width
        self.height = height
        self.i2c = i2c
        self.address = address
        self.buffer = bytearray(width * ((height + 7) // 8))
        self.framebuf = framebuf.FrameBuffer(
            self.buffer, width, height, framebuf.MONO_VLSB
        )
        self._packet = bytearray(width + 1)
        self._packet[0] = 0x40
        self.i2c.writeto(
            self.address,
            # Page addressing mode: show() writes one page at a time.
            b"\x00\xae\x20\x02\x40\xa1\xc8\x81\x7f\xa8"
            + bytes((height - 1,))
            + b"\xd3\x00\xda\x12\xd5\x80\xd9\xf1\xdb\x30\xa4\xa6\x8d\x14\xaf",
        )
        self.fill(0)
        self.show()

    def fill(self, color):
        self.framebuf.fill(color)

    def text(self, value, x, y, color=1):
        self.framebuf.text(str(value), x, y, color)

    def show(self):
        pages = (self.height + 7) // 8
        for page in range(pages):
            self.i2c.writeto(self.address, bytes((0x00, 0xB0 | page, 0x00, 0x10)))
            start = page * self.width
            self._packet[1:] = self.buffer[start:start + self.width]
            self.i2c.writeto(self.address, self._packet)
