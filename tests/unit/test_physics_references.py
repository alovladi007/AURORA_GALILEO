"""
Physics Reference Validation Tests
===================================

Each test validates a dynamics-code fix against an independent physical
reference (analytic result or published test case) rather than against
the code's own output. These are the Phase 1 W1.1 acceptance tests from
MASTER_BUILD_PROMPT_18_MONTHS.md.
"""

import numpy as np
import pytest
import jax.numpy as jnp

from sim.dynamics.keplerian import (
    GM_EARTH,
    R_EARTH,
    orbital_elements_to_cartesian,
    cartesian_to_orbital_elements,
    two_body_dynamics,
    mean_motion,
)
from sim.dynamics.perturbations import (
    J2_EARTH,
    j2_acceleration,
    atmospheric_density,
    atmospheric_drag_acceleration,
    solar_radiation_pressure_acceleration,
    perturbed_dynamics,
)
from sim.dynamics.propagators import propagate_orbit, propagate_orbit_jax


class TestJ2Direction:
    """J2 must pull inward at the equator and push outward at the poles
    (Earth's equatorial bulge adds mass near the equator)."""

    def test_equatorial_acceleration_points_inward(self):
        r = jnp.array([7000.0, 0.0, 0.0])
        a = j2_acceleration(r)
        assert float(a[0]) < 0.0, "J2 at the equator must point toward Earth"
        assert abs(float(a[1])) < 1e-12 and abs(float(a[2])) < 1e-12

    def test_polar_acceleration_points_outward(self):
        r = jnp.array([0.0, 0.0, 7000.0])
        a = j2_acceleration(r)
        assert float(a[2]) > 0.0, "J2 at the pole must point away from Earth"

    def test_magnitude_order(self):
        # |a_J2| ~ (3/2) J2 (R/r)^2 * mu/r^2 ~ 1e-5 km/s^2 at LEO
        r = jnp.array([7000.0, 0.0, 0.0])
        a_mag = float(jnp.linalg.norm(j2_acceleration(r)))
        expected = 1.5 * J2_EARTH * GM_EARTH * R_EARTH**2 / 7000.0**4
        assert a_mag == pytest.approx(expected, rel=1e-6)


class TestJ2SecularRates:
    """Numerically propagate a LEO orbit with two-body + J2 and compare
    the RAAN drift against the analytic secular rate
    dRAAN/dt = -(3/2) n J2 (R/p)^2 cos(i)  (Vallado Eq. 9-38)."""

    def test_raan_regression_sun_synchronous_sign_and_rate(self):
        a, e, inc = 7178.0, 0.001, jnp.deg2rad(98.6)
        raan0, argp0, nu0 = 0.5, 0.3, 0.0
        r0, v0 = orbital_elements_to_cartesian(a, e, inc, raan0, argp0, nu0)
        state0 = jnp.concatenate([r0, v0])

        def dynamics(t, s):
            d = two_body_dynamics(t, s)
            return d.at[3:6].add(j2_acceleration(s[:3]))

        # ~10 orbits
        period = 2 * np.pi / float(mean_motion(a))
        tf = 10.0 * period
        times, states = propagate_orbit(dynamics, state0, (0.0, tf), dt=10.0,
                                        save_every=30)

        elems_end = cartesian_to_orbital_elements(
            states[-1][:3], states[-1][3:]
        )
        raan_end = float(elems_end[3])
        d_raan = (raan_end - raan0 + np.pi) % (2 * np.pi) - np.pi
        measured_rate = d_raan / tf

        n = float(mean_motion(a))
        p = a * (1 - e**2)
        analytic_rate = (
            -1.5 * n * J2_EARTH * (R_EARTH / p) ** 2 * np.cos(float(inc))
        )
        # Sun-synchronous inclination (i > 90 deg): RAAN drifts eastward
        assert analytic_rate > 0
        assert measured_rate == pytest.approx(analytic_rate, rel=0.05)

    def test_prograde_orbit_raan_regresses_westward(self):
        a, e, inc = 7000.0, 0.001, jnp.deg2rad(51.6)  # ISS-like
        r0, v0 = orbital_elements_to_cartesian(a, e, inc, 1.0, 0.0, 0.0)
        state0 = jnp.concatenate([r0, v0])

        def dynamics(t, s):
            d = two_body_dynamics(t, s)
            return d.at[3:6].add(j2_acceleration(s[:3]))

        period = 2 * np.pi / float(mean_motion(a))
        times, states = propagate_orbit(dynamics, state0,
                                        (0.0, 5 * period), dt=10.0,
                                        save_every=30)
        raan_end = float(
            cartesian_to_orbital_elements(states[-1][:3], states[-1][3:])[3]
        )
        d_raan = (raan_end - 1.0 + np.pi) % (2 * np.pi) - np.pi
        assert d_raan < 0.0, "prograde-orbit RAAN must regress westward"


