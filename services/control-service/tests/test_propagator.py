"""
Orbit Propagator Unit Tests
===========================

Validates the two-body + J2 RK4 propagator against analytic orbital mechanics.
"""

import math

import numpy as np
import pytest

from src.propagator import (
    propagate,
    circular_state,
    orbital_elements,
    rk4_step,
    R_EARTH,
    GM_EARTH,
)


class TestCircularOrbit:

    def test_leo_period_matches_analytic(self):
        """A 500 km circular orbit should have ~94.6 min period."""
        alt = 500.0
        state0 = circular_state(alt, inclination_deg=0.0)
        radius = R_EARTH + alt
        analytic_period = 2 * math.pi * math.sqrt(radius ** 3 / GM_EARTH)
        # ~5670 s ≈ 94.6 min
        assert analytic_period == pytest.approx(5670, rel=0.01)

        elems = orbital_elements(state0)
        assert elems["period_s"] == pytest.approx(analytic_period, rel=0.001)
        assert elems["altitude_km"] == pytest.approx(alt, abs=1.0)

    def test_two_body_energy_conserved(self):
        """Without J2, specific orbital energy should be conserved."""
        state0 = circular_state(500.0, 45.0)
        times, states = propagate(state0, duration_s=5670.0, timestep_s=10.0,
                                  include_j2=False)

        def energy(s):
            r = np.linalg.norm(s[:3])
            v = np.linalg.norm(s[3:])
            return v ** 2 / 2 - GM_EARTH / r

        e0 = energy(states[0])
        ef = energy(states[-1])
        assert ef == pytest.approx(e0, rel=1e-3)

    def test_circular_orbit_returns_near_start(self):
        """After one period, a circular orbit should return near its start."""
        state0 = circular_state(500.0, 0.0)
        period = orbital_elements(state0)["period_s"]
        times, states = propagate(state0, duration_s=period, timestep_s=5.0,
                                  include_j2=False)
        start_pos = states[0][:3]
        end_pos = states[-1][:3]
        # Within ~50 km after a full ~6900 km-radius orbit.
        assert np.linalg.norm(end_pos - start_pos) < 50.0


class TestJ2Perturbation:

    def test_j2_changes_trajectory(self):
        """J2 should produce a measurably different trajectory than two-body."""
        state0 = circular_state(500.0, 89.0)
        _, states_2body = propagate(state0, 5670.0, 10.0, include_j2=False)
        _, states_j2 = propagate(state0, 5670.0, 10.0, include_j2=True)
        diff = np.linalg.norm(states_j2[-1][:3] - states_2body[-1][:3])
        # J2 nodal drift produces a non-trivial separation over one orbit.
        assert diff > 1.0  # km

    def test_altitude_bounded_under_j2(self):
        """A near-circular orbit should stay near its nominal altitude."""
        state0 = circular_state(500.0, 89.0)
        _, states = propagate(state0, 5670.0, 10.0, include_j2=True)
        altitudes = np.linalg.norm(states[:, :3], axis=1) - R_EARTH
        assert altitudes.min() > 400.0
        assert altitudes.max() < 600.0


class TestIntegrator:

    def test_rk4_step_preserves_shape(self):
        state0 = circular_state(500.0, 0.0)
        next_state = rk4_step(state0, 10.0, include_j2=True)
        assert next_state.shape == (6,)
        assert not np.allclose(next_state, state0)
