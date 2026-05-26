"""
Enhanced API Gateway for GALILEO
Connects to Data Service via gRPC and provides all frontend endpoints
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import logging
import sys
import os

try:
    import grpc
    from google.protobuf.timestamp_pb2 import Timestamp
    # Import all service protos (generated in /app/gen or ../X-service/src/gen for local)
    try:
        import data_service_pb2
        import data_service_pb2_grpc
        import ml_service_pb2
        import ml_service_pb2_grpc
        import inversion_service_pb2
        import inversion_service_pb2_grpc
        import control_service_pb2
        import control_service_pb2_grpc
        import common_pb2
    except ImportError:
        # Try local development path
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../data-service/src/gen'))
        import data_service_pb2
        import data_service_pb2_grpc
        import ml_service_pb2
        import ml_service_pb2_grpc
        import inversion_service_pb2
        import inversion_service_pb2_grpc
        import control_service_pb2
        import control_service_pb2_grpc
        import common_pb2
    GRPC_AVAILABLE = True
except ImportError as e:
    logging.warning(f"gRPC imports failed: {e}. Using mock data.")
    GRPC_AVAILABLE = False

app = FastAPI(title="GALILEO API Gateway", version="2.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:13003"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# gRPC connections
DATA_SERVICE_ADDR = os.getenv("GRPC_DATA_SERVICE_HOST", "data-service:50051")
ML_SERVICE_ADDR = os.getenv("GRPC_ML_SERVICE_HOST", "ml-service:50052")
INVERSION_SERVICE_ADDR = os.getenv("GRPC_INVERSION_SERVICE_HOST", "inversion-service:50053")
CONTROL_SERVICE_ADDR = os.getenv("GRPC_CONTROL_SERVICE_HOST", "control-service:50054")

data_stub = None
ml_stub = None
inversion_stub = None
control_stub = None

def get_data_stub():
    """Get or create gRPC stub for Data Service"""
    global data_stub
    if data_stub is None and GRPC_AVAILABLE:
        try:
            channel = grpc.insecure_channel(DATA_SERVICE_ADDR)
            data_stub = data_service_pb2_grpc.DataServiceStub(channel)
            logger.info(f"Connected to Data Service at {DATA_SERVICE_ADDR}")
        except Exception as e:
            logger.error(f"Failed to connect to Data Service: {e}")
    return data_stub

def get_ml_stub():
    """Get or create gRPC stub for ML Service"""
    global ml_stub
    if ml_stub is None and GRPC_AVAILABLE:
        try:
            channel = grpc.insecure_channel(ML_SERVICE_ADDR)
            ml_stub = ml_service_pb2_grpc.MLServiceStub(channel)
            logger.info(f"Connected to ML Service at {ML_SERVICE_ADDR}")
        except Exception as e:
            logger.error(f"Failed to connect to ML Service: {e}")
    return ml_stub

def get_inversion_stub():
    """Get or create gRPC stub for Inversion Service"""
    global inversion_stub
    if inversion_stub is None and GRPC_AVAILABLE:
        try:
            channel = grpc.insecure_channel(INVERSION_SERVICE_ADDR)
            inversion_stub = inversion_service_pb2_grpc.InversionServiceStub(channel)
            logger.info(f"Connected to Inversion Service at {INVERSION_SERVICE_ADDR}")
        except Exception as e:
            logger.error(f"Failed to connect to Inversion Service: {e}")
    return inversion_stub

def get_control_stub():
    """Get or create gRPC stub for Control Service"""
    global control_stub
    if control_stub is None and GRPC_AVAILABLE:
        try:
            channel = grpc.insecure_channel(CONTROL_SERVICE_ADDR)
            control_stub = control_service_pb2_grpc.ControlServiceStub(channel)
            logger.info(f"Connected to Control Service at {CONTROL_SERVICE_ADDR}")
        except Exception as e:
            logger.error(f"Failed to connect to Control Service: {e}")
    return control_stub

# Request/Response models
class TelemetryIngest(BaseModel):
    satellite_id: str
    latitude: float
    longitude: float
    altitude: float
    velocity_x: Optional[float] = 0.0
    velocity_y: Optional[float] = 0.0
    velocity_z: Optional[float] = 0.0
    temperature: Optional[float] = 0.0
    battery_level: Optional[float] = 0.0

class GravityIngest(BaseModel):
    satellite_id: str
    latitude: float
    longitude: float
    altitude: float
    gravity_x: float
    gravity_y: float
    gravity_z: float
    magnitude: float
    accuracy: Optional[float] = 0.0
    quality_flag: Optional[int] = 0

class TrainingConfig(BaseModel):
    epochs: Optional[int] = 1000
    learning_rate: Optional[float] = 0.001
    batch_size: Optional[int] = 32

class DataSource(BaseModel):
    satellite_ids: Optional[List[str]] = []
    start_time: Optional[str] = None
    end_time: Optional[str] = None

class TrainModelRequest(BaseModel):
    model_type: str
    training_config: Optional[TrainingConfig] = None
    data_source: Optional[DataSource] = None

class PredictionInput(BaseModel):
    features: dict

class PredictRequest(BaseModel):
    model_id: str
    inputs: List[PredictionInput]

class InversionConfig(BaseModel):
    max_degree: Optional[int] = 120
    regularization: Optional[str] = "tikhonov"
    convergence_threshold: Optional[float] = 0.0001
    max_iterations: Optional[int] = 1000

class DataQuery(BaseModel):
    satellite_ids: Optional[List[str]] = []
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    min_latitude: Optional[float] = -90.0
    max_latitude: Optional[float] = 90.0
    min_longitude: Optional[float] = -180.0
    max_longitude: Optional[float] = 180.0

class RunInversionRequest(BaseModel):
    inversion_type: str
    config: Optional[InversionConfig] = None
    data_query: Optional[DataQuery] = None

class Vector3(BaseModel):
    x: float
    y: float
    z: float

class MissionPlanRequest(BaseModel):
    mission_name: str
    satellite_ids: List[str]
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    objectives: Optional[List[str]] = []

class ManeuverRequest(BaseModel):
    satellite_id: str
    maneuver_type: str
    delta_v: Vector3
    execution_time: Optional[str] = None

class OrbitalState(BaseModel):
    position: Vector3
    velocity: Vector3

class PropagateRequest(BaseModel):
    satellite_id: str
    initial_state: Optional[OrbitalState] = None
    start_time: str
    duration: int
    timestep: Optional[int] = 60

class SimulateMissionRequest(BaseModel):
    mission_name: str
    plan_id: Optional[str] = None
    duration: Optional[int] = 86400
    timestep: Optional[int] = 60

class JobCreate(BaseModel):
    job_type: str
    parameters: dict

# Root endpoints
@app.get("/")
async def root():
    return {
        "service": "GALILEO API Gateway",
        "version": "2.0.0",
        "status": "running",
        "grpc_available": GRPC_AVAILABLE
    }

@app.get("/health")
async def health():
    """Health check with all microservices connectivity"""
    services_status = {}

    if GRPC_AVAILABLE:
        # Check Data Service
        stub = get_data_stub()
        if stub:
            try:
                req = common_pb2.HealthCheckRequest()
                resp = stub.HealthCheck(req, timeout=2.0)
                services_status["data_service"] = "healthy"
            except Exception as e:
                services_status["data_service"] = f"unhealthy: {str(e)}"
        else:
            services_status["data_service"] = "disconnected"

        # Check ML Service
        stub = get_ml_stub()
        if stub:
            try:
                req = common_pb2.HealthCheckRequest()
                resp = stub.HealthCheck(req, timeout=2.0)
                services_status["ml_service"] = "healthy"
            except Exception as e:
                services_status["ml_service"] = f"unhealthy: {str(e)}"
        else:
            services_status["ml_service"] = "disconnected"

        # Check Inversion Service
        stub = get_inversion_stub()
        if stub:
            try:
                req = common_pb2.HealthCheckRequest()
                resp = stub.HealthCheck(req, timeout=2.0)
                services_status["inversion_service"] = "healthy"
            except Exception as e:
                services_status["inversion_service"] = f"unhealthy: {str(e)}"
        else:
            services_status["inversion_service"] = "disconnected"

        # Check Control Service
        stub = get_control_stub()
        if stub:
            try:
                req = common_pb2.HealthCheckRequest()
                resp = stub.HealthCheck(req, timeout=2.0)
                services_status["control_service"] = "healthy"
            except Exception as e:
                services_status["control_service"] = f"unhealthy: {str(e)}"
        else:
            services_status["control_service"] = "disconnected"
    else:
        services_status = {
            "data_service": "mock_mode",
            "ml_service": "mock_mode",
            "inversion_service": "mock_mode",
            "control_service": "mock_mode"
        }

    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "services": services_status
    }

# Telemetry endpoints
@app.post("/api/v1/data/telemetry")
async def ingest_telemetry(data: TelemetryIngest):
    """Ingest telemetry via Data Service"""
    logger.info(f"Ingest telemetry for {data.satellite_id}")

    stub = get_data_stub()
    if stub and GRPC_AVAILABLE:
        try:
            # Create timestamp
            ts = Timestamp()
            ts.FromDatetime(datetime.utcnow())

            # Create request
            req = data_service_pb2.SatelliteTelemetry(
                satellite_id=data.satellite_id,
                timestamp=ts,
                location=common_pb2.GeoLocation(
                    latitude=data.latitude,
                    longitude=data.longitude,
                    altitude=data.altitude
                ),
                velocity_x=data.velocity_x,
                velocity_y=data.velocity_y,
                velocity_z=data.velocity_z,
                temperature=data.temperature,
                battery_level=data.battery_level
            )

            # Call gRPC service
            resp = stub.IngestTelemetry(req)

            return {
                "success": resp.success,
                "message": resp.message,
                "record_id": resp.data.get("record_id", "unknown")
            }
        except Exception as e:
            logger.error(f"gRPC error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # Mock response
    return {
        "success": True,
        "message": "Telemetry ingested (mock)",
        "record_id": "mock_001"
    }

@app.get("/api/v1/data/telemetry")
async def query_telemetry(
    satellite_ids: Optional[str] = None,
    limit: int = 100
):
    """Query telemetry from Data Service"""
    logger.info(f"Query telemetry: satellite_ids={satellite_ids}")

    stub = get_data_stub()
    if stub and GRPC_AVAILABLE:
        try:
            # Create request
            req = data_service_pb2.TelemetryQueryRequest(
                satellite_ids=satellite_ids.split(",") if satellite_ids else [],
                pagination=common_pb2.PaginationRequest(
                    offset=0,
                    limit=limit
                )
            )

            # Call gRPC service
            resp = stub.QueryTelemetry(req)

            # Convert to JSON
            telemetry = []
            for t in resp.telemetry:
                telemetry.append({
                    "satellite_id": t.satellite_id,
                    "timestamp": t.timestamp.ToDatetime().isoformat(),
                    "location": {
                        "latitude": t.location.latitude,
                        "longitude": t.location.longitude,
                        "altitude": t.location.altitude
                    },
                    "velocity_x": t.velocity_x,
                    "velocity_y": t.velocity_y,
                    "velocity_z": t.velocity_z,
                    "temperature": t.temperature,
                    "battery_level": t.battery_level
                })

            return {
                "telemetry": telemetry,
                "pagination": {
                    "total": resp.pagination.total,
                    "offset": resp.pagination.offset,
                    "limit": resp.pagination.limit
                }
            }
        except Exception as e:
            logger.error(f"gRPC error: {e}")
            # Fall through to mock data

    # Mock data
    return {
        "telemetry": [
            {
                "satellite_id": "SAT-001",
                "timestamp": datetime.utcnow().isoformat(),
                "location": {"latitude": 45.5, "longitude": -122.6, "altitude": 550000},
                "velocity_x": 7500.0,
                "velocity_y": 0.0,
                "velocity_z": 0.0,
                "temperature": 15.0,
                "battery_level": 85.0
            }
        ],
        "pagination": {"total": 1, "offset": 0, "limit": limit}
    }

@app.post("/api/v1/data/gravity")
async def ingest_gravity(data: GravityIngest):
    """Ingest gravity measurement via Data Service"""
    logger.info(f"Ingest gravity for {data.satellite_id}")

    stub = get_data_stub()
    if stub and GRPC_AVAILABLE:
        try:
            # Create timestamp
            ts = Timestamp()
            ts.FromDatetime(datetime.utcnow())

            # Create request
            req = data_service_pb2.GravityMeasurement(
                satellite_id=data.satellite_id,
                timestamp=ts,
                location=common_pb2.GeoLocation(
                    latitude=data.latitude,
                    longitude=data.longitude,
                    altitude=data.altitude
                ),
                gravity_x=data.gravity_x,
                gravity_y=data.gravity_y,
                gravity_z=data.gravity_z,
                magnitude=data.magnitude,
                accuracy=data.accuracy,
                quality_flag=data.quality_flag
            )

            # Call gRPC service
            resp = stub.IngestGravity(req)

            return {
                "success": resp.success,
                "message": resp.message,
                "record_id": resp.data.get("record_id", "unknown")
            }
        except Exception as e:
            logger.error(f"gRPC error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # Mock response
    return {
        "success": True,
        "message": "Gravity measurement ingested (mock)",
        "record_id": "mock_grav_001"
    }

@app.get("/api/v1/data/gravity")
async def query_gravity(
    satellite_ids: Optional[str] = None,
    limit: int = 100
):
    """Query gravity measurements from Data Service"""
    logger.info(f"Query gravity: satellite_ids={satellite_ids}")

    stub = get_data_stub()
    if stub and GRPC_AVAILABLE:
        try:
            # Create request
            req = data_service_pb2.GravityQueryRequest(
                satellite_ids=satellite_ids.split(",") if satellite_ids else [],
                pagination=common_pb2.PaginationRequest(
                    offset=0,
                    limit=limit
                )
            )

            # Call gRPC service
            resp = stub.QueryGravity(req)

            # Convert to JSON
            measurements = []
            for m in resp.measurements:
                measurements.append({
                    "satellite_id": m.satellite_id,
                    "timestamp": m.timestamp.ToDatetime().isoformat(),
                    "location": {
                        "latitude": m.location.latitude,
                        "longitude": m.location.longitude,
                        "altitude": m.location.altitude
                    },
                    "gravity_x": m.gravity_x,
                    "gravity_y": m.gravity_y,
                    "gravity_z": m.gravity_z,
                    "magnitude": m.magnitude,
                    "accuracy": m.accuracy,
                    "quality_flag": m.quality_flag
                })

            return {
                "measurements": measurements,
                "pagination": {
                    "total": resp.pagination.total,
                    "offset": resp.pagination.offset,
                    "limit": resp.pagination.limit
                }
            }
        except Exception as e:
            logger.error(f"gRPC error: {e}")
            # Fall through to mock data

    # Mock data
    return {
        "measurements": [
            {
                "satellite_id": "SAT-001",
                "timestamp": datetime.utcnow().isoformat(),
                "location": {"latitude": 45.5, "longitude": -122.6, "altitude": 550000},
                "gravity_x": 0.01,
                "gravity_y": 0.02,
                "gravity_z": 9.81,
                "magnitude": 9.81,
                "accuracy": 0.0001,
                "quality_flag": 1
            }
        ],
        "pagination": {"total": 1, "offset": 0, "limit": limit}
    }

# Operations endpoints
@app.get("/ops/jobs")
async def list_jobs():
    """List operation jobs"""
    return {"jobs": []}

@app.post("/ops/jobs")
async def create_job(job: JobCreate):
    """Create a new operation job"""
    logger.info(f"Create job: {job.job_type}")
    return {
        "job_id": f"job_{datetime.utcnow().timestamp()}",
        "status": "created",
        "job_type": job.job_type
    }

# Plan endpoints
@app.post("/api/plan")
async def create_plan(plan_data: dict):
    """Create mission plan"""
    logger.info(f"Create plan: {plan_data}")
    return {
        "plan_id": f"plan_{datetime.utcnow().timestamp()}",
        "status": "created"
    }

# Simulation endpoints
@app.post("/api/simulation/propagate")
async def propagate_orbit(sim_data: dict):
    """Propagate satellite orbit"""
    logger.info(f"Propagate orbit: {sim_data}")
    return {
        "status": "success",
        "states": [
            {
                "time": datetime.utcnow().isoformat(),
                "position": [6878000, 0, 0],
                "velocity": [0, 7500, 0]
            }
        ]
    }

# ============================================================================
# ML SERVICE ENDPOINTS
# ============================================================================

@app.post("/api/v1/models/train")
async def train_model(request: TrainModelRequest):
    """Train a new ML model"""
    logger.info(f"Training model: {request.model_type}")

    stub = get_ml_stub()
    if stub and GRPC_AVAILABLE:
        try:
            # Build training config
            config = {}
            if request.training_config:
                config["epochs"] = str(request.training_config.epochs)
                config["learning_rate"] = str(request.training_config.learning_rate)
                config["batch_size"] = str(request.training_config.batch_size)

            # Build data source config
            if request.data_source:
                config["satellite_ids"] = ",".join(request.data_source.satellite_ids)
                if request.data_source.start_time:
                    config["start_time"] = request.data_source.start_time
                if request.data_source.end_time:
                    config["end_time"] = request.data_source.end_time

            # Create gRPC request
            req = ml_service_pb2.TrainingRequest(
                model_type=request.model_type,
                config=config
            )

            # Call gRPC service
            resp = stub.TrainModel(req, timeout=5.0)

            return {
                "job_id": resp.job_id,
                "status": resp.status,
                "message": resp.message,
                "estimated_time": resp.estimated_time
            }
        except grpc.RpcError as e:
            logger.error(f"gRPC error: {e}")
            raise HTTPException(status_code=500, detail=f"ML Service error: {e.details()}")
        except Exception as e:
            logger.error(f"Error training model: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # Mock response
    return {
        "job_id": f"train_{datetime.utcnow().timestamp()}",
        "status": "training",
        "message": f"Training {request.model_type} model (mock)",
        "estimated_time": 3600.0
    }

@app.get("/api/v1/models/train/{job_id}/status")
async def get_training_status(job_id: str):
    """Get training job status"""
    logger.info(f"Get training status: {job_id}")

    stub = get_ml_stub()
    if stub and GRPC_AVAILABLE:
        try:
            req = ml_service_pb2.TrainingStatusRequest(job_id=job_id)
            resp = stub.GetTrainingStatus(req, timeout=5.0)

            return {
                "job_id": resp.job_id,
                "status": resp.status,
                "progress": resp.progress,
                "current_epoch": resp.current_epoch,
                "total_epochs": resp.total_epochs,
                "loss": resp.loss,
                "message": resp.message
            }
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.NOT_FOUND:
                raise HTTPException(status_code=404, detail="Training job not found")
            logger.error(f"gRPC error: {e}")
            raise HTTPException(status_code=500, detail=str(e))
        except Exception as e:
            logger.error(f"Error getting training status: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # Mock response
    return {
        "job_id": job_id,
        "status": "training",
        "progress": 0.5,
        "current_epoch": 500,
        "total_epochs": 1000,
        "loss": 0.0234,
        "message": "Training in progress (mock)"
    }

@app.get("/api/v1/models")
async def list_models():
    """List available ML models"""
    logger.info("Listing models")

    stub = get_ml_stub()
    if stub and GRPC_AVAILABLE:
        try:
            req = ml_service_pb2.ListModelsRequest()
            resp = stub.ListModels(req, timeout=5.0)

            models = []
            for m in resp.models:
                models.append({
                    "model_id": m.model_id,
                    "model_type": m.model_type,
                    "version": m.version,
                    "status": m.status,
                    "created_at": m.created_at.ToDatetime().isoformat() if m.created_at else None,
                    "metrics": dict(m.metrics) if m.metrics else {}
                })

            return {"models": models}
        except Exception as e:
            logger.error(f"Error listing models: {e}")
            # Fall through to mock

    # Mock response
    return {
        "models": [
            {
                "model_id": "pinn_001",
                "model_type": "pinn",
                "version": "1.0.0",
                "status": "trained",
                "created_at": datetime.utcnow().isoformat(),
                "metrics": {"loss": 0.0123, "accuracy": 0.987}
            }
        ]
    }

@app.get("/api/v1/models/{model_id}")
async def get_model(model_id: str):
    """Get model information"""
    logger.info(f"Get model: {model_id}")

    stub = get_ml_stub()
    if stub and GRPC_AVAILABLE:
        try:
            req = ml_service_pb2.GetModelRequest(model_id=model_id)
            resp = stub.GetModel(req, timeout=5.0)

            return {
                "model_id": resp.model_id,
                "model_type": resp.model_type,
                "version": resp.version,
                "status": resp.status,
                "created_at": resp.created_at.ToDatetime().isoformat() if resp.created_at else None,
                "metrics": dict(resp.metrics) if resp.metrics else {}
            }
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.NOT_FOUND:
                raise HTTPException(status_code=404, detail="Model not found")
            logger.error(f"gRPC error: {e}")
            raise HTTPException(status_code=500, detail=str(e))
        except Exception as e:
            logger.error(f"Error getting model: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # Mock response
    raise HTTPException(status_code=404, detail="Model not found (mock mode)")

@app.post("/api/v1/models/{model_id}/predict")
async def predict(model_id: str, request: PredictRequest):
    """Make predictions using trained model"""
    logger.info(f"Prediction request for model {model_id}")

    stub = get_ml_stub()
    if stub and GRPC_AVAILABLE:
        try:
            # Build inputs
            inputs = []
            for inp in request.inputs:
                inputs.append(ml_service_pb2.PredictionInput(
                    features=inp.features
                ))

            req = ml_service_pb2.PredictionRequest(
                model_id=model_id,
                inputs=inputs
            )

            resp = stub.Predict(req, timeout=10.0)

            predictions = []
            for p in resp.predictions:
                predictions.append({
                    "prediction": dict(p.prediction),
                    "confidence": p.confidence
                })

            return {"predictions": predictions}
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.NOT_FOUND:
                raise HTTPException(status_code=404, detail="Model not found")
            logger.error(f"gRPC error: {e}")
            raise HTTPException(status_code=500, detail=str(e))
        except Exception as e:
            logger.error(f"Error making prediction: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # Mock response
    predictions = [{"prediction": {"gravity_anomaly": 0.05}, "confidence": 0.95} for _ in request.inputs]
    return {"predictions": predictions}

# ============================================================================
# INVERSION SERVICE ENDPOINTS
# ============================================================================

@app.post("/api/v1/inversions/run")
async def run_inversion(request: RunInversionRequest):
    """Run gravity field inversion"""
    logger.info(f"Running inversion: {request.inversion_type}")

    stub = get_inversion_stub()
    if stub and GRPC_AVAILABLE:
        try:
            # Build config
            config = {}
            if request.config:
                config["max_degree"] = str(request.config.max_degree)
                config["regularization"] = request.config.regularization
                config["convergence_threshold"] = str(request.config.convergence_threshold)
                config["max_iterations"] = str(request.config.max_iterations)

            # Build data query (simplified for now)
            data_config = {}
            if request.data_query:
                if request.data_query.satellite_ids:
                    data_config["satellite_ids"] = ",".join(request.data_query.satellite_ids)
                if request.data_query.start_time:
                    data_config["start_time"] = request.data_query.start_time
                if request.data_query.end_time:
                    data_config["end_time"] = request.data_query.end_time

            # Create gRPC request
            req = inversion_service_pb2.InversionRequest(
                inversion_type=request.inversion_type,
                config=config,
                data_query=data_config
            )

            resp = stub.RunInversion(req, timeout=5.0)

            return {
                "job_id": resp.job_id,
                "status": resp.status,
                "message": resp.message,
                "estimated_time": resp.estimated_time
            }
        except grpc.RpcError as e:
            logger.error(f"gRPC error: {e}")
            raise HTTPException(status_code=500, detail=f"Inversion Service error: {e.details()}")
        except Exception as e:
            logger.error(f"Error running inversion: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # Mock response
    return {
        "job_id": f"inv_{datetime.utcnow().timestamp()}",
        "status": "running",
        "message": f"Inversion {request.inversion_type} started (mock)",
        "estimated_time": 7200.0
    }

@app.get("/api/v1/inversions/{job_id}/status")
async def get_inversion_status(job_id: str):
    """Get inversion job status"""
    logger.info(f"Get inversion status: {job_id}")

    stub = get_inversion_stub()
    if stub and GRPC_AVAILABLE:
        try:
            req = inversion_service_pb2.InversionStatusRequest(job_id=job_id)
            resp = stub.GetInversionStatus(req, timeout=5.0)

            return {
                "job_id": resp.job_id,
                "status": resp.status,
                "progress": resp.progress,
                "current_iteration": resp.current_iteration,
                "total_iterations": resp.total_iterations,
                "residual": resp.residual,
                "message": resp.message
            }
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.NOT_FOUND:
                raise HTTPException(status_code=404, detail="Inversion job not found")
            logger.error(f"gRPC error: {e}")
            raise HTTPException(status_code=500, detail=str(e))
        except Exception as e:
            logger.error(f"Error getting inversion status: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # Mock response
    return {
        "job_id": job_id,
        "status": "running",
        "progress": 0.65,
        "current_iteration": 650,
        "total_iterations": 1000,
        "residual": 0.0234,
        "message": "Inversion in progress (mock)"
    }

@app.get("/api/v1/inversions/{job_id}/result")
async def get_inversion_result(job_id: str):
    """Get inversion results"""
    logger.info(f"Get inversion result: {job_id}")

    stub = get_inversion_stub()
    if stub and GRPC_AVAILABLE:
        try:
            req = inversion_service_pb2.InversionResultRequest(job_id=job_id)
            resp = stub.GetInversionResult(req, timeout=5.0)

            return {
                "job_id": resp.job_id,
                "inversion_type": resp.inversion_type,
                "status": resp.status,
                "completed_at": resp.completed_at.ToDatetime().isoformat() if resp.completed_at else None,
                "iterations": resp.iterations,
                "final_residual": resp.final_residual,
                "convergence_achieved": resp.convergence_achieved,
                "gravity_field_url": resp.gravity_field_url,
                "coefficients_url": resp.coefficients_url,
                "metadata": dict(resp.metadata) if resp.metadata else {}
            }
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.NOT_FOUND:
                raise HTTPException(status_code=404, detail="Inversion result not found")
            logger.error(f"gRPC error: {e}")
            raise HTTPException(status_code=500, detail=str(e))
        except Exception as e:
            logger.error(f"Error getting inversion result: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # Mock response
    return {
        "job_id": job_id,
        "inversion_type": "spherical_harmonics",
        "status": "completed",
        "completed_at": datetime.utcnow().isoformat(),
        "iterations": 1000,
        "final_residual": 0.000123,
        "convergence_achieved": True,
        "gravity_field_url": "s3://galileo/inversions/mock/field.nc",
        "coefficients_url": "s3://galileo/inversions/mock/coeffs.json",
        "metadata": {"max_degree": "120", "algorithm": "conjugate_gradient"}
    }

@app.get("/api/v1/inversions")
async def list_inversions(status: Optional[str] = None):
    """List inversion jobs"""
    logger.info(f"List inversions: status={status}")

    stub = get_inversion_stub()
    if stub and GRPC_AVAILABLE:
        try:
            req = inversion_service_pb2.ListInversionsRequest(
                filter_status=status if status else ""
            )
            resp = stub.ListInversions(req, timeout=5.0)

            inversions = []
            for inv in resp.inversions:
                inversions.append({
                    "job_id": inv.job_id,
                    "inversion_type": inv.inversion_type,
                    "status": inv.status,
                    "created_at": inv.created_at.ToDatetime().isoformat() if inv.created_at else None,
                    "progress": inv.progress
                })

            return {"inversions": inversions}
        except Exception as e:
            logger.error(f"Error listing inversions: {e}")
            # Fall through to mock

    # Mock response
    return {
        "inversions": [
            {
                "job_id": "inv_001",
                "inversion_type": "spherical_harmonics",
                "status": "completed",
                "created_at": datetime.utcnow().isoformat(),
                "progress": 1.0
            },
            {
                "job_id": "inv_002",
                "inversion_type": "mascons",
                "status": "running",
                "created_at": datetime.utcnow().isoformat(),
                "progress": 0.45
            }
        ]
    }

@app.delete("/api/v1/inversions/{job_id}")
async def cancel_inversion(job_id: str):
    """Cancel running inversion"""
    logger.info(f"Cancel inversion: {job_id}")

    stub = get_inversion_stub()
    if stub and GRPC_AVAILABLE:
        try:
            req = inversion_service_pb2.CancelInversionRequest(job_id=job_id)
            resp = stub.CancelInversion(req, timeout=5.0)

            return {
                "success": resp.success,
                "message": resp.message
            }
        except grpc.RpcError as e:
            logger.error(f"gRPC error: {e}")
            raise HTTPException(status_code=500, detail=str(e))
        except Exception as e:
            logger.error(f"Error cancelling inversion: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # Mock response
    return {
        "success": True,
        "message": f"Inversion {job_id} cancelled (mock)"
    }

# ============================================================================
# CONTROL SERVICE ENDPOINTS
# ============================================================================

@app.post("/api/v1/missions/plans")
async def create_mission_plan(request: MissionPlanRequest):
    """Create mission plan"""
    logger.info(f"Creating mission plan: {request.mission_name}")

    stub = get_control_stub()
    if stub and GRPC_AVAILABLE:
        try:
            # Parse timestamps if provided
            start_time = None
            end_time = None
            if request.start_time:
                start_time = Timestamp()
                start_time.FromDatetime(datetime.fromisoformat(request.start_time.replace('Z', '+00:00')))
            if request.end_time:
                end_time = Timestamp()
                end_time.FromDatetime(datetime.fromisoformat(request.end_time.replace('Z', '+00:00')))

            req = control_service_pb2.MissionPlanRequest(
                mission_name=request.mission_name,
                satellite_ids=request.satellite_ids,
                start_time=start_time,
                end_time=end_time,
                objectives=request.objectives
            )

            resp = stub.CreateMissionPlan(req, timeout=5.0)

            return {
                "plan_id": resp.plan_id,
                "status": resp.status,
                "message": resp.message
            }
        except grpc.RpcError as e:
            logger.error(f"gRPC error: {e}")
            raise HTTPException(status_code=500, detail=f"Control Service error: {e.details()}")
        except Exception as e:
            logger.error(f"Error creating mission plan: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # Mock response
    return {
        "plan_id": f"plan_{datetime.utcnow().timestamp()}",
        "status": "created",
        "message": f"Mission plan '{request.mission_name}' created (mock)"
    }

@app.get("/api/v1/missions/plans/{plan_id}")
async def get_mission_plan(plan_id: str):
    """Get mission plan details"""
    logger.info(f"Get mission plan: {plan_id}")

    stub = get_control_stub()
    if stub and GRPC_AVAILABLE:
        try:
            req = control_service_pb2.MissionPlanQuery(plan_id=plan_id)
            resp = stub.GetMissionPlan(req, timeout=5.0)

            return {
                "plan_id": resp.plan_id,
                "mission_name": resp.mission_name,
                "satellite_ids": list(resp.satellite_ids),
                "start_time": resp.start_time.ToDatetime().isoformat() if resp.start_time else None,
                "end_time": resp.end_time.ToDatetime().isoformat() if resp.end_time else None,
                "status": resp.status,
                "objectives": list(resp.objectives),
                "metadata": dict(resp.metadata) if resp.metadata else {}
            }
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.NOT_FOUND:
                raise HTTPException(status_code=404, detail="Mission plan not found")
            logger.error(f"gRPC error: {e}")
            raise HTTPException(status_code=500, detail=str(e))
        except Exception as e:
            logger.error(f"Error getting mission plan: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # Mock response
    raise HTTPException(status_code=404, detail="Mission plan not found (mock mode)")

@app.post("/api/v1/control/maneuver")
async def execute_maneuver(request: ManeuverRequest):
    """Execute satellite maneuver"""
    logger.info(f"Executing maneuver for {request.satellite_id}")

    stub = get_control_stub()
    if stub and GRPC_AVAILABLE:
        try:
            # Parse execution time if provided
            exec_time = None
            if request.execution_time:
                exec_time = Timestamp()
                exec_time.FromDatetime(datetime.fromisoformat(request.execution_time.replace('Z', '+00:00')))

            req = control_service_pb2.ManeuverRequest(
                satellite_id=request.satellite_id,
                maneuver_type=request.maneuver_type,
                delta_v=common_pb2.Vector3(
                    x=request.delta_v.x,
                    y=request.delta_v.y,
                    z=request.delta_v.z
                ),
                execution_time=exec_time
            )

            resp = stub.ExecuteManeuver(req, timeout=5.0)

            return {
                "success": resp.success,
                "message": resp.message,
                "data": dict(resp.data) if resp.data else {}
            }
        except grpc.RpcError as e:
            logger.error(f"gRPC error: {e}")
            raise HTTPException(status_code=500, detail=str(e))
        except Exception as e:
            logger.error(f"Error executing maneuver: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # Mock response
    return {
        "success": True,
        "message": f"Maneuver executed for {request.satellite_id} (mock)",
        "data": {
            "maneuver_id": f"mnv_{datetime.utcnow().timestamp()}",
            "delta_v_applied": f"{request.delta_v.x},{request.delta_v.y},{request.delta_v.z}"
        }
    }

@app.post("/api/v1/simulation/propagate")
async def propagate_orbit(request: PropagateRequest):
    """Propagate satellite orbit"""
    logger.info(f"Propagating orbit for {request.satellite_id}")

    stub = get_control_stub()
    if stub and GRPC_AVAILABLE:
        try:
            # Parse start time
            start_time = Timestamp()
            start_time.FromDatetime(datetime.fromisoformat(request.start_time.replace('Z', '+00:00')))

            # Build initial state if provided
            initial_state = None
            if request.initial_state:
                initial_state = control_service_pb2.OrbitState(
                    timestamp=start_time,
                    position=common_pb2.Vector3(
                        x=request.initial_state.position.x,
                        y=request.initial_state.position.y,
                        z=request.initial_state.position.z
                    ),
                    velocity=common_pb2.Vector3(
                        x=request.initial_state.velocity.x,
                        y=request.initial_state.velocity.y,
                        z=request.initial_state.velocity.z
                    )
                )

            req = control_service_pb2.PropagationRequest(
                satellite_id=request.satellite_id,
                start_time=start_time,
                duration=request.duration,
                timestep=request.timestep,
                initial_state=initial_state
            )

            resp = stub.PropagateOrbit(req, timeout=30.0)

            # Convert states
            states = []
            for state in resp.states:
                states.append({
                    "timestamp": state.timestamp.ToDatetime().isoformat(),
                    "position": {
                        "x": state.position.x,
                        "y": state.position.y,
                        "z": state.position.z
                    },
                    "velocity": {
                        "x": state.velocity.x,
                        "y": state.velocity.y,
                        "z": state.velocity.z
                    }
                })

            return {
                "satellite_id": resp.satellite_id,
                "states": states,
                "propagator_type": resp.propagator_type,
                "message": resp.message
            }
        except grpc.RpcError as e:
            logger.error(f"gRPC error: {e}")
            raise HTTPException(status_code=500, detail=str(e))
        except Exception as e:
            logger.error(f"Error propagating orbit: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # Mock response
    return {
        "satellite_id": request.satellite_id,
        "states": [
            {
                "timestamp": datetime.utcnow().isoformat(),
                "position": {"x": 6878000, "y": 0, "z": 0},
                "velocity": {"x": 0, "y": 7500, "z": 0}
            }
        ],
        "propagator_type": "keplerian",
        "message": "Orbit propagated (mock)"
    }

@app.post("/api/v1/simulation/mission")
async def simulate_mission(request: SimulateMissionRequest):
    """Simulate entire mission"""
    logger.info(f"Simulating mission: {request.mission_name}")

    stub = get_control_stub()
    if stub and GRPC_AVAILABLE:
        try:
            config = {
                "duration": str(request.duration),
                "timestep": str(request.timestep)
            }
            if request.plan_id:
                config["plan_id"] = request.plan_id

            req = control_service_pb2.SimulationRequest(
                mission_name=request.mission_name,
                config=config
            )

            resp = stub.SimulateMission(req, timeout=5.0)

            return {
                "job_id": resp.job_id,
                "status": resp.status,
                "message": resp.message,
                "estimated_time": resp.estimated_time
            }
        except grpc.RpcError as e:
            logger.error(f"gRPC error: {e}")
            raise HTTPException(status_code=500, detail=str(e))
        except Exception as e:
            logger.error(f"Error simulating mission: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # Mock response
    return {
        "job_id": f"sim_{datetime.utcnow().timestamp()}",
        "status": "running",
        "message": f"Simulation '{request.mission_name}' started (mock)",
        "estimated_time": 1800.0
    }

@app.get("/api/v1/simulation/{job_id}/status")
async def get_simulation_status(job_id: str):
    """Get simulation status"""
    logger.info(f"Get simulation status: {job_id}")

    stub = get_control_stub()
    if stub and GRPC_AVAILABLE:
        try:
            req = control_service_pb2.SimulationStatusRequest(job_id=job_id)
            resp = stub.GetSimulationStatus(req, timeout=5.0)

            return {
                "job_id": resp.job_id,
                "status": resp.status,
                "progress": resp.progress,
                "current_time": resp.current_time.ToDatetime().isoformat() if resp.current_time else None,
                "message": resp.message
            }
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.NOT_FOUND:
                raise HTTPException(status_code=404, detail="Simulation not found")
            logger.error(f"gRPC error: {e}")
            raise HTTPException(status_code=500, detail=str(e))
        except Exception as e:
            logger.error(f"Error getting simulation status: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # Mock response
    return {
        "job_id": job_id,
        "status": "running",
        "progress": 0.55,
        "current_time": datetime.utcnow().isoformat(),
        "message": "Simulation in progress (mock)"
    }

# ============================================================================
# LEGACY ENDPOINTS (kept for backwards compatibility)
# ============================================================================

@app.post("/api/plan")
async def create_plan_legacy(plan_data: dict):
    """Create mission plan (legacy endpoint)"""
    logger.info(f"Create plan (legacy): {plan_data}")
    return {
        "plan_id": f"plan_{datetime.utcnow().timestamp()}",
        "status": "created"
    }

@app.get("/ops/jobs")
async def list_jobs():
    """List operation jobs"""
    return {"jobs": []}

@app.post("/ops/jobs")
async def create_job(job: JobCreate):
    """Create a new operation job"""
    logger.info(f"Create job: {job.job_type}")
    return {
        "job_id": f"job_{datetime.utcnow().timestamp()}",
        "status": "created",
        "job_type": job.job_type
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
