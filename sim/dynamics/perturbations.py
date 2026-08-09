"""
Orbital perturbations module.

Implements perturbation accelerations due to:
- J2 (Earth oblateness)
- Atmospheric drag
- Solar radiation pressure (SRP)

All perturbations are computed in the inertial frame and can be added
to the two-body acceleration for high-fidelity orbit propagation.
"""

from typing import Optional
import jax
import jax.numpy as jnp
from jax import Array

from .keplerian import GM_EARTH, R_EARTH, two_body_dynamics

# Physical constants
J2_EARTH = 1.08262668e-3  # Earth's J2 coefficient (dimensionless)
OMEGA_EARTH = 7.2921150e-5  # Earth's rotation rate (rad/s)

# Atmospheric density model parameters (simplified exponential atmosphere)
# More sophisticated models (NRLMSISE-00, JB2008) can be added later
DENSITY_PARAMS = {
    # Altitude (km): (base density kg/m³, scale height km)
    0: (1.225, 7.249),
    25: (3.899e-2, 6.349),
    30: (1.774e-2, 6.682),
    40: (3.972e-3, 7.554),
    50: (1.057e-3, 8.382),
    60: (3.206e-4, 7.714),
    70: (8.770e-5, 6.549),
    80: (1.905e-5, 5.799),
    90: (3.396e-6, 5.382),
    100: (5.297e-7, 5.877),
    110: (9.661e-8, 7.263),
    120: (2.438e-8, 9.473),
    130: (8.484e-9, 12.636),
    140: (3.845e-9, 16.149),
    150: (2.070e-9, 22.523),
    180: (5.464e-10, 29.740),
    200: (2.789e-10, 37.105),
    250: (7.248e-11, 45.546),
    300: (2.418e-11, 53.628),
    350: (9.518e-12, 53.298),
    400: (3.725e-12, 58.515),
    450: (1.585e-12, 60.828),
    500: (6.967e-13, 63.822),
    600: (1.454e-13, 71.835),
    700: (3.614e-14, 88.667),
    800: (1.170e-14, 124.64),
    900: (5.245e-15, 181.05),
    1000: (3.019e-15, 268.00),
}

# Array form of the density table for traceable (jit-safe) lookup
_DENSITY_ALTS = jnp.array(sorted(DENSITY_PARAMS.keys()), dtype=jnp.float32)
_DENSITY_RHO0 = jnp.array(
    [DENSITY_PARAMS[h][0] for h in sorted(DENSITY_PARAMS.keys())]
)
_DENSITY_SCALE_H = jnp.array(
    [DENSITY_PARAMS[h][1] for h in sorted(DENSITY_PARAMS.keys())]
)


def j2_acceleration(r: Array, mu: float = GM_EARTH,
                   j2: float = J2_EARTH, r_e: float = R_EARTH) -> Array:
    """
    Compute J2 perturbation acceleration due to Earth's oblateness.
    
    The J2 term represents the Earth's equatorial bulge and is the dominant
    non-spherical gravitational perturbation. It causes secular drift in
    RAAN and argument of periapsis.
    
    Equation (in inertial frame):
        a_J2 = -3/2 * J2 * μ * R_E² / r⁵ * 
               [x(5z²/r² - 1), y(5z²/r² - 1), z(5z²/r² - 3)]
    
    where:
        - r = [x, y, z] is the position vector
        - r = |r| is the distance from Earth's center
        - R_E is Earth's mean equatorial radius
        - J2 is the J2 coefficient (~1.08263 × 10⁻³)
    
    Args:
        r: Position vector [x, y, z] in inertial frame (km)
        mu: Gravitational parameter (km³/s²)
        j2: J2 coefficient (dimensionless)
        r_e: Earth's equatorial radius (km)
    
    Returns:
        J2 acceleration vector [ax, ay, az] (km/s²)
    
    Reference:
        Curtis (2013), "Orbital Mechanics for Engineering Students", Eq. 10.39
    
    Example:
        >>> r = jnp.array([7000.0, 0.0, 0.0])
        >>> a_j2 = j2_acceleration(r)
        >>> print(f"J2 acceleration magnitude: {jnp.linalg.norm(a_j2)*1e6:.2f} mm/s²")
    """
    x, y, z = r[0], r[1], r[2]
    r_mag = jnp.linalg.norm(r)
    
    # Precompute common terms
    r2 = r_mag ** 2
    r5 = r_mag ** 5
    z2_over_r2 = z ** 2 / r2
    
    # J2 acceleration coefficient (Curtis Eq. 10.39: +3/2 with these
    # bracket terms; at the equator the perturbation points inward, at
    # the poles outward)
    coeff = 1.5 * j2 * mu * (r_e ** 2) / r5
    
    # Acceleration components
    ax = coeff * x * (5 * z2_over_r2 - 1)
    ay = coeff * y * (5 * z2_over_r2 - 1)
    az = coeff * z * (5 * z2_over_r2 - 3)
    
    return jnp.array([ax, ay, az])


