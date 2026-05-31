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
