"""
Relativistic Time and Range Corrections
========================================

Implements relativistic corrections for precision timing and ranging.

Includes:
- Gravitational time dilation
- Special relativistic corrections
- Shapiro delay (signal propagation through gravitational field)
- Combined first-order corrections
"""

import numpy as np
from typing import Optional

# Physical constants
C = 299792458.0  # Speed of light (m/s)
GM_EARTH = 3.986004418e14  # Earth's gravitational parameter (m^3/s^2)
R_EARTH = 6371000.0  # Mean Earth radius (m)


def gravitational_time_dilation(
    r: np.ndarray,
    r_ref: Optional[float] = None,
) -> np.ndarray:
    """
    Compute gravitational time dilation correction.

    The proper time τ relates to coordinate time t by:
        dτ/dt = sqrt(1 - 2GM/(rc^2)) ≈ 1 - GM/(rc^2)

    Args:
        r: Radial distance from Earth center (m), shape (...,)
        r_ref: Reference radius for differential correction (m).
               If None, uses infinity (absolute correction)

    Returns:
        Time dilation factor (dimensionless), same shape as r
        Multiply coordinate time by this to get proper time
    """
    # First-order approximation
    factor = 1.0 - GM_EARTH / (r * C**2)

    if r_ref is not None:
        factor_ref = 1.0 - GM_EARTH / (r_ref * C**2)
        factor = factor / factor_ref

    return factor


def special_relativistic_correction(v: np.ndarray) -> np.ndarray:
    """
    Compute special relativistic time dilation correction.

    The proper time τ relates to coordinate time t by:
        dτ/dt = sqrt(1 - v^2/c^2) ≈ 1 - v^2/(2c^2)

    Args:
        v: Velocity magnitude (m/s), shape (...,)

    Returns:
        Time dilation factor (dimensionless), same shape as v
    """
    # First-order approximation
    v2 = v**2
    return 1.0 - v2 / (2.0 * C**2)


def relativistic_time_correction(
    r: np.ndarray,
    v: np.ndarray,
    r_ref: Optional[float] = None,
) -> np.ndarray:
    """
    Combined relativistic time correction (gravitational + special).

    This is the first-order correction for a clock in orbit at position r
    with velocity v, relative to a reference (typically Earth center or geoid).

    Args:
        r: Radial distance from Earth center (m), shape (...,)
        v: Velocity magnitude (m/s), shape (...,)
        r_ref: Reference radius (m), default is Earth surface

    Returns:
        dt/dtau - 1 (fractional time correction), same shape as r
        Positive means clock runs faster than reference
    """
    if r_ref is None:
        r_ref = R_EARTH

    # Gravitational correction (positive for higher altitudes)
    grav_corr = GM_EARTH / (C**2) * (1.0 / r_ref - 1.0 / r)

    # Special relativistic correction (negative for moving clocks)
    sr_corr = -v**2 / (2.0 * C**2)

    return grav_corr + sr_corr


def relativistic_range_correction(
    r_tx: np.ndarray,
    r_rx: np.ndarray,
    v_tx: Optional[np.ndarray] = None,
    v_rx: Optional[np.ndarray] = None,
) -> np.ndarray:
    """
    Relativistic correction to range measurement.

    Accounts for:
    1. Time dilation at transmitter and receiver
    2. Shapiro delay (signal propagation through gravitational field)

    Args:
        r_tx: Transmitter position (m), shape (..., 3)
        r_rx: Receiver position (m), shape (..., 3)
        v_tx: Transmitter velocity (m/s), shape (..., 3), optional
        v_rx: Receiver velocity (m/s), shape (..., 3), optional

    Returns:
        Range correction (m), same shape as r_tx[..., 0]
        Add this to geometric range
    """
    # Geometric range
    dr = r_rx - r_tx
    rho = np.linalg.norm(dr, axis=-1)

    # Radial distances
    r_tx_mag = np.linalg.norm(r_tx, axis=-1)
    r_rx_mag = np.linalg.norm(r_rx, axis=-1)

    # Shapiro delay (first-order)
    shapiro = shapiro_delay(r_tx_mag, r_rx_mag, rho)

    # Time dilation corrections (if velocities provided)
    if v_tx is not None and v_rx is not None:
        v_tx_mag = np.linalg.norm(v_tx, axis=-1)
        v_rx_mag = np.linalg.norm(v_rx, axis=-1)

        # Time correction at transmitter and receiver
        dt_tx = relativistic_time_correction(r_tx_mag, v_tx_mag)
        dt_rx = relativistic_time_correction(r_rx_mag, v_rx_mag)

        # Convert time correction to range correction
        # Δρ ≈ c * (Δt_rx - Δt_tx) * τ where τ is light time
        tau = rho / C
        time_corr = C * (dt_rx - dt_tx) * tau
    else:
        time_corr = 0.0

    return shapiro + time_corr


