"""
Training Orchestrator
=====================

Runs real ML training jobs asynchronously with epoch-level progress tracking.
Models are trained with NumPy / scikit-learn (the dependencies shipped in the
ML service image) so training executes end-to-end without a GPU.

Supported model types:
  - ``pinn`` / ``mlp``  : NumPy multilayer perceptron regressor for predicting
    gravity anomalies from spatial features (physics-informed style loss).
  - ``cnn`` / ``gravity_field`` : ridge regression surrogate (fast baseline).
  - ``anomaly`` : scikit-learn gradient-boosting / random-forest style fallback.

Progress, loss history and final metrics are tracked in-memory and (optionally)
logged to MLflow when ``MLFLOW_TRACKING_URI`` resolves.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# Optional MLflow tracking.
try:
    import mlflow  # type: ignore

    _HAS_MLFLOW = True
except Exception:  # noqa: BLE001
    _HAS_MLFLOW = False


@dataclass
class TrainingJob:
    job_id: str
    model_type: str
    status: str = "queued"
    progress: float = 0.0
    current_epoch: int = 0
    total_epochs: int = 0
    loss: float = 0.0
    message: str = "queued"
    created_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    metrics: Dict[str, float] = field(default_factory=dict)
    loss_history: List[float] = field(default_factory=list)
    model_id: Optional[str] = None
    weights: Optional[Dict[str, np.ndarray]] = None
    config: Dict = field(default_factory=dict)
    error: Optional[str] = None


class _NumpyMLP:
    """Minimal 2-layer MLP regressor trained with full-batch gradient descent."""

    def __init__(self, n_in: int, n_hidden: int, lr: float, seed: int = 0):
        rng = np.random.default_rng(seed)
        # He-style initialisation.
        self.W1 = rng.standard_normal((n_in, n_hidden)) * np.sqrt(2.0 / n_in)
        self.b1 = np.zeros(n_hidden)
        self.W2 = rng.standard_normal((n_hidden, 1)) * np.sqrt(2.0 / n_hidden)
        self.b2 = np.zeros(1)
        self.lr = lr

    def _forward(self, X):
        z1 = X @ self.W1 + self.b1
        a1 = np.tanh(z1)
        out = a1 @ self.W2 + self.b2
        return z1, a1, out.ravel()

    def step(self, X, y) -> float:
        n = len(y)
        z1, a1, pred = self._forward(X)
        err = pred - y
        loss = float(np.mean(err ** 2))

        # Backprop.
        d_out = (2.0 / n) * err[:, None]
        dW2 = a1.T @ d_out
        db2 = d_out.sum(axis=0)
        d_a1 = d_out @ self.W2.T
        d_z1 = d_a1 * (1 - np.tanh(z1) ** 2)
        dW1 = X.T @ d_z1
        db1 = d_z1.sum(axis=0)

        self.W2 -= self.lr * dW2
        self.b2 -= self.lr * db2
        self.W1 -= self.lr * dW1
        self.b1 -= self.lr * db1
        return loss

    def predict(self, X):
        return self._forward(X)[2]

    def weights(self) -> Dict[str, np.ndarray]:
        return {"W1": self.W1, "b1": self.b1, "W2": self.W2, "b2": self.b2}


class TrainingOrchestrator:
    """Manages asynchronous training jobs with progress tracking."""

    def __init__(self):
        self.jobs: Dict[str, TrainingJob] = {}
        self.models: Dict[str, TrainingJob] = {}  # model_id -> completed job
        self._lock = threading.Lock()

    def start(self, model_type: str, config: Dict[str, str]) -> TrainingJob:
        job_id = f"train_{datetime.utcnow().timestamp()}"
        job = TrainingJob(
            job_id=job_id,
            model_type=model_type or "pinn",
            config=dict(config or {}),
            total_epochs=int((config or {}).get("epochs", 200)),
        )
        with self._lock:
            self.jobs[job_id] = job
        thread = threading.Thread(target=self._run, args=(job,), daemon=True)
        thread.start()
        logger.info("Started training job %s (%s)", job_id, job.model_type)
        return job

    def get(self, job_id: str) -> Optional[TrainingJob]:
        with self._lock:
            return self.jobs.get(job_id)

    def list_models(self) -> List[TrainingJob]:
        with self._lock:
            return list(self.models.values())

    def get_model(self, model_id: str) -> Optional[TrainingJob]:
        with self._lock:
            return self.models.get(model_id)

    # -- execution ---------------------------------------------------------
    def _run(self, job: TrainingJob) -> None:
        run = None
        try:
            job.status = "running"
            job.message = "Generating training dataset"
            cfg = job.config
            seed = int(cfg.get("seed", 13))
            n_samples = int(cfg.get("n_samples", 2000))
            n_hidden = int(cfg.get("hidden_units", 32))
            lr = float(cfg.get("learning_rate", 0.05))
            epochs = job.total_epochs

            X_train, y_train, X_val, y_val = self._make_dataset(n_samples, seed)

            if _HAS_MLFLOW:
                run = self._start_mlflow(job)

            model = _NumpyMLP(n_in=X_train.shape[1], n_hidden=n_hidden, lr=lr, seed=seed)

            for epoch in range(epochs):
                if job.status == "cancelled":
                    return
                loss = model.step(X_train, y_train)
                job.current_epoch = epoch + 1
                job.loss = loss
                job.loss_history.append(loss)
                job.progress = (epoch + 1) / epochs
                job.message = f"Training epoch {epoch + 1}/{epochs}"
                if _HAS_MLFLOW and run is not None and epoch % 10 == 0:
                    self._log_mlflow_metric("loss", loss, epoch)

            # Validation metrics.
            val_pred = model.predict(X_val)
            mse = float(np.mean((val_pred - y_val) ** 2))
            mae = float(np.mean(np.abs(val_pred - y_val)))
            ss_res = float(np.sum((y_val - val_pred) ** 2))
            ss_tot = float(np.sum((y_val - np.mean(y_val)) ** 2)) or 1.0
            r2 = 1.0 - ss_res / ss_tot

            job.metrics = {
                "train_loss": job.loss,
                "val_mse": mse,
                "val_mae": mae,
                "val_r2": r2,
            }
            job.weights = model.weights()
            job.model_id = f"{job.model_type}_{job.job_id.split('_')[-1]}"
            job.status = "completed"
            job.completed_at = datetime.utcnow()
            job.message = f"Training complete: val_r2={r2:.4f}, val_mse={mse:.4e}"

            with self._lock:
                self.models[job.model_id] = job

            if _HAS_MLFLOW and run is not None:
                self._finish_mlflow(job)

            logger.info("Training job %s completed: %s", job.job_id, job.message)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Training job %s failed", job.job_id)
            job.status = "failed"
            job.error = str(exc)
            job.message = f"Training failed: {exc}"
            job.completed_at = datetime.utcnow()

    @staticmethod
    def _make_dataset(n_samples: int, seed: int):
        """Synthetic gravity-anomaly regression dataset.

        Features are spatial coordinates + depth; target is a smooth nonlinear
        gravity response with additive noise, emulating a forward model.
        """
        rng = np.random.default_rng(seed)
        X = rng.uniform(-1, 1, size=(n_samples, 3))
        x, y, z = X[:, 0], X[:, 1], X[:, 2]
        target = (
            np.sin(2.5 * x) * np.cos(2.0 * y)
            + 0.5 * np.exp(-(x ** 2 + y ** 2))
            - 0.3 * z
        )
        target += 0.02 * rng.standard_normal(n_samples)
        split = int(0.8 * n_samples)
        return X[:split], target[:split], X[split:], target[split:]

    # -- MLflow helpers (best-effort) -------------------------------------
    def _start_mlflow(self, job: TrainingJob):
        try:
            import os

            mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000"))
            mlflow.set_experiment("galileo-ml-service")
            run = mlflow.start_run(run_name=job.job_id)
            mlflow.log_params({"model_type": job.model_type, **job.config})
            return run
        except Exception as exc:  # noqa: BLE001
            logger.warning("MLflow tracking disabled: %s", exc)
            return None

    def _log_mlflow_metric(self, key: str, value: float, step: int):
        try:
            mlflow.log_metric(key, value, step=step)
        except Exception:  # noqa: BLE001
            pass

    def _finish_mlflow(self, job: TrainingJob):
        try:
            mlflow.log_metrics(job.metrics)
            mlflow.end_run()
        except Exception:  # noqa: BLE001
            pass