def atmospheric_density(altitude: float) -> float:
    """
    Compute atmospheric density using exponential atmosphere model.
    
    Uses a piecewise exponential model with altitude-dependent scale heights.
    For altitudes below 1000 km, uses tabulated values. For higher altitudes,
    extrapolates using the 1000 km scale height.
    
    Equation:
        ρ(h) = ρ₀ * exp(-(h - h₀) / H)
    
    where:
        - h is altitude
        - h₀ is reference altitude
        - ρ₀ is density at h₀
        - H is scale height
    
    Args:
        altitude: Altitude above Earth's surface (km)
    
    Returns:
        Atmospheric density (kg/m³)
    
    Note:
        This is a simplified model. For higher accuracy, use:
        - NRLMSISE-00 for altitudes up to 1000 km
        - JB2008 for operational orbits
        - MSIS-E-90 for LEO missions
    
    Example:
        >>> rho_400km = atmospheric_density(400.0)
        >>> print(f"Density at 400 km: {rho_400km:.2e} kg/m³")
    """
    # Traceable table lookup (works under jax.jit: no Python branching
    # on traced values). Bracketing bin via searchsorted, then
    # exponential decay from that bin's base; altitudes above the table
    # extrapolate with the last bin's scale height.
    alt = jnp.clip(altitude, 0.0, None)
    idx = jnp.clip(
        jnp.searchsorted(_DENSITY_ALTS, alt, side="right") - 1,
        0,
        _DENSITY_ALTS.shape[0] - 1,
    )
    h0 = _DENSITY_ALTS[idx]
    rho0 = _DENSITY_RHO0[idx]
    scale_h = _DENSITY_SCALE_H[idx]
    return rho0 * jnp.exp(-(alt - h0) / scale_h)


