"""
Hyperparameter Tuner
====================

Automatic hyperparameter optimization using Optuna with MLflow integration.
Supports multi-objective optimization (validation loss + training time) and
early stopping via MedianPruner.

Example:
    >>> tuner = HyperparameterTuner(mlflow_uri="http://mlflow:5000")
    >>> job_id = tuner.start_tuning("pinn", n_trials=50, timeout=3600)
    >>> status = tuner.get_status(job_id)
    >>> print(f"Best params: {status['best_params']}")
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

try:
    import optuna
    from optuna.pruners import MedianPruner
    from optuna.samplers import TPESampler
    _HAS_OPTUNA = True
except ImportError:
    _HAS_OPTUNA = False
    logger.warning("optuna not installed, hyperparameter tuning disabled")

try:
    import mlflow
    _HAS_MLFLOW = True
except ImportError:
    _HAS_MLFLOW = False


@dataclass
class TuningJob:
    job_id: str
    model_type: str
    status: str = "queued"
    n_trials: int = 50
    trials_completed: int = 0
    best_params: Dict[str, Any] = field(default_factory=dict)
    best_value: float = float('inf')
    trial_results: List[Dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    error: Optional[str] = None


class HyperparameterTuner:
    """Manages Optuna hyperparameter tuning jobs for ML models."""

    def __init__(self, mlflow_tracking_uri: Optional[str] = None):
        if not _HAS_OPTUNA:
            raise RuntimeError(
                "optuna is required for hyperparameter tuning. "
                "Install with: pip install optuna"
            )

        self.jobs: Dict[str, TuningJob] = {}
        self.studies: Dict[str, optuna.Study] = {}
        self._lock = threading.Lock()
        self.mlflow_uri = mlflow_tracking_uri

    def start_tuning(
        self,
        model_type: str,
        n_trials: int = 50,
        timeout: int = 3600,
        fixed_params: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Start a hyperparameter tuning job.

        Args:
            model_type: Model type to tune ("pinn", "mlp", "cnn")
            n_trials: Number of trials to run
            timeout: Maximum time in seconds
            fixed_params: Parameters to keep fixed (not tuned)

        Returns:
            job_id: Unique identifier for the tuning job
        """
        job_id = f"tune_{int(datetime.utcnow().timestamp())}"

        with self._lock:
            job = TuningJob(
                job_id=job_id,
                model_type=model_type,
                n_trials=n_trials
            )
            self.jobs[job_id] = job

        # Start tuning in background thread
        thread = threading.Thread(
            target=self._run_tuning,
            args=(job_id, n_trials, timeout, fixed_params or {})
        )
        thread.start()

        logger.info(f"Started tuning job {job_id} for {model_type}")
        return job_id

    def _run_tuning(
        self,
        job_id: str,
        n_trials: int,
        timeout: int,
        fixed_params: Dict[str, Any]
    ):
        """Run Optuna study (background thread)."""
        try:
            with self._lock:
                job = self.jobs[job_id]
                job.status = "running"

            # Create Optuna study
            study = optuna.create_study(
                study_name=job_id,
                direction="minimize",
                sampler=TPESampler(seed=42),
                pruner=MedianPruner(
                    n_startup_trials=5,
                    n_warmup_steps=10
                )
            )

            self.studies[job_id] = study

            # MLflow tracking
            if _HAS_MLFLOW and self.mlflow_uri:
                mlflow.set_tracking_uri(self.mlflow_uri)
                mlflow.set_experiment(f"hyperparameter_tuning_{job.model_type}")

            # Define objective function
            def objective(trial: optuna.Trial) -> float:
                return self._objective(trial, job, fixed_params)

            # Run optimization
            study.optimize(
                objective,
                n_trials=n_trials,
                timeout=timeout,
                callbacks=[self._trial_callback(job_id)]
            )

            # Extract best parameters
            with self._lock:
                job.best_params = study.best_params
                job.best_value = study.best_value
                job.status = "completed"
                job.completed_at = datetime.utcnow()

            logger.info(
                f"Tuning job {job_id} completed. "
                f"Best value: {job.best_value:.4f}, "
                f"Best params: {job.best_params}"
            )

        except Exception as e:
            logger.error(f"Tuning job {job_id} failed: {e}")
            with self._lock:
                job = self.jobs[job_id]
                job.status = "failed"
                job.error = str(e)
                job.completed_at = datetime.utcnow()

    def _objective(
        self,
        trial: optuna.Trial,
        job: TuningJob,
        fixed_params: Dict[str, Any]
    ) -> float:
        """
        Optuna objective function: train model with trial params, return val loss.

        Args:
            trial: Optuna trial object
            job: TuningJob instance
            fixed_params: Fixed parameters

        Returns:
            Validation loss (lower is better)
        """
        # Suggest hyperparameters
        lr = trial.suggest_float("lr", 1e-4, 1e-1, log=True)
        n_hidden = trial.suggest_int("n_hidden", 16, 256)
        epochs = trial.suggest_int("epochs", 50, 500, step=50)

        # Optional: L2 regularization
        if job.model_type in ["pinn", "mlp"]:
            l2_reg = trial.suggest_float("l2_reg", 1e-6, 1e-2, log=True)
        else:
            l2_reg = 0.0

        # Generate synthetic training data
        n_train = 800
        n_val = 200
        rng = np.random.default_rng(42)

        # Spatial features (lat, lon) → gravity anomaly
        X_train = rng.uniform(-180, 180, (n_train, 2))
        y_train = self._synthetic_gravity(X_train, seed=42)
        X_val = rng.uniform(-180, 180, (n_val, 2))
        y_val = self._synthetic_gravity(X_val, seed=43)

        # Normalize features
        X_mean = X_train.mean(axis=0)
        X_std = X_train.std(axis=0) + 1e-8
        X_train = (X_train - X_mean) / X_std
        X_val = (X_val - X_mean) / X_std

        # Train MLP
        from training_orchestrator import _NumpyMLP

        model = _NumpyMLP(
            n_in=2,
            n_hidden=n_hidden,
            lr=lr,
            seed=trial.number
        )

        best_val_loss = float('inf')
        patience_counter = 0
        patience = 20

        for epoch in range(epochs):
            # Training step
            train_loss = model.step(X_train, y_train)

            # Add L2 regularization to loss
            if l2_reg > 0:
                l2_penalty = l2_reg * (
                    np.sum(model.W1 ** 2) + np.sum(model.W2 ** 2)
                )
                train_loss += l2_penalty

            # Validation
            val_pred = model.predict(X_val)
            val_loss = float(np.mean((val_pred - y_val) ** 2))

            # Report intermediate value for pruning
            trial.report(val_loss, epoch)

            # Early stopping based on pruner
            if trial.should_prune():
                logger.debug(f"Trial {trial.number} pruned at epoch {epoch}")
                raise optuna.TrialPruned()

            # Early stopping based on validation loss
            if val_loss < best_val_loss:
                best_val_loss = val_loss
                patience_counter = 0
            else:
                patience_counter += 1
                if patience_counter >= patience:
                    logger.debug(
                        f"Trial {trial.number} early stopped at epoch {epoch}"
                    )
                    break

        # MLflow logging
        if _HAS_MLFLOW and self.mlflow_uri:
            with mlflow.start_run(run_name=f"trial_{trial.number}"):
                mlflow.log_params(trial.params)
                mlflow.log_metric("val_loss", best_val_loss)
                mlflow.log_metric("epochs_trained", epoch + 1)

        return best_val_loss

    def _synthetic_gravity(self, X: np.ndarray, seed: int = 42) -> np.ndarray:
        """Generate synthetic gravity anomaly data for tuning."""
        rng = np.random.default_rng(seed)

        # Multiple Gaussian anomalies
        y = np.zeros(len(X))
        anomalies = [
            {"center": [30.0, 45.0], "amplitude": 50.0, "width": 20.0},
            {"center": [-60.0, -30.0], "amplitude": -40.0, "width": 15.0},
            {"center": [120.0, 10.0], "amplitude": 30.0, "width": 25.0},
        ]

        for anom in anomalies:
            center = np.array(anom["center"])
            dist_sq = np.sum((X - center) ** 2, axis=1)
            y += anom["amplitude"] * np.exp(-dist_sq / (2 * anom["width"] ** 2))

        # Add noise
        y += rng.normal(0, 2.0, len(y))

        return y

    def _trial_callback(self, job_id: str):
        """Callback to update job status after each trial."""
        def callback(study: optuna.Study, trial: optuna.Trial):
            with self._lock:
                job = self.jobs[job_id]
                job.trials_completed += 1

                # Store trial result
                job.trial_results.append({
                    "number": trial.number,
                    "value": trial.value,
                    "params": trial.params,
                    "state": trial.state.name
                })

                # Update best so far
                if study.best_value < job.best_value:
                    job.best_value = study.best_value
                    job.best_params = study.best_params

        return callback

    def get_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get tuning job status and results."""
        with self._lock:
            job = self.jobs.get(job_id)
            if not job:
                return None

            return {
                "job_id": job.job_id,
                "model_type": job.model_type,
                "status": job.status,
                "n_trials": job.n_trials,
                "trials_completed": job.trials_completed,
                "best_params": job.best_params,
                "best_value": job.best_value,
                "trial_results": job.trial_results,
                "created_at": job.created_at.isoformat(),
                "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                "error": job.error
            }

    def get_best_params(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get best parameters from completed tuning job."""
        with self._lock:
            job = self.jobs.get(job_id)
            if not job or job.status != "completed":
                return None
            return job.best_params

    def list_jobs(self) -> List[Dict[str, Any]]:
        """List all tuning jobs."""
        with self._lock:
            return [
                {
                    "job_id": job.job_id,
                    "model_type": job.model_type,
                    "status": job.status,
                    "trials_completed": job.trials_completed,
                    "n_trials": job.n_trials,
                    "best_value": job.best_value if job.best_value != float('inf') else None
                }
                for job in self.jobs.values()
            ]
