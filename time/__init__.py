"""
GALILEO V2.0 - Time Module
==========================

Relativistic timing, time systems, and clock modeling for precision
space-based gravimetry.

Modules:
    timescales: TAI, TT, UTC, GPST conversions
    relativity: Relativistic corrections and Shapiro delay
    clock: Clock models (flicker, random walk, Allan deviation)
    discipline: Clock discipline via GPSDO and dual-clock fusion
"""

from time.timescales import (
    TimeScale,
    tai_to_tt,
    tt_to_tai,
    tai_to_utc,
    utc_to_tai,
    tai_to_gpst,
    gpst_to_tai,
    utc_to_gpst,
    gpst_to_utc,
)

from time.relativity import (
    relativistic_time_correction,
    relativistic_range_correction,
    shapiro_delay,
    gravitational_time_dilation,
    special_relativistic_correction,
)

from time.clock import (
    ClockModel,
    WhiteNoiseClock,
    FlickerNoiseClock,
    RandomWalkClock,
    allan_deviation,
    hadamard_variance,
    overlapping_allan_deviation,
    modified_allan_deviation,
)

from time.discipline import (
    GPSDOModel,
    DualClockFusion,
    clock_discipline_ekf,
)

__all__ = [
    # Timescales
    "TimeScale",
    "tai_to_tt",
    "tt_to_tai",
    "tai_to_utc",
    "utc_to_tai",
    "tai_to_gpst",
    "gpst_to_tai",
    "utc_to_gpst",
    "gpst_to_utc",
    # Relativity
    "relativistic_time_correction",
    "relativistic_range_correction",
    "shapiro_delay",
    "gravitational_time_dilation",
    "special_relativistic_correction",
    # Clock models
    "ClockModel",
    "WhiteNoiseClock",
    "FlickerNoiseClock",
    "RandomWalkClock",
    "allan_deviation",
    "hadamard_variance",
    "overlapping_allan_deviation",
    "modified_allan_deviation",
    # Discipline
    "GPSDOModel",
    "DualClockFusion",
    "clock_discipline_ekf",
]

__version__ = "0.1.0"
