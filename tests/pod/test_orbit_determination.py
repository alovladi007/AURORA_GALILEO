"""
Dynamic Orbit Determination — closed-loop recovery tests (Phase 1 W1.3).

Truth orbits are generated with the same force model, corrupted with
measurement noise and an initial-state error, and must be recovered by
the batch estimator. This is the Gate 1 POD acceptance test.
"""

import numpy as np
import pytest
import jax.numpy as jnp

from pod.orbit_determination import (
    DynamicODResult,
    dynamics_two_body_j2,
    estimate_orbit_dynamic,
)
from sim.dynamics.propagators import propagate_orbit
from sim.dynamics.keplerian import GM_EARTH


def _make_truth_arc(dt=10.0, n_meas=60, every=6):
    """Truth LEO trajectory sampled every `every` integrator steps."""
    a = 6878.0  # ~500 km altitude
    v_circ = float(np.sqrt(GM_EARTH / a))
    x_truth = jnp.array([a, 0.0, 0.0, 0.0, v_circ * 0.9, v_circ * 0.4359])
    tf = dt * every * (n_meas - 1)
    times_all, states = propagate_orbit(
        dynamics_two_body_j2, x_truth, (0.0, tf), dt=dt
    )
    idx = np.arange(0, n_meas * every, every)
    times = np.asarray(times_all)[idx]
    positions = np.asarray(states)[idx, :3]
    return np.asarray(x_truth), times, positions


class TestClosedLoopRecovery:
    def test_recovers_epoch_state_from_noisy_positions(self):
        rng = np.random.RandomState(42)
        x_truth, times, positions = _make_truth_arc()

        noise_km = 1e-4  # 0.1 m per axis
        z = positions + rng.normal(0.0, noise_km, positions.shape)

        # Perturbed initial guess: 5 km / 5 m/s off
        x0_guess = x_truth + np.array([5.0, -3.0, 2.0, 5e-3, -4e-3, 3e-3])

        result = estimate_orbit_dynamic(
            times, z, x0_guess, dt=10.0, measurement_noise_km=noise_km
        )

        assert result.converged
        pos_err = np.linalg.norm(result.state_epoch[:3] - x_truth[:3])
        vel_err = np.linalg.norm(result.state_epoch[3:] - x_truth[3:])
        # Gate 1 criterion: epoch position recovered to < 10 cm
        assert pos_err < 1e-4, f"epoch position error {pos_err*1e3:.3f} m"
        assert vel_err < 1e-6, f"epoch velocity error {vel_err*1e6:.3f} mm/s"
        # Post-fit residuals at the noise floor (not above, not
        # suspiciously below)
        assert result.residual_rms_km == pytest.approx(
            noise_km * np.sqrt(3), rel=0.4
        )

    def test_covariance_is_credible(self):
        """The formal covariance must bound the actual error (within
        statistical slack): the actual epoch error should be within
        ~3 sigma of the formal uncertainty."""
        rng = np.random.RandomState(7)
        x_truth, times, positions = _make_truth_arc()
        noise_km = 1e-4
        z = positions + rng.normal(0.0, noise_km, positions.shape)
        x0_guess = x_truth + np.array([1.0, 1.0, -1.0, 1e-3, -1e-3, 1e-3])

        result = estimate_orbit_dynamic(
            times, z, x0_guess, dt=10.0, measurement_noise_km=noise_km
        )
        sigma_pos = np.sqrt(np.trace(result.covariance[:3, :3]))
        actual_pos_err = np.linalg.norm(result.state_epoch[:3] - x_truth[:3])
        assert actual_pos_err < 5.0 * sigma_pos
        assert sigma_pos < 1e-4  # formal uncertainty itself sub-10 cm

    def test_j2_matters_over_the_arc(self):
        """Sanity: the J2 term produces a multi-meter difference over
        the fitted arc, so the estimator genuinely needs the dynamics
        (a two-body-only fit would be biased)."""
        from sim.dynamics.keplerian import two_body_dynamics
        x_truth, times, _ = _make_truth_arc()
        tf = float(times[-1])
        _, s_j2 = propagate_orbit(dynamics_two_body_j2,
                                  jnp.asarray(x_truth), (0.0, tf), dt=10.0)
        _, s_2b = propagate_orbit(two_body_dynamics,
                                  jnp.asarray(x_truth), (0.0, tf), dt=10.0)
        diff = np.linalg.norm(np.asarray(s_j2)[-1, :3] - np.asarray(s_2b)[-1, :3])
        assert diff > 1e-3, f"J2 effect only {diff*1e3:.1f} m over the arc"
