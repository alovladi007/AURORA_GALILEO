"""
Orbit Propagator
================

High-fidelity orbit propagation for the Control Service. Implements two-body
dynamics plus the dominant J2 (Earth oblateness) perturbation, integrated with
a fixed-step RK4 scheme in pure NumPy (self-contained; the repository-root
``sim/dynamics`` package uses JAX which is not in the service image).

State vector is [x, y, z, vx, vy, vz] in kilometres / km·s⁻¹, inertial frame.
"""

from __future__ import annotations

import math
from typing import List, Optional, Tuple

import numpy as np

# Physical constants (km, s).
GM_EARTH = 398600.4418      # km^3 / s^2
R_EARTH = 6378.137          # km, equatorial radius
J2_EARTH = 1.08262668e-3


def j2_acceleration(r: np.ndarray) -> np.ndarray:
    """J2 perturbation acceleration (km/s^2) for position ``r`` (km)."""
    x, y, z = r
    r_mag = np.linalg.norm(r)
    r2 = r_mag * r_mag
    r5 = r_mag ** 5
    z2_over_r2 = (z * z) / r2
    coeff = -1.5 * J2_EARTH * GM_EARTH * (R_EARTH ** 2) / r5
    return np.array([
        coeff * x * (5 * z2_over_r2 - 1),
        coeff * y * (5 * z2_over_r2 - 1),
        coeff * z * (5 * z2_over_r2 - 3),
    ])


def derivatives(state: np.ndarray, include_j2: bool = True) -> np.ndarray:
    """State derivative [v, a] for a 6-vector ``state``."""
    r = state[:3]
    v = state[3:]
    r_mag = np.linalg.norm(r)
    a = -GM_EARTH / (r_mag ** 3) * r
    if include_j2:
        a = a + j2_acceleration(r)
    return np.concatenate([v, a])


def rk4_step(state: np.ndarray, dt: float, include_j2: bool = True) -> np.ndarray:
    """Single classical Runge-Kutta 4 integration step."""
    k1 = derivatives(state, include_j2)
    k2 = derivatives(state + 0.5 * dt * k1, include_j2)
    k3 = derivatives(state + 0.5 * dt * k2, include_j2)
    k4 = derivatives(state + dt * k3, include_j2)
    return state + (dt / 6.0) * (k1 + 2 * k2 + 2 * k3 + k4)


def circular_state(altitude_km: float, inclination_deg: float = 0.0) -> np.ndarray:
    """Construct an initial circular-orbit state at a given altitude."""
    radius = R_EARTH + altitude_km
    speed = math.sqrt(GM_EARTH / radius)
    inc = math.radians(inclination_deg)
    # Position on the x-axis; velocity inclined by ``inc`` in the y-z plane.
    return np.array([
        radius, 0.0, 0.0,
        0.0, speed * math.cos(inc), speed * math.sin(inc),
    ])


def propagate(initial_state: np.ndarray, duration_s: float, timestep_s: float,
              include_j2: bool = True, max_points: int = 5000
              ) -> Tuple[List[float], np.ndarray]:
    """Propagate an orbit, returning (times, states).

    ``states`` has shape (n, 6). The number of points is capped at
    ``max_points`` by widening the output stride (integration step is kept fine
    for accuracy).
    """
    timestep_s = max(timestep_s, 1.0)
    n_steps = max(int(duration_s / timestep_s), 1)
    stride = max(1, math.ceil(n_steps / max_points))

    state = np.asarray(initial_state, dtype=float).copy()
    times = [0.0]
    out = [state.copy()]
    for i in range(1, n_steps + 1):
        state = rk4_step(state, timestep_s, include_j2)
        if i % stride == 0:
            times.append(i * timestep_s)
            out.append(state.copy())
    return times, np.array(out)


def orbital_elements(state: np.ndarray) -> dict:
    """Compute classical orbital elements from a state vector (for diagnostics)."""
    r = state[:3]
    v = state[3:]
    r_mag = np.linalg.norm(r)
    v_mag = np.linalg.norm(v)
    # Specific energy and semi-major axis.
    energy = v_mag ** 2 / 2 - GM_EARTH / r_mag
    a = -GM_EARTH / (2 * energy) if energy != 0 else float("inf")
    # Eccentricity vector.
    h = np.cross(r, v)
    e_vec = (np.cross(v, h) / GM_EARTH) - r / r_mag
    ecc = float(np.linalg.norm(e_vec))
    inc = float(math.degrees(math.acos(np.clip(h[2] / np.linalg.norm(h), -1, 1))))
    period = 2 * math.pi * math.sqrt(abs(a) ** 3 / GM_EARTH) if a > 0 else float("inf")
    return {
        "semi_major_axis_km": float(a),
        "eccentricity": ecc,
        "inclination_deg": inc,
        "period_s": float(period),
        "altitude_km": float(r_mag - R_EARTH),
    }