class TestElementConversion:
    """Element <-> Cartesian conversions against known geometry and
    round-trip identity."""

    def test_raan_90_places_ascending_node_on_plus_y(self):
        # i=0 degenerate; use small inclination, nu=0 at ascending node
        r, v = orbital_elements_to_cartesian(
            a=7000.0, e=0.0, i=jnp.deg2rad(10.0),
            omega=jnp.pi / 2, w=0.0, nu=0.0
        )
        # At the ascending node with RAAN=90 deg, position is along +y
        assert float(r[1]) == pytest.approx(7000.0, rel=1e-6)
        assert abs(float(r[0])) < 1.0 and abs(float(r[2])) < 1.0

    def test_round_trip_vallado(self):
        # Vallado-style general case
        elems_in = dict(a=8000.0, e=0.1, i=jnp.deg2rad(45.0),
                        omega=jnp.deg2rad(60.0), w=jnp.deg2rad(30.0),
                        nu=jnp.deg2rad(75.0))
        r, v = orbital_elements_to_cartesian(**elems_in)
        a, e, i, raan, argp, nu = cartesian_to_orbital_elements(r, v)
        assert float(a) == pytest.approx(8000.0, rel=1e-5)
        assert float(e) == pytest.approx(0.1, abs=1e-5)
        assert float(i) == pytest.approx(float(elems_in["i"]), abs=1e-5)
        assert float(raan) == pytest.approx(float(elems_in["omega"]), abs=1e-5)
        assert float(argp) == pytest.approx(float(elems_in["w"]), abs=1e-4)
        assert float(nu) == pytest.approx(float(elems_in["nu"]), abs=1e-4)

    def test_vis_viva(self):
        r, v = orbital_elements_to_cartesian(
            a=7500.0, e=0.05, i=0.4, omega=1.0, w=2.0, nu=0.7
        )
        r_mag, v_mag = float(jnp.linalg.norm(r)), float(jnp.linalg.norm(v))
        v_expected = np.sqrt(GM_EARTH * (2 / r_mag - 1 / 7500.0))
        assert v_mag == pytest.approx(v_expected, rel=1e-6)


