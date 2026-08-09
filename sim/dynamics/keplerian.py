"""
Keplerian orbital dynamics (two-body problem).

Implements the fundamental equations of motion for satellites in orbit around Earth,
including conversions between Cartesian coordinates and classical orbital elements.

Physical Constants:
    - GM_EARTH: Earth's gravitational parameter (km³/s²)
    - R_EARTH: Earth's mean equatorial radius (km)
"""

from typing import Tuple
import jax
import jax.numpy as jnp
from jax import Array

# Physical constants (SI units converted to km and km/s for orbital mechanics)
GM_EARTH = 398600.4418  # km³/s², Earth's gravitational parameter
R_EARTH = 6378.137      # km, Earth's mean equatorial radius


def two_body_dynamics(t: float, state: Array, mu: float = GM_EARTH) -> Array:
    """
    Two-body equation of motion (Keplerian dynamics).
    
    Computes the time derivative of the state vector for an object orbiting
    a point mass under gravitational attraction only.
    
    Equation:
        d²r/dt² = -μ/r³ * r
    
    where:
        - r is the position vector
        - μ is the gravitational parameter
        - r = |r| is the distance from the central body
    
    Args:
        t: Time (s) - not used but included for ODE integrator compatibility
        state: State vector [x, y, z, vx, vy, vz] (km, km/s)
        mu: Gravitational parameter (km³/s²), default is Earth's GM
    
    Returns:
        State derivative [vx, vy, vz, ax, ay, az] (km/s, km/s²)
    
    Example:
        >>> state = jnp.array([7000.0, 0.0, 0.0, 0.0, 7.5, 0.0])
        >>> dstate_dt = two_body_dynamics(0.0, state)
    """
    # Extract position and velocity
    r = state[:3]  # Position (km)
    v = state[3:]  # Velocity (km/s)
    
    # Compute distance
    r_mag = jnp.linalg.norm(r)
    
    # Two-body acceleration: a = -μ/r³ * r
    a = -mu / (r_mag ** 3) * r
    
    # Return derivative [velocity, acceleration]
    return jnp.concatenate([v, a])


def mean_motion(a: float, mu: float = GM_EARTH) -> float:
    """
    Compute mean motion (orbital angular velocity) from semi-major axis.
    
    Equation:
        n = sqrt(μ/a³)
    
    Args:
        a: Semi-major axis (km)
        mu: Gravitational parameter (km³/s²)
    
    Returns:
        Mean motion (rad/s)
    
    Example:
        >>> n = mean_motion(7000.0)  # LEO orbit
        >>> print(f"Period: {2*jnp.pi/n/60:.1f} min")
    """
    return jnp.sqrt(mu / (a ** 3))


def orbital_period(a: float, mu: float = GM_EARTH) -> float:
    """
    Compute orbital period from semi-major axis.
    
    Equation:
        T = 2π * sqrt(a³/μ)
    
    Args:
        a: Semi-major axis (km)
        mu: Gravitational parameter (km³/s²)
    
    Returns:
        Orbital period (s)
    
    Example:
        >>> T = orbital_period(7000.0)
        >>> print(f"Period: {T/60:.1f} min")
    """
    return 2 * jnp.pi * jnp.sqrt((a ** 3) / mu)


def orbital_elements_to_cartesian(
    a: float,
    e: float,
    i: float,
    omega: float,
    w: float,
    nu: float,
    mu: float = GM_EARTH
) -> Tuple[Array, Array]:
    """
    Convert classical orbital elements to Cartesian position and velocity.
    
    Orbital Elements (all angles in radians):
        - a: Semi-major axis (km)
        - e: Eccentricity (dimensionless)
        - i: Inclination (rad)
        - Ω (omega): Right ascension of ascending node (RAAN) (rad)
        - ω (w): Argument of periapsis (rad)
        - ν (nu): True anomaly (rad)
    
    Algorithm:
        1. Compute position and velocity in perifocal frame
        2. Rotate to inertial frame using rotation matrices
    
    Args:
        a: Semi-major axis (km)
        e: Eccentricity
        i: Inclination (rad)
        omega: RAAN (rad)
        w: Argument of periapsis (rad)
        nu: True anomaly (rad)
        mu: Gravitational parameter (km³/s²)
    
    Returns:
        Tuple of (position, velocity):
            - position: [x, y, z] in inertial frame (km)
            - velocity: [vx, vy, vz] in inertial frame (km/s)
    
    Example:
        >>> # LEO circular orbit
        >>> r, v = orbital_elements_to_cartesian(
        ...     a=7000.0, e=0.0, i=jnp.pi/4,
        ...     omega=0.0, w=0.0, nu=0.0
        ... )
    """
    # Compute distance and velocity magnitude in perifocal frame
    p = a * (1 - e**2)  # Semi-latus rectum
    r_mag = p / (1 + e * jnp.cos(nu))
    
    # Position in perifocal frame
    r_peri = jnp.array([
        r_mag * jnp.cos(nu),
        r_mag * jnp.sin(nu),
        0.0
    ])
    
    # Velocity in perifocal frame
    v_peri = jnp.sqrt(mu / p) * jnp.array([
        -jnp.sin(nu),
        e + jnp.cos(nu),
        0.0
    ])
    
    # Rotation matrices: perifocal -> inertial
    # R = R3(-Ω) @ R1(-i) @ R3(-ω)
    
    # R3(-Ω): rotation about z-axis by -RAAN
    # (Vallado Alg. 10: r_ECI = R3(-Ω) R1(-i) R3(-ω) r_PQW, with
    # R3(-θ) = [[c, -s, 0], [s, c, 0], [0, 0, 1]])
    cos_omega, sin_omega = jnp.cos(omega), jnp.sin(omega)
    R3_omega = jnp.array([
        [cos_omega, -sin_omega, 0.0],
        [sin_omega, cos_omega, 0.0],
        [0.0, 0.0, 1.0]
    ])

    # R1(-i): rotation about x-axis by -inclination
    cos_i, sin_i = jnp.cos(i), jnp.sin(i)
    R1_i = jnp.array([
        [1.0, 0.0, 0.0],
        [0.0, cos_i, -sin_i],
        [0.0, sin_i, cos_i]
    ])

    # R3(-ω): rotation about z-axis by -argument of periapsis
    cos_w, sin_w = jnp.cos(w), jnp.sin(w)
    R3_w = jnp.array([
        [cos_w, -sin_w, 0.0],
        [sin_w, cos_w, 0.0],
        [0.0, 0.0, 1.0]
    ])
    
    # Combined rotation matrix
    R = R3_omega @ R1_i @ R3_w
    
    # Transform to inertial frame
    r_inertial = R @ r_peri
    v_inertial = R @ v_peri
    
    return r_inertial, v_inertial


