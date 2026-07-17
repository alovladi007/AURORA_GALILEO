"""
Tests for timescale conversions.
"""

import pytest
import numpy as np
from datetime import datetime

from gtime.timescales import (
    TimeScale,
    tai_to_tt,
    tt_to_tai,
    tai_to_utc,
    utc_to_tai,
    tai_to_gpst,
    gpst_to_tai,
    get_leap_second_offset,
)


class TestTimeScaleConversions:
    """Test basic timescale conversion functions."""

    def test_tai_tt_roundtrip(self):
        """Test TAI ↔ TT round-trip conversion."""
        tai_mjd, tai_sec = 59000.0, 43200.0

        # TAI → TT → TAI
        tt_mjd, tt_sec = tai_to_tt(tai_mjd, tai_sec)
        tai_mjd2, tai_sec2 = tt_to_tai(tt_mjd, tt_sec)

        assert abs(tai_mjd2 - tai_mjd) < 1e-10
        assert abs(tai_sec2 - tai_sec) < 1e-10

    def test_tt_offset(self):
        """Test TT - TAI = 32.184 seconds."""
        tai_mjd, tai_sec = 59000.0, 0.0
        tt_mjd, tt_sec = tai_to_tt(tai_mjd, tai_sec)

        # Should add 32.184 seconds
        assert abs(tt_sec - 32.184) < 1e-10

    def test_tai_gpst_roundtrip(self):
        """Test TAI ↔ GPST round-trip conversion."""
        tai_mjd, tai_sec = 59000.0, 43200.0

        gpst_mjd, gpst_sec = tai_to_gpst(tai_mjd, tai_sec)
        tai_mjd2, tai_sec2 = gpst_to_tai(gpst_mjd, gpst_sec)

        assert abs(tai_mjd2 - tai_mjd) < 1e-10
        assert abs(tai_sec2 - tai_sec) < 1e-10

    def test_gpst_offset(self):
        """Test GPST = TAI - 19 seconds."""
        tai_mjd, tai_sec = 59000.0, 30.0
        gpst_mjd, gpst_sec = tai_to_gpst(tai_mjd, tai_sec)

        # GPST should be 19 seconds behind TAI
        total_tai = tai_mjd * 86400 + tai_sec
        total_gpst = gpst_mjd * 86400 + gpst_sec

        assert abs((total_tai - total_gpst) - 19.0) < 1e-10

    def test_leap_seconds(self):
        """Test leap second handling."""
        # MJD 57754 = 2017-01-01, UTC-TAI = -37s
        offset = get_leap_second_offset(57754.0)
        assert offset == -37.0

        # MJD 57000 = 2014-12-09 (before the 2015-07-01 leap), UTC-TAI = -35s
        offset = get_leap_second_offset(57000.0)
        assert offset == -35.0

        # MJD 57300 = 2015-10-05 (after the 2015-07-01 leap), UTC-TAI = -36s
        offset = get_leap_second_offset(57300.0)
        assert offset == -36.0

    def test_utc_tai_conversion(self):
        """Test UTC ↔ TAI conversion with leap seconds."""
        # Use a date with known leap seconds
        utc_mjd, utc_sec = 57754.0, 0.0  # 2017-01-01 00:00:00 UTC

        # Convert to TAI
        tai_mjd, tai_sec = utc_to_tai(utc_mjd, utc_sec)

        # UTC should be 37 seconds behind TAI at this date
        # So TAI = UTC + 37
        assert abs(tai_sec - 37.0) < 1e-10

        # Round trip
        utc_mjd2, utc_sec2 = tai_to_utc(tai_mjd, tai_sec)
        assert abs(utc_mjd2 - utc_mjd) < 1e-10
        assert abs(utc_sec2 - utc_sec) < 1e-10


