"""
Inversion Service gRPC implementation
"""

import grpc
import logging
from datetime import datetime
from typing import List

from src.gen import inversion_service_pb2, inversion_service_pb2_grpc, common_pb2
from google.protobuf.timestamp_pb2 import Timestamp

logger = logging.getLogger(__name__)


def datetime_to_timestamp(dt: datetime) -> Timestamp:
    """Convert datetime to protobuf Timestamp"""
    ts = Timestamp()
    ts.FromDatetime(dt)
    return ts


class InversionServicer(inversion_service_pb2_grpc.InversionServiceServicer):
    """Inversion Service implementation"""

    def __init__(self):
        self.inversion_jobs = {}  # Track inversion jobs

    def RunInversion(self, request, context):
        """Run gravity inversion"""
        try:
            logger.info(f"Starting inversion: {request.inversion_type}")

            # Create job
            job_id = f"inv_{datetime.utcnow().timestamp()}"
            self.inversion_jobs[job_id] = {
                "inversion_type": request.inversion_type,
                "status": "running",
                "started_at": datetime.utcnow()
            }

            # In production, this would:
            # 1. Fetch gravity data from Data Service
            # 2. Run inversion algorithm (spherical harmonics, mascons, etc.)
            # 3. Use ML models if hybrid_ml is enabled
            # 4. Store results back to Data Service

            return inversion_service_pb2.InversionResponse(
                job_id=job_id,
                status="running",
                message=f"Inversion {request.inversion_type} started",
                estimated_time=7200.0  # Mock: 2 hours
            )

        except Exception as e:
            logger.error(f"Error starting inversion: {e}")
            return inversion_service_pb2.InversionResponse(
                job_id="",
                status="failed",
                message=f"Error: {str(e)}",
                estimated_time=0.0
            )

    def GetInversionStatus(self, request, context):
        """Get status of inversion job"""
        try:
            job = self.inversion_jobs.get(request.job_id)
            if not job:
                return inversion_service_pb2.InversionStatusResponse(
                    job_id=request.job_id,
                    status="not_found",
                    progress=0.0,
                    message="Inversion job not found"
                )

            # Mock progress
            return inversion_service_pb2.InversionStatusResponse(
                job_id=request.job_id,
                status=job["status"],
                progress=0.65,  # Mock: 65% complete
                current_iteration=650,
                total_iterations=1000,
                residual=0.0234,
                message="Inversion in progress"
            )

        except Exception as e:
            logger.error(f"Error getting inversion status: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return inversion_service_pb2.InversionStatusResponse()

    def GetInversionResult(self, request, context):
        """Get inversion results"""
        try:
            logger.info(f"Retrieving inversion result: {request.job_id}")

            # Mock result - in production, this would load from storage
            result = inversion_service_pb2.InversionResult(
                job_id=request.job_id,
                inversion_type="spherical_harmonics",
                status="completed",
                completed_at=datetime_to_timestamp(datetime.utcnow()),
                iterations=1000,
                final_residual=0.000123,
                convergence_achieved=True,
                gravity_field_url="s3://galileo/inversions/inv_12345/field.nc",
                coefficients_url="s3://galileo/inversions/inv_12345/coeffs.json",
                metadata={
                    "max_degree": "120",
                    "algorithm": "conjugate_gradient",
                    "regularization": "tikhonov"
                }
            )

            return result

        except Exception as e:
            logger.error(f"Error getting inversion result: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return inversion_service_pb2.InversionResult()

    def ListInversions(self, request, context):
        """List inversion jobs"""
        try:
            # Mock list
            inversions = [
                inversion_service_pb2.InversionJobInfo(
                    job_id="inv_001",
                    inversion_type="spherical_harmonics",
                    status="completed",
                    created_at=datetime_to_timestamp(datetime.utcnow()),
                    progress=1.0
                ),
                inversion_service_pb2.InversionJobInfo(
                    job_id="inv_002",
                    inversion_type="mascons",
                    status="running",
                    created_at=datetime_to_timestamp(datetime.utcnow()),
                    progress=0.45
                )
            ]

            logger.info(f"Listing {len(inversions)} inversions")

            return inversion_service_pb2.ListInversionsResponse(
                inversions=inversions
            )

        except Exception as e:
            logger.error(f"Error listing inversions: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return inversion_service_pb2.ListInversionsResponse()

    def CancelInversion(self, request, context):
        """Cancel running inversion"""
        try:
            job = self.inversion_jobs.get(request.job_id)
            if job:
                job["status"] = "cancelled"
                logger.info(f"Cancelled inversion: {request.job_id}")

            return common_pb2.Response(
                success=True,
                message=f"Inversion {request.job_id} cancelled"
            )

        except Exception as e:
            logger.error(f"Error cancelling inversion: {e}")
            return common_pb2.Response(
                success=False,
                message=f"Error: {str(e)}",
                error=common_pb2.Error(
                    code="CANCEL_ERROR",
                    message=str(e)
                )
            )

    def HealthCheck(self, request, context):
        """Health check endpoint"""
        try:
            return common_pb2.HealthCheckResponse(
                status=common_pb2.HealthCheckResponse.SERVING
            )
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return common_pb2.HealthCheckResponse(
                status=common_pb2.HealthCheckResponse.NOT_SERVING,
                details={"error": str(e)}
            )
