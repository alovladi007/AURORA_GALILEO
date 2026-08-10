from pydantic import BaseModel, EmailStr, Field, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID

# User schemas
class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=255)
    email: EmailStr
    password: str = Field(..., min_length=6)

class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    username: str
    email: str
    is_active: bool
    is_superuser: bool
    created_at: datetime
    updated_at: datetime

# Authentication schemas
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

# Job schemas
class JobStatus(BaseModel):
    pending: str = "pending"
    running: str = "running"
    completed: str = "completed"
    failed: str = "failed"
    cancelled: str = "cancelled"

class JobCreate(BaseModel):
    job_type: str
    config: Dict[str, Any]

class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    job_type: str
    status: str
    user_id: UUID
    config: Optional[Dict[str, Any]] = None
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    updated_at: datetime

# Processing request schemas
class PlanRequest(BaseModel):
    """Planning request for satellite constellation"""
    start_time: datetime
    end_time: datetime
    satellites: List[str] = Field(..., min_length=1, description="List of satellite IDs")
    time_step: int = Field(60, ge=1, le=3600, description="Time step in seconds")
    processing_mode: str = Field("standard", pattern="^(standard|quick|full)$")
    output_format: str = Field("spherical_harmonic", pattern="^(spherical_harmonic|grid|mascon)$")
    degree_max: int = Field(60, ge=2, le=360)
    
    class Config:
        json_schema_extra = {
            "example": {
                "start_time": "2025-01-01T00:00:00Z",
                "end_time": "2025-01-31T23:59:59Z",
                "satellites": ["GRACE-A", "GRACE-B"],
                "time_step": 60,
                "processing_mode": "standard",
                "output_format": "spherical_harmonic",
                "degree_max": 60
            }
        }

class IngestRequest(BaseModel):
    """Data ingestion request"""
    data_source: str = Field(..., description="Data source URL or path")
    data_type: str = Field(..., pattern="^(l1b|l2|auxiliary)$")
    satellites: List[str]
    start_time: datetime
    end_time: datetime
    validate_data: bool = Field(True, description="Validate data integrity")
    
    class Config:
        json_schema_extra = {
            "example": {
                "data_source": "s3://gravity-data/raw/2025-01/",
                "data_type": "l1b",
                "satellites": ["GRACE-A", "GRACE-B"],
                "start_time": "2025-01-01T00:00:00Z",
                "end_time": "2025-01-31T23:59:59Z",
                "validate_data": True
            }
        }

class ProcessRequest(BaseModel):
    """Processing request for gravity field computation"""
    job_id: Optional[UUID] = Field(None, description="Reference to planning job")
    algorithm: str = Field("variational", pattern="^(variational|spherical_harmonic|mascon)$")
    degree_max: int = Field(60, ge=2, le=360)
    regularization: Dict[str, float] = Field(
        default_factory=lambda: {"kaula": 1e-5, "tikhonov": 0.0}
    )
    constraints: Optional[Dict[str, Any]] = None
    output_products: List[str] = Field(
        default_factory=lambda: ["coefficients", "grids", "uncertainties"]
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "algorithm": "variational",
                "degree_max": 60,
                "regularization": {
                    "kaula": 1e-5,
                    "tikhonov": 0.0
                },
                "output_products": ["coefficients", "grids", "uncertainties"]
            }
        }

class CatalogRequest(BaseModel):
    """Cataloging request for processed products"""
    product_ids: List[UUID] = Field(..., min_length=1)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    publish: bool = Field(False, description="Publish to public catalog")
    archive: bool = Field(True, description="Archive to long-term storage")
    
    class Config:
        json_schema_extra = {
            "example": {
                "product_ids": ["550e8400-e29b-41d4-a716-446655440000"],
                "metadata": {
                    "mission": "GRACE-FO",
                    "processing_center": "CSR",
                    "version": "RL06.1"
                },
                "publish": False,
                "archive": True
            }
        }

# Observation schemas
class SatelliteObservationCreate(BaseModel):
    time: datetime
    satellite_id: str
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    altitude: float = Field(..., ge=0)
    gravity_value: Optional[float] = None
    gravity_uncertainty: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None

class SatelliteObservationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    time: datetime
    satellite_id: str
    latitude: float
    longitude: float
    altitude: float
    gravity_value: Optional[float]
    gravity_uncertainty: Optional[float]
    metadata: Optional[Dict[str, Any]]
    job_id: Optional[UUID]

# Product schemas
class GravityProductCreate(BaseModel):
    product_type: str
    version: str
    time_start: datetime
    time_end: datetime
    degree_max: Optional[int] = None
    spatial_resolution: Optional[float] = None
    s3_path: str
    metadata: Optional[Dict[str, Any]] = None

class GravityProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    product_type: str
    version: str
    time_start: datetime
    time_end: datetime
    degree_max: Optional[int]
    spatial_resolution: Optional[float]
    s3_path: str
    metadata: Optional[Dict[str, Any]]
    job_id: Optional[UUID]
    created_at: datetime

# Baseline vector schemas
class BaselineVectorCreate(BaseModel):
    time: datetime
    satellite_1: str
    satellite_2: str
    range_rate: Optional[float] = None
    range_acceleration: Optional[float] = None
    baseline_length: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None

class BaselineVectorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    time: datetime
    satellite_1: str
    satellite_2: str
    range_rate: Optional[float]
    range_acceleration: Optional[float]
    baseline_length: Optional[float]
    metadata: Optional[Dict[str, Any]]
    job_id: Optional[UUID]

# Audit log schemas
class AuditLogCreate(BaseModel):
    action: str
    resource_type: Optional[str] = None
    resource_id: Optional[UUID] = None
    details: Optional[Dict[str, Any]] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None

class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    timestamp: datetime
    user_id: Optional[UUID]
    action: str
    resource_type: Optional[str]
    resource_id: Optional[UUID]
    details: Optional[Dict[str, Any]]
    ip_address: Optional[str]
    user_agent: Optional[str]
