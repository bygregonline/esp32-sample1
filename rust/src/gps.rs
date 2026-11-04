use heapless::String;

const LINE_CAPACITY: usize = 96;
const FIX_TIMEOUT_MS: u32 = 10_000;

#[derive(Clone, Copy)]
enum Update {
    Fix(f32, f32, Option<u8>),
    Lost(Option<u8>),
}

pub struct NmeaParser {
    line: String<LINE_CAPACITY>,
    pub latitude: Option<f32>,
    pub longitude: Option<f32>,
    pub satellites: Option<u8>,
    pub fix_valid: bool,
    last_fix_ms: Option<u32>,
}

impl NmeaParser {
    pub const fn new() -> Self {
        Self {
            line: String::new(),
            latitude: None,
            longitude: None,
            satellites: None,
            fix_valid: false,
            last_fix_ms: None,
        }
    }

    pub fn feed(&mut self, bytes: &[u8], now_ms: u32) {
        for &byte in bytes {
            match byte {
                b'\n' => {
                    if let Some(update) = parse_sentence(self.line.as_str()) {
                        match update {
                            Update::Fix(latitude, longitude, satellites) => {
                                self.latitude = Some(latitude);
                                self.longitude = Some(longitude);
                                self.satellites = satellites.or(self.satellites);
                                self.fix_valid = true;
                                self.last_fix_ms = Some(now_ms);
                            }
                            Update::Lost(satellites) => {
                                self.satellites = satellites.or(self.satellites);
                                self.fix_valid = false;
                            }
                        }
                    }
                    self.line.clear();
                }
                b'\r' => {}
                0x20..=0x7e => {
                    if self.line.push(byte as char).is_err() {
                        self.line.clear();
                    }
                }
                _ => self.line.clear(),
            }
        }
    }

    pub fn has_recent_fix(&self, now_ms: u32) -> bool {
        self.fix_valid
            && self
                .last_fix_ms
                .map(|last| now_ms.wrapping_sub(last) <= FIX_TIMEOUT_MS)
                .unwrap_or(false)
    }
}

fn parse_sentence(line: &str) -> Option<Update> {
    if !line.starts_with('$') {
        return None;
    }

    let star = line.find('*').unwrap_or(line.len());
    if star < 2 {
        return None;
    }
    if star < line.len() && !checksum_is_valid(line, star) {
        return None;
    }

    let body = line.get(1..star)?;
    let mut fields = body.split(',');
    let sentence = fields.next()?;

    if sentence.ends_with("RMC") {
        let _time = fields.next()?;
        let status = fields.next()?;
        if status != "A" {
            return Some(Update::Lost(None));
        }
        let latitude = coordinate(fields.next()?, fields.next()?, 2)?;
        let longitude = coordinate(fields.next()?, fields.next()?, 3)?;
        return Some(Update::Fix(latitude, longitude, None));
    }

    if sentence.ends_with("GGA") {
        let _time = fields.next()?;
        let latitude_text = fields.next()?;
        let north_south = fields.next()?;
        let longitude_text = fields.next()?;
        let east_west = fields.next()?;
        let quality = fields.next()?.parse::<u8>().ok()?;
        let satellites = fields.next()?.parse::<u8>().ok();
        if quality == 0 {
            return Some(Update::Lost(satellites));
        }
        let latitude = coordinate(latitude_text, north_south, 2)?;
        let longitude = coordinate(longitude_text, east_west, 3)?;
        return Some(Update::Fix(latitude, longitude, satellites));
    }

    None
}

fn checksum_is_valid(line: &str, star: usize) -> bool {
    let bytes = line.as_bytes();
    if star + 2 >= bytes.len() {
        return false;
    }
    let mut checksum = 0u8;
    for byte in &bytes[1..star] {
        checksum ^= *byte;
    }
    let Some(high) = hex_nibble(bytes[star + 1]) else {
        return false;
    };
    let Some(low) = hex_nibble(bytes[star + 2]) else {
        return false;
    };
    checksum == (high << 4) | low
}

fn hex_nibble(byte: u8) -> Option<u8> {
    match byte {
        b'0'..=b'9' => Some(byte - b'0'),
        b'A'..=b'F' => Some(byte - b'A' + 10),
        b'a'..=b'f' => Some(byte - b'a' + 10),
        _ => None,
    }
}

fn coordinate(value: &str, hemisphere: &str, degree_digits: usize) -> Option<f32> {
    if value.len() <= degree_digits {
        return None;
    }
    let degrees = value.get(..degree_digits)?.parse::<f32>().ok()?;
    let minutes = value.get(degree_digits..)?.parse::<f32>().ok()?;
    let mut result = degrees + minutes / 60.0;
    if hemisphere == "S" || hemisphere == "W" {
        result = -result;
    }
    Some(result)
}

