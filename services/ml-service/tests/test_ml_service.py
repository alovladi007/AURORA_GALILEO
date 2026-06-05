"""
ML Service Tests
===============

Tests the MLServicer (training, status, listing, prediction) and the
underlying NumPy MLP training orchestrator against real protobuf stubs.
"""

import time

import pytest

from src.gen import ml_service_pb2, common_pb2


def _wait_training(servicer, context, job_id, timeout=20.0):
    start = time.time()
    while time.time() - start < timeout:
        status = servicer.GetTrainingStatus(
            ml_service_pb2.TrainingStatusRequest(job_id=job_id), context)
        if status.status in ("completed", "failed"):
            return status
        time.sleep(0.1)
    return status


class TestTraining:

    def test_train_and_complete(self, servicer, context):
        req = ml_service_pb2.TrainingRequest(
            model_type="mlp",
            config={"epochs": "50", "n_samples": "500"},
        )
        resp = servicer.TrainModel(req, context)
        assert resp.job_id
        assert resp.status in ("queued", "running")

        status = _wait_training(servicer, context, resp.job_id)
        assert status.status == "completed"
        # Loss should be finite and progress complete.
        assert status.progress >= 0.99

    def test_training_status_not_found(self, servicer, context):
        status = servicer.GetTrainingStatus(
            ml_service_pb2.TrainingStatusRequest(job_id="missing"), context)
        assert status.status == "not_found"

    def test_list_models_after_training(self, servicer, context):
        resp = servicer.TrainModel(
            ml_service_pb2.TrainingRequest(
                model_type="mlp", config={"epochs": "30", "n_samples": "300"}),
            context,
        )
        _wait_training(servicer, context, resp.job_id)

        models = servicer.ListModels(ml_service_pb2.ListModelsRequest(), context)
        assert len(models.models) >= 1
        # Each entry is a full Model message.
        m = models.models[0]
        assert m.model_id
        assert m.framework == "numpy"


class TestPrediction:

    def test_predict_with_trained_model(self, servicer, context):
        # Train a model first.
        resp = servicer.TrainModel(
            ml_service_pb2.TrainingRequest(
                model_type="mlp", config={"epochs": "50", "n_samples": "500"}),
            context,
        )
        _wait_training(servicer, context, resp.job_id)

        # The model_id is the training job's model_id; fetch from ListModels.
        models = servicer.ListModels(ml_service_pb2.ListModelsRequest(), context)
        model_id = models.models[0].model_id

        pred_req = ml_service_pb2.PredictionRequest(
            model_id=model_id,
            inputs=[
                ml_service_pb2.PredictionInput(features={"x": 0.5, "y": -0.3, "z": 0.1}),
            ],
        )
        pred = servicer.Predict(pred_req, context)
        assert len(pred.predictions) == 1
        assert "gravity_anomaly" in pred.predictions[0].prediction

    def test_predict_unknown_model(self, servicer, context):
        import grpc
        pred = servicer.Predict(
            ml_service_pb2.PredictionRequest(model_id="nope", inputs=[]),
            context,
        )
        assert context.code == grpc.StatusCode.NOT_FOUND


class TestHealth:

    def test_health_check(self, servicer, context):
        resp = servicer.HealthCheck(common_pb2.HealthCheckRequest(), context)
        assert resp.status == common_pb2.HealthCheckResponse.SERVING
