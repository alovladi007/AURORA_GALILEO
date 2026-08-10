"""
Inversion Service gRPC Tests
============================

Tests the InversionServicer against real generated protobuf stubs.
"""

import time

import pytest

from src.gen import inversion_service_pb2, common_pb2


def _wait_complete(servicer, context, job_id, timeout=15.0):
    # Proto contract: GetInversionStatusResponse{job: InversionJob}
    start = time.time()
    while time.time() - start < timeout:
        resp = servicer.GetInversionStatus(
            inversion_service_pb2.GetInversionStatusRequest(job_id=job_id),
            context)
        if resp.job.status in ("completed", "failed", "cancelled"):
            return resp.job
        time.sleep(0.1)
    return resp.job


class TestRunInversion:

    def test_run_and_complete_tikhonov(self, servicer, context):
        req = inversion_service_pb2.InversionRequest(
            inversion_type="tikhonov",
            config={"grid_rows": "10", "grid_cols": "10"},
        )
        resp = servicer.RunInversion(req, context)
        assert resp.job_id
        assert resp.status in ("queued", "running")

        status = _wait_complete(servicer, context, resp.job_id)
        assert status.status == "completed"

    def test_get_result_after_completion(self, servicer, context):
        req = inversion_service_pb2.InversionRequest(
            inversion_type="tikhonov",
            config={"grid_rows": "8", "grid_cols": "8"},
        )
        resp = servicer.RunInversion(req, context)
        _wait_complete(servicer, context, resp.job_id)

        result = servicer.GetInversionResult(
            inversion_service_pb2.InversionResultRequest(job_id=resp.job_id),
            context,
        )
        assert result.job_id == resp.job_id
        assert result.status == "completed"
        assert result.inversion_type == "tikhonov"

    def test_status_not_found(self, servicer, context):
        servicer.GetInversionStatus(
            inversion_service_pb2.GetInversionStatusRequest(
                job_id="does_not_exist"),
            context,
        )
        import grpc
        assert context.code == grpc.StatusCode.NOT_FOUND

    def test_list_inversions(self, servicer, context):
        servicer.RunInversion(
            inversion_service_pb2.InversionRequest(
                inversion_type="tikhonov",
                config={"grid_rows": "6", "grid_cols": "6"}),
            context,
        )
        resp = servicer.ListInversions(
            inversion_service_pb2.ListInversionsRequest(), context)
        assert len(resp.jobs) >= 1
        # Each entry is a full InversionJob message.
        assert resp.jobs[0].job_id

    def test_cancel_inversion(self, servicer, context):
        resp = servicer.RunInversion(
            inversion_service_pb2.InversionRequest(
                inversion_type="gauss_newton",
                config={"grid_rows": "20", "grid_cols": "20"}),
            context,
        )
        cancel = servicer.CancelInversion(
            inversion_service_pb2.CancelInversionRequest(job_id=resp.job_id),
            context,
        )
        # status_code 200 (cancelled) or 409 (already terminal)
        assert cancel.status_code in (200, 409)


class TestHealth:

    def test_health_check(self, servicer, context):
        resp = servicer.HealthCheck(common_pb2.HealthCheckRequest(), context)
        assert resp.status == common_pb2.HealthCheckResponse.SERVING
