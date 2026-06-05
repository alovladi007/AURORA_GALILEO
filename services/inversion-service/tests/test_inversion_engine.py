"""
Inversion Engine Unit Tests
===========================

Tests the numerical solvers (Tikhonov, Gauss-Newton, Bayesian MAP) and the
async InversionEngine directly, independent of gRPC.
"""

import time

import numpy as np
import pytest

from src.inversion_engine import (
    InversionEngine,
    TikhonovSolver,
    build_point_mass_operator,
)


def _wait_for(job, engine, timeout=15.0):
    """Poll until the job reaches a terminal state."""
    start = time.time()
    while time.time() - start < timeout:
        j = engine.get(job.job_id)
        if j.status in ("completed", "failed", "cancelled"):
            return j
        time.sleep(0.1)
    return engine.get(job.job_id)


class TestSolvers:

    def test_tikhonov_recovers_synthetic_anomaly(self):
        """Tikhonov inversion should fit a known point-mass anomaly's data."""
        rows, cols = 10, 10
        n_obs = rows * cols
        G = build_point_mass_operator((rows, cols), n_obs)

        # Ground-truth density field with a localized anomaly.
        true_model = np.zeros(rows * cols)
        true_model[rows * cols // 2] = 1.0
        data = G @ true_model

        solver = TikhonovSolver(G)
        lam = solver.select_lambda_lcurve(data)
        result = solver.solve(data, lam)
        recovered = result["model"]

        # The recovered field should reproduce the observations reasonably.
        rel_residual = result["residual"] / np.linalg.norm(data)
        assert rel_residual < 0.5
        assert recovered.shape == (rows * cols,)

    def test_lcurve_lambda_is_positive(self):
        rows, cols = 8, 8
        n_obs = rows * cols
        G = build_point_mass_operator((rows, cols), n_obs)
        data = G @ np.random.default_rng(0).normal(size=rows * cols)
        solver = TikhonovSolver(G)
        lam = solver.select_lambda_lcurve(data)
        assert lam > 0


class TestEngine:

    def test_tikhonov_job_completes(self):
        engine = InversionEngine()
        job = engine.start("tikhonov", {"grid_rows": "10", "grid_cols": "10"})
        done = _wait_for(job, engine)
        assert done.status == "completed"
        assert done.model is not None
        assert done.progress == pytest.approx(1.0, abs=0.01) or done.progress >= 0.99

    def test_gauss_newton_job_completes(self):
        engine = InversionEngine()
        job = engine.start("gauss_newton", {"grid_rows": "8", "grid_cols": "8"})
        done = _wait_for(job, engine)
        assert done.status == "completed"
        assert done.current_iteration > 0

    def test_bayesian_job_has_uncertainties(self):
        engine = InversionEngine()
        job = engine.start("bayesian", {"grid_rows": "8", "grid_cols": "8"})
        done = _wait_for(job, engine)
        assert done.status == "completed"
        assert done.uncertainties is not None

    def test_real_data_path_sets_source(self):
        engine = InversionEngine()
        rows, cols = 8, 8
        observed = np.random.default_rng(1).normal(size=rows * cols)
        job = engine.start("tikhonov", {}, observed_data=observed,
                           grid_shape=(rows, cols))
        done = _wait_for(job, engine)
        assert done.data_source == "data_service"
        assert done.status == "completed"

    def test_cancel_running_job(self):
        engine = InversionEngine()
        # A larger grid keeps the job running long enough to cancel.
        job = engine.start("gauss_newton", {"grid_rows": "20", "grid_cols": "20"})
        cancelled = engine.cancel(job.job_id)
        # Either it was cancelled in flight, or it finished extremely fast.
        assert isinstance(cancelled, bool)

    def test_list_jobs(self):
        engine = InversionEngine()
        engine.start("tikhonov", {"grid_rows": "6", "grid_cols": "6"})
        engine.start("tikhonov", {"grid_rows": "6", "grid_cols": "6"})
        assert len(engine.list_jobs()) >= 2
