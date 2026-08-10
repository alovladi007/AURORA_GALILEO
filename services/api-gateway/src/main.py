"""
API Gateway Service for GALILEO
FastAPI-based REST API gateway that routes to gRPC microservices
"""

from fastapi import FastAPI, Depends, HTTPException, Header, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from contextlib import asynccontextmanager
import grpc
from typing import Optional, List, Dict, Any
import logging
from datetime import datetime, timedelta
import os

# Import generated gRPC clients
from gen.python.proto import (
    data_service_pb2,
    data_service_pb2_grpc,
    ml_service_pb2,
    ml_service_pb2_grpc,
    inversion_service_pb2,
    inversion_service_pb2_grpc,
    control_service_pb2,
    control_service_pb2_grpc,
    common_pb2,
)

from api.auth_v2 import verify_token, create_token_pair
from api.rbac import PermissionChecker, Permission
from api.circuit_breaker import circuit_breaker, CircuitBreakerOpenError
from api.telemetry import (
    instrument_fastapi,
    trace_span,
    add_span_attributes,
    get_current_trace_id,
)
from api.websocket_routes import router as websocket_router
from api.websocket_bridge import get_bridge
from api.workflow_routes import router as workflow_router
from api.event_orchestrator import get_orchestrator
from api.metrics import MetricsMiddleware, update_service_health, grpc_call_metrics

# Configure logging. The format references %(trace_id)s, so EVERY log
# record — including ones from third-party libraries — must carry that
# attribute or the formatter raises on every line; the filter below
# injects it (formerly missing: every log call printed a ValueError).
class _TraceIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "trace_id"):
            try:
                record.trace_id = get_current_trace_id() or "-"
            except Exception:
                record.trace_id = "-"
        return True


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s - trace_id=%(trace_id)s'
)
for _handler in logging.getLogger().handlers:
    _handler.addFilter(_TraceIdFilter())
logger = logging.getLogger(__name__)

# Configuration
DATA_SERVICE_HOST = os.getenv("GRPC_DATA_SERVICE_HOST", "localhost:50051")
ML_SERVICE_HOST = os.getenv("GRPC_ML_SERVICE_HOST", "localhost:50052")
INVERSION_SERVICE_HOST = os.getenv("GRPC_INVERSION_SERVICE_HOST", "localhost:50053")
CONTROL_SERVICE_HOST = os.getenv("GRPC_CONTROL_SERVICE_HOST", "localhost:50054")

# gRPC channel management
class GRPCChannelManager:
    """Manages gRPC channels with connection pooling"""

    def __init__(self):
        self.channels: Dict[str, grpc.aio.Channel] = {}
        self.stubs: Dict[str, Any] = {}

    async def initialize(self):
        """Initialize all gRPC channels"""
        # Data Service
        self.channels["data"] = grpc.aio.insecure_channel(DATA_SERVICE_HOST)
        self.stubs["data"] = data_service_pb2_grpc.DataServiceStub(self.channels["data"])

        # ML Service
        self.channels["ml"] = grpc.aio.insecure_channel(ML_SERVICE_HOST)
        self.stubs["ml"] = ml_service_pb2_grpc.MLServiceStub(self.channels["ml"])

        # Inversion Service
        self.channels["inversion"] = grpc.aio.insecure_channel(INVERSION_SERVICE_HOST)
        self.stubs["inversion"] = inversion_service_pb2_grpc.InversionServiceStub(self.channels["inversion"])

        # Control Service
        self.channels["control"] = grpc.aio.insecure_channel(CONTROL_SERVICE_HOST)
        self.stubs["control"] = control_service_pb2_grpc.ControlServiceStub(self.channels["control"])

        logger.info("gRPC channels initialized")

    async def close(self):
        """Close all gRPC channels"""
        for name, channel in self.channels.items():
            await channel.close()
            logger.info(f"Closed gRPC channel: {name}")

grpc_manager = GRPCChannelManager()

# Lifespan context manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management"""
    # Startup
    logger.info("Starting API Gateway...")
    await grpc_manager.initialize()

    # Start WebSocket bridge for real-time streaming
    bridge = get_bridge()
    await bridge.start()
    logger.info("WebSocket bridge started")

    # Start event orchestrator for workflow execution
    orchestrator = get_orchestrator()
    orchestrator.register_grpc_stubs(grpc_manager.stubs)
    await orchestrator.start()
    logger.info("Event orchestrator started")

    yield

    # Shutdown
    logger.info("Shutting down API Gateway...")
    await orchestrator.stop()
    await bridge.stop()
    await grpc_manager.close()

# Create FastAPI app
app = FastAPI(
    title="GALILEO API Gateway",
    version="2.0.0",
    description="REST API Gateway for GALILEO microservices",
    lifespan=lifespan,
)

