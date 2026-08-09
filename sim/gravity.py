"""
Gravity field modeling and simulation using spherical harmonics.

Implements Earth's gravitational field as a spherical-harmonic expansion

    V(r, phi, lam) = (GM/r) [ 1 + sum_{n=2}^{N} (R/r)^n
                     sum_{m=0}^{n} P_nm(sin phi)
                     (C_nm cos(m lam) + S_nm sin(m lam)) ]

Conventions
-----------
- Coefficients are **unnormalized** (geodesy convention, no
  Condon-Shortley phase): the Earth's oblateness appears as
  ``C[2,0] = -J2``.
- The degree-0 central term (GM/r) is implicit; the coefficient matrix
  holds only the perturbation terms. Degree-1 terms are zero for a
  geocentric frame and are ignored if present.
- Acceleration is the gradient of the (positive) geodesy potential:
  ``a = grad V`` points toward the Earth.

The associated Legendre recursion used here is stable to degree ~50 in
float32 (JAX default) and ~150 in float64. Full EGM2008 (degree 2190)
requires fully-normalized (Holmes-Featherstone) recursions - planned,
see MASTER_BUILD_PROMPT_18_MONTHS.md Phase 1 W1.1.
"""

from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Optional, Tuple

import jax
import jax.numpy as jnp
import numpy as np

# Unnormalized zonal harmonics of the Earth (EGM2008 / IERS values).
# J_n = -C_{n,0} (unnormalized).
J2 = 1.08262668e-3
J3 = -2.53265649e-6
J4 = -1.61962159e-6
J5 = -2.27296083e-7
J6 = 5.40681239e-7


@dataclass
class GravityModel:
    """Spherical harmonic gravity model coefficients (unnormalized)."""

    C_nm: jnp.ndarray  # Cosine coefficients, indexed [degree, order]
    S_nm: jnp.ndarray  # Sine coefficients, indexed [degree, order]
    max_degree: int
    max_order: int
    reference_radius: float = 6378137.0  # meters
    gm: float = 3.986004418e14  # m³/s²


def _legendre_all(nmax: int, x):
    """All unnormalized associated Legendre values P[n][m] at scalar x.

    Standard geodesy recursions (no Condon-Shortley phase):
        P[0,0] = 1
        P[m,m] = (2m-1) u P[m-1,m-1],          u = sqrt(1-x^2)
        P[m+1,m] = (2m+1) x P[m,m]
        (n-m) P[n,m] = (2n-1) x P[n-1,m] - (n+m-1) P[n-2,m]

    Returns a list of lists (Python-level; nmax must be static under jit).
    """
    u = jnp.sqrt(jnp.clip(1.0 - x * x, 0.0, 1.0))
    P = [[None] * (nmax + 1) for _ in range(nmax + 1)]
    P[0][0] = jnp.ones_like(x)
    for m in range(1, nmax + 1):
        P[m][m] = (2 * m - 1) * u * P[m - 1][m - 1]
    for m in range(0, nmax):
        P[m + 1][m] = (2 * m + 1) * x * P[m][m]
    for m in range(0, nmax + 1):
        for n in range(m + 2, nmax + 1):
            P[n][m] = ((2 * n - 1) * x * P[n - 1][m]
                       - (n + m - 1) * P[n - 2][m]) / (n - m)
    return P


@partial(jax.jit, static_argnums=(3,))
def _potential(r, lat, lon, nmax, C, S, ref_radius, gm):
    """Geodesy potential V (m^2/s^2) at spherical coordinates."""
    x = jnp.sin(lat)
    P = _legendre_all(nmax, x)

    central = gm / r
    if nmax < 2:
        return central

    perturbation = jnp.zeros_like(r)
    ratio = ref_radius / r
    for n in range(2, nmax + 1):
        ratio_n = ratio ** n
        for m in range(0, n + 1):
            harmonic = C[n, m] * jnp.cos(m * lon) + S[n, m] * jnp.sin(m * lon)
            perturbation = perturbation + ratio_n * P[n][m] * harmonic
    return central * (1.0 + perturbation)


@partial(jax.jit, static_argnums=(1,))
def _acceleration(position, nmax, C, S, ref_radius, gm):
    """Acceleration a = grad V at Cartesian ECEF position (m -> m/s^2)."""

    def V(p):
        r = jnp.linalg.norm(p)
        lat = jnp.arcsin(p[2] / r)
        lon = jnp.arctan2(p[1], p[0])
        return _potential(r, lat, lon, nmax, C, S, ref_radius, gm)

    return jax.grad(V)(position)