def atmospheric_drag_acceleration(
    r: Array,
    v: Array,
    cd: float = 2.2,
    area_to_mass: float = 0.01,
    omega_earth: float = OMEGA_EARTH
) -> Array:
    """
    Compute atmospheric drag acceleration.
    
    Atmospheric drag is a velocity-dependent perturbation that causes orbital
    decay. The drag force opposes the satellite's velocity relative to the
    rotating atmosphere.
    
    Equation:
        a_drag = -1/2 * ρ * Cd * (A/m) * |v_rel| * v_rel
    
    where:
        - ρ is atmospheric density
        - Cd is drag coefficient (~2.0-2.5 for satellites)
        - A/m is area-to-mass ratio (m²/kg)
        - v_rel is velocity relative to rotating atmosphere
    
    Args:
        r: Position vector [x, y, z] (km)
        v: Velocity vector [vx, vy, vz] (km/s)
        cd: Drag coefficient (dimensionless), typically 2.0-2.5
        area_to_mass: Area-to-mass ratio (m²/kg), typically 0.005-0.05
        omega_earth: Earth's rotation rate (rad/s)
    
    Returns:
        Drag acceleration vector [ax, ay, az] (km/s²)
    
    Note:
        The atmosphere co-rotates with Earth, so we need to account for
        the relative velocity. For most LEO satellites, this is a small
        correction (~0.5 km/s at equator).
    
    Example:
        >>> r = jnp.array([6800.0, 0.0, 0.0])  # 400 km altitude
        >>> v = jnp.array([0.0, 7.7, 0.0])
        >>> a_drag = atmospheric_drag_acceleration(r, v)
        >>> print(f"Drag deceleration: {jnp.linalg.norm(a_drag)*1e6:.2f} mm/s²")
    """
    # Compute altitude
    r_mag = jnp.linalg.norm(r)
    altitude = r_mag - R_EARTH
    
    # Get atmospheric density
    rho = atmospheric_density(altitude)
    
    # Velocity of atmosphere (co-rotating with Earth)
    # v_atm = ω_earth × r ; with r in km and ω in rad/s this is already km/s
    v_atm = omega_earth * jnp.array([-r[1], r[0], 0.0])

    # Relative velocity (satellite w.r.t. atmosphere), km/s
    v_rel = v - v_atm
    v_rel_mag = jnp.linalg.norm(v_rel)

    # Drag acceleration. Unit algebra with rho [kg/m³], A/m [m²/kg],
    # v_rel [km/s]:  a[m/s²] = -1/2 rho Cd (A/m) (1000 v)² -> a[km/s²]
    # = a[m/s²]/1000 = -1/2 rho Cd (A/m) * 1e3 * |v_rel| v_rel.
    a_drag = -0.5 * cd * area_to_mass * rho * 1e3 * v_rel_mag * v_rel
    
    return a_drag


def solar_radiation_pressure_acceleration(
    r: Array,
    r_sun: Array,
    cr: float = 1.3,
    area_to_mass: float = 0.01,
    p_sr: float = 4.56e-6,
    r_e: float = R_EARTH
) -> Array:
    """
    Compute solar radiation pressure (SRP) acceleration.
    
    SRP is caused by momentum transfer from solar photons impinging on the
    satellite surface. It's significant for satellites with high area-to-mass
    ratios (e.g., solar sails, GPS satellites).
    
    Equation:
        a_SRP = -P_SR * Cr * (A/m) * (r - r_sun) / |r - r_sun| * ν(shadow)
    
    where:
        - P_SR is solar radiation pressure at 1 AU
        - Cr is reflectivity coefficient (1.0-2.0)
        - A/m is area-to-mass ratio
        - ν is shadow function (0 in eclipse, 1 in sunlight)
    
    Args:
        r: Satellite position vector [x, y, z] (km)
        r_sun: Sun position vector [x, y, z] (km)
        cr: Reflectivity coefficient (1.0-2.0), typical value 1.3
        area_to_mass: Area-to-mass ratio (m²/kg)
        p_sr: Solar radiation pressure at 1 AU (N/m²)
        r_e: Earth's radius for shadow calculation (km)
    
    Returns:
        SRP acceleration vector [ax, ay, az] (km/s²)
    
    Note:
        - Cr = 1.0 for perfect absorption
        - Cr = 2.0 for perfect reflection (specular)
        - Typical satellites: Cr ≈ 1.3-1.5
    
    Shadow Model:
        Simple cylindrical shadow (ignores penumbra). For higher accuracy:
        - Implement conical shadow model
        - Account for Earth's atmospheric refraction
        - Model penumbra transitions
    
    Example:
        >>> r = jnp.array([7000.0, 0.0, 0.0])
        >>> r_sun = jnp.array([1.5e8, 0.0, 0.0])  # ~1 AU
        >>> a_srp = solar_radiation_pressure_acceleration(r, r_sun)
    """
    # Vector from satellite to sun
    r_sat_to_sun = r_sun - r
    r_sat_to_sun_mag = jnp.linalg.norm(r_sat_to_sun)
    r_sat_to_sun_unit = r_sat_to_sun / r_sat_to_sun_mag
    
    # Shadow function (cylindrical shadow model)
    # Satellite is in shadow if angle between r and r_sun > 90° 
    # AND satellite is within Earth's shadow cylinder
    angle_sun_sat = jnp.dot(r, r_sun) / (jnp.linalg.norm(r) * jnp.linalg.norm(r_sun))
    
    # Project satellite position onto sun direction
    r_proj = jnp.dot(r, r_sat_to_sun_unit)
    
    # Distance from shadow axis
    r_perp = r - r_proj * r_sat_to_sun_unit
    r_perp_mag = jnp.linalg.norm(r_perp)
    
    # Shadow function
    # In shadow if: pointing away from sun AND within Earth's shadow cylinder
    in_shadow = (angle_sun_sat < 0) & (r_perp_mag < r_e)
    shadow_factor = jnp.where(in_shadow, 0.0, 1.0)
    
    # SRP acceleration. p_sr[N/m²] * Cr * (A/m)[m²/kg] gives m/s²;
    # 1 m/s² = 1e-3 km/s², so divide by 1000. Direction: away from the
    # sun (-r_sat_to_sun_unit ... the leading minus sign).
    a_srp = -p_sr * cr * area_to_mass * r_sat_to_sun_unit * shadow_factor / 1000.0
    
    return a_srp


