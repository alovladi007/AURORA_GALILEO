"""
GNSS Measurement Models
=======================

Dual-frequency GNSS pseudorange and carrier-phase measurements with
ionospheric and tropospheric corrections.
"""

import numpy as np
from dataclasses import dataclass
from typing import Optional, Tuple
import warnings


# Physical constants
C = 299792458.0  # Speed of light (m/s)
F_L1 = 1575.42e6  # GPS L1 frequency (Hz)
F_L2 = 1227.60e6  # GPS L2 frequency (Hz)


@dataclass
class GNSSMeasurement:
    """
    GNSS measurement (pseudorange or carrier-phase).

    Attributes:
        time: Measurement time (s)
        satellite_id: Satellite identifier
        pseudorange_L1: L1 pseudorange (m)
        pseudorange_L2: L2 pseudorange (m)
        carrier_L1: L1 carrier-phase (cycles)
        carrier_L2: L2 carrier-phase (cycles)
        sat_position: Satellite ECEF position (m), shape (3,)
        sat_velocity: Satellite ECEF velocity (m/s), shape (3,)
        elevation: Elevation angle (rad)
        azimuth: Azimuth angle (rad)
    """
    time: float
    satellite_id: int
    pseudorange_L1: float
    pseudorange_L2: Optional[float] = None
    carrier_L1: Optional[float] = None
    carrier_L2: Optional[float] = None
    sat_position: Optional[np.ndarray] = None
    sat_velocity: Optional[np.ndarray] = None
    elevation: Optional[float] = None
    azimuth: Optional[float] = None

    def __post_init__(self):
        """Validate measurements."""
        if self.sat_position is not None:
            self.sat_position = np.asarray(self.sat_position)
            if self.sat_position.shape != (3,):
                raise ValueError("sat_position must have shape (3,)")

        if self.sat_velocity is not None:
            self.sat_velocity = np.asarray(self.sat_velocity)
            if self.sat_velocity.shape != (3,):
                raise ValueError("sat_velocity must have shape (3,)")


@dataclass
class SLRMeasurement:
    """
    Satellite Laser Ranging measurement.

    Attributes:
        time: Measurement time (s)
        range: Two-way range (m)
        range_rate: Range rate (m/s), optional
        station_position: Ground station ECEF position (m), shape (3,)
        sat_position: Satellite ECEF position (m), shape (3,)
    """
    time: float
    range: float
    range_rate: Optional[float] = None
    station_position: Optional[np.ndarray] = None
    sat_position: Optional[np.ndarray] = None


@dataclass
class DORISMeasurement:
    """
    DORIS (Doppler Orbitography and Radiopositioning Integrated by Satellite).

    Attributes:
        time: Measurement time (s)
        frequency_shift: Doppler frequency shift (Hz)
        station_position: Ground beacon ECEF position (m), shape (3,)
        sat_position: Satellite ECEF position (m), shape (3,)
        sat_velocity: Satellite ECEF velocity (m/s), shape (3,)
    """
    time: float
    frequency_shift: float
    station_position: Optional[np.ndarray] = None
    sat_position: Optional[np.ndarray] = None
    sat_velocity: Optional[np.ndarray] = None


def dual_frequency_ionosphere_correction(
    pseudorange_L1: float,
    pseudorange_L2: float,
    frequency_L1: float = F_L1,
    frequency_L2: float = F_L2,
) -> Tuple[float, float]:
    """
    Ionosphere-free pseudorange combination.

    The ionospheric delay is dispersive (proportional to 1/f^2).
    The dual-frequency combination eliminates first-order ionosphere:

        P_IF = (f1^2 * P1 - f2^2 * P2) / (f1^2 - f2^2)

    Args:
        pseudorange_L1: L1 pseudorange (m)
        pseudorange_L2: L2 pseudorange (m)
        frequency_L1: L1 frequency (Hz)
        frequency_L2: L2 frequency (Hz)

    Returns:
        (corrected_range, ionosphere_delay)
        corrected_range: Ionosphere-free range (m)
        ionosphere_delay: Ionospheric delay on L1 (m)
    """
    f1_sq = frequency_L1**2
    f2_sq = frequency_L2**2

    # Ionosphere-free combination
    P_IF = (f1_sq * pseudorange_L1 - f2_sq * pseudorange_L2) / (f1_sq - f2_sq)

    # Ionospheric delay on L1
    ionosphere_delay = pseudorange_L1 - P_IF

    return P_IF, ionosphere_delay