class TestTimeScaleClass:
    """Test TimeScale dataclass."""

    def test_timescale_to_tai(self):
        """Test conversion to TAI."""
        ts = TimeScale(mjd=59000.0, seconds=0.0, scale='TT')
        tai = ts.to_tai()

        assert tai.scale == 'TAI'
        # TT = TAI + 32.184, so TAI = TT - 32.184
        assert abs(tai.seconds - (-32.184)) < 1e-10

    def test_timescale_to_tt(self):
        """Test conversion to TT."""
        ts = TimeScale(mjd=59000.0, seconds=0.0, scale='TAI')
        tt = ts.to_tt()

        assert tt.scale == 'TT'
        assert abs(tt.seconds - 32.184) < 1e-10

    def test_timescale_to_gpst(self):
        """Test conversion to GPST."""
        ts = TimeScale(mjd=59000.0, seconds=19.0, scale='TAI')
        gpst = ts.to_gpst()

        assert gpst.scale == 'GPST'
        # GPST = TAI - 19
        assert abs(gpst.seconds - 0.0) < 1e-10

    def test_timescale_to_utc(self):
        """Test conversion to UTC."""
        # TAI at MJD 57754 (2017-01-01)
        ts = TimeScale(mjd=57754.0, seconds=37.0, scale='TAI')
        utc = ts.to_utc()

        assert utc.scale == 'UTC'
        # UTC = TAI - 37 at this date
        assert abs(utc.seconds - 0.0) < 1e-10

    def test_timescale_from_datetime(self):
        """Test creation from datetime."""
        dt = datetime(2020, 1, 1, 12, 0, 0)
        ts = TimeScale.from_datetime(dt, scale='UTC')

        assert ts.scale == 'UTC'
        # Check round-trip
        dt2 = ts.to_datetime()
        assert abs((dt2 - dt).total_seconds()) < 1.0

    def test_timescale_total_seconds(self):
        """Test total_seconds method."""
        ts = TimeScale(mjd=1.0, seconds=3600.0, scale='TAI')
        total = ts.total_seconds()

        expected = 1.0 * 86400.0 + 3600.0
        assert abs(total - expected) < 1e-10


class TestDayRollover:
    """Test handling of day rollovers."""

    def test_positive_rollover(self):
        """Test rollover when seconds > 86400."""
        tai_mjd, tai_sec = 59000.0, 86400.0 + 3600.0  # 1 day + 1 hour

        tt_mjd, tt_sec = tai_to_tt(tai_mjd, tai_sec)

        # Should rollover to next day
        assert tt_mjd == 59001.0
        assert abs(tt_sec - (3600.0 + 32.184)) < 1e-10

    def test_negative_rollover(self):
        """Test rollover when seconds < 0."""
        tai_mjd, tai_sec = 59000.0, -3600.0  # -1 hour

        gpst_mjd, gpst_sec = tai_to_gpst(tai_mjd, tai_sec)

        # Should rollover to previous day
        assert gpst_mjd == 58999.0
        expected_sec = 86400.0 - 3600.0 - 19.0
        assert abs(gpst_sec - expected_sec) < 1e-10


@pytest.mark.parametrize("scale1,scale2", [
    ('TAI', 'TT'),
    ('TAI', 'GPST'),
    ('TAI', 'UTC'),
    ('TT', 'GPST'),
])
def test_all_conversion_roundtrips(scale1, scale2):
    """Test round-trip conversions between all time scales."""
    ts1 = TimeScale(mjd=59000.0, seconds=43200.0, scale=scale1)

    # Convert to scale2
    if scale2 == 'TAI':
        ts2 = ts1.to_tai()
    elif scale2 == 'TT':
        ts2 = ts1.to_tt()
    elif scale2 == 'GPST':
        ts2 = ts1.to_gpst()
    elif scale2 == 'UTC':
        ts2 = ts1.to_utc()

    # Convert back to scale1
    if scale1 == 'TAI':
        ts3 = ts2.to_tai()
    elif scale1 == 'TT':
        ts3 = ts2.to_tt()
    elif scale1 == 'GPST':
        ts3 = ts2.to_gpst()
    elif scale1 == 'UTC':
        ts3 = ts2.to_utc()

    # Should match original
    assert abs(ts3.mjd - ts1.mjd) < 1e-10
    assert abs(ts3.seconds - ts1.seconds) < 1e-6  # 1 microsecond tolerance
