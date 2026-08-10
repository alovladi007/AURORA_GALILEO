"""
Inversion Service gRPC implementation

Runs real gravity inversions (Tikhonov, Gauss-Newton, Bayesian MAP) via the
InversionEngine, tracks job progress, and serializes results to storage.
"""

import grpc
import numpy as np
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
                    observed, counts, grid_shape = fetched
                    logger.info(
                        "Using real gravity data for inversion: %d/%d cells populated",
                        int((counts > 0).sum()), observed.size)
                else:
                    counts = None
                    logger.info("No real data available; using synthetic problem")
            else:
                counts = None

            job = self.engine.start(
                request.inversion_type, dict(request.config),
                observed_data=observed, grid_shape=grid_shape,
                cell_counts=counts,
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

    def StartInversion(self, request, context):
        """Proto-first entry point (used by the API gateway): fetch the
        requested gravity measurements from the Data Service and invert
        them with the honest masked-gridding path. measurement_ids are
        interpreted as satellite IDs to select (empty = all)."""
        try:
            grid = request.grid
            rows = grid.num_lat_points or 12
            cols = grid.num_lon_points or 12
            data_query = {
                "satellite_ids": ",".join(request.measurement_ids),
                "grid_rows": str(rows),
                "grid_cols": str(cols),
            }
            if grid.max_latitude or grid.min_latitude:
                data_query.update({
                    "min_latitude": str(grid.min_latitude),
                    "max_latitude": str(grid.max_latitude),
                    "min_longitude": str(grid.min_longitude),
                    "max_longitude": str(grid.max_longitude),
                })

            observed = counts = grid_shape = None
            fetched = self.fetcher.fetch_grid(data_query)
            if fetched is not None:
                observed, counts, grid_shape = fetched
                logger.info(
                    "StartInversion '%s': %d/%d cells populated",
                    request.name, int((counts > 0).sum()), observed.size)
            else:
                context.set_code(grpc.StatusCode.FAILED_PRECONDITION)
                context.set_details(
                    "no gravity measurements available for the requested "
                    "satellites/region")
                return inversion_service_pb2.StartInversionResponse()

            method = request.parameters.method or "tikhonov"
            config = {"grid_rows": str(rows), "grid_cols": str(cols)}
            # Preserve geographic bounds so the model can be served as
            # a georeferenced map later (GetDensityModel).
            for k in ("min_latitude", "max_latitude",
                      "min_longitude", "max_longitude"):
                if k in data_query:
                    config[k] = data_query[k]
            if request.parameters.max_iterations:
                config["max_iterations"] = str(request.parameters.max_iterations)

            job = self.engine.start(
                method, config,
                observed_data=observed, grid_shape=grid_shape,
                cell_counts=counts,
            )
            self.store.upsert(job)

            resp = inversion_service_pb2.StartInversionResponse(
                job_id=job.job_id, status=job.status)
            return resp
        except Exception as e:  # noqa: BLE001
            logger.exception("StartInversion failed")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return inversion_service_pb2.StartInversionResponse()

    def GetDensityModel(self, request, context):
        """Return the completed inversion model as a georeferenced grid
        (used by the gateway /model route and the UI anomaly map)."""
        try:
            job = self.engine.get(request.job_id)
            if not job:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details(f"job {request.job_id} not found")
                return inversion_service_pb2.GetDensityModelResponse()
            if job.status != "completed" or job.model is None:
                context.set_code(grpc.StatusCode.FAILED_PRECONDITION)
                context.set_details(f"job {request.job_id} is {job.status}")
                return inversion_service_pb2.GetDensityModelResponse()

            rows = int(job.config.get("grid_rows", 12))
            cols = int(job.config.get("grid_cols", 12))
            model = inversion_service_pb2.DensityModel(
                model_id=f"model_{job.job_id}",
                job_id=job.job_id,
                density_values=[float(v) for v in np.asarray(job.model).ravel()],
                rms_residual=float(job.residual or 0.0),
            )
            if job.uncertainties is not None:
                model.uncertainty_values.extend(
                    float(v) for v in np.asarray(job.uncertainties).ravel())
            model.grid.num_lat_points = rows
            model.grid.num_lon_points = cols
            model.grid.min_latitude = float(job.config.get("min_latitude", -90))
            model.grid.max_latitude = float(job.config.get("max_latitude", 90))
            model.grid.min_longitude = float(job.config.get("min_longitude", -180))
            model.grid.max_longitude = float(job.config.get("max_longitude", 180))
            stats = np.asarray(job.model)
            model.statistics["min"] = float(stats.min())
            model.statistics["max"] = float(stats.max())
            model.statistics["mean"] = float(stats.mean())
            return inversion_service_pb2.GetDensityModelResponse(model=model)
        except Exception as e:  # noqa: BLE001
            logger.exception("GetDensityModel failed")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return inversion_service_pb2.GetDensityModelResponse()

    def GetInversionStatus(self, request, context):
        """Get real-time status of an inversion job.

        NOTE: the proto contract for this RPC is
        GetInversionStatusResponse{job: InversionJob} — the previous
        implementation returned the legacy InversionStatusResponse,
        which failed wire deserialization on every call.
        """
        try:
            job = self.engine.get(request.job_id)
            if not job:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details(f"Inversion job {request.job_id} not found")
                return inversion_service_pb2.GetInversionStatusResponse()

            pj = inversion_service_pb2.InversionJob(
                job_id=job.job_id,
                status=job.status,
                progress=float(job.progress),
                rms_residual=float(job.residual or 0.0),
                error_message=job.error or "",
            )
            if getattr(job, "created_at", None):
                pj.created_at.CopyFrom(datetime_to_timestamp(job.created_at))
            if getattr(job, "completed_at", None):
                pj.completed_at.CopyFrom(datetime_to_timestamp(job.completed_at))
            return inversion_service_pb2.GetInversionStatusResponse(job=pj)

        except Exception as e:
            logger.error("Error getting inversion status: %s", e)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return inversion_service_pb2.GetInversionStatusResponse()

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
