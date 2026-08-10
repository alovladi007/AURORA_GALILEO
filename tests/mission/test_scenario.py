"""
Mission scenario generator tests (Phase 3 W3.1 acceptance).

The generator must produce physically consistent, provenance-tagged
observables from the validated dynamics — with no invented numbers.
"""

import numpy as np
import pytest

from mission.scenario import (
    MissionConfig,
    MissionScenario,
    ecef_to_geodetic_spherical,
    eci_to_ecef,
)
from sim.dynamics.keplerian import R_EARTH


@pytest.fixture(scope="module")
def scenario():
    s = MissionScenario(MissionConfig(duration_s=1800.0, dt_s=10.0))
    s.propagate()
    s.synthesize()
    return s


class TestOrbits:
    def test_two_satellites_propagated(self, scenario):
        assert len(scenario.arcs) == 2
        for arc in scenario.arcs:
            assert arc.states_eci.shape[1] == 6
            radii = np.linalg.norm(arc.states_eci[:, :3], axis=1)
            # near-circular 500 km orbit stays within a few km of a
            alt = radii - R_EARTH
            assert np.all(alt > 480.0) and np.all(alt < 520.0)

    def test_along_track_separation(self, scenario):
        a, b = scenario.arcs
        sep = np.linalg.norm(a.states_eci[0, :3] - b.states_eci[0, :3])
        # 30 s at ~7.6 km/s -> ~230 km separation
        assert 150.0 < sep < 300.0


class TestObservables:
    def test_telemetry_positions_match_truth(self, scenario):
        """Round-trip lat/lon/alt back to ECI: must match the truth
        state to the injected noise level (no invented positions)."""
        arc = scenario.arcs[0]
        errs = []
        for rec, t, state in zip(arc.telemetry, arc.times, arc.states_eci):
            lat = np.deg2rad(rec["location"]["latitude"])
            lon = np.deg2rad(rec["location"]["longitude"])
            r = R_EARTH + rec["location"]["altitude"] / 1e3
            r_ecef = r * np.array([
                np.cos(lat) * np.cos(lon),
                np.cos(lat) * np.sin(lon),
                np.sin(lat),
            ])
            r_eci = eci_to_ecef(r_ecef, -float(t))
            errs.append(np.linalg.norm(r_eci - state[:3]) * 1e3)  # m
        errs = np.array(errs)
        # noise is 1 m/axis -> 3D RMS ~1.7 m; anything >20 m would mean
        # the transform chain is broken
        assert np.median(errs) < 5.0
        assert np.max(errs) < 20.0

    def test_gravity_values_from_real_field(self, scenario):
        """Anomalies must match the analytic J2 radial perturbation at
        500 km: -(3/2) J2 g (R/r)^2 at the equator (inward), and twice
        that magnitude outward at the poles."""
        from sim.dynamics.keplerian import GM_EARTH
        from sim.dynamics.perturbations import J2_EARTH

        arc = scenario.arcs[0]
        values = np.array([g["gravity_value"] for g in arc.gravity])
        lats = np.array([g["location"]["latitude"] for g in arc.gravity])

        r = R_EARTH + scenario.config.altitude_km
        g_r = GM_EARTH / r**2 * 1e3          # m/s^2 (GM in km^3/s^2)
        base = 1.5 * J2_EARTH * g_r * (R_EARTH / r) ** 2 / 1e-5  # mGal
        # Equator: -base (inward); pole: +2*base (outward)
        assert np.min(values) == pytest.approx(-base, rel=0.05)
        assert np.max(values) == pytest.approx(2 * base, rel=0.05)
        # Radial perturbation ~ (3 sin^2(lat) - 1): strong POSITIVE
        # correlation with sin^2(lat)
        corr = np.corrcoef(np.sin(np.deg2rad(lats)) ** 2, values)[0, 1]
        assert corr > 0.9, f"gravity does not track latitude (corr={corr:.2f})"

    def test_provenance_tagged(self, scenario):
        for arc in scenario.arcs:
            assert all(g["quality_flag"] == "synthetic" for g in arc.gravity)

    def test_reproducible(self):
        a = MissionScenario(MissionConfig(duration_s=600.0))
        a.propagate(); a.synthesize()
        b = MissionScenario(MissionConfig(duration_s=600.0))
        b.propagate(); b.synthesize()
        ga = [g["gravity_value"] for g in a.arcs[0].gravity]
        gb = [g["gravity_value"] for g in b.arcs[0].gravity]
        assert ga == gb, "same seed must reproduce the same dataset"


class TestClosedLoopOD:
    def test_orbit_recovery_from_own_telemetry(self, scenario):
        """The dynamic estimator must recover the truth epoch state
        from the generated (noisy) telemetry to better than 10 m."""
        od = scenario.orbit_determination_check(
            scenario.arcs[0].telemetry, scenario.arcs[0]
        )
        assert od["converged"]
        assert od["epoch_position_error_m"] < 10.0
        assert od["postfit_rms_m"] < 10.0