class SphericalHarmonics:
    """Spherical harmonic gravity field computations using JAX."""

    def __init__(self, model: GravityModel) -> None:
        self.model = model

    @staticmethod
    def associated_legendre(n: int, m: int, x: jnp.ndarray) -> jnp.ndarray:
        """Unnormalized associated Legendre P_n^m(x) (no C-S phase).

        Args:
            n: Degree (Python int)
            m: Order (Python int, 0 <= m <= n)
            x: Argument, typically sin(latitude)
        """
        if m > n:
            return jnp.zeros_like(x)
        return _legendre_all(n, x)[n][m]

    def gravitational_potential(self, r, lat, lon):
        """Geodesy gravitational potential V at (r, lat, lon).

        Args:
            r: Radial distance (m)
            lat: Geocentric latitude (rad)
            lon: Longitude (rad)

        Returns:
            Potential (m²/s²); positive, ~GM/r.
        """
        m = self.model
        return _potential(r, lat, lon, m.max_degree, m.C_nm, m.S_nm,
                          m.reference_radius, m.gm)

    def gravitational_acceleration(self, position):
        """Gravitational acceleration a = grad V at ECEF position (m).

        Returns:
            Acceleration vector (m/s²), pointing toward the Earth.
        """
        m = self.model
        return _acceleration(position, m.max_degree, m.C_nm, m.S_nm,
                             m.reference_radius, m.gm)


def load_egm2008_model(
    max_degree: int = 360,
    coefficient_file: Optional[str] = None,
) -> GravityModel:
    """Load a gravity model.

    Without a coefficient file this returns the **zonal subset**
    (J2..J6, real EGM2008/IERS values) - correct oblateness physics but
    no tesseral structure. Pass ``coefficient_file`` (ICGEM .gfc format,
    fully normalized) to load a full model; coefficients are converted
    to the unnormalized convention (stable to degree ~150 in float64).

    Args:
        max_degree: Maximum degree of the returned model.
        coefficient_file: Optional path to an ICGEM .gfc file.

    Returns:
        GravityModel (unnormalized coefficients).
    """
    n = max_degree
    C = np.zeros((n + 1, n + 1))
    S = np.zeros((n + 1, n + 1))

    zonals = {2: J2, 3: J3, 4: J4, 5: J5, 6: J6}
    for deg, j in zonals.items():
        if deg <= n:
            C[deg, 0] = -j

    if coefficient_file is not None:
        C, S = _read_icgem(Path(coefficient_file), n)

    return GravityModel(
        C_nm=jnp.asarray(C),
        S_nm=jnp.asarray(S),
        max_degree=n,
        max_order=n,
    )


def _unnormalization_factor(n: int, m: int) -> float:
    """N_nm such that P_unnorm = N_nm * P_fully_normalized (log-space)."""
    from math import lgamma, log, sqrt, exp
    # N = sqrt( (2 - delta_m0) (2n+1) (n-m)! / (n+m)! )
    delta = 1.0 if m == 0 else 2.0
    log_n = 0.5 * (log(delta) + log(2 * n + 1)
                   + lgamma(n - m + 1) - lgamma(n + m + 1))
    return exp(log_n)


def _read_icgem(path: Path, max_degree: int):
    """Parse an ICGEM .gfc coefficient file into unnormalized C/S arrays."""
    C = np.zeros((max_degree + 1, max_degree + 1))
    S = np.zeros((max_degree + 1, max_degree + 1))
    with open(path) as fh:
        in_data = False
        for line in fh:
            if line.startswith("end_of_head"):
                in_data = True
                continue
            if not in_data or not line.strip().startswith("gfc"):
                continue
            parts = line.split()
            n, m = int(parts[1]), int(parts[2])
            if n > max_degree:
                continue
            factor = _unnormalization_factor(n, m)
            C[n, m] = float(parts[3].replace("D", "E")) * factor
            S[n, m] = float(parts[4].replace("D", "E")) * factor
    # The central term and geocenter terms are implicit in our convention
    C[0, 0] = 0.0
    if max_degree >= 1:
        C[1, :2] = 0.0
        S[1, :2] = 0.0
    return C, S


def compute_geoid_height(
    lat: np.ndarray,
    lon: np.ndarray,
    model: GravityModel,
) -> np.ndarray:
    """Geoid undulation N via Bruns' formula, N = T / gamma.

    The disturbing potential T is the perturbation part of V evaluated
    on the reference sphere r = R; normal gravity is approximated by
    gamma = GM / R^2 (spherical normal field; sufficient for the
    zonal/tesseral perturbation magnitudes involved).

    Args:
        lat: Latitude array (degrees)
        lon: Longitude array (degrees)
        model: Gravity model

    Returns:
        Geoid height (m), same shape as lat.
    """
    lat = np.atleast_1d(np.asarray(lat, dtype=float))
    lon = np.atleast_1d(np.asarray(lon, dtype=float))
    lat_rad = np.deg2rad(lat)
    lon_rad = np.deg2rad(lon)

    R = model.reference_radius
    gamma = model.gm / R**2

    geoid = np.zeros_like(lat, dtype=float)
    for k in range(lat.size):
        V = float(_potential(
            jnp.asarray(R), jnp.asarray(lat_rad.flat[k]),
            jnp.asarray(lon_rad.flat[k]), model.max_degree,
            model.C_nm, model.S_nm, model.reference_radius, model.gm,
        ))
        T = V - model.gm / R  # disturbing potential
        geoid.flat[k] = T / gamma
    return geoid
