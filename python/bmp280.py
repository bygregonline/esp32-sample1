"""Small BMP280 I2C driver for MicroPython (Bosch compensation formulas)."""

class BMP280:
    def __init__(self, i2c, address=0x76):
        self.i2c = i2c
        self.address = address
        if i2c.readfrom_mem(address, 0xD0, 1)[0] != 0x58:
            raise OSError("BMP280 chip ID mismatch")
        c = i2c.readfrom_mem(address, 0x88, 24)
        u16 = lambda n: c[n] | c[n + 1] << 8
        s16 = lambda n: (u16(n) ^ 0x8000) - 0x8000
        self.t1, self.t2, self.t3 = u16(0), s16(2), s16(4)
        self.p1 = u16(6)
        self.p2, self.p3, self.p4 = s16(8), s16(10), s16(12)
        self.p5, self.p6, self.p7 = s16(14), s16(16), s16(18)
        self.p8, self.p9 = s16(20), s16(22)
        i2c.writeto_mem(address, 0xF4, b"\x27")
        i2c.writeto_mem(address, 0xF5, b"\xA0")

    def pressure_hpa(self):
        d = self.i2c.readfrom_mem(self.address, 0xF7, 6)
        adc_p = (d[0] << 12) | (d[1] << 4) | (d[2] >> 4)
        adc_t = (d[3] << 12) | (d[4] << 4) | (d[5] >> 4)
        v1 = (((adc_t >> 3) - (self.t1 << 1)) * self.t2) >> 11
        v2 = (((((adc_t >> 4) - self.t1) ** 2) >> 12) * self.t3) >> 14
        fine = v1 + v2
        v1p = fine - 128000
        v2p = v1p * v1p * self.p6
        v2p += (v1p * self.p5) << 17
        v2p += self.p4 << 35
        v1p = ((v1p * v1p * self.p3) >> 8) + ((v1p * self.p2) << 12)
        v1p = (((1 << 47) + v1p) * self.p1) >> 33
        if not v1p:
            raise OSError("BMP280 invalid calibration")
        pressure = 1048576 - adc_p
        pressure = (((pressure << 31) - v2p) * 3125) // v1p
        v1p = (self.p9 * (pressure >> 13) * (pressure >> 13)) >> 25
        v2p = (self.p8 * pressure) >> 19
        pressure = ((pressure + v1p + v2p) >> 8) + (self.p7 << 4)
        return pressure / 25600.0