#[cfg(test)]
mod nmea {
    use super::*;

    fn feed(p: &mut NmeaParser, s: &str) {
        p.feed(s.as_bytes(), 0);
    }

    #[test]
    fn rmc_valid_sets_fix() {
        let mut p = NmeaParser::new();
        feed(
            &mut p,
            "$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A\r\n",
        );
        assert!(p.fix_valid);
        assert!(p.latitude.is_some());
        assert!(p.longitude.is_some());
    }

    #[test]
    fn rmc_latitude_conversion() {
        let mut p = NmeaParser::new();
        feed(
            &mut p,
            "$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A\r\n",
        );
        let lat = p.latitude.unwrap();
        // 48°07.038′ N → 48 + 7.038/60 ≈ 48.11730
        assert!((lat - 48.1173_f32).abs() < 0.001, "got {}", lat);
    }

    #[test]
    fn rmc_longitude_conversion() {
        let mut p = NmeaParser::new();
        feed(
            &mut p,
            "$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A\r\n",
        );
        let lon = p.longitude.unwrap();
        // 011°31.000′ E → 11 + 31/60 ≈ 11.5167
        assert!((lon - 11.5167_f32).abs() < 0.001, "got {}", lon);
    }

    #[test]
    fn rmc_south_negative_latitude() {
        let mut p = NmeaParser::new();
        feed(
            &mut p,
            "$GPRMC,000000,A,1926.556,S,09908.000,W,0,0,010101,,*11\r\n",
        );
        assert!(p.latitude.unwrap() < 0.0);
    }

    #[test]
    fn rmc_west_negative_longitude() {
        let mut p = NmeaParser::new();
        feed(
            &mut p,
            "$GPRMC,000000,A,1926.556,S,09908.000,W,0,0,010101,,*11\r\n",
        );
        assert!(p.longitude.unwrap() < 0.0);
    }

    #[test]
    fn rmc_void_status_clears_fix() {
        let mut p = NmeaParser::new();
        feed(
            &mut p,
            "$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A\r\n",
        );
        assert!(p.fix_valid);
        feed(
            &mut p,
            "$GPRMC,123520,V,4807.038,N,01131.000,E,,,230394,,*11\r\n",
        );
        assert!(!p.fix_valid);
    }

    #[test]
    fn rmc_bad_checksum_ignored() {
        let mut p = NmeaParser::new();
        feed(
            &mut p,
            "$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*FF\r\n",
        );
        assert!(!p.fix_valid);
    }

    #[test]
    fn gnrmc_also_parsed() {
        let mut p = NmeaParser::new();
        feed(
            &mut p,
            "$GNRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*74\r\n",
        );
        assert!(p.fix_valid);
    }

    #[test]
    fn gga_sets_satellites() {
        let mut p = NmeaParser::new();
        feed(
            &mut p,
            "$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47\r\n",
        );
        assert_eq!(p.satellites, Some(8));
    }

    #[test]
    fn gga_quality_zero_no_fix() {
        let mut p = NmeaParser::new();
        feed(
            &mut p,
            "$GPGGA,123519,4807.038,N,01131.000,E,0,00,,,,,,,*66\r\n",
        );
        assert!(!p.fix_valid);
    }

    #[test]
    fn fix_timeout_expired() {
        let mut p = NmeaParser::new();
        p.feed(
            b"$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A\r\n",
            0,
        );
        // 10 001 ms later — past the 10 000 ms timeout
        assert!(!p.has_recent_fix(10_001));
    }

    #[test]
    fn fix_within_timeout() {
        let mut p = NmeaParser::new();
        p.feed(
            b"$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A\r\n",
            1_000,
        );
        assert!(p.has_recent_fix(5_000));
    }

    #[test]
    fn split_feed_buffered() {
        let s = b"$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A\r\n";
        let mid = s.len() / 2;
        let mut p = NmeaParser::new();
        p.feed(&s[..mid], 0);
        assert!(!p.fix_valid, "should not have fix on partial sentence");
        p.feed(&s[mid..], 0);
        assert!(p.fix_valid);
    }

    #[test]
    fn monitor_state_interval_clamp() {
        use crate::monitor_state::{
            MonitorState, SENSOR_INTERVAL_MAX_SECS, SENSOR_INTERVAL_MIN_SECS,
        };
        let state = MonitorState::new();
        state.set_sensor_interval(1); // below min → clamped to MIN
        assert_eq!(
            state.snapshot().sensor_interval_secs,
            SENSOR_INTERVAL_MIN_SECS
        );
        state.set_sensor_interval(9999); // above max → clamped to MAX
        assert_eq!(
            state.snapshot().sensor_interval_secs,
            SENSOR_INTERVAL_MAX_SECS
        );
        state.set_sensor_interval(30); // valid
        assert_eq!(state.snapshot().sensor_interval_secs, 30);
    }
}
