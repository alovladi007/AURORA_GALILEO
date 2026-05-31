"""
Inversion Service gRPC implementation

Runs real gravity inversions (Tikhonov, Gauss-Newton, Bayesian MAP) via the
InversionEngine, tracks job progress, and serializes results to storage.
"""

import grpc
import logging
from datetime import datetime

from src.gen import inversion_service_pb2, inversion_service_pb2_grpc, common_pb2
from google.protobuf.timestamp_pb2 import Timestamp

from src.inversion_engine import InversionEngine
from src.result_writer import ResultWriter
from src.persistence import JobStore
from src.data_fetcher import GravityDataFetcher

logger = logging.getLogger(__name__)


def datetime_to_timestamp(dt: datetime) -> Timestamp:
    """Convert datetime to protobuf Timestamp"""
    ts = Timestamp()
    ts.FromDatetime(dt)
    return ts


class InversionServicer(inversion_service_pb2_grpc.InversionServiceServicer):
    """Inversion Service implementation backed by a real inversion engine."""

    def __init__(self):
        self.engine = InversionEngine()
        self.writer = ResultWriter()
        self.store = JobStore()
        self.fetcher = GravityDataFetcher()
        self._result_urls = {}  # job_id -> {gravity_field_url, coefficients_url}

    def RunInversion(self, request, context):
        """Run a gravity inversion using real numerical solvers."""
        try:
            logger.info("Starting inversion: %s", request.inversion_type)

            # If a data_query is supplied, fetch real gravity data from the
            # Data Service and invert that; otherwise use the synthetic problem.
            observed, grid_shape = None, None
            data_query = dict(request.data_query)
            if data_query:
                fetched = self.fetcher.fetch_grid(data_query)
                if fetched is not None:
                    observed, _counts, grid_shape = fetched
                    logger.info("Using real gravity data (%d cells) for inversion",
                                observed.size)
                else:
                    logger.info("No real data available; using synthetic problem")

            job = self.engine.start(
                request.inversion_type, dict(request.config),
                observed_data=observed, grid_shape=grid_shape,
            )
            self.store.upsert(job)

            # Rough estimate based on configured grid size.
            grid_cells = int(job.config.get("grid_rows", 12)) * int(job.config.get("grid_cols", 12))
            estimated = max(5.0, grid_cells * 0.05)

            return inversion_service_pb2.InversionResponse(
                job_id=job.job_id,
                status=job.status,
                message=f"Inversion {job.inversion_type} started",
                estimated_time=estimated,
            )

        except Exception as e:
            logger.error("Error starting inversion: %s", e)
            return inversion_service_pb2.InversionResponse(
                job_id="",
                status="failed",
                message=f"Error: {str(e)}",
                estimated_time=0.0,
            )

    def GetInversionStatus(self, request, context):
        """Get real-time status of an inversion job."""
        try:
            job = self.engine.get(request.job_id)
            if not job:
                return inversion_service_pb2.InversionStatusResponse(
                    job_id=request.job_id,
                    status="not_found",
                    progress=0.0,
                    message="Inversion job not found",
                )

            return inversion_service_pb2.InversionStatusResponse(
                job_id=job.job_id,
                status=job.status,
                progress=job.progress,
                current_iteration=job.current_iteration,
                total_iterations=job.total_iterations,
                residual=job.residual,
                message=job.message,
            )

        except Exception as e:
            logger.error("Error getting inversion status: %s", e)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return inversion_service_pb2.InversionStatusResponse()

    def GetInversionResult(self, request, context):
        """Get inversion results, serializing artifacts on first completion."""
        try:
            logger.info("Retrieving inversion result: %s", request.job_id)
            job = self.engine.get(request.job_id)

            if not job:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details(f"Job {request.job_id} not found")
                return inversion_service_pb2.InversionResult()

            if job.status != "completed":
                return inversion_service_pb2.InversionResult(
                    job_id=job.job_id,
                    inversion_type=job.inversion_type,
                    status=job.status,
                    convergence_achieved=False,
                    metadata={"message": job.message},
                )

            # Serialize result artifacts once and cache the URLs.
            urls = self._result_urls.get(job.job_id)
            if urls is None and job.model is not None:
                urls = self.writer.write(
                    job_id=job.job_id,
                    model=job.model,
                    grid_shape=job.grid_shape,
                    metadata={
                        "inversion_type": job.inversion_type,
                        "lambda": job.config.get("lambda", "auto"),
                        "residual": f"{job.residual:.6e}",
                    },
                    uncertainties=job.uncertainties,
                )
                self._result_urls[job.job_id] = urls
                self.store.upsert(job, urls)
            urls = urls or {}

            return inversion_service_pb2.InversionResult(
                job_id=job.job_id,
                inversion_type=job.inversion_type,
                status=job.status,
                completed_at=datetime_to_timestamp(job.completed_at or datetime.utcnow()),
                iterations=job.current_iteration,
                final_residual=job.residual,
                convergence_achieved=job.convergence_achieved,
                gravity_field_url=urls.get("gravity_field_url", ""),
                coefficients_url=urls.get("coefficients_url", ""),
                metadata={
                    "grid_shape": f"{job.grid_shape[0]}x{job.grid_shape[1]}",
                    "regularization": job.config.get("lambda", "auto"),
                    "algorithm": job.inversion_type,
                },
            )

        except Exception as e:
            logger.error("Error getting inversion result: %s", e)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return inversion_service_pb2.InversionResult()

    def ListInversions(self, request, context):
        """List inversion jobs tracked by the engine.

        ``ListInversionsResponse.jobs`` is ``repeated InversionJob`` (the full
        message), so build InversionJob entries here.
        """
        try:
            jobs = []
            for job in sorted(self.engine.list_jobs(),
                              key=lambda j: j.created_at, reverse=True):
                entry = inversion_service_pb2.InversionJob(
                    job_id=job.job_id,
                    created_at=datetime_to_timestamp(job.created_at),
                    status=job.status,
                    progress=job.progress,
                    rms_residual=job.residual,
                    error_message=job.error or "",
                )
                if job.completed_at:
                    entry.completed_at.CopyFrom(datetime_to_timestamp(job.completed_at))
                jobs.append(entry)

            logger.info("Listing %d inversions", len(jobs))
            return inversion_service_pb2.ListInversionsResponse(jobs=jobs)

        except Exception as e:
            logger.error("Error listing inversions: %s", e)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return inversion_service_pb2.ListInversionsResponse()

    def CancelInversion(self, request, context):
        """Cancel a running inversion."""
        try:
            cancelled = self.engine.cancel(request.job_id)
            if cancelled:
                logger.info("Cancelled inversion: %s", request.job_id)
            ts = Timestamp()
            ts.FromDatetime(datetime.utcnow())
            return common_pb2.Response(
                status_code=200 if cancelled else 409,
                message=(
                    f"Inversion {request.job_id} cancelled"
                    if cancelled
                    else f"Inversion {request.job_id} not cancellable"
                ),
                timestamp=ts,
            )

        except Exception as e:
            logger.error("Error cancelling inversion: %s", e)
            ts = Timestamp()
            ts.FromDatetime(datetime.utcnow())
            return common_pb2.Response(
                status_code=500,
                message=f"Error: {str(e)}",
                timestamp=ts,
            )

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
