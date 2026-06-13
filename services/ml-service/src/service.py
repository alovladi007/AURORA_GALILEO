"""
ML Service gRPC implementation

Runs real model training jobs via the TrainingOrchestrator, tracks epoch-level
progress, serves predictions from trained models, and exposes a model registry.
"""

import grpc
import logging
from datetime import datetime

import numpy as np

from src.gen import ml_service_pb2, ml_service_pb2_grpc, common_pb2
from google.protobuf.timestamp_pb2 import Timestamp

from src.training_orchestrator import TrainingOrchestrator

try:
    from src.hyperparameter_tuner import HyperparameterTuner
    _HAS_TUNER = True
except ImportError:
    _HAS_TUNER = False
    logger.warning("Hyperparameter tuner not available (optuna not installed)")

logger = logging.getLogger(__name__)


def datetime_to_timestamp(dt: datetime) -> Timestamp:
    """Convert datetime to protobuf Timestamp"""
    ts = Timestamp()
    ts.FromDatetime(dt)
    return ts


def _mlp_predict(weights, X: np.ndarray) -> np.ndarray:
    """Forward pass matching training_orchestrator._NumpyMLP."""
    a1 = np.tanh(X @ weights["W1"] + weights["b1"])
    return (a1 @ weights["W2"] + weights["b2"]).ravel()


