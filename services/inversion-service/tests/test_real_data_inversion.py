"""
Real-data inversion path tests (Phase 3 W3.3 acceptance).

When observed gravity arrives from the data service, the engine must
invert THOSE observations through an honest observation operator
(selection of populated cells + Laplacian completion) — not a random
kernel — and recover the underlying field.
"""

import time

import numpy as np

from src.inversion_engine import InversionEngine


def _track_sampled_field(rows=16, cols=16, coverage=0.45, seed=3):
    """A smooth latitude-structured truth field sampled along
    ground-track-like stripes (as the fetcher's binning produces)."""
    rng = np.random.RandomState(seed)
    lat = np.linspace(-60, 60, rows)
    truth = 30.0 * (3.0 * np.sin(np.deg2rad(lat))[:, None] ** 2 - 1.0)
    truth = np.repeat(truth, cols, axis=1)
    truth += 5.0 * np.cos(np.linspace(0, 3 * np.pi, cols))[None, :]

    counts = np.zeros((rows, cols))
    # diagonal stripes emulate ascending/descending tracks
    for k in range(-rows, cols, 3):
        for r in range(rows):
            c = r + k
            if 0 <= c < cols:
                counts[r, c] = 1.0
    # thin out to the requested coverage (bounded by available cells)
    populated = np.flatnonzero(counts.ravel())
    n_keep = min(len(populated), int(coverage * rows * cols))
    keep = rng.choice(populated, n_keep, replace=False)
    mask = np.zeros(rows * cols)
    mask[keep] = 1.0
    counts = mask.reshape(rows, cols)

    observed = np.where(counts > 0, truth, 0.0)
    noise = rng.normal(0.0, 0.2, truth.shape)
    observed = np.where(counts > 0, observed + noise, 0.0)
    return truth, observed, counts


def _wait(engine, job_id, timeout=60):
    t0 = time.time()
    while time.time() - t0 < timeout:
        job = engine.get(job_id)
        if job.status in ("completed", "failed", "cancelled"):
            return job
        time.sleep(0.2)
    raise TimeoutError("inversion did not finish")


class TestMaskedGriddingInversion:
    def test_recovers_field_on_observed_cells(self):
        truth, observed, counts = _track_sampled_field()
        engine = InversionEngine()
        job = engine.start(
            "tikhonov", {"grid_rows": "16", "grid_cols": "16"},
            observed_data=observed, grid_shape=(16, 16),
            cell_counts=counts,
        )
        job = _wait(engine, job.job_id)
        assert job.status == "completed", job.error
        model = np.asarray(job.model).reshape(16, 16)

        mask = counts > 0
        corr = np.corrcoef(model[mask], truth[mask])[0, 1]
        assert corr > 0.95, f"observed-cell recovery corr={corr:.3f}"

    def test_completes_unobserved_cells_smoothly(self):
        truth, observed, counts = _track_sampled_field()
        engine = InversionEngine()
        job = engine.start(
            "tikhonov", {"grid_rows": "16", "grid_cols": "16"},
            observed_data=observed, grid_shape=(16, 16),
            cell_counts=counts,
        )
        job = _wait(engine, job.job_id)
        model = np.asarray(job.model).reshape(16, 16)

        holes = counts == 0
        assert np.any(holes)
        # Laplacian completion must land near the smooth truth in the
        # gaps too (structure is large-scale) — far better than the
        # zero-fill the old path implicitly asserted.
        rms_holes = float(np.sqrt(np.mean((model[holes] - truth[holes]) ** 2)))
        rms_zerofill = float(np.sqrt(np.mean(truth[holes] ** 2)))
        assert rms_holes < 0.5 * rms_zerofill, (
            f"gap completion rms {rms_holes:.2f} vs zero-fill "
            f"{rms_zerofill:.2f}"
        )

    def test_empty_observations_fail_honestly(self):
        engine = InversionEngine()
        job = engine.start(
            "tikhonov", {"grid_rows": "8", "grid_cols": "8"},
            observed_data=np.zeros((8, 8)), grid_shape=(8, 8),
            cell_counts=np.zeros((8, 8)),
        )
        job = _wait(engine, job.job_id)
        assert job.status == "failed"
        assert "no populated" in (job.error or "")
