"""
Relativity & Timing Reference Tests (Phase 1 W1.2 acceptance)
==============================================================

Validates the gtime fixes against independent physical references.
"""

import numpy as np
import pytest

from gtime.relativity import (
    C,
    GM_EARTH,
    redshift_doppler,
    relativistic_range_correction,
    relativistic_time_correction,
)
from gtime.timescales import get_leap_second_offset, tai_to_utc
from gtime.clock import WhiteNoiseClock, FlickerNoiseClock, allan_deviation


class TestGPSClockRate:
    """The canonical GPS test: a satellite clock at 20,200 km altitude
    runs fast by ~38.6 microseconds/day relative to the geoid
    (gravitational +45.7 us/day, velocity -7.1 us/day)."""

    def test_combined_rate_38_us_per_day(self):
        r_gps = 26_571_000.0  # m (20200 km altitude + R_E)
        v_gps = np.sqrt(GM_EARTH / r_gps)  # circular orbital speed
        rate = relativistic_time_correction(r_gps, v_gps)
        us_per_day = rate * 86400.0 * 1e6
        # Standard value ~ +38.6 us/day when referenced to the geoid;
        # our reference surface is the mean-radius sphere, giving a
        # slightly different constant - accept 35-42 us/day.
        assert 35.0 < us_per_day < 42.0, us_per_day

    def test_gravitational_term_positive_velocity_negative(self):
        r_gps = 26_571_000.0
        v_gps = np.sqrt(GM_EARTH / r_gps)
        grav_only = relativistic_time_correction(r_gps, 0.0)
        vel_only = relativistic_time_correction(6371000.0, v_gps)  # at ref radius
        assert grav_only > 0.0, "higher clock must run fast"
        assert vel_only < 0.0, "moving clock must run slow"


class TestRedshiftDoppler:
    def test_uphill_photon_redshifts(self):
        """Emission low (r1), reception high (r2): f_rx < f_tx."""
        r1, r2 = 6.4e6, 2.6e7
        zero = np.zeros(3)
        ratio = redshift_doppler(r1, zero, r2, zero, np.array([0.0, 0.0, r2 - r1]))
        assert ratio < 1.0

    def test_downhill_photon_blueshifts(self):
        r1, r2 = 2.6e7, 6.4e6
        zero = np.zeros(3)
        ratio = redshift_doppler(r1, zero, r2, zero, np.array([0.0, 0.0, r2 - r1]))
        assert ratio > 1.0

    def test_receding_receiver_redshifts(self):
        r = 7.0e6
        r12 = np.array([1.0, 0.0, 0.0])
        v_rx_receding = np.array([1000.0, 0.0, 0.0])  # along emitter->rx
        ratio = redshift_doppler(r, np.zeros(3), r, v_rx_receding, r12)
        assert ratio < 1.0, "receding receiver must see lower frequency"
        # magnitude ~ v/c
        assert ratio == pytest.approx(1.0 - 1000.0 / C, abs=1e-9)


class TestRangeCorrection:
    def test_eccentricity_correction_form(self):
        """The periodic correction is -2 r.v/c: zero for circular orbits
        (r perpendicular to v), maximal magnitude when aligned."""
        r_tx = np.array([2.6571e7, 0.0, 0.0])
        r_rx = np.array([6.4e6, 0.0, 0.0])
        v_circ = np.array([0.0, 3874.0, 0.0])  # r . v = 0
        corr_circ = relativistic_range_correction(r_tx, r_rx,
                                                  v_tx=v_circ, v_rx=None)
        # Circular: only Shapiro remains (positive, centimeter level)
        from gtime.relativity import shapiro_delay
        rho = np.linalg.norm(r_tx - r_rx)
        shapiro = shapiro_delay(np.linalg.norm(r_tx), np.linalg.norm(r_rx), rho)
        assert float(corr_circ) == pytest.approx(float(shapiro), rel=1e-9)

        # Radial velocity component adds -2 r.v/c
        v_radial = np.array([100.0, 0.0, 0.0])
        corr = relativistic_range_correction(r_tx, r_rx,
                                             v_tx=v_circ + v_radial, v_rx=None)
        expected_ecc = -2.0 * (2.6571e7 * 100.0) / C
        assert float(corr - shapiro) == pytest.approx(expected_ecc, rel=1e-9)


class TestLeapSecondBoundary:
    def test_tai_to_utc_near_boundary(self):
        """Just after the 2017-01-01 leap (UTC MJD 57754), TAI-UTC=37.
        A TAI epoch in the first 37 s of TAI day 57754 corresponds to
        UTC still on 2016-12-31 with offset -36->-37 handling."""
        # TAI = 57754 00:00:10 is BEFORE the boundary in UTC terms:
        # the corresponding UTC epoch is 2016-12-31 23:59:34 (offset
        # -36, since -37 only applies from UTC 2017-01-01). This is the
        # consistent inverse of utc_to_tai.
        utc_mjd, utc_sec = tai_to_utc(57754.0, 10.0)
        assert utc_mjd == pytest.approx(57753.0)
        assert utc_sec == pytest.approx(86400.0 - 26.0)
        # Round-trip closes
        from gtime.timescales import utc_to_tai
        tai_mjd, tai_sec = utc_to_tai(utc_mjd, utc_sec)
        assert tai_mjd == pytest.approx(57754.0)
        assert tai_sec == pytest.approx(10.0)

    def test_offsets(self):
        assert get_leap_second_offset(57754.0) == -37.0
        assert get_leap_second_offset(57300.0) == -36.0


class TestClockNoiseConsistency:
    """Generated noise must reproduce its own theoretical Allan
    deviation - the generator and the formula must agree."""

    def test_white_fm_adev_matches_theory(self):
        h0 = 1e-20
        clock = WhiteNoiseClock(h0)
        t = np.arange(0, 20000.0, 1.0)
        x = clock.generate_phase(t, seed=42)
        taus = np.array([1.0, 4.0, 16.0])
        _, measured = allan_deviation(x, 1.0, taus, overlapping=True)
        theory = clock.allan_deviation(taus)
        for m, th in zip(measured, theory):
            assert m == pytest.approx(th, rel=0.25)

    def test_white_fm_slope_minus_half(self):
        clock = WhiteNoiseClock(1e-20)
        t = np.arange(0, 40000.0, 1.0)
        x = clock.generate_phase(t, seed=7)
        taus = np.array([1.0, 100.0])
        _, a = allan_deviation(x, 1.0, taus, overlapping=True)
        slope = np.log10(a[1] / a[0]) / np.log10(100.0)
        assert slope == pytest.approx(-0.5, abs=0.1)

    def test_flicker_fm_adev_flat(self):
        clock = FlickerNoiseClock(1e-22, f_low=1e-5, f_high=0.5)
        t = np.arange(0, 40000.0, 1.0)
        x = clock.generate_phase(t, seed=11)
        taus = np.array([10.0, 100.0, 1000.0])
        _, a = allan_deviation(x, 1.0, taus, overlapping=True)
        # Flicker floor: ADEV varies by less than a factor 2 across
        # two decades of tau (vs sqrt(100)=10x for white FM)
        assert max(a) / min(a) < 2.0
