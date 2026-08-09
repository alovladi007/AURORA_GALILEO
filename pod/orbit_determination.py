"""
Dynamic Orbit Determination
============================

Batch least-squares orbit determination with a real force model
(two-body + J2 from ``sim.dynamics``), replacing the kinematic
single-epoch solvers in ``pod.estimators`` for arcs of tracking data.

The estimated state is the epoch state x0 = [r0 (km), v0 (km/s)].
Measurement partials with respect to x0 are obtained by automatic
differentiation (JAX ``jacfwd``) straight through the RK4 propagation
— no hand-derived state transition matrix, no finite differencing.

Units: kilometers / seconds throughout (matching ``sim.dynamics``).
"""

from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np
import jax

# Orbit determination requires float64: at LEO radius (~6878 km) the
# float32 representational granularity is ~0.8 m, far above the
# centimeter-level recovery this module must deliver.
jax.config.update("jax_enable_x64", True)

import jax.numpy as jnp

from sim.dynamics.keplerian import two_body_dynamics
from sim.dynamics.perturbations import j2_acceleration
from sim.dynamics.propagators import rk4_step


def dynamics_two_body_j2(t: float, state: jnp.ndarray) -> jnp.ndarray:
    """Two-body + J2 equations of motion (km, km/s)."""
    deriv = two_body_dynamics(t, state)
    return deriv.at[3:6].add(j2_acceleration(state[:3]))


def _propagate_to_indices(x0: jnp.ndarray, dt: float, n_steps: int,
                          meas_indices: jnp.ndarray) -> jnp.ndarray:
    """Propagate x0 over n_steps of RK4 and gather states at the given
    step indices. Differentiable w.r.t. x0."""

    def step(state, k):
        next_state = rk4_step(dynamics_two_body_j2, k * dt, state, dt)
        return next_state, next_state

    _, states = jax.lax.scan(step, x0, jnp.arange(n_steps))
    all_states = jnp.vstack([x0[None, :], states])
    return all_states[meas_indices]


@dataclass
class DynamicODResult:
    """Result of a dynamic batch least-squares fit."""

    state_epoch: np.ndarray          # estimated [r0, v0] (km, km/s)
    covariance: np.ndarray           # 6x6 epoch-state covariance
    residual_rms_km: float           # post-fit position residual RMS
    iterations: int
    converged: bool


def estimate_orbit_dynamic(
    times: np.ndarray,
    position_measurements: np.ndarray,
    x0_guess: np.ndarray,
    dt: float = 10.0,
    measurement_noise_km: float = 1e-3,
    max_iterations: int = 10,
    convergence_tol_km: float = 1e-7,
) -> DynamicODResult:
    """Batch least-squares orbit determination over a tracking arc.

    Args:
        times: Measurement epochs (s), starting at 0, each a multiple
            of ``dt`` (measurements are matched to propagation steps).
        position_measurements: Observed positions (km), shape (n, 3).
        x0_guess: Initial guess for the epoch state [r0, v0].
        dt: Integrator step (s).
        measurement_noise_km: 1-sigma per-axis position noise (km).
        max_iterations: Gauss-Newton iteration cap.
        convergence_tol_km: Stop when the position part of the state
            update falls below this (km).

    Returns:
        DynamicODResult with the estimated epoch state, covariance
        (from the normal matrix and the stated measurement noise),
        post-fit residual RMS, and convergence info.
    """
    times = np.asarray(times, dtype=float)
    z = jnp.asarray(position_measurements, dtype=jnp.float64)
    n_meas = z.shape[0]

    meas_indices = jnp.asarray(np.rint(times / dt).astype(int))
    n_steps = int(meas_indices[-1])

    def predict_positions(x0):
        return _propagate_to_indices(x0, dt, n_steps, meas_indices)[:, :3]

    predict_jac = jax.jacfwd(predict_positions)

    x = jnp.asarray(x0_guess, dtype=jnp.float64)
    converged = False
    iterations = 0
    for iterations in range(1, max_iterations + 1):
        pred = predict_positions(x)
        resid = (z - pred).reshape(-1)              # (3n,)
        J = predict_jac(x).reshape(-1, 6)           # (3n, 6)

        # Gauss-Newton normal equations (uniform weights)
        JTJ = J.T @ J
        JTr = J.T @ resid
        delta = jnp.linalg.solve(JTJ, JTr)
        x = x + delta

        if float(jnp.linalg.norm(delta[:3])) < convergence_tol_km:
            converged = True
            break

    pred = predict_positions(x)
    resid = np.asarray(z - pred)
    residual_rms = float(np.sqrt(np.mean(np.sum(resid**2, axis=1))))

    # Epoch-state covariance: sigma^2 (J^T J)^-1
    J = np.asarray(predict_jac(x).reshape(-1, 6), dtype=float)
    cov = measurement_noise_km**2 * np.linalg.inv(J.T @ J)

    return DynamicODResult(
        state_epoch=np.asarray(x, dtype=float),
        covariance=cov,
        residual_rms_km=residual_rms,
        iterations=iterations,
        converged=converged,
    )