class TestDragMagnitude:
    """Drag at 400 km with A/m=0.01, Cd=2.2 must be ~2e-9 km/s^2
    (i.e. ~2e-6 m/s^2), not 1e6x larger."""

    def test_400km_drag_order_of_magnitude(self):
        r = jnp.array([R_EARTH + 400.0, 0.0, 0.0])
        v = jnp.array([0.0, 7.67, 0.0])
        a = atmospheric_drag_acceleration(r, v, cd=2.2, area_to_mass=0.01)
        a_mag = float(jnp.linalg.norm(a))
        # rho(400km)=3.725e-12 kg/m^3 -> a = 0.5*2.2*0.01*rho*1e3*v^2
        rho = 3.725e-12
        v_rel = 7.67 - 7.2921150e-5 * (R_EARTH + 400.0)  # co-rotation
        expected = 0.5 * 2.2 * 0.01 * rho * 1e3 * v_rel**2
        assert a_mag == pytest.approx(expected, rel=0.05)
        assert 1e-10 < a_mag < 1e-8, f"drag magnitude {a_mag} km/s^2 wrong scale"

    def test_drag_opposes_relative_velocity(self):
        r = jnp.array([R_EARTH + 400.0, 0.0, 0.0])
        v = jnp.array([0.0, 7.67, 0.0])
        a = atmospheric_drag_acceleration(r, v)
        assert float(a[1]) < 0.0

    def test_density_reference_values(self):
        # Vallado exponential-atmosphere table anchor points
        assert float(atmospheric_density(400.0)) == pytest.approx(3.725e-12, rel=1e-3)
        assert float(atmospheric_density(0.0)) == pytest.approx(1.225, rel=1e-3)
        # Between anchors: decays monotonically
        assert float(atmospheric_density(425.0)) < float(atmospheric_density(400.0))


class TestSRPMagnitude:
    """SRP for A/m=0.01, Cr=1.3 must be ~5.9e-11 km/s^2 and point away
    from the sun."""

    def test_srp_magnitude_and_direction(self):
        r = jnp.array([7000.0, 0.0, 0.0])
        r_sun = jnp.array([1.496e8, 0.0, 0.0])
        a = solar_radiation_pressure_acceleration(r, r_sun, cr=1.3,
                                                  area_to_mass=0.01)
        expected = 4.56e-6 * 1.3 * 0.01 / 1000.0  # km/s^2
        assert float(jnp.linalg.norm(a)) == pytest.approx(expected, rel=1e-6)
        assert float(a[0]) < 0.0, "SRP must push away from the sun"


class TestJITCallability:
    """The jitted entry points must actually be callable (previously
    crashed with TracerBoolConversionError / ConcretizationTypeError)."""

    def test_perturbed_dynamics_with_drag_runs(self):
        state = jnp.array([7000.0, 0.0, 0.0, 0.0, 7.5, 0.0])
        d = perturbed_dynamics(0.0, state, include_j2=True, include_drag=True)
        assert d.shape == (6,)
        assert np.all(np.isfinite(np.asarray(d)))

    def test_propagate_orbit_jax_runs_and_conserves_energy(self):
        state0 = jnp.array([7000.0, 0.0, 0.0, 0.0,
                            float(np.sqrt(GM_EARTH / 7000.0)), 0.0])
        times, states = propagate_orbit_jax(
            two_body_dynamics, state0, t_span=(0.0, 5400.0), dt=10.0
        )
        assert states.shape[0] == times.shape[0]

        def energy(s):
            r = np.linalg.norm(s[:3]); v = np.linalg.norm(s[3:])
            return 0.5 * v**2 - GM_EARTH / r

        e0, e1 = energy(np.asarray(states[0])), energy(np.asarray(states[-1]))
        assert e1 == pytest.approx(e0, rel=1e-5)

    def test_two_body_propagation_matches_analytic_period(self):
        # After one full period the satellite returns to its start point
        a = 7000.0
        v_circ = float(np.sqrt(GM_EARTH / a))
        state0 = jnp.array([a, 0.0, 0.0, 0.0, v_circ, 0.0])
        period = 2 * np.pi * np.sqrt(a**3 / GM_EARTH)
        n_steps = int(period / 5.0)
        times, states = propagate_orbit(two_body_dynamics, state0,
                                        (0.0, n_steps * 5.0), dt=5.0)
        # position error after ~1 period, relative to orbit radius
        err = np.linalg.norm(np.asarray(states[-1][:3]) - np.array([a, 0, 0]))
        # allow the residual arc from period-vs-grid mismatch (<5 s * v)
        assert err < 5.0 * v_circ + 1.0
