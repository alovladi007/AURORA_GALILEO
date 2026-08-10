"""
Closed-loop anomaly recovery benchmark (Phase 3 flagship KPI).

Inject a known ground-fixed mass anomaly into the synthetic Earth,
fly the two-satellite formation over it, grid the observables exactly
as the platform's fetcher does, invert with the engine's honest masked
path, and require the anomaly to be recovered — in the right place,
with the right sign, at a defensible amplitude.

Twin-experiment design: an identical scenario WITHOUT the anomaly
(same seed, same tracks, same noise draws) is processed identically;
differencing the two recovered maps isolates the injected signal from
the J2 background and any gridding artifacts.
"""

import sys
import time
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services" / "inversion-service"))

from mission.scenario import MissionConfig, MissionScenario  # noqa: E402
from src.inversion_engine import InversionEngine  # noqa: E402

# Anomaly position is chosen under an actual overflight (computed from
# the background scenario's ground track) so the benchmark tests
# RECOVERY quality, not orbit-geometry luck.
ANOMALY_AMPLITUDE = 80.0
ANOMALY_SIGMA_DEG = 18.0
ROWS, COLS = 18, 18
LAT_RANGE = (-85.0, 85.0)
LON_RANGE = (-180.0, 180.0)


def _bin_to_grid(arcs):
    """Bin gravity records onto the grid exactly as the platform's
    GravityDataFetcher does (mean per cell)."""
    accum = np.zeros(ROWS * COLS)
    counts = np.zeros(ROWS * COLS)
    lat_span = LAT_RANGE[1] - LAT_RANGE[0]
    lon_span = LON_RANGE[1] - LON_RANGE[0]
    for arc in arcs:
        for g in arc.gravity:
            r = int((g["location"]["latitude"] - LAT_RANGE[0])
                    / lat_span * (ROWS - 1))
            c = int((g["location"]["longitude"] - LON_RANGE[0])
                    / lon_span * (COLS - 1))
            r = min(max(r, 0), ROWS - 1)
            c = min(max(c, 0), COLS - 1)
            accum[r * COLS + c] += g["gravity_value"]
            counts[r * COLS + c] += 1
    data = np.where(counts > 0, accum / np.maximum(counts, 1), 0.0)
    return data.reshape(ROWS, COLS), counts.reshape(ROWS, COLS)


def _invert(observed, counts):
    engine = InversionEngine()
    job = engine.start(
        "tikhonov",
        {"grid_rows": str(ROWS), "grid_cols": str(COLS)},
        observed_data=observed, grid_shape=(ROWS, COLS),
        cell_counts=counts,
    )
    t0 = time.time()
    while time.time() - t0 < 90:
        j = engine.get(job.job_id)
        if j.status in ("completed", "failed"):
            break
        time.sleep(0.2)
    assert j.status == "completed", j.error
    return np.asarray(j.model).reshape(ROWS, COLS)


def _run_pair():
    """Twin experiment: background-only scenario fixes the ground
    tracks and the reference field; the anomaly is injected under a
    mid-arc overflight point; the REFERENCE-CORRECTED observations
    (with-anomaly minus background — exactly the reference-field
    removal every real gravimetry processor performs) are inverted
    through the platform's masked path."""
    base = dict(duration_s=3 * 5700.0, dt_s=10.0, sample_every=3, seed=42)

    background = MissionScenario(MissionConfig(**base))
    background.propagate(); background.synthesize()

    # Place the anomaly under an overflight around 1/3 of the arc,
    # away from the poles so the grid cell geometry is benign.
    recs = background.arcs[0].gravity
    pick = next(r for r in recs[len(recs) // 3:]
                if abs(r["location"]["latitude"]) < 40.0)
    anomaly = {
        "lat": pick["location"]["latitude"],
        "lon": pick["location"]["longitude"],
        "amplitude_mgal": ANOMALY_AMPLITUDE,
        "sigma_deg": ANOMALY_SIGMA_DEG,
    }

    with_anom = MissionScenario(MissionConfig(anomalies=(anomaly,), **base))
    with_anom.propagate(); with_anom.synthesize()

    obs_a, counts_a = _bin_to_grid(with_anom.arcs)
    obs_b, counts_b = _bin_to_grid(background.arcs)
    assert np.array_equal(counts_a, counts_b)  # identical tracks

    corrected = np.where(counts_a > 0, obs_a - obs_b, 0.0)
    recovered = _invert(corrected, counts_a)
    return recovered, counts_a, anomaly, corrected


@pytest.fixture(scope="module")
def recovery():
    return _run_pair()


def _cell_of(lat, lon):
    r = int((lat - LAT_RANGE[0]) / (LAT_RANGE[1] - LAT_RANGE[0]) * (ROWS - 1))
    c = int((lon - LON_RANGE[0]) / (LON_RANGE[1] - LON_RANGE[0]) * (COLS - 1))
    return r, c


class TestClosedLoopRecovery:
    def test_signal_survives_binning(self, recovery):
        """Sanity gate: the injected anomaly must actually appear in
        the reference-corrected observations (overflight guaranteed)."""
        _, counts, anomaly, corrected = recovery
        assert float(np.max(corrected)) > 0.5 * ANOMALY_AMPLITUDE

    def test_anomaly_recovered_at_injected_location(self, recovery):
        recovered, _, anomaly, _ = recovery
        r_true, c_true = _cell_of(anomaly["lat"], anomaly["lon"])
        r_peak, c_peak = np.unravel_index(np.argmax(recovered),
                                          recovered.shape)
        dist = np.hypot(r_peak - r_true, c_peak - c_true)
        assert dist <= 2.0, (
            f"peak at cell ({r_peak},{c_peak}), injected at "
            f"({r_true},{c_true}) — {dist:.1f} cells away"
        )

    def test_recovered_amplitude_within_bounds(self, recovery):
        recovered, _, anomaly, corrected = recovery
        peak = float(np.max(recovered))
        obs_peak = float(np.max(corrected))
        # The inversion may smooth but must retain most of the observed
        # signal and must not amplify it.
        assert peak > 0.6 * obs_peak, (
            f"recovered peak {peak:.1f} mGal vs observed {obs_peak:.1f}"
        )
        assert peak < 1.2 * ANOMALY_AMPLITUDE

    def test_no_spurious_structure_far_from_anomaly(self, recovery):
        recovered, counts, anomaly, _ = recovery
        r_true, c_true = _cell_of(anomaly["lat"], anomaly["lon"])
        rr, cc = np.meshgrid(np.arange(ROWS), np.arange(COLS), indexing="ij")
        far = (np.hypot(rr - r_true, cc - c_true) > 6) & (counts > 0)
        assert np.any(far)
        far_rms = float(np.sqrt(np.mean(recovered[far] ** 2)))
        peak = float(np.max(recovered))
        assert far_rms < 0.15 * peak, (
            f"spurious far-field structure: rms {far_rms:.1f} vs peak "
            f"{peak:.1f} mGal"
        )
