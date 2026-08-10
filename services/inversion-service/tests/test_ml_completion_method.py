"""The ml_completion inversion method must run the shipped learned
model (Phase 4 serving path)."""

import sys
import time
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from src.inversion_engine import InversionEngine  # noqa: E402
from ml.gravity_completion import GravityMapCompleter  # noqa: E402
import json  # noqa: E402


def test_ml_completion_matches_shipped_model():
    rows = cols = 12
    rng = np.random.RandomState(5)
    counts = (rng.random((rows, cols)) < 0.4).astype(float)
    truth = 10.0 * np.exp(
        -((np.arange(rows)[:, None] - 6) ** 2
          + (np.arange(cols)[None, :] - 6) ** 2) / 18.0)
    observed = np.where(counts > 0, truth, 0.0)

    engine = InversionEngine()
    job = engine.start(
        "ml_completion", {"grid_rows": str(rows), "grid_cols": str(cols)},
        observed_data=observed, grid_shape=(rows, cols),
        cell_counts=counts,
    )
    t0 = time.time()
    while time.time() - t0 < 60:
        j = engine.get(job.job_id)
        if j.status in ("completed", "failed"):
            break
        time.sleep(0.1)
    assert j.status == "completed", j.error
    assert j.config.get("model_artifact") == "gravity_completion_v1"

    # The served result must equal the shipped model's own prediction
    cfg = json.loads(
        (REPO / "ml" / "models" / "gravity_completion_v1.json").read_text())
    expected = GravityMapCompleter.from_dict(cfg).predict(observed, counts)
    assert np.allclose(np.asarray(j.model).reshape(rows, cols), expected)
