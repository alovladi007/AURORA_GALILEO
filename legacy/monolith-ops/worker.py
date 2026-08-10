from celery import Celery, Task
from celery.result import AsyncResult
import os
import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Any, List
import json
from sqlalchemy.orm import Session

from ops.models import SessionLocal, ProcessingJob, SatelliteObservation, GravityProduct, BaselineVector
from ops.minio_client import get_minio_client, upload_to_minio, download_from_minio

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Celery configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

celery_app = Celery(
    "gravity_worker",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["worker"]
)

# Celery config
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour
    task_soft_time_limit=3300,  # 55 minutes
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=100,
)

class DatabaseTask(Task):
    """Custom task class with database session management"""
    _db = None
    
    @property
    def db(self) -> Session:
        if self._db is None:
            self._db = SessionLocal()
        return self._db
    
    def after_return(self, status, retval, task_id, args, kwargs, einfo):
        if self._db is not None:
            self._db.close()
            self._db = None

# Helper functions
def update_job_status(db: Session, job_id: str, status: str, result: Dict = None, error: str = None):
    """Update job status in database"""
    job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
    if job:
        job.status = status
        if status == "running" and not job.started_at:
            job.started_at = datetime.utcnow()
        elif status in ["completed", "failed"]:
            job.completed_at = datetime.utcnow()
        if result:
            job.result = result
        if error:
            job.error_message = error
        db.commit()
    return job

def simulate_gravity_processing(config: Dict) -> np.ndarray:
    """Simulate gravity field processing (placeholder for real algorithms)"""
    degree_max = config.get("degree_max", 60)
    # Generate synthetic spherical harmonic coefficients
    n_coeffs = (degree_max + 1) ** 2
    coefficients = np.random.randn(n_coeffs) * 1e-9
    return coefficients

def generate_satellite_orbit(satellite_id: str, start_time: datetime, end_time: datetime, time_step: int) -> List[Dict]:
    """Generate simulated satellite orbit data"""
    observations = []
    current_time = start_time
    
    while current_time <= end_time:
        # Simulate satellite position (simplified circular orbit)
        t = (current_time - start_time).total_seconds()
        orbit_period = 5400  # 90 minutes
        angle = 2 * np.pi * t / orbit_period
        
        lat = 70 * np.sin(angle + np.random.randn() * 0.01)  # Inclination ~70 degrees
        lon = (t * 360 / 86400) % 360 - 180  # Earth rotation
        alt = 450 + 10 * np.sin(angle * 2) + np.random.randn() * 0.5  # ~450 km altitude
        
        # Simulate gravity measurement
        gravity_value = 9.8 + np.random.randn() * 1e-6
        gravity_uncertainty = 1e-7
        
        observations.append({
            "time": current_time.isoformat(),
            "satellite_id": satellite_id,
            "latitude": lat,
            "longitude": lon,
            "altitude": alt,
            "gravity_value": gravity_value,
            "gravity_uncertainty": gravity_uncertainty,
            "metadata": {
                "quality_flag": "good",
                "temperature": 20 + np.random.randn()
            }
        })
        
        current_time += timedelta(seconds=time_step)
    
    return observations