def perturbed_dynamics(
    t: float,
    state: Array,
    mu: float = GM_EARTH,
    include_j2: bool = True,
    include_drag: bool = True,
    include_srp: bool = False,
    cd: float = 2.2,
    cr: float = 1.3,
    area_to_mass: float = 0.01,
    r_sun: Optional[Array] = None
) -> Array:
    """
    Complete equation of motion including two-body plus perturbations.
    
    Combines the Keplerian two-body dynamics with various perturbations:
    - J2 (Earth oblateness)
    - Atmospheric drag
    - Solar radiation pressure
    
    This provides a high-fidelity orbit propagation model suitable for
    precision orbit determination and mission analysis.
    
    Args:
        t: Time (s)
        state: State vector [x, y, z, vx, vy, vz] (km, km/s)
        mu: Gravitational parameter (km³/s²)
        include_j2: Include J2 perturbation
        include_drag: Include atmospheric drag
        include_srp: Include solar radiation pressure
        cd: Drag coefficient
        cr: Reflectivity coefficient (for SRP)
        area_to_mass: Area-to-mass ratio (m²/kg)
        r_sun: Sun position vector [x, y, z] (km), required if include_srp=True
    
    Returns:
        State derivative [vx, vy, vz, ax, ay, az] (km/s, km/s²)
    
    Example:
        >>> state = jnp.array([7000.0, 0.0, 0.0, 0.0, 7.5, 0.0])
        >>> dstate_dt = perturbed_dynamics(0.0, state, include_j2=True, include_drag=True)
    """
    # Extract position and velocity
    r = state[:3]
    v = state[3:]
    
    # Two-body acceleration
    r_mag = jnp.linalg.norm(r)
    a_twobody = -mu / (r_mag ** 3) * r
    
    # Initialize total acceleration
    a_total = a_twobody
    
    # Add J2 perturbation
    if include_j2:
        a_total += j2_acceleration(r, mu)
    
    # Add atmospheric drag
    if include_drag:
        a_total += atmospheric_drag_acceleration(r, v, cd, area_to_mass)
    
    # Add solar radiation pressure
    if include_srp:
        if r_sun is None:
            raise ValueError("r_sun must be provided when include_srp=True")
        a_total += solar_radiation_pressure_acceleration(r, r_sun, cr, area_to_mass)
    
    # Return derivative
    return jnp.concatenate([v, a_total])


# JIT-compile for performance
j2_acceleration = jax.jit(j2_acceleration)
atmospheric_drag_acceleration = jax.jit(atmospheric_drag_acceleration)
solar_radiation_pressure_acceleration = jax.jit(solar_radiation_pressure_acceleration)
perturbed_dynamics = jax.jit(perturbed_dynamics, static_argnames=[
    'include_j2', 'include_drag', 'include_srp'
])
