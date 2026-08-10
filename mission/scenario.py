"""
Mission scenario generation: a GRACE-like two-satellite formation.

The pipeline this module feeds (Phase 3 of
MASTER_BUILD_PROMPT_18_MONTHS.md):

    dynamics (two-body + J2, validated Phase 1)
      -> satellite telemetry (positions, housekeeping)
      -> gravity observables (real spherical-harmonic field, mGal)
      -> gateway REST ingestion (auth + gRPC + TimescaleDB)
      -> query-back -> precise orbit determination (pod.orbit_determination)

Every generated record is tagged with provenance "synthetic". No
numbers are invented at the presentation layer: telemetry positions
come from the propagated orbit, gravity values from the degree-6 zonal
spherical-harmonic model evaluated at the satellite location.

Units: the dynamics work in km (sim.dynamics convention); REST
payloads use meters for altitude (proto convention) and mGal for
gravity anomalies.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

import jax

jax.config.update("jax_enable_x64", True)

import jax.numpy as jnp  # noqa: E402

from sim.dynamics.keplerian import (  # noqa: E402
    GM_EARTH,
    R_EARTH,
    orbital_elements_to_cartesian,
)
from sim.dynamics.propagators import propagate_orbit  # noqa: E402
from pod.orbit_determination import dynamics_two_body_j2  # noqa: E402
from sim.gravity import SphericalHarmonics, load_egm2008_model  # noqa: E402

OMEGA_EARTH = 7.2921150e-5  # rad/s


def eci_to_ecef(r_eci: np.ndarray, t: float, theta0: float = 0.0) -> np.ndarray:
    """Rotate an ECI position into ECEF for Earth rotation angle
    theta = theta0 + omega_E * t (spherical Earth, no polar motion)."""
    theta = theta0 + OMEGA_EARTH * t
    c, s = np.cos(theta), np.sin(theta)
    rot = np.array([[c, s, 0.0], [-s, c, 0.0], [0.0, 0.0, 1.0]])
    return rot @ r_eci


def ecef_to_geodetic_spherical(r_ecef: np.ndarray) -> Tuple[float, float, float]:
    """ECEF -> (lat_deg, lon_deg, alt_m) on a spherical Earth of radius
    R_EARTH (documented simplification; WGS84 geodesy is Phase 3 work)."""
    r = float(np.linalg.norm(r_ecef))
    lat = float(np.degrees(np.arcsin(r_ecef[2] / r)))
    lon = float(np.degrees(np.arctan2(r_ecef[1], r_ecef[0])))
    alt_m = (r - R_EARTH) * 1e3
    return lat, lon, alt_m


@dataclass
class MissionConfig:
    """Two-satellite along-track formation (GRACE-like)."""

    altitude_km: float = 500.0
    inclination_deg: float = 89.0     # near-polar for global coverage
    separation_s: float = 30.0        # along-track separation (seconds)
    duration_s: float = 5400.0        # one orbit by default
    dt_s: float = 10.0                # integrator step
    sample_every: int = 6             # telemetry cadence = dt * this
    gravity_degree: int = 6           # zonal spherical-harmonic degree
    seed: int = 42
    satellite_ids: Tuple[str, str] = ("GAL-SIM-A", "GAL-SIM-B")
    telemetry_noise_m: float = 1.0    # per-axis position noise (1 sigma)
    gravity_noise_mgal: float = 0.05  # measurement noise (1 sigma)


@dataclass
class SatelliteArc:
    satellite_id: str
    times: np.ndarray                 # (n,) seconds from epoch
    states_eci: np.ndarray            # (n, 6) km, km/s (truth)
    telemetry: List[Dict] = field(default_factory=list)
    gravity: List[Dict] = field(default_factory=list)


class MissionScenario:
    """Generate a mission data arc with real physics end to end."""

    def __init__(self, config: Optional[MissionConfig] = None):
        self.config = config or MissionConfig()
        self.rng = np.random.RandomState(self.config.seed)
        model = load_egm2008_model(max_degree=self.config.gravity_degree)
        self._gravity_field = SphericalHarmonics(model)
        self._gm_si = model.gm
        self.arcs: List[SatelliteArc] = []

    # ── Orbit generation ─────────────────────────────────────────────
    def _initial_state(self, along_track_offset_s: float) -> jnp.ndarray:
        cfg = self.config
        a = R_EARTH + cfg.altitude_km
        n = float(np.sqrt(GM_EARTH / a**3))
        nu0 = -n * along_track_offset_s  # trailing satellite
        r0, v0 = orbital_elements_to_cartesian(
            a=a,
            e=0.0011,
            i=float(np.deg2rad(cfg.inclination_deg)),
            omega=0.35,
            w=0.0,
            nu=nu0,
        )
        return jnp.concatenate([r0, v0])

    def propagate(self) -> None:
        """Propagate both satellites with the validated two-body + J2
        dynamics."""
        cfg = self.config
        offsets = (0.0, cfg.separation_s)
        self.arcs = []
        for sat_id, offset in zip(cfg.satellite_ids, offsets):
            x0 = self._initial_state(offset)
            times, states = propagate_orbit(
                dynamics_two_body_j2, x0, (0.0, cfg.duration_s), dt=cfg.dt_s
            )
            idx = np.arange(0, len(np.asarray(times)), cfg.sample_every)
            self.arcs.append(
                SatelliteArc(
                    satellite_id=sat_id,
                    times=np.asarray(times)[idx],
                    states_eci=np.asarray(states)[idx],
                )
            )

    # ── Observable synthesis ─────────────────────────────────────────
    def _gravity_anomaly_mgal(self, r_eci_km: np.ndarray) -> float:
        """Radial gravity anomaly at the satellite location: full
        spherical-harmonic field minus the central term, in mGal
        (1 mGal = 1e-5 m/s^2)."""
        pos_m = jnp.asarray(r_eci_km * 1e3)
        a_full = np.asarray(self._gravity_field.gravitational_acceleration(pos_m))
        r = float(np.linalg.norm(np.asarray(pos_m)))
        a_central = -self._gm_si / r**3 * np.asarray(pos_m)
        d_a = a_full - a_central
        # Signed radial component of the perturbation
        radial = float(np.dot(d_a, np.asarray(pos_m)) / r)
        return radial / 1e-5

    def synthesize(self, epoch_iso: str = "2026-08-10T00:00:00") -> None:
        """Build telemetry + gravity records for every sample."""
        from datetime import datetime, timedelta

        cfg = self.config
        epoch = datetime.fromisoformat(epoch_iso)
        for arc in self.arcs:
            arc.telemetry.clear()
            arc.gravity.clear()
            for t, state in zip(arc.times, arc.states_eci):
                r_eci = state[:3]
                # Position with realistic GNSS-level noise (km)
                r_noisy = r_eci + self.rng.normal(
                    0.0, cfg.telemetry_noise_m / 1e3, 3
                )
                r_ecef = eci_to_ecef(r_noisy, float(t))
                lat, lon, alt_m = ecef_to_geodetic_spherical(r_ecef)
                stamp = (epoch + timedelta(seconds=float(t))).isoformat() + "Z"

                arc.telemetry.append({
                    "satellite_id": arc.satellite_id,
                    "timestamp": stamp,
                    "location": {
                        "latitude": lat,
                        "longitude": lon,
                        "altitude": alt_m,
                    },
                    # Housekeeping follows a simple thermal/power model:
                    # temperature swings with the orbit angle, battery
                    # discharges in eclipse-half and recharges in sun.
                    "temperature": 20.0 + 8.0 * np.sin(
                        2 * np.pi * float(t) / cfg.duration_s
                    ),
                    "battery_level": 85.0 + 10.0 * np.cos(
                        2 * np.pi * float(t) / cfg.duration_s
                    ),
                })

                anomaly = self._gravity_anomaly_mgal(r_eci)
                arc.gravity.append({
                    "satellite_id": arc.satellite_id,
                    "timestamp": stamp,
                    "location": {
                        "latitude": lat,
                        "longitude": lon,
                        "altitude": alt_m,
                    },
                    "gravity_value": anomaly + self.rng.normal(
                        0.0, cfg.gravity_noise_mgal
                    ),
                    "uncertainty": cfg.gravity_noise_mgal,
                    # Provenance tag: these are simulated observables.
                    "quality_flag": "synthetic",
                })

    # ── Closed-loop check ────────────────────────────────────────────
    def orbit_determination_check(
        self, telemetry: List[Dict], truth_arc: SatelliteArc
    ) -> Dict[str, float]:
        """Reconstruct ECI positions from (queried-back) telemetry and
        run the dynamic batch estimator against them; report recovery
        error vs the truth epoch state."""
        from pod.orbit_determination import estimate_orbit_dynamic

        times, positions = [], []
        for rec, t in zip(telemetry, truth_arc.times):
            lat = np.deg2rad(rec["location"]["latitude"])
            lon = np.deg2rad(rec["location"]["longitude"])
            r = R_EARTH + rec["location"]["altitude"] / 1e3
            r_ecef = r * np.array([
                np.cos(lat) * np.cos(lon),
                np.cos(lat) * np.sin(lon),
                np.sin(lat),
            ])
            # invert the Earth rotation applied at synthesis time
            r_eci = eci_to_ecef(r_ecef, -float(t))
            times.append(float(t))
            positions.append(r_eci)

        x_truth = truth_arc.states_eci[0]
        x_guess = x_truth + np.array([2.0, -1.0, 1.5, 2e-3, -1e-3, 1e-3])
        result = estimate_orbit_dynamic(
            np.array(times),
            np.array(positions),
            x_guess,
            dt=self.config.dt_s,
            measurement_noise_km=self.config.telemetry_noise_m / 1e3,
        )
        pos_err_m = float(
            np.linalg.norm(result.state_epoch[:3] - x_truth[:3]) * 1e3
        )
        vel_err_mm_s = float(
            np.linalg.norm(result.state_epoch[3:] - x_truth[3:]) * 1e6
        )
        return {
            "converged": float(result.converged),
            "epoch_position_error_m": pos_err_m,
            "epoch_velocity_error_mm_s": vel_err_mm_s,
            "postfit_rms_m": result.residual_rms_km * 1e3,
        }