def troposphere_correction(
    elevation: float,
    height: float = 0.0,
    pressure: float = 1013.25,
    temperature: float = 20.0,
    humidity: float = 50.0,
    model: str = "saastamoinen",
) -> float:
    """
    Tropospheric delay correction.

    Uses simplified Saastamoinen or Neill mapping function.

    Args:
        elevation: Elevation angle (rad)
        height: Station height above sea level (m)
        pressure: Atmospheric pressure (hPa)
        temperature: Temperature (°C)
        humidity: Relative humidity (%)
        model: 'saastamoinen' or 'neill'

    Returns:
        Tropospheric delay (m)
    """
    if elevation < np.deg2rad(5):
        warnings.warn("Troposphere model unreliable below 5° elevation")

    # Convert to absolute temperature
    T_K = temperature + 273.15

    if model == "saastamoinen":
        # Saastamoinen model (zenith delay)
        # Dry component
        P = pressure
        Z_hd = 0.0022768 * P / (1 - 0.00266 * np.cos(2 * elevation) - 0.00028 * height / 1000)

        # Wet component (simplified)
        e = humidity / 100.0 * 6.11 * np.exp(17.27 * temperature / (temperature + 237.3))
        Z_wd = 0.002277 * (1255 / T_K + 0.05) * e

        zenith_delay = Z_hd + Z_wd

        # Simple mapping function: 1/sin(elevation)
        mapping = 1.0 / np.sin(elevation)

    elif model == "neill":
        # Neill mapping function (more accurate)
        # Simplified version
        a = 0.0012 * height / 1000
        b = 0.003
        c = 0.07

        sin_el = np.sin(elevation)
        mapping = 1.0 / (sin_el + a / (sin_el + b / (sin_el + c)))

        # Zenith delay (simplified)
        zenith_delay = 2.3 * pressure / 1013.25
    else:
        raise ValueError(f"Unknown troposphere model: {model}")

    return zenith_delay * mapping


def gnss_geometric_range(
    receiver_pos: np.ndarray,
    satellite_pos: np.ndarray,
) -> Tuple[float, np.ndarray]:
    """
    Compute geometric range and line-of-sight vector.

    Args:
        receiver_pos: Receiver ECEF position (m), shape (3,)
        satellite_pos: Satellite ECEF position (m), shape (3,)

    Returns:
        (range, los_unit_vector)
        range: Geometric range (m)
        los_unit_vector: Unit vector from receiver to satellite, shape (3,)
    """
    dr = satellite_pos - receiver_pos
    rho = np.linalg.norm(dr)
    los = dr / rho

    return rho, los


def compute_elevation_azimuth(
    receiver_pos: np.ndarray,
    satellite_pos: np.ndarray,
    lat: float,
    lon: float,
) -> Tuple[float, float]:
    """
    Compute elevation and azimuth angles.

    Args:
        receiver_pos: Receiver ECEF position (m), shape (3,)
        satellite_pos: Satellite ECEF position (m), shape (3,)
        lat: Receiver latitude (rad)
        lon: Receiver longitude (rad)

    Returns:
        (elevation, azimuth) in radians
    """
    # Vector from receiver to satellite
    dr = satellite_pos - receiver_pos

    # Rotation from ECEF to ENU (East-North-Up)
    sin_lat = np.sin(lat)
    cos_lat = np.cos(lat)
    sin_lon = np.sin(lon)
    cos_lon = np.cos(lon)

    R = np.array([
        [-sin_lon, cos_lon, 0],
        [-sin_lat * cos_lon, -sin_lat * sin_lon, cos_lat],
        [cos_lat * cos_lon, cos_lat * sin_lon, sin_lat],
    ])

    # Transform to ENU
    enu = R @ dr

    # Elevation and azimuth
    elevation = np.arctan2(enu[2], np.sqrt(enu[0]**2 + enu[1]**2))
    azimuth = np.arctan2(enu[0], enu[1])

    # Wrap azimuth to [0, 2π)
    if azimuth < 0:
        azimuth += 2 * np.pi

    return elevation, azimuth


def pseudorange_residual(
    receiver_pos: np.ndarray,
    receiver_clock_bias: float,
    measurement: GNSSMeasurement,
    use_dual_freq: bool = True,
) -> float:
    """
    Compute pseudorange residual (observed - computed).

    Args:
        receiver_pos: Receiver ECEF position (m), shape (3,)
        receiver_clock_bias: Receiver clock bias (m)
        measurement: GNSS measurement
        use_dual_freq: If True and L2 available, use ionosphere-free combination

    Returns:
        Residual (m)
    """
    if measurement.sat_position is None:
        raise ValueError("Satellite position required")

    # Geometric range
    rho, _ = gnss_geometric_range(receiver_pos, measurement.sat_position)

    # Observed pseudorange
    if use_dual_freq and measurement.pseudorange_L2 is not None:
        # Ionosphere-free combination
        P_obs, _ = dual_frequency_ionosphere_correction(
            measurement.pseudorange_L1,
            measurement.pseudorange_L2,
        )
    else:
        P_obs = measurement.pseudorange_L1

    # Computed pseudorange
    P_computed = rho + receiver_clock_bias

    # Tropospheric correction (if elevation known)
    if measurement.elevation is not None:
        tropo_delay = troposphere_correction(measurement.elevation)
        P_computed += tropo_delay

    # Residual
    residual = P_obs - P_computed

    return residual


