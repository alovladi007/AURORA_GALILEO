"""
Database Persistence Service for GeoSense Platform API

Provides unified database persistence across all services:
- User management and authentication
- Processing job tracking
- Satellite observations storage
- Gravity product cataloging
- Baseline vector time series
- Audit log querying

This service integrates SQLAlchemy models from ops/ with the main API layer.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from typing import Dict, List, Optional, Any
from datetime import datetime
from uuid import UUID
import logging

# Import database models from ops
try:
    from ops.models import (
        Base, get_db, engine,
        User, ProcessingJob, SatelliteObservation,
        GravityProduct, BaselineVector, AuditLog
    )
    DB_IMPORTS_AVAILABLE = True
except ImportError as e:
    DB_IMPORTS_AVAILABLE = False
    print(f"Database imports not available: {e}")

logger = logging.getLogger(__name__)


class DatabaseService:
    """
    Service for database persistence operations.

    Provides high-level CRUD operations for all models,
    with session management and error handling.
    """

    def __init__(self):
        """Initialize database service."""
        if not DB_IMPORTS_AVAILABLE:
            print("Warning: Database infrastructure not available.")
            return

        # Initialize database tables
        try:
            Base.metadata.create_all(bind=engine)
            logger.info("Database tables initialized")
        except Exception as e:
            logger.error(f"Failed to initialize database tables: {e}")

    # =================================================================
    # User Management
    # =================================================================

    def create_user(
        self,
        username: str,
        email: str,
        hashed_password: str,
        is_superuser: bool = False
    ) -> Dict[str, Any]:
        """
        Create new user account.

        Args:
            username: Unique username
            email: User email
            hashed_password: Pre-hashed password
            is_superuser: Admin privileges

        Returns:
            Created user details
        """
        if not DB_IMPORTS_AVAILABLE:
            raise RuntimeError("Database not available")

        db = next(get_db())
        try:
            user = User(
                username=username,
                email=email,
                hashed_password=hashed_password,
                is_superuser=is_superuser
            )
            db.add(user)
            db.commit()
            db.refresh(user)

            return self._user_to_dict(user)
        except Exception as e:
            db.rollback()
            raise RuntimeError(f"Failed to create user: {e}")
        finally:
            db.close()

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Get user by username."""
        if not DB_IMPORTS_AVAILABLE:
            raise RuntimeError("Database not available")

        db = next(get_db())
        try:
            user = db.query(User).filter(User.username == username).first()
            return self._user_to_dict(user) if user else None
        finally:
            db.close()

    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user by ID."""
        if not DB_IMPORTS_AVAILABLE:
            raise RuntimeError("Database not available")

        db = next(get_db())
        try:
            user = db.query(User).filter(User.id == UUID(user_id)).first()
            return self._user_to_dict(user) if user else None
        finally:
            db.close()

    def list_users(
        self,
        active_only: bool = True,
        limit: int = 100
    ) -> Dict[str, Any]:
        """List all users."""
        if not DB_IMPORTS_AVAILABLE:
            raise RuntimeError("Database not available")

        db = next(get_db())
        try:
            query = db.query(User)
            if active_only:
                query = query.filter(User.is_active == True)

            users = query.limit(limit).all()

            return {
                'users': [self._user_to_dict(u) for u in users],
                'count': len(users)
            }
        finally:
            db.close()

    def _user_to_dict(self, user: User) -> Dict[str, Any]:
        """Convert User model to dictionary."""
        return {
            'id': str(user.id),
            'username': user.username,
            'email': user.email,
            'is_active': user.is_active,
            'is_superuser': user.is_superuser,
            'created_at': user.created_at.isoformat(),
            'updated_at': user.updated_at.isoformat()
        }

    # =================================================================
    # Processing Jobs
    # =================================================================

    def create_job(
        self,
        job_type: str,
        user_id: str,
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create processing job record.

        Args:
            job_type: Type of processing job
            user_id: User who created job
            config: Job configuration

        Returns:
            Created job details
        """
        if not DB_IMPORTS_AVAILABLE:
            raise RuntimeError("Database not available")

        db = next(get_db())
        try:
            job = ProcessingJob(
                job_type=job_type,
                user_id=UUID(user_id),
                config=config
            )
            db.add(job)
            db.commit()
            db.refresh(job)

            return self._job_to_dict(job)
        except Exception as e:
            db.rollback()
            raise RuntimeError(f"Failed to create job: {e}")
        finally:
            db.close()

    def update_job_status(
        self,
        job_id: str,
        status: str,
        result: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update job status and result."""
        if not DB_IMPORTS_AVAILABLE:
            raise RuntimeError("Database not available")

        db = next(get_db())
        try:
            job = db.query(ProcessingJob).filter(ProcessingJob.id == UUID(job_id)).first()
            if not job:
                raise ValueError(f"Job not found: {job_id}")

            job.status = status
            if result:
                job.result = result
            if error_message:
                job.error_message = error_message

            if status == 'running' and not job.started_at:
                job.started_at = datetime.utcnow()
            elif status in ['completed', 'failed', 'cancelled']:
                job.completed_at = datetime.utcnow()

            db.commit()
            db.refresh(job)

            return self._job_to_dict(job)
        except Exception as e:
            db.rollback()
            raise RuntimeError(f"Failed to update job: {e}")
        finally:
            db.close()

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job by ID."""
        if not DB_IMPORTS_AVAILABLE:
            raise RuntimeError("Database not available")

        db = next(get_db())
        try:
            job = db.query(ProcessingJob).filter(ProcessingJob.id == UUID(job_id)).first()
            return self._job_to_dict(job) if job else None
        finally:
            db.close()

    def list_jobs(
        self,
        user_id: Optional[str] = None,
        status: Optional[str] = None,
        job_type: Optional[str] = None,
        limit: int = 100
    ) -> Dict[str, Any]:
        """List processing jobs with filters."""
        if not DB_IMPORTS_AVAILABLE:
            raise RuntimeError("Database not available")

        db = next(get_db())
        try:
            query = db.query(ProcessingJob)

            if user_id:
                query = query.filter(ProcessingJob.user_id == UUID(user_id))
            if status:
                query = query.filter(ProcessingJob.status == status)
            if job_type:
                query = query.filter(ProcessingJob.job_type == job_type)

            jobs = query.order_by(ProcessingJob.created_at.desc()).limit(limit).all()

            return {
                'jobs': [self._job_to_dict(j) for j in jobs],
                'count': len(jobs)
            }
        finally:
            db.close()

    def _job_to_dict(self, job: ProcessingJob) -> Dict[str, Any]:
        """Convert ProcessingJob model to dictionary."""
        return {
            'id': str(job.id),
            'job_type': job.job_type,
            'status': job.status,
            'user_id': str(job.user_id),
            'config': job.config,
            'result': job.result,
            'error_message': job.error_message,
            'created_at': job.created_at.isoformat(),
            'started_at': job.started_at.isoformat() if job.started_at else None,
            'completed_at': job.completed_at.isoformat() if job.completed_at else None,
            'updated_at': job.updated_at.isoformat()
        }

    # =================================================================
    # Satellite Observations
    # =================================================================

    def create_observation(
        self,
        time: datetime,
        satellite_id: str,
        latitude: float,
        longitude: float,
        altitude: float,
        gravity_value: Optional[float] = None,
        gravity_uncertainty: Optional[float] = None,
        job_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create satellite observation record."""
        if not DB_IMPORTS_AVAILABLE:
            raise RuntimeError("Database not available")

        db = next(get_db())
        try:
            obs = SatelliteObservation(
                time=time,
                satellite_id=satellite_id,
                latitude=latitude,
                longitude=longitude,
                altitude=altitude,
                gravity_value=gravity_value,
                gravity_uncertainty=gravity_uncertainty,
                job_id=UUID(job_id) if job_id else None,
                metadata=metadata or {}
            )
            db.add(obs)
            db.commit()
            db.refresh(obs)

            return self._observation_to_dict(obs)
        except Exception as e:
            db.rollback()
            raise RuntimeError(f"Failed to create observation: {e}")
        finally:
            db.close()

    def bulk_create_observations(
        self,
        observations: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Bulk create observations for efficiency."""
        if not DB_IMPORTS_AVAILABLE:
            raise RuntimeError("Database not available")

        db = next(get_db())
        try:
            obs_objects = []
            for obs_data in observations:
                obs = SatelliteObservation(**obs_data)
                obs_objects.append(obs)

            db.bulk_save_objects(obs_objects)
            db.commit()

            return {
                'created': len(obs_objects),
                'message': f'Created {len(obs_objects)} observations'
            }
        except Exception as e:
            db.rollback()
            raise RuntimeError(f"Failed to bulk create observations: {e}")
        finally:
            db.close()

    def query_observations(
        self,
        satellite_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        job_id: Optional[str] = None,
        limit: int = 1000
    ) -> Dict[str, Any]:
        """Query satellite observations."""
        if not DB_IMPORTS_AVAILABLE:
            raise RuntimeError("Database not available")

        db = next(get_db())
        try:
            query = db.query(SatelliteObservation)

            if satellite_id:
                query = query.filter(SatelliteObservation.satellite_id == satellite_id)
            if start_time:
                query = query.filter(SatelliteObservation.time >= start_time)
            if end_time:
                query = query.filter(SatelliteObservation.time <= end_time)
            if job_id:
                query = query.filter(SatelliteObservation.job_id == UUID(job_id))

            observations = query.order_by(SatelliteObservation.time).limit(limit).all()

            return {
                'observations': [self._observation_to_dict(o) for o in observations],
                'count': len(observations)
            }
        finally:
            db.close()

    def _observation_to_dict(self, obs: SatelliteObservation) -> Dict[str, Any]:
        """Convert SatelliteObservation model to dictionary."""
        return {
            'time': obs.time.isoformat(),
            'satellite_id': obs.satellite_id,
            'latitude': obs.latitude,
            'longitude': obs.longitude,
            'altitude': obs.altitude,
            'gravity_value': obs.gravity_value,
            'gravity_uncertainty': obs.gravity_uncertainty,
            'job_id': str(obs.job_id) if obs.job_id else None,
            'metadata': obs.metadata
        }

    # =================================================================
    # Gravity Products
    # =================================================================

    def create_product(
        self,
        product_type: str,
        version: str,
        time_start: datetime,
        time_end: datetime,
        s3_path: str,
        degree_max: Optional[int] = None,
        spatial_resolution: Optional[float] = None,
        job_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create gravity product record."""
        if not DB_IMPORTS_AVAILABLE:
            raise RuntimeError("Database not available")

        db = next(get_db())
        try:
            product = GravityProduct(
                product_type=product_type,
                version=version,
                time_start=time_start,
                time_end=time_end,
                s3_path=s3_path,
                degree_max=degree_max,
                spatial_resolution=spatial_resolution,
                job_id=UUID(job_id) if job_id else None,
                metadata=metadata or {}
            )
            db.add(product)
            db.commit()
            db.refresh(product)

            return self._product_to_dict(product)
        except Exception as e:
            db.rollback()
            raise RuntimeError(f"Failed to create product: {e}")
        finally:
            db.close()

    def query_products(
        self,
        product_type: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        job_id: Optional[str] = None,
        limit: int = 100
    ) -> Dict[str, Any]:
        """Query gravity products."""
        if not DB_IMPORTS_AVAILABLE:
            raise RuntimeError("Database not available")

        db = next(get_db())
        try:
            query = db.query(GravityProduct)

            if product_type:
                query = query.filter(GravityProduct.product_type == product_type)
            if start_time:
                query = query.filter(GravityProduct.time_start >= start_time)
            if end_time:
                query = query.filter(GravityProduct.time_end <= end_time)
            if job_id:
                query = query.filter(GravityProduct.job_id == UUID(job_id))

            products = query.order_by(GravityProduct.created_at.desc()).limit(limit).all()

            return {
                'products': [self._product_to_dict(p) for p in products],
                'count': len(products)
            }
        finally:
            db.close()

    def _product_to_dict(self, product: GravityProduct) -> Dict[str, Any]:
        """Convert GravityProduct model to dictionary."""
        return {
            'id': str(product.id),
            'product_type': product.product_type,
            'version': product.version,
            'time_start': product.time_start.isoformat(),
            'time_end': product.time_end.isoformat(),
            'degree_max': product.degree_max,
            'spatial_resolution': product.spatial_resolution,
            's3_path': product.s3_path,
            'job_id': str(product.job_id) if product.job_id else None,
            'metadata': product.metadata,
            'created_at': product.created_at.isoformat()
        }

    # =================================================================
    # Baseline Vectors
    # =================================================================

    def create_baseline_vector(
        self,
        time: datetime,
        satellite_1: str,
        satellite_2: str,
        range_rate: Optional[float] = None,
        range_acceleration: Optional[float] = None,
        baseline_length: Optional[float] = None,
        job_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create baseline vector record."""
        if not DB_IMPORTS_AVAILABLE:
            raise RuntimeError("Database not available")

        db = next(get_db())
        try:
            baseline = BaselineVector(
                time=time,
                satellite_1=satellite_1,
                satellite_2=satellite_2,
                range_rate=range_rate,
                range_acceleration=range_acceleration,
                baseline_length=baseline_length,
                job_id=UUID(job_id) if job_id else None,
                metadata=metadata or {}
            )
            db.add(baseline)
            db.commit()
            db.refresh(baseline)

            return self._baseline_to_dict(baseline)
        except Exception as e:
            db.rollback()
            raise RuntimeError(f"Failed to create baseline vector: {e}")
        finally:
            db.close()

    def bulk_create_baseline_vectors(
        self,
        baseline_vectors: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Bulk create baseline vectors."""
        if not DB_IMPORTS_AVAILABLE:
            raise RuntimeError("Database not available")

        db = next(get_db())
        try:
            baseline_objects = []
            for bv_data in baseline_vectors:
                bv = BaselineVector(**bv_data)
                baseline_objects.append(bv)

            db.bulk_save_objects(baseline_objects)
            db.commit()

            return {
                'created': len(baseline_objects),
                'message': f'Created {len(baseline_objects)} baseline vectors'
            }
        except Exception as e:
            db.rollback()
            raise RuntimeError(f"Failed to bulk create baseline vectors: {e}")
        finally:
            db.close()

    def query_baseline_vectors(
        self,
        satellite_1: Optional[str] = None,
        satellite_2: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        job_id: Optional[str] = None,
        limit: int = 1000
    ) -> Dict[str, Any]:
        """Query baseline vectors."""
        if not DB_IMPORTS_AVAILABLE:
            raise RuntimeError("Database not available")

        db = next(get_db())
        try:
            query = db.query(BaselineVector)

            if satellite_1:
                query = query.filter(BaselineVector.satellite_1 == satellite_1)
            if satellite_2:
                query = query.filter(BaselineVector.satellite_2 == satellite_2)
            if start_time:
                query = query.filter(BaselineVector.time >= start_time)
            if end_time:
                query = query.filter(BaselineVector.time <= end_time)
            if job_id:
                query = query.filter(BaselineVector.job_id == UUID(job_id))

            baselines = query.order_by(BaselineVector.time).limit(limit).all()

            return {
                'baseline_vectors': [self._baseline_to_dict(b) for b in baselines],
                'count': len(baselines)
            }
        finally:
            db.close()

    def _baseline_to_dict(self, baseline: BaselineVector) -> Dict[str, Any]:
        """Convert BaselineVector model to dictionary."""
        return {
            'time': baseline.time.isoformat(),
            'satellite_1': baseline.satellite_1,
            'satellite_2': baseline.satellite_2,
            'range_rate': baseline.range_rate,
            'range_acceleration': baseline.range_acceleration,
            'baseline_length': baseline.baseline_length,
            'job_id': str(baseline.job_id) if baseline.job_id else None,
            'metadata': baseline.metadata
        }

    # =================================================================
    # Audit Logs
    # =================================================================

    def create_audit_log(
        self,
        action: str,
        user_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create audit log entry."""
        if not DB_IMPORTS_AVAILABLE:
            raise RuntimeError("Database not available")

        db = next(get_db())
        try:
            log = AuditLog(
                timestamp=datetime.utcnow(),
                user_id=UUID(user_id) if user_id else None,
                action=action,
                resource_type=resource_type,
                resource_id=UUID(resource_id) if resource_id else None,
                details=details or {},
                ip_address=ip_address,
                user_agent=user_agent
            )
            db.add(log)
            db.commit()
            db.refresh(log)

            return self._audit_log_to_dict(log)
        except Exception as e:
            db.rollback()
            raise RuntimeError(f"Failed to create audit log: {e}")
        finally:
            db.close()

    def query_audit_logs(
        self,
        user_id: Optional[str] = None,
        action: Optional[str] = None,
        resource_type: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> Dict[str, Any]:
        """Query audit logs."""
        if not DB_IMPORTS_AVAILABLE:
            raise RuntimeError("Database not available")

        db = next(get_db())
        try:
            query = db.query(AuditLog)

            if user_id:
                query = query.filter(AuditLog.user_id == UUID(user_id))
            if action:
                query = query.filter(AuditLog.action == action)
            if resource_type:
                query = query.filter(AuditLog.resource_type == resource_type)
            if start_time:
                query = query.filter(AuditLog.timestamp >= start_time)
            if end_time:
                query = query.filter(AuditLog.timestamp <= end_time)

            logs = query.order_by(AuditLog.timestamp.desc()).limit(limit).all()

            return {
                'logs': [self._audit_log_to_dict(l) for l in logs],
                'count': len(logs)
            }
        finally:
            db.close()

    def _audit_log_to_dict(self, log: AuditLog) -> Dict[str, Any]:
        """Convert AuditLog model to dictionary."""
        return {
            'id': str(log.id),
            'timestamp': log.timestamp.isoformat(),
            'user_id': str(log.user_id) if log.user_id else None,
            'action': log.action,
            'resource_type': log.resource_type,
            'resource_id': str(log.resource_id) if log.resource_id else None,
            'details': log.details,
            'ip_address': log.ip_address,
            'user_agent': log.user_agent
        }


# Singleton
_database_service = None

def get_database_service() -> DatabaseService:
    """Get or create database service singleton."""
    global _database_service
    if _database_service is None:
        _database_service = DatabaseService()
    return _database_service
