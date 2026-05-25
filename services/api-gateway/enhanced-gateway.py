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
    # Import Data Service protos (generated in /app/gen or ../data-service/src/gen for local)
    try:
        import data_service_pb2
        import data_service_pb2_grpc
        import common_pb2
    except ImportError:
        # Try local development path
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../data-service/src/gen'))
        import data_service_pb2
        import data_service_pb2_grpc
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

# gRPC connection
DATA_SERVICE_ADDR = "localhost:50051"
data_stub = None

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
    """Health check with Data Service connectivity"""
    services_status = {}

    if GRPC_AVAILABLE:
        stub = get_data_stub()
        if stub:
            try:
                # Try health check
                req = common_pb2.HealthCheckRequest()
                resp = stub.HealthCheck(req, timeout=2.0)
                services_status["data_service"] = "healthy"
            except Exception as e:
                services_status["data_service"] = f"unhealthy: {str(e)}"
        else:
            services_status["data_service"] = "disconnected"
    else:
        services_status["data_service"] = "mock_mode"

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

# ML endpoints
@app.get("/api/v1/models")
async def list_models():
    """List ML models"""
    return {
        "models": [
            {
                "model_id": "pinn_001",
                "model_type": "pinn",
                "status": "trained",
                "created_at": datetime.utcnow().isoformat()
            }
        ]
    }

@app.post("/api/v1/models/train")
async def train_model(model_data: dict):
    """Train ML model"""
    logger.info(f"Train model: {model_data}")
    return {
        "job_id": f"train_{datetime.utcnow().timestamp()}",
        "status": "started"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=18000)