def carrier_phase_residual(
    receiver_pos: np.ndarray,
    receiver_clock_bias: float,
    ambiguity: float,
    measurement: GNSSMeasurement,
    wavelength: float = C / F_L1,
) -> float:
    """
    Compute carrier-phase residual.

    Carrier phase is more precise than pseudorange but has integer ambiguity.

    Args:
        receiver_pos: Receiver ECEF position (m), shape (3,)
        receiver_clock_bias: Receiver clock bias (m)
        ambiguity: Integer ambiguity (cycles)
        measurement: GNSS measurement
        wavelength: Carrier wavelength (m)

    Returns:
        Residual (cycles)
    """
    if measurement.sat_position is None or measurement.carrier_L1 is None:
        raise ValueError("Satellite position and carrier phase required")

    # Geometric range
    rho, _ = gnss_geometric_range(receiver_pos, measurement.sat_position)

    # Observed phase (cycles)
    phi_obs = measurement.carrier_L1

    # Computed phase (cycles)
    phi_computed = (rho + receiver_clock_bias) / wavelength + ambiguity

    # Tropospheric correction
    if measurement.elevation is not None:
        tropo_delay = troposphere_correction(measurement.elevation)
        phi_computed += tropo_delay / wavelength

    # Residual
    residual = phi_obs - phi_computed

    return residual


def gnss_measurement_jacobian(
    receiver_pos: np.ndarray,
    satellite_pos: np.ndarray,
) -> np.ndarray:
    """
    Compute Jacobian (partial derivatives) of pseudorange w.r.t. receiver position.

    ∂ρ/∂r = -los_unit_vector

    Args:
        receiver_pos: Receiver ECEF position (m), shape (3,)
        satellite_pos: Satellite ECEF position (m), shape (3,)

    Returns:
        Jacobian, shape (1, 3) - row vector
    """
    _, los = gnss_geometric_range(receiver_pos, satellite_pos)

    # Partial derivatives: ∂ρ/∂x, ∂ρ/∂y, ∂ρ/∂z
    H = -los.reshape(1, 3)

    return H


def doppler_residual(
    receiver_pos: np.ndarray,
    receiver_vel: np.ndarray,
    receiver_clock_drift: float,
    measurement: GNSSMeasurement,
) -> float:
    """
    Compute Doppler residual.

    Args:
        receiver_pos: Receiver ECEF position (m), shape (3,)
        receiver_vel: Receiver ECEF velocity (m/s), shape (3,)
        receiver_clock_drift: Receiver clock drift (m/s)
        measurement: GNSS measurement

    Returns:
        Residual (Hz)
    """
    if measurement.sat_position is None or measurement.sat_velocity is None:
        raise ValueError("Satellite position and velocity required")

    # Line-of-sight vector
    _, los = gnss_geometric_range(receiver_pos, measurement.sat_position)

    # Relative velocity projection
    v_rel = measurement.sat_velocity - receiver_vel
    v_los = np.dot(v_rel, los)

    # Range rate
    rho_dot = v_los + receiver_clock_drift

    # Doppler shift (observed would come from measurement)
    # For now, return computed range rate (residual needs observed value)

    return rho_dot


# ============================================================================
# Multi-GNSS support
# ============================================================================

GPS_FREQUENCIES = {
    'L1': 1575.42e6,
    'L2': 1227.60e6,
    'L5': 1176.45e6,
}

GALILEO_FREQUENCIES = {
    'E1': 1575.42e6,
    'E5a': 1176.45e6,
    'E5b': 1207.14e6,
    'E6': 1278.75e6,
}

GLONASS_FREQUENCIES = {
    'G1': lambda k: 1602.0e6 + k * 0.5625e6,  # k = -7..6
    'G2': lambda k: 1246.0e6 + k * 0.4375e6,
}


def get_wavelength(system: str, band: str, channel: int = 0) -> float:
    """
    Get carrier wavelength for given GNSS system and band.

    Args:
        system: 'GPS', 'Galileo', 'GLONASS', 'BeiDou'
        band: Frequency band ('L1', 'L2', 'E1', etc.)
        channel: GLONASS frequency channel (default 0)

    Returns:
        Wavelength (m)
    """
    if system == 'GPS':
        freq = GPS_FREQUENCIES.get(band)
    elif system == 'Galileo':
        freq = GALILEO_FREQUENCIES.get(band)
    elif system == 'GLONASS':
        freq_func = GLONASS_FREQUENCIES.get(band)
        freq = freq_func(channel) if freq_func else None
    else:
        raise ValueError(f"Unknown GNSS system: {system}")

    if freq is None:
        raise ValueError(f"Unknown band {band} for {system}")

    return C / freq
