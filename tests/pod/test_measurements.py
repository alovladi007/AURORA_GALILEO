"""Tests for POD measurements."""

import pytest
import numpy as np
from pod.measurements import (
    GNSSMeasurement,
    dual_frequency_ionosphere_correction,
    troposphere_correction,
    gnss_geometric_range,
)


def test_dual_frequency_correction():
    """Test ionosphere-free combination."""
    P1 = 23000000.0  # 23,000 km
    P2 = 23000010.0  # 10m ionospheric delay on L2

    P_IF, iono_delay = dual_frequency_ionosphere_correction(P1, P2)

    # Should remove first-order ionosphere
    assert isinstance(P_IF, float)
    assert isinstance(iono_delay, float)
    assert abs(iono_delay) < 20.0  # meters


def test_troposphere_correction():
    """Test tropospheric delay model."""
    elevation = np.deg2rad(30)  # 30 degrees

    delay = troposphere_correction(elevation)

    # Should be a few meters at 30° elevation
    assert 1.0 < delay < 10.0


def test_geometric_range():
    """Test range computation."""
    receiver = np.array([6371000.0, 0.0, 0.0])
    satellite = np.array([6371000.0 + 400000.0, 0.0, 0.0])

    rho, los = gnss_geometric_range(receiver, satellite)

    assert abs(rho - 400000.0) < 1.0
    np.testing.assert_array_almost_equal(los, [1, 0, 0])


def test_gnss_measurement_creation():
    """Test measurement dataclass."""
    meas = GNSSMeasurement(
        time=0.0,
        satellite_id=1,
        pseudorange_L1=23000000.0,
        sat_position=np.array([26000000.0, 0, 0]),
    )

    assert meas.time == 0.0
    assert meas.satellite_id == 1
    assert meas.sat_position.shape == (3,)
