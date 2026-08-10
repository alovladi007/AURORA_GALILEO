"""
Phase 4 W4.1 ship criterion: the learned completion model must beat
the classical Tikhonov baseline on the closed-loop anomaly-recovery
benchmark, training only on data from the real mission generator.

Training scenarios use different seeds and anomaly placements than the
evaluation scenario (no leakage): the model learns *hyperparameters*
that generalize across the generator's data distribution.
"""

import sys
import time
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "services" / "inversion-service"))

from mission.scenario import MissionConfig, MissionScenario  # noqa: E402
from ml.gravity_completion import GravityMapCompleter  # noqa: E402
from src.inversion_engine import InversionEngine  # noqa: E402

ROWS, COLS = 18, 18
LAT_RANGE = (-85.0, 85.0)
LON_RANGE = (-180.0, 180.0)


def _bin(arcs):
    accum = np.zeros(ROWS * COLS)
    counts = np.zeros(ROWS * COLS)
    for arc in arcs:
        for g in arc.gravity:
            r = int((g["location"]["latitude"] - LAT_RANGE[0])
                    / (LAT_RANGE[1] - LAT_RANGE[0]) * (ROWS - 1))
            c = int((g["location"]["longitude"] - LON_RANGE[0])
                    / (LON_RANGE[1] - LON_RANGE[0]) * (COLS - 1))
            r = min(max(r, 0), ROWS - 1)
            c = min(max(c, 0), COLS - 1)
            accum[r * COLS + c] += g["gravity_value"]
            counts[r * COLS + c] += 1
    data = np.where(counts > 0, accum / np.maximum(counts, 1), 0.0)
    return data.reshape(ROWS, COLS), counts.reshape(ROWS, COLS)


def _truth_grid(anomaly):
    """The injected Gaussian evaluated at grid-cell centers — the
    reference-corrected map the pipeline should recover."""
    lats = np.linspace(LAT_RANGE[0], LAT_RANGE[1], ROWS)
    lons = np.linspace(LON_RANGE[0], LON_RANGE[1], COLS)
    LA, LO = np.meshgrid(lats, lons, indexing="ij")
    dlon = (LO - anomaly["lon"] + 180.0) % 360.0 - 180.0
    sig = anomaly["sigma_deg"]
    return anomaly["amplitude_mgal"] * np.exp(
        -((LA - anomaly["lat"]) ** 2 + dlon**2) / (2.0 * sig**2)
    )


def _corrected_pair(seed, amplitude=80.0, sigma=18.0, pick_frac=3):
    """One reference-corrected scenario: returns (truth_grid,
    corrected_observations, counts, anomaly)."""
    base = dict(duration_s=3 * 5700.0, dt_s=10.0, sample_every=3, seed=seed)
    background = MissionScenario(MissionConfig(**base))
    background.propagate(); background.synthesize()
    recs = background.arcs[0].gravity
    pick = next(r for r in recs[len(recs) // pick_frac:]
                if abs(r["location"]["latitude"]) < 40.0)
    anomaly = {
        "lat": pick["location"]["latitude"],
        "lon": pick["location"]["longitude"],
        "amplitude_mgal": amplitude,
        "sigma_deg": sigma,
    }
    with_anom = MissionScenario(MissionConfig(anomalies=(anomaly,), **base))
    with_anom.propagate(); with_anom.synthesize()
    obs_a, counts = _bin(with_anom.arcs)
    obs_b, _ = _bin(background.arcs)
    corrected = np.where(counts > 0, obs_a - obs_b, 0.0)
    return _truth_grid(anomaly), corrected, counts, anomaly


def _tikhonov_baseline(corrected, counts):
    engine = InversionEngine()
    job = engine.start(
        "tikhonov", {"grid_rows": str(ROWS), "grid_cols": str(COLS)},
        observed_data=corrected, grid_shape=(ROWS, COLS),
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


@pytest.fixture(scope="module")
def trained_model():
    """Train on three generator scenarios with varied seeds/anomalies
    (distinct from the evaluation scenario)."""
    pairs = []
    for seed, amp, sig, frac in [(7, 60.0, 15.0, 4),
                                 (11, 100.0, 22.0, 2),
                                 (23, 75.0, 12.0, 5)]:
        truth, corrected, counts, _ = _corrected_pair(
            seed, amplitude=amp, sigma=sig, pick_frac=frac)
        pairs.append((truth, corrected, counts))
    completer = GravityMapCompleter()
    model = completer.fit(pairs)
    return completer, model


@pytest.fixture(scope="module")
def evaluation():
    """The held-out closed-loop benchmark scenario (seed 42)."""
    return _corrected_pair(42)


class TestLearnedCompletion:
    def test_training_selects_finite_hyperparameters(self, trained_model):
        _, model = trained_model
        assert np.isfinite(model.train_score_rms)
        assert model.length_scale > 0 and model.alpha > 0

    def test_ml_beats_tikhonov_baseline_on_benchmark(
        self, trained_model, evaluation
    ):
        """The Phase 4 ship criterion: on the held-out closed-loop
        scenario, the learned model's full-map recovery error must be
        at least 10% better than the classical baseline."""
        completer, model = trained_model
        truth, corrected, counts, anomaly = evaluation

        ml_map = completer.predict(corrected, counts)
        baseline_map = _tikhonov_baseline(corrected, counts)

        ml_rms = float(np.sqrt(np.mean((ml_map - truth) ** 2)))
        base_rms = float(np.sqrt(np.mean((baseline_map - truth) ** 2)))

        print(f"\n  learned model: ls={model.length_scale}, "
              f"alpha={model.alpha} -> RMS {ml_rms:.2f} mGal")
        print(f"  tikhonov baseline           -> RMS {base_rms:.2f} mGal")

        assert ml_rms < 0.9 * base_rms, (
            f"learned model (RMS {ml_rms:.2f}) does not beat the "
            f"baseline (RMS {base_rms:.2f}) by >=10% — do not ship"
        )

    def test_ml_recovers_peak_location(self, trained_model, evaluation):
        completer, _ = trained_model
        truth, corrected, counts, anomaly = evaluation
        ml_map = completer.predict(corrected, counts)
        r_t, c_t = np.unravel_index(np.argmax(truth), truth.shape)
        r_p, c_p = np.unravel_index(np.argmax(ml_map), ml_map.shape)
        assert np.hypot(r_p - r_t, c_p - c_t) <= 2.0

    def test_serialization_round_trip(self, trained_model, evaluation):
        completer, _ = trained_model
        truth, corrected, counts, _ = evaluation
        clone = GravityMapCompleter.from_dict(completer.to_dict())
        a = completer.predict(corrected, counts)
        b = clone.predict(corrected, counts)
        assert np.allclose(a, b)