def cartesian_to_orbital_elements(
    r: Array,
    v: Array,
    mu: float = GM_EARTH
) -> Tuple[float, float, float, float, float, float]:
    """
    Convert Cartesian position and velocity to classical orbital elements.
    
    Algorithm follows Curtis (2013), "Orbital Mechanics for Engineering Students".
    Handles edge cases: circular orbits (e ≈ 0) and equatorial orbits (i ≈ 0).
    
    Args:
        r: Position vector [x, y, z] (km)
        v: Velocity vector [vx, vy, vz] (km/s)
        mu: Gravitational parameter (km³/s²)
    
    Returns:
        Tuple of (a, e, i, omega, w, nu):
            - a: Semi-major axis (km)
            - e: Eccentricity
            - i: Inclination (rad)
            - omega: RAAN (rad)
            - w: Argument of periapsis (rad)
            - nu: True anomaly (rad)
    
    Example:
        >>> r = jnp.array([7000.0, 0.0, 0.0])
        >>> v = jnp.array([0.0, 7.5, 0.0])
        >>> a, e, i, omega, w, nu = cartesian_to_orbital_elements(r, v)
    """
    r_mag = jnp.linalg.norm(r)
    v_mag = jnp.linalg.norm(v)
    
    # Angular momentum vector
    h = jnp.cross(r, v)
    h_mag = jnp.linalg.norm(h)
    
    # Node vector (points toward ascending node)
    k = jnp.array([0.0, 0.0, 1.0])
    n = jnp.cross(k, h)
    n_mag = jnp.linalg.norm(n)
    
    # Eccentricity vector
    e_vec = ((v_mag**2 - mu/r_mag) * r - jnp.dot(r, v) * v) / mu
    e = jnp.linalg.norm(e_vec)
    
    # Specific orbital energy
    xi = v_mag**2 / 2 - mu / r_mag
    
    # Semi-major axis
    a = -mu / (2 * xi)
    
    # Inclination
    i = jnp.arccos(h[2] / h_mag)
    
    # Right ascension of ascending node (RAAN)
    # Handle equatorial orbits (i ≈ 0)
    omega = jnp.where(
        n_mag > 1e-10,
        jnp.where(
            n[1] >= 0,
            jnp.arccos(n[0] / n_mag),
            2 * jnp.pi - jnp.arccos(n[0] / n_mag)
        ),
        0.0  # Undefined for equatorial orbits
    )
    
    # Argument of periapsis
    # Handle circular orbits (e ≈ 0) and equatorial orbits
    w = jnp.where(
        (e > 1e-10) & (n_mag > 1e-10),
        jnp.where(
            e_vec[2] >= 0,
            jnp.arccos(jnp.dot(n, e_vec) / (n_mag * e)),
            2 * jnp.pi - jnp.arccos(jnp.dot(n, e_vec) / (n_mag * e))
        ),
        0.0  # Undefined for circular or equatorial orbits
    )
    
    # True anomaly
    # Handle circular orbits
    nu = jnp.where(
        e > 1e-10,
        jnp.where(
            jnp.dot(r, v) >= 0,
            jnp.arccos(jnp.dot(e_vec, r) / (e * r_mag)),
            2 * jnp.pi - jnp.arccos(jnp.dot(e_vec, r) / (e * r_mag))
        ),
        jnp.where(
            n_mag > 1e-10,
            # Use argument of latitude for circular inclined orbits
            jnp.where(
                jnp.dot(r, k) >= 0,
                jnp.arccos(jnp.dot(n, r) / (n_mag * r_mag)),
                2 * jnp.pi - jnp.arccos(jnp.dot(n, r) / (n_mag * r_mag))
            ),
            # Use true longitude for circular equatorial orbits
            jnp.where(
                r[1] >= 0,
                jnp.arccos(r[0] / r_mag),
                2 * jnp.pi - jnp.arccos(r[0] / r_mag)
            )
        )
    )
    
    return a, e, i, omega, w, nu


# JIT-compile the functions for performance
two_body_dynamics = jax.jit(two_body_dynamics)
mean_motion = jax.jit(mean_motion)
orbital_period = jax.jit(orbital_period)
orbital_elements_to_cartesian = jax.jit(orbital_elements_to_cartesian)
cartesian_to_orbital_elements = jax.jit(cartesian_to_orbital_elements)
