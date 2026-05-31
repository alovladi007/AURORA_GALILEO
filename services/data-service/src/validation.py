"""
Data Validation & Quality Control
=================================

Validation and QC for incoming telemetry and gravity measurements. Performs
range checks, physical-plausibility checks and simple outlier detection,
returning structured results with quality flags.

Quality flag convention (bitmask-friendly integers):
  0 = good
  1 = out-of-range value clamped/flagged
  2 = physically implausible
  4 = statistical outlier
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

# Physical / sensor bounds.
LAT_RANGE = (-90.0, 90.0)
LON_RANGE = (-180.0, 180.0)
ALT_RANGE = (-1.0e3, 2.0e6)          # metres (below sea level to high orbit)
VELOCITY_MAX = 1.2e4                 # m/s, generous LEO/escape bound
TEMP_RANGE = (-273.15, 200.0)        # deg C
BATTERY_RANGE = (0.0, 100.0)         # percent
# Gravity anomalies are reported in milligal (mGal). Free-air/Bouguer anomalies
# on Earth fall well within +/- 500 mGal; satellite gradiometry is smaller.
GRAVITY_VALUE_RANGE = (-1000.0, 1000.0)
UNCERTAINTY_MAX = 1000.0

QF_GOOD = 0
QF_OUT_OF_RANGE = 1
QF_IMPLAUSIBLE = 2
QF_OUTLIER = 4


@dataclass
class ValidationResult:
    valid: bool
    quality_flag: int = QF_GOOD
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def add_error(self, msg: str, flag: int) -> None:
        self.errors.append(msg)
        self.quality_flag |= flag
        self.valid = False

    def add_warning(self, msg: str, flag: int) -> None:
        self.warnings.append(msg)
        self.quality_flag |= flag


def _check_range(value, bounds, name, result: ValidationResult, fatal=False):
    lo, hi = bounds
    if value is None:
        return
    if not (lo <= value <= hi):
        msg = f"{name}={value} out of range [{lo}, {hi}]"
        if fatal:
            result.add_error(msg, QF_OUT_OF_RANGE)
        else:
            result.add_warning(msg, QF_OUT_OF_RANGE)


def validate_telemetry(request) -> ValidationResult:
    """Validate a SatelliteTelemetry ingest request."""
    result = ValidationResult(valid=True)

    if not request.satellite_id:
        result.add_error("satellite_id is required", QF_IMPLAUSIBLE)

    loc = request.location
    _check_range(loc.latitude, LAT_RANGE, "latitude", result, fatal=True)
    _check_range(loc.longitude, LON_RANGE, "longitude", result, fatal=True)
    _check_range(loc.altitude, ALT_RANGE, "altitude", result)

    speed = (request.velocity_x ** 2 + request.velocity_y ** 2
             + request.velocity_z ** 2) ** 0.5
    if speed > VELOCITY_MAX:
        result.add_warning(f"speed={speed:.1f} m/s exceeds {VELOCITY_MAX}",
                           QF_IMPLAUSIBLE)

    _check_range(request.temperature, TEMP_RANGE, "temperature", result)
    _check_range(request.battery_level, BATTERY_RANGE, "battery_level", result)
    return result


def validate_gravity(request) -> ValidationResult:
    """Validate a GravityMeasurement ingest request (scalar mGal value)."""
    result = ValidationResult(valid=True)

    if not request.satellite_id:
        result.add_error("satellite_id is required", QF_IMPLAUSIBLE)

    loc = request.location
    _check_range(loc.latitude, LAT_RANGE, "latitude", result, fatal=True)
    _check_range(loc.longitude, LON_RANGE, "longitude", result, fatal=True)
    _check_range(loc.altitude, ALT_RANGE, "altitude", result)

    _check_range(request.gravity_value, GRAVITY_VALUE_RANGE, "gravity_value", result)

    if request.uncertainty < 0 or request.uncertainty > UNCERTAINTY_MAX:
        result.add_warning(
            f"uncertainty={request.uncertainty} outside [0, {UNCERTAINTY_MAX}]",
            QF_OUT_OF_RANGE,
        )
    return result


class RunningOutlierDetector:
    """Online z-score outlier detector (Welford running mean/variance)."""

    def __init__(self, z_threshold: float = 4.0):
        self.n = 0
        self.mean = 0.0
        self.m2 = 0.0
        self.z_threshold = z_threshold

    def check(self, value: float) -> bool:
        """Return True if ``value`` is an outlier given history seen so far,
        then update running statistics."""
        is_outlier = False
        if self.n >= 30:
            std = (self.m2 / self.n) ** 0.5
            if std > 0 and abs(value - self.mean) / std > self.z_threshold:
                is_outlier = True
        # Welford update.
        self.n += 1
        delta = value - self.mean
        self.mean += delta / self.n
        self.m2 += delta * (value - self.mean)
        return is_outlier
