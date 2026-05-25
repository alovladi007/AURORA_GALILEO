"""
Minimal API Gateway for GALILEO
Connects frontend to Data Service
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import grpc
from datetime import datetime
import logging

# Import generated proto (we'll need to generate these)
# For now, create mock responses

app = FastAPI(title="GALILEO API Gateway")

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:13003"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@app.get("/")
async def root():
    return {
        "service": "GALILEO API Gateway",
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/health")
async def health():
    """Health check"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {
            "data_service": "connected"  # TODO: Actually check
        }
    }


# Telemetry endpoints
@app.post("/api/v1/data/telemetry")
async def ingest_telemetry(data: dict):
    """Ingest telemetry data"""
    logger.info(f"Ingest telemetry: {data}")

    # TODO: Connect to Data Service via gRPC
    # For now, return success
    return {
        "success": True,
        "message": "Telemetry ingested",
        "record_id": "mock_001"
    }


@app.get("/api/v1/data/telemetry")
async def query_telemetry(
    satellite_ids: str = None,
    start_time: str = None,
    end_time: str = None,
    limit: int = 100
):
    """Query telemetry data"""
    logger.info(f"Query telemetry: satellite_ids={satellite_ids}")

    # Mock data for now
    return {
        "telemetry": [
            {
                "satellite_id": "SAT-001",
                "timestamp": datetime.utcnow().isoformat(),
                "location": {
                    "latitude": 45.5,
                    "longitude": -122.6,
                    "altitude": 550000
                },
                "velocity_x": 7500.0,
                "velocity_y": 0.0,
                "velocity_z": 0.0,
                "temperature": 15.0,
                "battery_level": 85.0
            }
        ],
        "pagination": {
            "total": 1,
            "offset": 0,
            "limit": limit
        }
    }


# Gravity measurement endpoints
@app.get("/api/v1/data/gravity")
async def query_gravity(
    satellite_ids: str = None,
    start_time: str = None,
    end_time: str = None,
    limit: int = 100
):
    """Query gravity measurements"""
    logger.info(f"Query gravity: satellite_ids={satellite_ids}")

    # Mock data
    return {
        "measurements": [
            {
                "satellite_id": "SAT-001",
                "timestamp": datetime.utcnow().isoformat(),
                "location": {
                    "latitude": 45.5,
                    "longitude": -122.6,
                    "altitude": 550000
                },
                "gravity_x": -0.05,
                "gravity_y": 0.02,
                "gravity_z": -9.81,
                "magnitude": 9.81,
                "accuracy": 0.001,
                "quality_flag": 1
            }
        ],
        "pagination": {
            "total": 1,
            "offset": 0,
            "limit": limit
        }
    }


# ML endpoints
@app.get("/api/v1/models")
async def list_models():
    """List ML models"""
    return {
        "models": [
            {
                "model_id": "model_001",
                "model_type": "pinn",
                "status": "trained",
                "created_at": datetime.utcnow().isoformat()
            }
        ]
    }


# Operations endpoints
@app.get("/ops/jobs")
async def list_jobs():
    """List operation jobs"""
    return {
        "jobs": []
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=18000)
