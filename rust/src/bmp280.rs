//! BMP280 pressure driver using the second ESP32 I2C controller.
use esp_idf_svc::hal::i2c::I2cDriver;

pub struct Bmp280<'d> {
    i2c: I2cDriver<'d>,
    addr: u8,
    t1: u16,
    t2: i16,
    t3: i16,
    p1: u16,
    p2: i16,
    p3: i16,
    p4: i16,
    p5: i16,
    p6: i16,
    p7: i16,
    p8: i16,
    p9: i16,
}

impl<'d> Bmp280<'d> {
    pub fn new(mut i2c: I2cDriver<'d>) -> anyhow::Result<Self> {
        let mut addr = 0;
        for candidate in [0x76, 0x77] {
            let mut id = [0u8; 1];
            if i2c.write_read(candidate, &[0xD0], &mut id, 1000).is_ok() && id[0] == 0x58 {
                addr = candidate;
                break;
            }
        }
        if addr == 0 {
            anyhow::bail!("BMP280 not detected at 0x76/0x77");
        }
        let mut c = [0u8; 24];
        i2c.write_read(addr, &[0x88], &mut c, 1000)?;
        let u = |n: usize| u16::from_le_bytes([c[n], c[n + 1]]);
        let s = |n: usize| i16::from_le_bytes([c[n], c[n + 1]]);
        i2c.write(addr, &[0xF4, 0x27], 1000)?;
        i2c.write(addr, &[0xF5, 0xA0], 1000)?;
        Ok(Self {
            i2c,
            addr,
            t1: u(0),
            t2: s(2),
            t3: s(4),
            p1: u(6),
            p2: s(8),
            p3: s(10),
            p4: s(12),
            p5: s(14),
            p6: s(16),
            p7: s(18),
            p8: s(20),
            p9: s(22),
        })
    }
    pub fn pressure_hpa(&mut self) -> anyhow::Result<f32> {
        let mut d = [0u8; 6];
        self.i2c.write_read(self.addr, &[0xF7], &mut d, 1000)?;
        let ap = ((d[0] as i32) << 12) | ((d[1] as i32) << 4) | ((d[2] as i32) >> 4);
        let at = ((d[3] as i32) << 12) | ((d[4] as i32) << 4) | ((d[5] as i32) >> 4);
        let v1 = (((at >> 3) - ((self.t1 as i32) << 1)) * (self.t2 as i32)) >> 11;
        let v2 = (((((at >> 4) - (self.t1 as i32)) * ((at >> 4) - (self.t1 as i32))) >> 12)
            * (self.t3 as i32))
            >> 14;
        let fine = v1 + v2;
        let mut a = fine as f64 / 2.0 - 64000.0;
        let mut b = a * a * (self.p6 as f64) / 32768.0;
        b += a * (self.p5 as f64) * 2.0;
        b = b / 4.0 + (self.p4 as f64) * 65536.0;
        a = ((self.p3 as f64) * a * a / 524288.0 + (self.p2 as f64) * a) / 524288.0;
        a = (1.0 + a / 32768.0) * (self.p1 as f64);
        if a == 0.0 {
            anyhow::bail!("BMP280 invalid calibration");
        }
        let mut p = 1048576.0 - (ap as f64);
        p = (p - b / 4096.0) * 6250.0 / a;
        let x = (self.p9 as f64) * p * p / 2147483648.0;
        let y = p * (self.p8 as f64) / 32768.0;
        p += (x + y + (self.p7 as f64)) / 16.0;
        Ok((p / 100.0) as f32)
    }
}