class MLServicer(ml_service_pb2_grpc.MLServiceServicer):
    """ML Service implementation backed by a real training orchestrator."""

    def __init__(self):
        self.orchestrator = TrainingOrchestrator()
        if _HAS_TUNER:
            import os
            mlflow_uri = os.getenv("MLFLOW_TRACKING_URI")
            self.tuner = HyperparameterTuner(mlflow_tracking_uri=mlflow_uri)
        else:
            self.tuner = None

    def TrainModel(self, request, context):
        """Start a real training job."""
        try:
            logger.info("Training model: %s", request.model_type)
            job = self.orchestrator.start(request.model_type, dict(request.config))

            epochs = int(job.config.get("epochs", 200))
            n_samples = int(job.config.get("n_samples", 2000))
            estimated = max(2.0, epochs * n_samples * 5e-6)

            return ml_service_pb2.TrainingResponse(
                job_id=job.job_id,
                status=job.status,
                message=f"Training {job.model_type} model started",
                estimated_time=estimated,
            )

        except Exception as e:
            logger.error("Error training model: %s", e)
            return ml_service_pb2.TrainingResponse(
                job_id="",
                status="failed",
                message=f"Error: {str(e)}",
                estimated_time=0.0,
            )

    def GetTrainingStatus(self, request, context):
        """Get real-time training progress."""
        try:
            job = self.orchestrator.get(request.job_id)
            if not job:
                return ml_service_pb2.TrainingStatusResponse(
                    job_id=request.job_id,
                    status="not_found",
                    progress=0.0,
                    message="Training job not found",
                )

            return ml_service_pb2.TrainingStatusResponse(
                job_id=job.job_id,
                status=job.status,
                progress=job.progress,
                current_epoch=job.current_epoch,
                total_epochs=job.total_epochs,
                loss=job.loss,
                message=job.message,
            )

        except Exception as e:
            logger.error("Error getting training status: %s", e)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return ml_service_pb2.TrainingStatusResponse()

    def ListModels(self, request, context):
        """List models trained in this session.

        ``ListModelsResponse.models`` is ``repeated Model`` (the full message),
        so build Model entries here (GetModel returns the simplified ModelInfo).
        """
        try:
            models = [
                ml_service_pb2.Model(
                    model_id=job.model_id,
                    name=job.model_id,
                    version="1.0.0",
                    model_type=job.model_type,
                    framework="numpy",
                    created_at=datetime_to_timestamp(job.completed_at or job.created_at),
                    updated_at=datetime_to_timestamp(job.completed_at or job.created_at),
                    status="ready",
                    metrics={k: float(v) for k, v in job.metrics.items()},
                )
                for job in self.orchestrator.list_models()
            ]

            logger.info("Listing %d models", len(models))
            return ml_service_pb2.ListModelsResponse(models=models)

        except Exception as e:
            logger.error("Error listing models: %s", e)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return ml_service_pb2.ListModelsResponse()

    def GetModel(self, request, context):
        """Get information about a trained model."""
        try:
            job = self.orchestrator.get_model(request.model_id)
            if not job:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details(f"Model {request.model_id} not found")
                return ml_service_pb2.ModelInfo()

            return ml_service_pb2.ModelInfo(
                model_id=job.model_id,
                model_type=job.model_type,
                version="1.0.0",
                status="trained",
                created_at=datetime_to_timestamp(job.completed_at or job.created_at),
                metrics={k: float(v) for k, v in job.metrics.items()},
            )

        except Exception as e:
            logger.error("Error getting model: %s", e)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return ml_service_pb2.ModelInfo()

    def Predict(self, request, context):
        """Run inference using a trained model."""
        try:
            logger.info("Prediction request for model %s", request.model_id)
            job = self.orchestrator.get_model(request.model_id)

            if not job or job.weights is None:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details(f"Trained model {request.model_id} not available")
                return ml_service_pb2.PredictionResponse()

            predictions = []
            for inp in request.inputs:
                feats = inp.features
                # Order-stable feature vector; pad/truncate to model input dim.
                n_in = job.weights["W1"].shape[0]
                vec = np.array([feats.get(k, 0.0) for k in sorted(feats.keys())], dtype=float)
                if vec.size < n_in:
                    vec = np.pad(vec, (0, n_in - vec.size))
                else:
                    vec = vec[:n_in]
                value = float(_mlp_predict(job.weights, vec[None, :])[0])
                predictions.append(
                    ml_service_pb2.PredictionResult(
                        prediction={"gravity_anomaly": value},
                        confidence=float(max(0.0, min(1.0, job.metrics.get("val_r2", 0.0)))),
                    )
                )

            return ml_service_pb2.PredictionResponse(predictions=predictions)

        except Exception as e:
            logger.error("Error making prediction: %s", e)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return ml_service_pb2.PredictionResponse()

    def TuneHyperparameters(self, request, context):
        """Start hyperparameter tuning job."""
        try:
            if not self.tuner:
                context.set_code(grpc.StatusCode.UNIMPLEMENTED)
                context.set_details("Hyperparameter tuning not available (optuna not installed)")
                return ml_service_pb2.TuneHyperparametersResponse(
                    status="unavailable",
                    response=common_pb2.Response(
                        success=False,
                        message="Optuna not installed"
                    )
                )

            logger.info("Starting hyperparameter tuning for %s", request.model_type)

            job_id = self.tuner.start_tuning(
                model_type=request.model_type,
                n_trials=request.n_trials or 50,
                timeout=request.timeout_seconds or 3600,
                fixed_params=dict(request.fixed_params)
            )

            return ml_service_pb2.TuneHyperparametersResponse(
                job_id=job_id,
                status="started",
                response=common_pb2.Response(
                    success=True,
                    message=f"Hyperparameter tuning started for {request.model_type}"
                )
            )

        except Exception as e:
            logger.error("Error starting hyperparameter tuning: %s", e)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return ml_service_pb2.TuneHyperparametersResponse(
                status="failed",
                response=common_pb2.Response(
                    success=False,
                    message=str(e)
                )
            )

    def GetTuningStatus(self, request, context):
        """Get hyperparameter tuning job status."""
        try:
            if not self.tuner:
                context.set_code(grpc.StatusCode.UNIMPLEMENTED)
                context.set_details("Hyperparameter tuning not available")
                return ml_service_pb2.TuningStatusResponse()

            status = self.tuner.get_status(request.job_id)
            if not status:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details(f"Tuning job {request.job_id} not found")
                return ml_service_pb2.TuningStatusResponse()

            # Separate best params into float and int maps
            best_params_float = {}
            best_params_int = {}
            for k, v in status.get("best_params", {}).items():
                if isinstance(v, int):
                    best_params_int[k] = v
                else:
                    best_params_float[k] = float(v)

            # Convert trial results
            trials = []
            for trial in status.get("trial_results", []):
                params_float = {}
                params_int = {}
                for k, v in trial.get("params", {}).items():
                    if isinstance(v, int):
                        params_int[k] = v
                    else:
                        params_float[k] = float(v)

                trials.append(
                    ml_service_pb2.TrialResult(
                        number=trial["number"],
                        value=trial["value"] if trial["value"] is not None else 0.0,
                        params_float=params_float,
                        params_int=params_int,
                        state=trial["state"]
                    )
                )

            return ml_service_pb2.TuningStatusResponse(
                job_id=status["job_id"],
                model_type=status["model_type"],
                status=status["status"],
                trials_completed=status["trials_completed"],
                trials_total=status["n_trials"],
                best_params_float=best_params_float,
                best_params_int=best_params_int,
                best_value=status["best_value"] if status["best_value"] != float('inf') else 0.0,
                trials=trials,
                error=status.get("error", ""),
                response=common_pb2.Response(
                    success=True,
                    message="Tuning status retrieved"
                )
            )

        except Exception as e:
            logger.error("Error getting tuning status: %s", e)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return ml_service_pb2.TuningStatusResponse()

    def HealthCheck(self, request, context):
        """Health check endpoint"""
        try:
            return common_pb2.HealthCheckResponse(
                status=common_pb2.HealthCheckResponse.SERVING
            )
        except Exception as e:
            logger.error("Health check failed: %s", e)
            return common_pb2.HealthCheckResponse(
                status=common_pb2.HealthCheckResponse.NOT_SERVING,
                details={"error": str(e)},
            )
