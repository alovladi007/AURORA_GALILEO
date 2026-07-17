"""
Empirical Accelerations and Force Modeling
===========================================

Empirical accelerations for orbit determination.

Provides piecewise-constant empirical accelerations expressed in the
RTN (radial / transverse / normal) orbital frame, and a least-squares
estimator that fits segment accelerations to observed dynamic residuals.
These absorb unmodeled forces (drag mis-modeling, SRP errors, thruster
leakage) in the POD estimation state, following the standard reduced-
dynamic orbit determination approach.

Note: full dynamic force models (two-body, J2) live in ``sim.dynamics``;
this module only models the *residual* accelerations on top of them.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np


def rtn_basis(position: np.ndarray, velocity: np.ndarray) -> np.ndarray:
    """Rotation matrix whose rows are the RTN unit vectors in the
    inertial frame.

    R: radial (along position), N: orbit normal (r x v), T: completes
    the right-handed triad (N x R, close to velocity direction).

    Parameters
    ----------
    position, velocity : ndarray, shape (3,)
        Inertial position and velocity.

    Returns
    -------
    ndarray, shape (3, 3)
        Matrix M with rows [R; T; N]; transforms inertial vectors into
        RTN via ``M @ v_inertial``; ``M.T @ v_rtn`` maps back.
    """
    r_hat = position / np.linalg.norm(position)
    n_vec = np.cross(position, velocity)
    n_hat = n_vec / np.linalg.norm(n_vec)
    t_hat = np.cross(n_hat, r_hat)
    return np.vstack([r_hat, t_hat, n_hat])


@dataclass
class PiecewiseConstantAccel:
    """Piecewise-constant empirical acceleration in the RTN frame.

    Attributes
    ----------
    segment_bounds : ndarray, shape (n_segments + 1,)
        Monotonic epoch boundaries [t_0, t_1, ..., t_n].
    accelerations_rtn : ndarray, shape (n_segments, 3)
        RTN acceleration for each segment (m/s^2).
    """

    segment_bounds: np.ndarray
    accelerations_rtn: np.ndarray

    def __post_init__(self):
        self.segment_bounds = np.asarray(self.segment_bounds, dtype=float)
        self.accelerations_rtn = np.asarray(self.accelerations_rtn, dtype=float)
        if self.accelerations_rtn.shape != (len(self.segment_bounds) - 1, 3):
            raise ValueError(
                "accelerations_rtn must have shape (n_segments, 3) with "
                "n_segments = len(segment_bounds) - 1"
            )

    def segment_index(self, t: float) -> int:
        """Segment containing epoch t (clamped to valid range)."""
        idx = int(np.searchsorted(self.segment_bounds, t, side="right") - 1)
        return int(np.clip(idx, 0, len(self.accelerations_rtn) - 1))

    def acceleration_rtn(self, t: float) -> np.ndarray:
        """RTN acceleration at epoch t (m/s^2)."""
        return self.accelerations_rtn[self.segment_index(t)]

    def acceleration_inertial(
        self, t: float, position: np.ndarray, velocity: np.ndarray
    ) -> np.ndarray:
        """Inertial-frame acceleration at epoch t given the orbit state."""
        m = rtn_basis(position, velocity)
        return m.T @ self.acceleration_rtn(t)


@dataclass
class EmpiricalAccelerations:
    """Collection of empirical acceleration models applied additively."""

    models: List[PiecewiseConstantAccel] = field(default_factory=list)

    def add(self, model: PiecewiseConstantAccel) -> None:
        self.models.append(model)

    def total_acceleration(
        self, t: float, position: np.ndarray, velocity: np.ndarray
    ) -> np.ndarray:
        """Sum of all empirical accelerations in the inertial frame."""
        accel = np.zeros(3)
        for model in self.models:
            accel += model.acceleration_inertial(t, position, velocity)
        return accel

    @property
    def n_parameters(self) -> int:
        return sum(m.accelerations_rtn.size for m in self.models)


def estimate_empirical_forces(
    times: np.ndarray,
    residual_accelerations: np.ndarray,
    positions: np.ndarray,
    velocities: np.ndarray,
    n_segments: int = 4,
    weights: Optional[np.ndarray] = None,
) -> Tuple[PiecewiseConstantAccel, np.ndarray]:
    """Fit piecewise-constant RTN accelerations to dynamic residuals.

    For each time segment, solves the weighted least-squares problem for
    the constant RTN acceleration that best explains the inertial-frame
    residual accelerations observed in that segment. Because the RTN
    basis is orthonormal, the per-segment solution is the weighted mean
    of the residuals rotated into RTN.

    Parameters
    ----------
    times : ndarray, shape (n,)
        Observation epochs (monotonic).
    residual_accelerations : ndarray, shape (n, 3)
        Observed-minus-modeled accelerations in the inertial frame (m/s^2).
    positions, velocities : ndarray, shape (n, 3)
        Orbit states at each epoch (used for the RTN rotation).
    n_segments : int
        Number of equal-duration segments.
    weights : ndarray, shape (n,), optional
        Per-epoch weights (default: uniform).

    Returns
    -------
    model : PiecewiseConstantAccel
        Fitted empirical acceleration model.
    postfit_rms : ndarray, shape (3,)
        Post-fit residual RMS per RTN axis (m/s^2).
    """
    times = np.asarray(times, dtype=float)
    residual_accelerations = np.asarray(residual_accelerations, dtype=float)
    n = len(times)
    if residual_accelerations.shape != (n, 3):
        raise ValueError("residual_accelerations must have shape (n, 3)")
    if weights is None:
        weights = np.ones(n)

    # Rotate residuals into RTN at each epoch
    residuals_rtn = np.empty_like(residual_accelerations)
    for i in range(n):
        m = rtn_basis(positions[i], velocities[i])
        residuals_rtn[i] = m @ residual_accelerations[i]

    bounds = np.linspace(times[0], times[-1], n_segments + 1)
    accels = np.zeros((n_segments, 3))
    postfit = np.zeros_like(residuals_rtn)

    for k in range(n_segments):
        if k < n_segments - 1:
            mask = (times >= bounds[k]) & (times < bounds[k + 1])
        else:
            mask = (times >= bounds[k]) & (times <= bounds[k + 1])
        if not np.any(mask):
            continue
        w = weights[mask]
        accels[k] = np.average(residuals_rtn[mask], axis=0, weights=w)
        postfit[mask] = residuals_rtn[mask] - accels[k]

    model = PiecewiseConstantAccel(segment_bounds=bounds, accelerations_rtn=accels)
    postfit_rms = np.sqrt(np.mean(postfit**2, axis=0))
    return model, postfit_rms