# Celery tasks
@celery_app.task(base=DatabaseTask, bind=True, name="worker.execute_plan_task")
def execute_plan_task(self, job_id: str, config: Dict[str, Any]):
    """Execute planning task"""
    try:
        logger.info(f"Starting plan task for job {job_id}")
        update_job_status(self.db, job_id, "running")
        
        # Extract configuration
        start_time = datetime.fromisoformat(config["start_time"].replace("Z", "+00:00"))
        end_time = datetime.fromisoformat(config["end_time"].replace("Z", "+00:00"))
        satellites = config["satellites"]
        time_step = config.get("time_step", 60)
        
        # Generate processing plan
        plan = {
            "mission_duration": (end_time - start_time).days,
            "total_observations": len(satellites) * ((end_time - start_time).total_seconds() / time_step),
            "satellites": satellites,
            "processing_stages": [
                {"stage": "ingest", "estimated_time": "10 minutes"},
                {"stage": "calibration", "estimated_time": "15 minutes"},
                {"stage": "gravity_field_estimation", "estimated_time": "30 minutes"},
                {"stage": "product_generation", "estimated_time": "5 minutes"}
            ],
            "resource_requirements": {
                "cpu_cores": 16,
                "memory_gb": 64,
                "storage_gb": 100
            },
            "output_products": {
                "spherical_harmonics": f"degree {config.get('degree_max', 60)}",
                "gravity_grids": "0.5° resolution",
                "uncertainty_maps": "included"
            }
        }
        
        # Store plan in MinIO
        minio_client = get_minio_client()
        plan_key = f"plans/{job_id}/plan.json"
        upload_to_minio(
            minio_client,
            "products",
            plan_key,
            json.dumps(plan, indent=2).encode()
        )
        
        result = {
            "status": "success",
            "plan_location": f"s3://products/{plan_key}",
            "summary": plan
        }
        
        update_job_status(self.db, job_id, "completed", result)
        logger.info(f"Plan task completed for job {job_id}")
        
        return result
        
    except Exception as e:
        logger.error(f"Plan task failed for job {job_id}: {str(e)}")
        update_job_status(self.db, job_id, "failed", error=str(e))
        raise

@celery_app.task(base=DatabaseTask, bind=True, name="worker.execute_ingest_task")
def execute_ingest_task(self, job_id: str, config: Dict[str, Any]):
    """Execute data ingestion task"""
    try:
        logger.info(f"Starting ingest task for job {job_id}")
        update_job_status(self.db, job_id, "running")
        
        # Extract configuration
        start_time = datetime.fromisoformat(config["start_time"].replace("Z", "+00:00"))
        end_time = datetime.fromisoformat(config["end_time"].replace("Z", "+00:00"))
        satellites = config["satellites"]
        
        # Simulate data ingestion
        minio_client = get_minio_client()
        ingested_files = []
        total_observations = 0
        
        for satellite in satellites:
            # Generate simulated observations
            observations = generate_satellite_orbit(satellite, start_time, end_time, 60)
            
            # Store in database
            for obs in observations:
                db_obs = SatelliteObservation(
                    time=datetime.fromisoformat(obs["time"]),
                    satellite_id=obs["satellite_id"],
                    latitude=obs["latitude"],
                    longitude=obs["longitude"],
                    altitude=obs["altitude"],
                    gravity_value=obs["gravity_value"],
                    gravity_uncertainty=obs["gravity_uncertainty"],
                    metadata=obs["metadata"],
                    job_id=job_id
                )
                self.db.add(db_obs)
                total_observations += 1
            
            # Store raw data in MinIO
            raw_key = f"raw-data/{job_id}/{satellite}_raw.json"
            upload_to_minio(
                minio_client,
                "raw-data",
                raw_key,
                json.dumps(observations, indent=2).encode()
            )
            ingested_files.append(f"s3://raw-data/{raw_key}")
        
        self.db.commit()
        
        result = {
            "status": "success",
            "total_observations": total_observations,
            "satellites_processed": len(satellites),
            "ingested_files": ingested_files,
            "time_range": {
                "start": start_time.isoformat(),
                "end": end_time.isoformat()
            }
        }
        
        update_job_status(self.db, job_id, "completed", result)
        logger.info(f"Ingest task completed for job {job_id}")
        
        return result
        
    except Exception as e:
        logger.error(f"Ingest task failed for job {job_id}: {str(e)}")
        update_job_status(self.db, job_id, "failed", error=str(e))
        raise