# Rate limiting
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure properly in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Add Prometheus metrics middleware
app.add_middleware(MetricsMiddleware)

# Instrument with OpenTelemetry
instrument_fastapi(app)

# Include WebSocket routes
app.include_router(websocket_router)

# Include Workflow routes
app.include_router(workflow_router)

# Include Authentication routes (register / token / refresh / me)
from api.auth_routes import router as auth_router  # noqa: E402
app.include_router(auth_router)

# Dependency: Extract user context from JWT token
async def get_user_context(authorization: str = Header(None)) -> common_pb2.UserContext:
    """Extract and validate user context from JWT token"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header"
        )

    token = authorization.replace("Bearer ", "")

    # Verify token
    payload = verify_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )

    # Create user context (tokens issued by auth_v2 carry "user_id";
    # accept legacy "sub" claims as well)
    user_context = common_pb2.UserContext(
        user_id=payload.get("user_id") or payload.get("sub", ""),
        roles=payload.get("roles", []),
        permissions=payload.get("permissions", []),
        session_id=payload.get("jti", ""),
    )

    return user_context

# Extended routes: expose the remaining gRPC RPCs (gravity, export,
# model lifecycle, inversion list/results/cancel, satellite/command
# status, orbit prediction). Mounted after get_user_context so the
# router can borrow the channel manager and the auth dependency.
from api.extended_routes import build_extended_router  # noqa: E402
app.include_router(build_extended_router(grpc_manager, get_user_context))

# Operations console routes: real observability state (Prometheus
# targets, Alertmanager alerts, rule states) for the ops UI.
from api.ops_routes import build_ops_router  # noqa: E402
app.include_router(build_ops_router(get_user_context))

# Health check
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "2.0.0",
        "services": {
            "data": "connected",
            "ml": "connected",
            "inversion": "connected",
            "control": "connected",
        }
    }

# Metrics endpoint
@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    from api.metrics import get_metrics
    return get_metrics()

#
# Data Service Endpoints
#

@app.post("/api/v1/data/telemetry")
@limiter.limit("1000/minute")
@circuit_breaker("data_service_ingest", failure_threshold=5)
async def ingest_telemetry(
    request: Request,
    telemetry_data: Dict[str, Any],
    user_context: common_pb2.UserContext = Depends(get_user_context)
):
    """Ingest satellite telemetry data"""
    with trace_span("ingest_telemetry"):
        try:
            # Create gRPC request
            telemetry = data_service_pb2.SatelliteTelemetry(
                satellite_id=telemetry_data["satellite_id"],
                location=common_pb2.GeoLocation(
                    latitude=telemetry_data["location"]["latitude"],
                    longitude=telemetry_data["location"]["longitude"],
                    altitude=telemetry_data["location"]["altitude"],
                ),
                velocity_x=telemetry_data.get("velocity_x", 0.0),
                velocity_y=telemetry_data.get("velocity_y", 0.0),
                velocity_z=telemetry_data.get("velocity_z", 0.0),
                temperature=telemetry_data.get("temperature", 0.0),
                battery_level=telemetry_data.get("battery_level", 0.0),
            )
            # Without this every record lands at epoch 0 in TimescaleDB
            if telemetry_data.get("timestamp"):
                telemetry.timestamp.FromJsonString(
                    telemetry_data["timestamp"]
                )

            grpc_request = data_service_pb2.IngestTelemetryRequest(
                telemetry=[telemetry],
                user_context=user_context,
            )

            # Call gRPC service
            response = await grpc_manager.stubs["data"].IngestTelemetry(grpc_request)

            add_span_attributes({
                "records_ingested": response.records_ingested,
                "records_failed": response.records_failed,
            })

            return {
                "records_ingested": response.records_ingested,
                "records_failed": response.records_failed,
                "trace_id": get_current_trace_id(),
            }

        except grpc.RpcError as e:
            logger.error(f"gRPC error: {e.code()} - {e.details()}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Data service error: {e.details()}"
            )
        except CircuitBreakerOpenError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Data service temporarily unavailable"
            )

@app.get("/api/v1/data/telemetry")
@limiter.limit("500/minute")
@circuit_breaker("data_service_query", failure_threshold=5)
async def query_telemetry(
    request: Request,
    # Query(...) is required: a bare List[str] parameter on a GET route
    # is treated as a JSON body by FastAPI, which browsers cannot send
    satellite_ids: List[str] = Query(...),
    start_time: str = Query(...),
    end_time: str = Query(...),
    page: int = 1,
    page_size: int = 100,
    user_context: common_pb2.UserContext = Depends(get_user_context)
):
    """Query satellite telemetry data"""
    with trace_span("query_telemetry"):
        try:
            # TimeRange fields are protobuf Timestamps, not strings
            time_range = common_pb2.TimeRange()
            time_range.start_time.FromJsonString(start_time)
            time_range.end_time.FromJsonString(end_time)
            grpc_request = data_service_pb2.QueryTelemetryRequest(
                satellite_ids=satellite_ids,
                time_range=time_range,
                pagination=common_pb2.PaginationRequest(
                    page=page,
                    page_size=page_size,
                ),
                user_context=user_context,
            )

            response = await grpc_manager.stubs["data"].QueryTelemetry(grpc_request)

            return {
                "telemetry": [
                    {
                        "satellite_id": t.satellite_id,
                        # protobuf Timestamp is not JSON-serializable
                        "timestamp": t.timestamp.ToJsonString(),
                        "location": {
                            "latitude": t.location.latitude,
                            "longitude": t.location.longitude,
                            "altitude": t.location.altitude,
                        },
                        "velocity_x": t.velocity_x,
                        "velocity_y": t.velocity_y,
                        "velocity_z": t.velocity_z,
                        "temperature": t.temperature,
                        "battery_level": t.battery_level,
                    }
                    for t in response.telemetry
                ],
                "pagination": {
                    "total_items": response.pagination.total_items,
                    "total_pages": response.pagination.total_pages,
                    "current_page": response.pagination.current_page,
                    "page_size": response.pagination.page_size,
                },
                "trace_id": get_current_trace_id(),
            }

        except grpc.RpcError as e:
            logger.error(f"gRPC error: {e.code()} - {e.details()}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Data service error: {e.details()}"
            )

#
# ML Service Endpoints
#

@app.post("/api/v1/models/train")
@limiter.limit("10/minute")
@circuit_breaker("ml_service_train", failure_threshold=3)
async def train_model(
    request: Request,
    training_request: Dict[str, Any],
    user_context: common_pb2.UserContext = Depends(get_user_context)
):
    """Start model training job"""
    with trace_span("train_model"):
        try:
            # Check permission
            if not PermissionChecker.has_permission(
                user_context.roles,
                Permission.TRAIN_MODEL
            ):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient permissions"
                )

            grpc_request = ml_service_pb2.TrainModelRequest(
                model_name=training_request["model_name"],
                model_type=training_request["model_type"],
                dataset_id=training_request["dataset_id"],
                num_epochs=training_request.get("num_epochs", 100),
                batch_size=training_request.get("batch_size", 32),
                learning_rate=training_request.get("learning_rate", 0.001),
                user_context=user_context,
            )

            response = await grpc_manager.stubs["ml"].TrainModel(grpc_request)

            return {
                "job_id": response.job_id,
                "model_id": response.model_id,
                "status": response.status,
                "trace_id": get_current_trace_id(),
            }

        except grpc.RpcError as e:
            logger.error(f"gRPC error: {e.code()} - {e.details()}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"ML service error: {e.details()}"
            )

@app.post("/api/v1/models/{model_id}/predict")
@limiter.limit("1000/minute")
@circuit_breaker("ml_service_predict", failure_threshold=5)
async def predict(
    request: Request,
    model_id: str,
    prediction_request: Dict[str, Any],
    user_context: common_pb2.UserContext = Depends(get_user_context)
):
    """Make prediction with model"""
    with trace_span("predict"):
        try:
            grpc_request = ml_service_pb2.PredictRequest(
                model_id=model_id,
                input_features=prediction_request["input_features"],
                user_context=user_context,
            )

            response = await grpc_manager.stubs["ml"].Predict(grpc_request)

            return {
                "predictions": list(response.predictions),
                "confidence_scores": list(response.confidence_scores),
                "trace_id": get_current_trace_id(),
            }

        except grpc.RpcError as e:
            logger.error(f"gRPC error: {e.code()} - {e.details()}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"ML service error: {e.details()}"
            )

#
# Inversion Service Endpoints
#

@app.post("/api/v1/inversions")
@limiter.limit("20/hour")
@circuit_breaker("inversion_service_start", failure_threshold=3)
async def start_inversion(
    request: Request,
    inversion_request: Dict[str, Any],
    user_context: common_pb2.UserContext = Depends(get_user_context)
):
    """Start gravity field inversion"""
    with trace_span("start_inversion"):
        try:
            # Check permission
            if not PermissionChecker.has_permission(
                user_context.roles,
                Permission.START_INVERSION
            ):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient permissions"
                )

            grpc_request = inversion_service_pb2.StartInversionRequest(
                name=inversion_request["name"],
                description=inversion_request.get("description", ""),
                measurement_ids=inversion_request.get("measurement_ids", []),
                user_context=user_context,
            )
            params = inversion_request.get("parameters") or {}
            grpc_request.parameters.method = params.get("method", "tikhonov")
            grpc_request.parameters.max_iterations = int(params.get("max_iterations", 50))
            grpc_request.parameters.regularization_lambda = float(
                params.get("regularization_lambda", 0.0))
            grid = inversion_request.get("grid") or {}
            if grid:
                grpc_request.grid.min_latitude = float(grid.get("min_latitude", -90))
                grpc_request.grid.max_latitude = float(grid.get("max_latitude", 90))
                grpc_request.grid.min_longitude = float(grid.get("min_longitude", -180))
                grpc_request.grid.max_longitude = float(grid.get("max_longitude", 180))
                grpc_request.grid.num_lat_points = int(grid.get("num_lat_points", 12))
                grpc_request.grid.num_lon_points = int(grid.get("num_lon_points", 12))

            response = await grpc_manager.stubs["inversion"].StartInversion(grpc_request)

            return {
                "job_id": response.job_id,
                "status": response.status,
                # protobuf Timestamp is not JSON-serializable directly
                "estimated_completion": (
                    response.estimated_completion.ToJsonString()
                    if response.HasField("estimated_completion") else None
                ),
                "trace_id": get_current_trace_id(),
            }

        except grpc.RpcError as e:
            logger.error(f"gRPC error: {e.code()} - {e.details()}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Inversion service error: {e.details()}"
            )

@app.get("/api/v1/inversions/{job_id}")
@limiter.limit("100/minute")
async def get_inversion_status(
    request: Request,
    job_id: str,
    user_context: common_pb2.UserContext = Depends(get_user_context)
):
    """Get inversion job status"""
    with trace_span("get_inversion_status"):
        try:
            grpc_request = inversion_service_pb2.GetInversionStatusRequest(
                job_id=job_id,
                user_context=user_context,
            )

            response = await grpc_manager.stubs["inversion"].GetInversionStatus(grpc_request)

            return {
                "job_id": response.job.job_id,
                "status": response.job.status,
                "progress": response.job.progress,
                "rms_residual": response.job.rms_residual,
                "result_url": response.job.result_url,
                "trace_id": get_current_trace_id(),
            }

        except grpc.RpcError as e:
            logger.error(f"gRPC error: {e.code()} - {e.details()}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Inversion service error: {e.details()}"
            )

#
# Control Service Endpoints
#

@app.get("/api/v1/satellites")
@limiter.limit("100/minute")
async def list_satellites(
    request: Request,
    status_filter: Optional[str] = None,
    user_context: common_pb2.UserContext = Depends(get_user_context)
):
    """List all satellites"""
    with trace_span("list_satellites"):
        try:
            grpc_request = control_service_pb2.ListSatellitesRequest(
                status=status_filter or "",
                user_context=user_context,
            )

            response = await grpc_manager.stubs["control"].ListSatellites(grpc_request)

            return {
                "satellites": [
                    {
                        "satellite_id": s.satellite_id,
                        "name": s.name,
                        "mission": s.mission,
                        "status": s.status,
                        "battery_level": s.battery_level,
                    }
                    for s in response.satellites
                ],
                "trace_id": get_current_trace_id(),
            }

        except grpc.RpcError as e:
            logger.error(f"gRPC error: {e.code()} - {e.details()}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Control service error: {e.details()}"
            )

@app.post("/api/v1/satellites/{satellite_id}/commands")
@limiter.limit("50/hour")
async def send_command(
    request: Request,
    satellite_id: str,
    command_request: Dict[str, Any],
    user_context: common_pb2.UserContext = Depends(get_user_context)
):
    """Send command to satellite"""
    with trace_span("send_command"):
        try:
            # Check permission
            if not PermissionChecker.has_permission(
                user_context.roles,
                Permission.CONTROL_SATELLITE
            ):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient permissions"
                )

            command = control_service_pb2.SatelliteCommand(
                satellite_id=satellite_id,
                command_type=command_request["command_type"],
                parameters=command_request.get("parameters", {}),
                priority=command_request.get("priority", 5),
                user_context=user_context,
            )

            grpc_request = control_service_pb2.SendCommandRequest(
                command=command,
                wait_for_acknowledgment=command_request.get("wait_for_ack", False),
                timeout_seconds=command_request.get("timeout", 60),
            )

            response = await grpc_manager.stubs["control"].SendCommand(grpc_request)

            return {
                "command_id": response.command_id,
                "status": response.status,
                "trace_id": get_current_trace_id(),
            }

        except grpc.RpcError as e:
            logger.error(f"gRPC error: {e.code()} - {e.details()}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Control service error: {e.details()}"
            )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
