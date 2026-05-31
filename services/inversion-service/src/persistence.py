"""
Inversion Job Persistence
=========================

Optional SQLAlchemy persistence for inversion jobs and results. Enables jobs to
survive service restarts and be queried historically. Degrades gracefully: if
the database is unavailable or SQLAlchemy is not installed, persistence becomes
a no-op and the service continues with in-memory tracking only.

Set ``DATABASE_URL`` to enable (e.g.
``postgresql://galileo:...@postgres:5432/galileo``).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from sqlalchemy import (Column, String, Float, Integer, Boolean, DateTime,
                            JSON, create_engine)
    from sqlalchemy.orm import declarative_base, sessionmaker

    _HAS_SQLALCHEMY = True
    Base = declarative_base()

    class InversionJobRecord(Base):
        """Persistent record of an inversion job and its result metadata."""

        __tablename__ = "inversion_jobs"

        job_id = Column(String(128), primary_key=True)
        inversion_type = Column(String(64), nullable=False, index=True)
        status = Column(String(32), nullable=False, index=True)
        progress = Column(Float, default=0.0)
        iterations = Column(Integer, default=0)
        final_residual = Column(Float, default=0.0)
        convergence_achieved = Column(Boolean, default=False)
        grid_shape = Column(String(32), default="")
        gravity_field_url = Column(String(512), default="")
        coefficients_url = Column(String(512), default="")
        config = Column(JSON, default=dict)
        error = Column(String(1024), default="")
        created_at = Column(DateTime, default=datetime.utcnow, index=True)
        completed_at = Column(DateTime, nullable=True)

except Exception:  # noqa: BLE001
    _HAS_SQLALCHEMY = False
    Base = None
    InversionJobRecord = None


class JobStore:
    """Thin persistence wrapper with graceful no-op fallback."""

    def __init__(self):
        self.enabled = False
        self.SessionLocal = None
        url = os.getenv("DATABASE_URL")
        if _HAS_SQLALCHEMY and url:
            try:
                self.engine = create_engine(url, pool_pre_ping=True)
                Base.metadata.create_all(bind=self.engine)
                self.SessionLocal = sessionmaker(bind=self.engine)
                self.enabled = True
                logger.info("Inversion job persistence enabled")
            except Exception as exc:  # noqa: BLE001
                logger.warning("Inversion persistence disabled (%s)", exc)
        else:
            logger.info("Inversion persistence disabled (no DATABASE_URL/SQLAlchemy)")

    def upsert(self, job, urls: Optional[dict] = None) -> None:
        if not self.enabled:
            return
        urls = urls or {}
        session = self.SessionLocal()
        try:
            rec = session.get(InversionJobRecord, job.job_id)
            if rec is None:
                rec = InversionJobRecord(job_id=job.job_id)
                session.add(rec)
            rec.inversion_type = job.inversion_type
            rec.status = job.status
            rec.progress = job.progress
            rec.iterations = job.current_iteration
            rec.final_residual = job.residual
            rec.convergence_achieved = job.convergence_achieved
            rec.grid_shape = f"{job.grid_shape[0]}x{job.grid_shape[1]}"
            rec.gravity_field_url = urls.get("gravity_field_url", rec.gravity_field_url or "")
            rec.coefficients_url = urls.get("coefficients_url", rec.coefficients_url or "")
            rec.config = {k: str(v) for k, v in (job.config or {}).items()}
            rec.error = job.error or ""
            rec.created_at = job.created_at
            rec.completed_at = job.completed_at
            session.commit()
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            logger.warning("Failed to persist inversion job %s: %s", job.job_id, exc)
        finally:
            session.close()
