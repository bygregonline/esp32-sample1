"""Tests for the MicroPython NMEA parser (python/gps.py).

These tests run on host Python 3 — no ESP32 hardware needed.
The parser is pure Python with no MicroPython-specific imports.
"""

import sys
from pathlib import Path

# Make python/ importable without installing anything
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "python"))

import gps  # noqa: E402
from gps import NMEAParser  # noqa: E402


def _feed(parser: NMEAParser, sentence: str) -> None:
    parser.feed(sentence.encode())


# ── RMC ──────────────────────────────────────────────────────────────────


class TestRMC:
    def test_valid_rmc_sets_fix(self):
        p = NMEAParser()
        _feed(p, "$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A\r\n")
        assert p.fix_valid
        assert p.latitude is not None
        assert p.longitude is not None

    def test_rmc_latitude_decimal(self):
        p = NMEAParser()
        _feed(p, "$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A\r\n")
        # 48°07.038' N = 48 + 7.038/60 ≈ 48.1173
        assert abs(p.latitude - 48.1173) < 0.001

    def test_rmc_longitude_decimal(self):
        p = NMEAParser()
        _feed(p, "$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A\r\n")
        # 011°31.000' E = 11 + 31/60 ≈ 11.5167
        assert abs(p.longitude - 11.5167) < 0.001

    def test_rmc_south_negative_latitude(self):
        p = NMEAParser()
        _feed(p, "$GPRMC,123519,A,1926.556,S,09908.000,W,000.0,000.0,230394,000.0,E*79\r\n")
        assert p.latitude is not None and p.latitude < 0

    def test_rmc_west_negative_longitude(self):
        p = NMEAParser()
        _feed(p, "$GPRMC,123519,A,1926.556,S,09908.000,W,000.0,000.0,230394,000.0,E*79\r\n")
        assert p.longitude is not None and p.longitude < 0

    def test_rmc_invalid_status_clears_fix(self):
        p = NMEAParser()
        # First get a valid fix
        _feed(p, "$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A\r\n")
        assert p.fix_valid
        # Then receive void status
        _feed(p, "$GPRMC,123520,V,4807.038,N,01131.000,E,,,230394,,*00\r\n")
        assert not p.fix_valid

    def test_rmc_bad_checksum_ignored(self):
        p = NMEAParser()
        _feed(p, "$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*FF\r\n")
        assert not p.fix_valid

    def test_gnrmc_also_parsed(self):
        p = NMEAParser()
        _feed(p, "$GNRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*74\r\n")
        assert p.fix_valid


# ── GGA ──────────────────────────────────────────────────────────────────


class TestGGA:
    def test_valid_gga_sets_fix(self):
        p = NMEAParser()
        _feed(p, "$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47\r\n")
        assert p.fix_valid

    def test_gga_satellite_count(self):
        p = NMEAParser()
        _feed(p, "$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47\r\n")
        assert p.satellites == 8

    def test_gga_quality_zero_no_fix(self):
        p = NMEAParser()
        _feed(p, "$GPGGA,123519,4807.038,N,01131.000,E,0,00,,,,,,,*66\r\n")
        assert not p.fix_valid

    def test_gngga_also_parsed(self):
        p = NMEAParser()
        _feed(p, "$GNGGA,123519,4807.038,N,01131.000,E,1,09,0.9,545.4,M,46.9,M,,*58\r\n")
        assert p.fix_valid


# ── has_recent_fix ────────────────────────────────────────────────────────


class TestHasRecentFix:
    def test_no_fix_returns_false(self):
        p = NMEAParser()
        assert not p.has_recent_fix()

    def test_fix_within_timeout(self):
        p = NMEAParser()
        _feed(p, "$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A\r\n")
        assert p.has_recent_fix(timeout_ms=10_000)

    def test_fix_expired(self):
        p = NMEAParser()
        _feed(p, "$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A\r\n")
        # Manually expire the fix timestamp
        p.last_fix_ms = 0
        gps.ticks_ms = lambda: 20_000
        assert not p.has_recent_fix(timeout_ms=10_000)
        gps.ticks_ms = lambda: 1000  # restore the test clock


# ── Buffer handling ───────────────────────────────────────────────────────


class TestBufferHandling:
    def test_split_across_two_feeds(self):
        p = NMEAParser()
        sentence = "$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A\r\n"
        mid = len(sentence) // 2
        p.feed(sentence[:mid].encode())
        p.feed(sentence[mid:].encode())
        assert p.fix_valid

    def test_multiple_sentences_in_one_feed(self):
        p = NMEAParser()
        data = (
            "$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47\r\n"
            "$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A\r\n"
        )
        p.feed(data.encode())
        assert p.fix_valid
        assert p.satellites == 8

    def test_garbage_before_sentence(self):
        p = NMEAParser()
        data = b"\x00\xffinvalid garbage\r\n$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A\r\n"
        p.feed(data)
        assert p.fix_valid

    def test_empty_feed_no_crash(self):
        p = NMEAParser()
        p.feed(b"")
        p.feed(None)
        assert not p.fix_valid