@celery_app.task(base=DatabaseTask, bind=True, name="worker.execute_process_task")
def execute_process_task(self, job_id: str, config: Dict[str, Any]):
    """Execute gravity field processing task"""
    try:
        logger.info(f"Starting process task for job {job_id}")
        update_job_status(self.db, job_id, "running")
        
        # Simulate gravity field computation
        algorithm = config.get("algorithm", "variational")
        degree_max = config.get("degree_max", 60)
        
        # Generate synthetic gravity field solution
        coefficients = simulate_gravity_processing(config)
        
        # Generate gravity grid
        lats = np.linspace(-90, 90, 361)
        lons = np.linspace(-180, 180, 721)
        grid = np.random.randn(len(lats), len(lons)) * 1e-5 + 9.8
        
        # Generate uncertainty estimates
        uncertainties = np.abs(np.random.randn(len(lats), len(lons)) * 1e-6)
        
        # Store products in MinIO
        minio_client = get_minio_client()
        product_keys = []
        
        # Store spherical harmonic coefficients
        coeff_key = f"products/{job_id}/coefficients.npy"
        upload_to_minio(
            minio_client,
            "processed-data",
            coeff_key,
            coefficients.tobytes()
        )
        product_keys.append(f"s3://processed-data/{coeff_key}")
        
        # Store gravity grid
        grid_key = f"products/{job_id}/gravity_grid.npy"
        upload_to_minio(
            minio_client,
            "processed-data",
            grid_key,
            grid.tobytes()
        )
        product_keys.append(f"s3://processed-data/{grid_key}")
        
        # Store uncertainty grid
        unc_key = f"products/{job_id}/uncertainty_grid.npy"
        upload_to_minio(
            minio_client,
            "processed-data",
            unc_key,
            uncertainties.tobytes()
        )
        product_keys.append(f"s3://processed-data/{unc_key}")
        
        # Create database record for product
        product = GravityProduct(
            product_type="spherical_harmonic",
            version="v1.0",
            time_start=datetime.utcnow() - timedelta(days=30),
            time_end=datetime.utcnow(),
            degree_max=degree_max,
            spatial_resolution=0.5,
            s3_path=f"s3://processed-data/products/{job_id}/",
            metadata={
                "algorithm": algorithm,
                "regularization": config.get("regularization", {}),
                "processing_date": datetime.utcnow().isoformat()
            },
            job_id=job_id
        )
        self.db.add(product)
        self.db.commit()
        
        result = {
            "status": "success",
            "product_id": str(product.id),
            "algorithm": algorithm,
            "degree_max": degree_max,
            "products": product_keys,
            "statistics": {
                "mean_gravity": float(np.mean(grid)),
                "std_gravity": float(np.std(grid)),
                "mean_uncertainty": float(np.mean(uncertainties))
            }
        }
        
        update_job_status(self.db, job_id, "completed", result)
        logger.info(f"Process task completed for job {job_id}")
        
        return result
        
    except Exception as e:
        logger.error(f"Process task failed for job {job_id}: {str(e)}")
        update_job_status(self.db, job_id, "failed", error=str(e))
        raise

@celery_app.task(base=DatabaseTask, bind=True, name="worker.execute_catalog_task")
def execute_catalog_task(self, job_id: str, config: Dict[str, Any]):
    """Execute cataloging task"""
    try:
        logger.info(f"Starting catalog task for job {job_id}")
        update_job_status(self.db, job_id, "running")
        
        product_ids = config.get("product_ids", [])
        metadata = config.get("metadata", {})
        publish = config.get("publish", False)
        archive = config.get("archive", True)
        
        # Process each product
        cataloged_products = []
        for product_id in product_ids:
            product = self.db.query(GravityProduct).filter(
                GravityProduct.id == product_id
            ).first()
            
            if product:
                # Update metadata
                if product.metadata:
                    product.metadata.update(metadata)
                else:
                    product.metadata = metadata
                
                # Archive to long-term storage if requested
                if archive:
                    minio_client = get_minio_client()
                    archive_key = f"archive/{product_id}/product.json"
                    product_data = {
                        "id": str(product.id),
                        "type": product.product_type,
                        "version": product.version,
                        "metadata": product.metadata
                    }
                    upload_to_minio(
                        minio_client,
                        "products",
                        archive_key,
                        json.dumps(product_data, indent=2).encode()
                    )
                
                cataloged_products.append({
                    "id": str(product.id),
                    "type": product.product_type,
                    "archived": archive,
                    "published": publish
                })
        
        self.db.commit()
        
        result = {
            "status": "success",
            "products_cataloged": len(cataloged_products),
            "products": cataloged_products,
            "metadata_applied": metadata,
            "archived": archive,
            "published": publish
        }
        
        update_job_status(self.db, job_id, "completed", result)
        logger.info(f"Catalog task completed for job {job_id}")
        
        return result
        
    except Exception as e:
        logger.error(f"Catalog task failed for job {job_id}: {str(e)}")
        update_job_status(self.db, job_id, "failed", error=str(e))
        raise
