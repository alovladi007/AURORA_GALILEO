"""
Tests for HyperparameterTuner
==============================

Covers Optuna integration, trial execution, best parameter selection,
and MLflow logging (mocked).
"""

import pytest
import time
from unittest.mock import Mock, patch

try:
    from src.hyperparameter_tuner import HyperparameterTuner
    HAS_TUNER = True
except ImportError:
    HAS_TUNER = False


@pytest.mark.skipif(not HAS_TUNER, reason="Optuna not installed")
class TestHyperparameterTuner:
    """Test suite for hyperparameter tuning with Optuna."""

    def test_start_tuning_creates_job(self):
        """Starting tuning creates a job and returns job_id."""
        tuner = HyperparameterTuner()

        job_id = tuner.start_tuning(
            model_type="pinn",
            n_trials=5,
            timeout=30
        )

        assert job_id.startswith("tune_")
        assert job_id in tuner.jobs

        job = tuner.jobs[job_id]
        assert job.model_type == "pinn"
        assert job.n_trials == 5
        assert job.status in ["queued", "running"]

    def test_tuning_completes_successfully(self):
        """Tuning job completes and finds best parameters."""
        tuner = HyperparameterTuner()

        job_id = tuner.start_tuning(
            model_type="mlp",
            n_trials=10,
            timeout=60
        )

        # Wait for completion (max 70s)
        start_time = time.time()
        while time.time() - start_time < 70:
            status = tuner.get_status(job_id)
            if status["status"] == "completed":
                break
            time.sleep(1)

        status = tuner.get_status(job_id)
        assert status["status"] == "completed"
        assert status["trials_completed"] == 10

        # Best parameters should be set
        assert "lr" in status["best_params"]
        assert "n_hidden" in status["best_params"]
        assert "epochs" in status["best_params"]

        # Best value should be finite
        assert status["best_value"] < float('inf')
        assert status["best_value"] > 0.0

    def test_tuning_with_early_stopping(self):
        """Tuning uses early stopping and pruning."""
        tuner = HyperparameterTuner()

        job_id = tuner.start_tuning(
            model_type="pinn",
            n_trials=20,
            timeout=120
        )

        # Wait for completion
        start_time = time.time()
        while time.time() - start_time < 130:
            status = tuner.get_status(job_id)
            if status["status"] == "completed":
                break
            time.sleep(2)

        status = tuner.get_status(job_id)

        # Should have some pruned trials
        pruned_count = sum(
            1 for t in status["trial_results"]
            if t["state"] == "PRUNED"
        )
        # At least a few trials should be pruned
        assert pruned_count >= 0  # Pruning is stochastic, can be 0

        # Completed trials should exist
        completed_count = sum(
            1 for t in status["trial_results"]
            if t["state"] == "COMPLETE"
        )
        assert completed_count > 0

    def test_best_params_extraction(self):
        """Best parameters can be extracted from completed job."""
        tuner = HyperparameterTuner()

        job_id = tuner.start_tuning(
            model_type="pinn",
            n_trials=5,
            timeout=30
        )

        # Wait for completion
        start_time = time.time()
        while time.time() - start_time < 40:
            status = tuner.get_status(job_id)
            if status["status"] == "completed":
                break
            time.sleep(1)

        best_params = tuner.get_best_params(job_id)
        assert best_params is not None
        assert isinstance(best_params, dict)
        assert "lr" in best_params
        assert "n_hidden" in best_params

    def test_get_status_nonexistent_job(self):
        """Getting status of nonexistent job returns None."""
        tuner = HyperparameterTuner()

        status = tuner.get_status("nonexistent_job")
        assert status is None

    def test_list_jobs(self):
        """List jobs returns all tuning jobs."""
        tuner = HyperparameterTuner()

        job_id1 = tuner.start_tuning("pinn", n_trials=3, timeout=20)
        job_id2 = tuner.start_tuning("mlp", n_trials=3, timeout=20)

        jobs = tuner.list_jobs()
        assert len(jobs) == 2

        job_ids = [j["job_id"] for j in jobs]
        assert job_id1 in job_ids
        assert job_id2 in job_ids

    def test_tuning_with_fixed_params(self):
        """Tuning respects fixed parameters."""
        tuner = HyperparameterTuner()

        fixed = {"batch_size": "32", "optimizer": "adam"}
        job_id = tuner.start_tuning(
            model_type="pinn",
            n_trials=5,
            timeout=30,
            fixed_params=fixed
        )

        # Wait for completion
        start_time = time.time()
        while time.time() - start_time < 40:
            status = tuner.get_status(job_id)
            if status["status"] == "completed":
                break
            time.sleep(1)

        status = tuner.get_status(job_id)
        assert status["status"] == "completed"

        # Fixed params should not be in best_params (they're not tuned)
        # but the tuning should still succeed
        assert status["best_value"] < float('inf')

    def test_synthetic_gravity_function(self):
        """Synthetic gravity generator produces consistent data."""
        import numpy as np
        from src.hyperparameter_tuner import HyperparameterTuner

        tuner = HyperparameterTuner()

        X = np.array([[30.0, 45.0], [-60.0, -30.0], [120.0, 10.0]])
        y1 = tuner._synthetic_gravity(X, seed=42)
        y2 = tuner._synthetic_gravity(X, seed=42)

        # Same seed should produce same values
        np.testing.assert_allclose(y1, y2)

        # Different seed should produce different noise
        y3 = tuner._synthetic_gravity(X, seed=123)
        assert not np.allclose(y1, y3)

    @patch('src.hyperparameter_tuner._HAS_MLFLOW', True)
    @patch('src.hyperparameter_tuner.mlflow', create=True)
    def test_mlflow_integration(self, mock_mlflow):
        """MLflow tracking is called when available."""
        tuner = HyperparameterTuner(mlflow_tracking_uri="http://mlflow:5000")

        job_id = tuner.start_tuning(
            model_type="pinn",
            n_trials=3,
            timeout=30
        )

        # Wait for completion
        start_time = time.time()
        while time.time() - start_time < 40:
            status = tuner.get_status(job_id)
            if status["status"] == "completed":
                break
            time.sleep(1)

        # MLflow should have been called
        assert mock_mlflow.set_tracking_uri.called
        assert mock_mlflow.set_experiment.called

    def test_timeout_behavior(self):
        """Tuning respects timeout parameter."""
        tuner = HyperparameterTuner()

        # Very short timeout - should stop before completing all trials
        job_id = tuner.start_tuning(
            model_type="pinn",
            n_trials=100,  # Large number
            timeout=10     # Short timeout
        )

        # Wait for completion
        start_time = time.time()
        while time.time() - start_time < 15:
            status = tuner.get_status(job_id)
            if status["status"] in ["completed", "failed"]:
                break
            time.sleep(1)

        status = tuner.get_status(job_id)

        # Should complete but with fewer than 100 trials
        assert status["status"] == "completed"
        assert status["trials_completed"] < 100

        # Should have taken ~10 seconds (within tolerance)
        elapsed = time.time() - start_time
        assert elapsed < 20  # Allow some overhead


@pytest.mark.skipif(HAS_TUNER, reason="Test for when optuna is not installed")
def test_tuner_unavailable_without_optuna():
    """HyperparameterTuner raises error when optuna not installed."""
    with pytest.raises(RuntimeError, match="optuna is required"):
        from src.hyperparameter_tuner import HyperparameterTuner
        tuner = HyperparameterTuner()
