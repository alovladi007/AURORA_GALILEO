"""
Time Scale Conversions
======================

Implements conversions between TAI, TT, UTC, GPST with leap-second management.

Time scales:
- TAI: International Atomic Time
- TT: Terrestrial Time (TT = TAI + 32.184s)
- UTC: Coordinated Universal Time (TAI - UTC varies with leap seconds)
- GPST: GPS Time (continuous time; GPST = TAI - 19s)
"""

import numpy as np
from dataclasses import dataclass
from typing import Union, Optional
from datetime import datetime, timedelta
import bisect

# Constants
TT_MINUS_TAI = 32.184  # seconds
GPST_MINUS_TAI = -19.0  # seconds (GPS time is 19s behind TAI)

# Leap seconds table (UTC - TAI) in seconds
# Source: IERS Bulletin C
# Format: (MJD, UTC-TAI offset in seconds)
LEAP_SECONDS = [
    (41317.0, -10.0),  # 1972-01-01
    (41499.0, -11.0),  # 1972-07-01
    (41683.0, -12.0),  # 1973-01-01
    (42048.0, -13.0),  # 1974-01-01
    (42413.0, -14.0),  # 1975-01-01
    (42778.0, -15.0),  # 1976-01-01
    (43144.0, -16.0),  # 1977-01-01
    (43509.0, -17.0),  # 1978-01-01
    (43874.0, -18.0),  # 1979-01-01
    (44239.0, -19.0),  # 1980-01-01
    (44786.0, -20.0),  # 1981-07-01
    (45151.0, -21.0),  # 1982-07-01
    (45516.0, -22.0),  # 1983-07-01
    (46247.0, -23.0),  # 1985-07-01
    (47161.0, -24.0),  # 1988-01-01
    (47892.0, -25.0),  # 1990-01-01
    (48257.0, -26.0),  # 1991-01-01
    (48804.0, -27.0),  # 1992-07-01
    (49169.0, -28.0),  # 1993-07-01
    (49534.0, -29.0),  # 1994-07-01
    (50083.0, -30.0),  # 1996-01-01
    (50630.0, -31.0),  # 1997-07-01
    (51179.0, -32.0),  # 1999-01-01
    (53736.0, -33.0),  # 2006-01-01
    (54832.0, -34.0),  # 2009-01-01
    (56109.0, -35.0),  # 2012-07-01
    (57204.0, -36.0),  # 2015-07-01
    (57754.0, -37.0),  # 2017-01-01
]


@dataclass
class TimeScale:
    """
    Represents a time value in a specific time scale.

    Attributes:
        mjd: Modified Julian Date
        seconds: Fractional seconds within the day
        scale: Time scale identifier ('TAI', 'TT', 'UTC', 'GPST')
    """
    mjd: float
    seconds: float = 0.0
    scale: str = 'TAI'

    def to_tai(self) -> 'TimeScale':
        """Convert to TAI."""
        if self.scale == 'TAI':
            return self
        elif self.scale == 'TT':
            return TimeScale(self.mjd, self.seconds - TT_MINUS_TAI, 'TAI')
        elif self.scale == 'GPST':
            return TimeScale(self.mjd, self.seconds - GPST_MINUS_TAI, 'TAI')
        elif self.scale == 'UTC':
            offset = get_leap_second_offset(self.mjd)
            return TimeScale(self.mjd, self.seconds - offset, 'TAI')
        else:
            raise ValueError(f"Unknown time scale: {self.scale}")

    def to_tt(self) -> 'TimeScale':
        """Convert to TT."""
        tai = self.to_tai()
        return TimeScale(tai.mjd, tai.seconds + TT_MINUS_TAI, 'TT')

    def to_gpst(self) -> 'TimeScale':
        """Convert to GPST."""
        tai = self.to_tai()
        return TimeScale(tai.mjd, tai.seconds + GPST_MINUS_TAI, 'GPST')

    def to_utc(self) -> 'TimeScale':
        """Convert to UTC."""
        tai = self.to_tai()
        offset = get_leap_second_offset(tai.mjd)
        return TimeScale(tai.mjd, tai.seconds + offset, 'UTC')

    def total_seconds(self) -> float:
        """Total time in seconds since MJD epoch."""
        return self.mjd * 86400.0 + self.seconds

    @classmethod
    def from_datetime(cls, dt: datetime, scale: str = 'UTC') -> 'TimeScale':
        """Create TimeScale from Python datetime."""
        # Convert datetime to MJD
        # MJD = JD - 2400000.5
        # JD for datetime: (dt - 1858-11-17 00:00:00).total_seconds() / 86400 + 2400000.5
        mjd_epoch = datetime(1858, 11, 17, 0, 0, 0)
        delta = dt - mjd_epoch
        mjd = delta.total_seconds() / 86400.0

        day_mjd = int(mjd)
        seconds = (mjd - day_mjd) * 86400.0

        return cls(day_mjd, seconds, scale)

    def to_datetime(self) -> datetime:
        """Convert to Python datetime (in the current scale)."""
        mjd_epoch = datetime(1858, 11, 17, 0, 0, 0)
        total_days = self.mjd + self.seconds / 86400.0
        return mjd_epoch + timedelta(days=total_days)