def shapiro_delay(
    r1: np.ndarray,
    r2: np.ndarray,
    rho: np.ndarray,
) -> np.ndarray:
    """
    Compute Shapiro delay (extra light-time through gravitational field).

    First-order approximation for Earth's field.

    The delay is:
        Δt ≈ (2GM/c^3) * ln((r1 + r2 + rho) / (r1 + r2 - rho))

    Args:
        r1: Distance from Earth center to point 1 (m), shape (...,)
        r2: Distance from Earth center to point 2 (m), shape (...,)
        rho: Geometric distance between points (m), shape (...,)

    Returns:
        Extra range due to Shapiro delay (m), same shape as inputs
    """
    # Avoid singularities
    epsilon = 1e-3  # 1mm

    numerator = r1 + r2 + rho
    denominator = r1 + r2 - rho + epsilon

    delay_time = (2.0 * GM_EARTH / C**3) * np.log(numerator / denominator)

    # Convert time delay to range delay
    delay_range = C * delay_time

    return delay_range


def sagnac_correction(
    r_tx: np.ndarray,
    r_rx: np.ndarray,
    omega_earth: float = 7.2921159e-5,
) -> np.ndarray:
    """
    Sagnac effect correction for rotating reference frame.

    The Sagnac effect is the extra light-time due to Earth's rotation
    during signal propagation.

    Args:
        r_tx: Transmitter position in ECEF (m), shape (..., 3)
        r_rx: Receiver position in ECEF (m), shape (..., 3)
        omega_earth: Earth's rotation rate (rad/s)

    Returns:
        Range correction (m), same shape as r_tx[..., 0]
    """
    # Sagnac correction: Δρ = (ω/c) * (r_tx × r_rx) · ẑ
    # where ẑ is the Earth's rotation axis

    cross = np.cross(r_tx, r_rx)
    sagnac_range = (omega_earth / C) * cross[..., 2]  # z-component

    return sagnac_range


def proper_time_integral(
    t: np.ndarray,
    r: np.ndarray,
    v: np.ndarray,
    r_ref: Optional[float] = None,
) -> np.ndarray:
    """
    Integrate proper time along a trajectory.

    Computes:
        τ = ∫ sqrt(1 - 2GM/(rc^2) - v^2/c^2) dt

    Using first-order approximation:
        τ ≈ ∫ (1 - GM/(rc^2) - v^2/(2c^2)) dt

    Args:
        t: Coordinate time (s), shape (n,)
        r: Radial distance from Earth center (m), shape (n,)
        v: Velocity magnitude (m/s), shape (n,)
        r_ref: Reference radius (m), default Earth surface

    Returns:
        Proper time (s), shape (n,)
    """
    if r_ref is None:
        r_ref = R_EARTH

    # First-order correction factor
    factor = 1.0 + relativistic_time_correction(r, v, r_ref)

    # Integrate using trapezoidal rule
    dt = np.diff(t)
    integrand = 0.5 * (factor[:-1] + factor[1:])
    dtau = integrand * dt

    # Cumulative sum
    tau = np.zeros_like(t)
    tau[1:] = np.cumsum(dtau)

    return tau


def redshift_doppler(
    r1: np.ndarray,
    v1: np.ndarray,
    r2: np.ndarray,
    v2: np.ndarray,
    r12: np.ndarray,
) -> np.ndarray:
    """
    Combined gravitational redshift and Doppler shift.

    Frequency ratio f2/f1 where signal is emitted at 1, received at 2.

    Args:
        r1: Emitter radial distance (m), shape (...,)
        v1: Emitter velocity vector (m/s), shape (..., 3)
        r2: Receiver radial distance (m), shape (...,)
        v2: Receiver velocity vector (m/s), shape (..., 3)
        r12: Position vector from emitter to receiver (m), shape (..., 3)

    Returns:
        Frequency ratio f_rx/f_tx (dimensionless), same shape as r1
    """
    # Gravitational redshift
    grav_redshift = np.sqrt((1.0 - 2.0 * GM_EARTH / (r2 * C**2)) /
                            (1.0 - 2.0 * GM_EARTH / (r1 * C**2)))

    # First-order Doppler shift
    # v_rel = (v2 - v1) · r̂12
    r12_mag = np.linalg.norm(r12, axis=-1, keepdims=True)
    r12_unit = r12 / (r12_mag + 1e-10)

    v_rel = np.sum((v2 - v1) * r12_unit, axis=-1)
    doppler = 1.0 + v_rel / C

    return grav_redshift * doppler


# ============================================================================
# Utility functions
# ============================================================================

def time_correction_to_range(dt: float, direction: str = 'add') -> float:
    """
    Convert time correction to equivalent range correction.

    Args:
        dt: Time correction (s)
        direction: 'add' or 'subtract' - whether to add or subtract correction

    Returns:
        Range correction (m)
    """
    dr = C * dt
    return dr if direction == 'add' else -dr


def range_correction_to_time(dr: float, direction: str = 'add') -> float:
    """
    Convert range correction to equivalent time correction.

    Args:
        dr: Range correction (m)
        direction: 'add' or 'subtract'

    Returns:
        Time correction (s)
    """
    dt = dr / C
    return dt if direction == 'add' else -dt
