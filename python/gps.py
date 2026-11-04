"""Parser ligero para sentencias NMEA RMC y GGA de un GPS NEO-6M."""

from time import ticks_diff, ticks_ms


def _coordinate(value, hemisphere, degree_digits):
    if not value or not hemisphere:
        return None
    try:
        degrees = int(value[:degree_digits])
        minutes = float(value[degree_digits:])
    except ValueError:
        return None
    result = degrees + minutes / 60.0
    if hemisphere in ("S", "W"):
        result = -result
    return result


class NMEAParser:
    def __init__(self):
        self._buffer = bytearray()
        self.latitude = None
        self.longitude = None
        self.satellites = None
        self.fix_valid = False
        self.last_fix_ms = None

    def feed(self, data):
        if not data:
            return
        self._buffer.extend(data)
        while True:
            end = self._buffer.find(b"\n")
            if end < 0:
                # Evita conservar basura si se pierde una separacion NMEA.
                if len(self._buffer) > 160:
                    self._buffer = self._buffer[-80:]
                return
            raw = bytes(self._buffer[:end]).strip()
            del self._buffer[:end + 1]
            self._parse_line(raw)

    def _parse_line(self, raw):
        if not raw.startswith(b"$"):
            return
        star = raw.find(b"*")
        if star >= 0:
            checksum = 0
            for byte in raw[1:star]:
                checksum ^= byte
            try:
                expected = int(raw[star + 1:star + 3], 16)
            except ValueError:
                return
            if checksum != expected:
                return

        try:
            fields = raw[1:star if star >= 0 else None].decode().split(",")
        except Exception:
            return
        if not fields:
            return

        sentence = fields[0][-3:]
        if sentence == "RMC" and len(fields) > 6:
            if fields[2] != "A":
                self.fix_valid = False
                return
            latitude = _coordinate(fields[3], fields[4], 2)
            longitude = _coordinate(fields[5], fields[6], 3)
            self._set_fix(latitude, longitude)
        elif sentence == "GGA" and len(fields) > 7:
            try:
                quality = int(fields[6] or "0")
                self.satellites = int(fields[7] or "0")
            except ValueError:
                return
            if quality <= 0:
                self.fix_valid = False
                return
            latitude = _coordinate(fields[2], fields[3], 2)
            longitude = _coordinate(fields[4], fields[5], 3)
            self._set_fix(latitude, longitude)

    def _set_fix(self, latitude, longitude):
        if latitude is None or longitude is None:
            return
        self.latitude = latitude
        self.longitude = longitude
        self.fix_valid = True
        self.last_fix_ms = ticks_ms()

    def has_recent_fix(self, timeout_ms=10000):
        if not self.fix_valid or self.last_fix_ms is None:
            return False
        return ticks_diff(ticks_ms(), self.last_fix_ms) <= timeout_ms