def get_leap_second_offset(mjd: float) -> float:
    """
    Get the UTC - TAI offset (leap seconds) for a given MJD.

    Args:
        mjd: Modified Julian Date

    Returns:
        UTC - TAI offset in seconds (negative value)
    """
    # Find the appropriate leap second entry
    mjds = [ls[0] for ls in LEAP_SECONDS]
    idx = bisect.bisect_right(mjds, mjd)

    if idx == 0:
        # Before first leap second entry, use -10s
        return -10.0
    else:
        return LEAP_SECONDS[idx - 1][1]


def tai_to_tt(tai_mjd: float, tai_seconds: float = 0.0) -> tuple[float, float]:
    """
    Convert TAI to TT.

    Args:
        tai_mjd: TAI Modified Julian Date (integer days)
        tai_seconds: TAI seconds within day

    Returns:
        (tt_mjd, tt_seconds)
    """
    tt_seconds = tai_seconds + TT_MINUS_TAI

    # Handle day rollover
    tt_mjd = tai_mjd
    if tt_seconds >= 86400.0:
        tt_mjd += int(tt_seconds // 86400.0)
        tt_seconds = tt_seconds % 86400.0
    elif tt_seconds < 0:
        days_back = int((-tt_seconds) // 86400.0) + 1
        tt_mjd -= days_back
        tt_seconds += days_back * 86400.0

    return tt_mjd, tt_seconds


def tt_to_tai(tt_mjd: float, tt_seconds: float = 0.0) -> tuple[float, float]:
    """
    Convert TT to TAI.

    Args:
        tt_mjd: TT Modified Julian Date (integer days)
        tt_seconds: TT seconds within day

    Returns:
        (tai_mjd, tai_seconds)
    """
    tai_seconds = tt_seconds - TT_MINUS_TAI

    # Handle day rollover
    tai_mjd = tt_mjd
    if tai_seconds >= 86400.0:
        tai_mjd += int(tai_seconds // 86400.0)
        tai_seconds = tai_seconds % 86400.0
    elif tai_seconds < 0:
        days_back = int((-tai_seconds) // 86400.0) + 1
        tai_mjd -= days_back
        tai_seconds += days_back * 86400.0

    return tai_mjd, tai_seconds


def tai_to_utc(tai_mjd: float, tai_seconds: float = 0.0) -> tuple[float, float]:
    """
    Convert TAI to UTC.

    Args:
        tai_mjd: TAI Modified Julian Date (integer days)
        tai_seconds: TAI seconds within day

    Returns:
        (utc_mjd, utc_seconds)
    """
    offset = get_leap_second_offset(tai_mjd)
    utc_seconds = tai_seconds + offset  # offset is negative

    # Handle day rollover
    utc_mjd = tai_mjd
    if utc_seconds >= 86400.0:
        utc_mjd += int(utc_seconds // 86400.0)
        utc_seconds = utc_seconds % 86400.0
    elif utc_seconds < 0:
        days_back = int((-utc_seconds) // 86400.0) + 1
        utc_mjd -= days_back
        utc_seconds += days_back * 86400.0

    return utc_mjd, utc_seconds


def utc_to_tai(utc_mjd: float, utc_seconds: float = 0.0) -> tuple[float, float]:
    """
    Convert UTC to TAI.

    Args:
        utc_mjd: UTC Modified Julian Date (integer days)
        utc_seconds: UTC seconds within day

    Returns:
        (tai_mjd, tai_seconds)
    """
    offset = get_leap_second_offset(utc_mjd)
    tai_seconds = utc_seconds - offset  # offset is negative, so this adds

    # Handle day rollover
    tai_mjd = utc_mjd
    if tai_seconds >= 86400.0:
        tai_mjd += int(tai_seconds // 86400.0)
        tai_seconds = tai_seconds % 86400.0
    elif tai_seconds < 0:
        days_back = int((-tai_seconds) // 86400.0) + 1
        tai_mjd -= days_back
        tai_seconds += days_back * 86400.0

    return tai_mjd, tai_seconds


def tai_to_gpst(tai_mjd: float, tai_seconds: float = 0.0) -> tuple[float, float]:
    """
    Convert TAI to GPS Time.

    Args:
        tai_mjd: TAI Modified Julian Date (integer days)
        tai_seconds: TAI seconds within day

    Returns:
        (gpst_mjd, gpst_seconds)
    """
    gpst_seconds = tai_seconds + GPST_MINUS_TAI

    # Handle day rollover
    gpst_mjd = tai_mjd
    if gpst_seconds >= 86400.0:
        gpst_mjd += int(gpst_seconds // 86400.0)
        gpst_seconds = gpst_seconds % 86400.0
    elif gpst_seconds < 0:
        days_back = int((-gpst_seconds) // 86400.0) + 1
        gpst_mjd -= days_back
        gpst_seconds += days_back * 86400.0

    return gpst_mjd, gpst_seconds


def gpst_to_tai(gpst_mjd: float, gpst_seconds: float = 0.0) -> tuple[float, float]:
    """
    Convert GPS Time to TAI.

    Args:
        gpst_mjd: GPS Time Modified Julian Date (integer days)
        gpst_seconds: GPS Time seconds within day

    Returns:
        (tai_mjd, tai_seconds)
    """
    tai_seconds = gpst_seconds - GPST_MINUS_TAI

    # Handle day rollover
    tai_mjd = gpst_mjd
    if tai_seconds >= 86400.0:
        tai_mjd += int(tai_seconds // 86400.0)
        tai_seconds = tai_seconds % 86400.0
    elif tai_seconds < 0:
        days_back = int((-tai_seconds) // 86400.0) + 1
        tai_mjd -= days_back
        tai_seconds += days_back * 86400.0

    return tai_mjd, tai_seconds


def utc_to_gpst(utc_mjd: float, utc_seconds: float = 0.0) -> tuple[float, float]:
    """
    Convert UTC to GPS Time.

    Args:
        utc_mjd: UTC Modified Julian Date (integer days)
        utc_seconds: UTC seconds within day

    Returns:
        (gpst_mjd, gpst_seconds)
    """
    tai_mjd, tai_seconds = utc_to_tai(utc_mjd, utc_seconds)
    return tai_to_gpst(tai_mjd, tai_seconds)


def gpst_to_utc(gpst_mjd: float, gpst_seconds: float = 0.0) -> tuple[float, float]:
    """
    Convert GPS Time to UTC.

    Args:
        gpst_mjd: GPS Time Modified Julian Date (integer days)
        gpst_seconds: GPS Time seconds within day

    Returns:
        (utc_mjd, utc_seconds)
    """
    tai_mjd, tai_seconds = gpst_to_tai(gpst_mjd, gpst_seconds)
    return tai_to_utc(tai_mjd, tai_seconds)


# Vectorized versions for numpy arrays
def tai_to_tt_vec(tai_mjd: np.ndarray) -> np.ndarray:
    """Vectorized TAI to TT conversion (MJD only)."""
    return tai_mjd + TT_MINUS_TAI / 86400.0


def tt_to_tai_vec(tt_mjd: np.ndarray) -> np.ndarray:
    """Vectorized TT to TAI conversion (MJD only)."""
    return tt_mjd - TT_MINUS_TAI / 86400.0


def tai_to_gpst_vec(tai_mjd: np.ndarray) -> np.ndarray:
    """Vectorized TAI to GPST conversion (MJD only)."""
    return tai_mjd + GPST_MINUS_TAI / 86400.0


def gpst_to_tai_vec(gpst_mjd: np.ndarray) -> np.ndarray:
    """Vectorized GPST to TAI conversion (MJD only)."""
    return gpst_mjd - GPST_MINUS_TAI / 86400.0
