from fastapi import FastAPI, Depends, HTTPException, status, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import os
import logging
from jose import JWTError, jwt
from passlib.context import CryptContext

from models import Base, get_db, User, ProcessingJob, AuditLog
from schemas import (
    UserCreate, UserResponse, Token, TokenData,
    JobCreate, JobResponse, JobStatus,
    PlanRequest, IngestRequest, ProcessRequest, CatalogRequest
)
from worker import (
    execute_plan_task, execute_ingest_task,
    execute_process_task, execute_catalog_task
)
from middleware import audit_log_middleware
from minio_client import get_minio_client
import uvicorn

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Security
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")

# JWT settings
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("JWT_SECRET_KEY environment variable must be set for security")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

# CORS origins - parse from comma-separated list
CORS_ORIGINS_STR = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:3001")
CORS_ORIGINS = [origin.strip() for origin in CORS_ORIGINS_STR.split(",") if origin.strip()]

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    logger.info("Starting Gravity Processing API...")
    
    # Initialize MinIO buckets
    minio_client = get_minio_client()
    buckets = ["raw-data", "processed-data", "products", "temp"]
    for bucket in buckets:
        try:
            if not minio_client.bucket_exists(bucket):
                minio_client.make_bucket(bucket)
                logger.info(f"Created MinIO bucket: {bucket}")
        except Exception as e:
            logger.error(f"Failed to create bucket {bucket}: {e}")
    
    yield
    
    logger.info("Shutting down Gravity Processing API...")

# Create FastAPI app
app = FastAPI(
    title="Gravity Processing API",
    description="Backend Operations for Satellite Gravity Data Processing",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,  # No eval() - security fix
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add custom audit logging middleware
app.middleware("http")(audit_log_middleware)

# Authentication functions
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme), db = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception
    
    user = db.query(User).filter(User.username == token_data.username).first()
    if user is None:
        raise credentials_exception
    return user

# Root endpoint
@app.get("/")
async def root():
    return {
        "message": "Gravity Processing API",
        "version": "1.0.0",
        "docs": "/docs",
        "endpoints": {
            "auth": "/auth",
            "plan": "/ops/plan",
            "ingest": "/ops/ingest",
            "process": "/ops/process",
            "catalog": "/ops/catalog",
            "jobs": "/ops/jobs"
        }
    }

# Authentication endpoints
@app.post("/auth/register", response_model=UserResponse)
async def register(user: UserCreate, db = Depends(get_db)):
    """Register a new user"""
    db_user = db.query(User).filter(
        (User.username == user.username) | (User.email == user.email)
    ).first()
    if db_user:
        raise HTTPException(
            status_code=400,
            detail="Username or email already registered"
        )
    
    hashed_password = get_password_hash(user.password)
    db_user = User(
        username=user.username,
        email=user.email,
        hashed_password=hashed_password
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

@app.post("/auth/token", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db = Depends(get_db)):
    """Login to get access token"""
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/auth/me", response_model=UserResponse)
async def read_users_me(current_user: User = Depends(get_current_user)):
    """Get current user info"""
    return current_user

# Processing endpoints
@app.post("/ops/plan", response_model=JobResponse)
async def create_plan(
    request: PlanRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db = Depends(get_db)
):
    """Create processing plan for satellite constellation"""
    job = ProcessingJob(
        job_type="plan",
        user_id=current_user.id,
        config=request.dict()
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    
    # Queue async task
    execute_plan_task.delay(str(job.id), request.dict())
    
    return job

@app.post("/ops/ingest", response_model=JobResponse)
async def ingest_data(
    request: IngestRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db = Depends(get_db)
):
    """Ingest raw satellite data"""
    job = ProcessingJob(
        job_type="ingest",
        user_id=current_user.id,
        config=request.dict()
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    
    # Queue async task
    execute_ingest_task.delay(str(job.id), request.dict())
    
    return job

@app.post("/ops/process", response_model=JobResponse)
async def process_data(
    request: ProcessRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db = Depends(get_db)
):
    """Process gravity field from satellite data"""
    job = ProcessingJob(
        job_type="process",
        user_id=current_user.id,
        config=request.dict()
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    
    # Queue async task
    execute_process_task.delay(str(job.id), request.dict())
    
    return job

@app.post("/ops/catalog", response_model=JobResponse)
async def catalog_products(
    request: CatalogRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db = Depends(get_db)
):
    """Catalog processed gravity products"""
    job = ProcessingJob(
        job_type="catalog",
        user_id=current_user.id,
        config=request.dict()
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    
    # Queue async task
    execute_catalog_task.delay(str(job.id), request.dict())
    
    return job

@app.get("/ops/jobs", response_model=List[JobResponse])
async def list_jobs(
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db = Depends(get_db)
):
    """List processing jobs"""
    query = db.query(ProcessingJob).filter(ProcessingJob.user_id == current_user.id)
    
    if status:
        query = query.filter(ProcessingJob.status == status)
    
    jobs = query.order_by(ProcessingJob.created_at.desc()).offset(skip).limit(limit).all()
    return jobs

@app.get("/ops/jobs/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db = Depends(get_db)
):
    """Get specific job details"""
    job = db.query(ProcessingJob).filter(
        ProcessingJob.id == job_id,
        ProcessingJob.user_id == current_user.id
    ).first()
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return job

@app.delete("/ops/jobs/{job_id}")
async def cancel_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db = Depends(get_db)
):
    """Cancel a processing job"""
    job = db.query(ProcessingJob).filter(
        ProcessingJob.id == job_id,
        ProcessingJob.user_id == current_user.id
    ).first()
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.status in ["completed", "failed"]:
        raise HTTPException(status_code=400, detail="Cannot cancel completed or failed job")
    
    job.status = "cancelled"
    db.commit()
    
    return {"message": "Job cancelled successfully"}

# Health check
@app.get("/health")
async def health_check(db = Depends(get_db)):
    """Health check endpoint"""
    try:
        # Check database
        db.execute("SELECT 1")
        
        # Check MinIO
        minio_client = get_minio_client()
        minio_client.list_buckets()
        
        return {
            "status": "healthy",
            "database": "connected",
            "storage": "connected",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unhealthy")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
