"""
Database models for GALILEO Platform

Geospatial Analytics, Learning, and Intelligence for Land, Environment & Oceanography

Supports both PostgreSQL (production) and SQLite (development)
"""

from sqlalchemy import create_engine, Column, String, Boolean, DateTime, Text, Float, Integer, ForeignKey, TypeDecorator
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import uuid
import os
import json

# Database URL - defaults to SQLite for development
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./galileo_dev.db")

# Detect database type
IS_SQLITE = DATABASE_URL.startswith("sqlite")

# Import PostgreSQL-specific types only if using PostgreSQL
if not IS_SQLITE:
    from sqlalchemy.dialects.postgresql import UUID as PG_UUID, INET, JSONB
else:
    PG_UUID = None
    INET = None
    JSONB = None


# Custom UUID type that works with both SQLite and PostgreSQL
class UUID(TypeDecorator):
    """Platform-independent UUID type.
    Uses PostgreSQL's UUID type when available, otherwise uses String(36).
    """
    impl = String(36)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            if isinstance(value, uuid.UUID):
                return str(value)
            return str(value)
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            if not isinstance(value, uuid.UUID):
                return uuid.UUID(value)
        return value

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql' and PG_UUID:
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(String(36))


# Custom JSON type that works with both SQLite and PostgreSQL
class JSONType(TypeDecorator):
    """Platform-independent JSON type.
    Uses PostgreSQL's JSONB when available, otherwise uses Text with JSON serialization.
    """
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            return json.dumps(value)
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            return json.loads(value)
        return value

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql' and JSONB:
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(Text())


# Custom INET type that works with both SQLite and PostgreSQL
class InetType(TypeDecorator):
    """Platform-independent INET type.
    Uses PostgreSQL's INET when available, otherwise uses String.
    """
    impl = String(45)  # Max length for IPv6 with port
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql' and INET:
            return dialect.type_descriptor(INET())
        return dialect.type_descriptor(String(45))


# Create engine with appropriate settings
if IS_SQLITE:
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},  # Needed for SQLite
        echo=False
    )
else:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()


# Dependency for FastAPI
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Helper to generate UUID
def generate_uuid():
    return uuid.uuid4()


# Models
class User(Base):
    __tablename__ = "users"

    id = Column(UUID(), primary_key=True, default=generate_uuid)
    username = Column(String(255), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    jobs = relationship("ProcessingJob", back_populates="user")
    audit_logs = relationship("AuditLog", back_populates="user")


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"

    id = Column(UUID(), primary_key=True, default=generate_uuid)
    job_type = Column(String(50), nullable=False, index=True)
    status = Column(String(50), default="pending", index=True)
    user_id = Column(UUID(), ForeignKey("users.id", ondelete="CASCADE"))
    config = Column(JSONType())
    result = Column(JSONType())
    error_message = Column(Text)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="jobs")
    observations = relationship("SatelliteObservation", back_populates="job")
    products = relationship("GravityProduct", back_populates="job")
    baseline_vectors = relationship("BaselineVector", back_populates="job")


class SatelliteObservation(Base):
    __tablename__ = "satellite_observations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    time = Column(DateTime(timezone=True), nullable=False, index=True)
    satellite_id = Column(String(50), nullable=False, index=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    altitude = Column(Float, nullable=False)
    gravity_value = Column(Float)
    gravity_uncertainty = Column(Float)
    meta_info = Column(JSONType())
    job_id = Column(UUID(), ForeignKey("processing_jobs.id", ondelete="CASCADE"))

    # Relationships
    job = relationship("ProcessingJob", back_populates="observations")


class GravityProduct(Base):
    __tablename__ = "gravity_products"

    id = Column(UUID(), primary_key=True, default=generate_uuid)
    product_type = Column(String(50), nullable=False, index=True)
    version = Column(String(20), nullable=False)
    time_start = Column(DateTime(timezone=True), nullable=False, index=True)
    time_end = Column(DateTime(timezone=True), nullable=False)
    degree_max = Column(Integer)
    spatial_resolution = Column(Float)
    s3_path = Column(Text, nullable=False)
    meta_info = Column(JSONType())
    job_id = Column(UUID(), ForeignKey("processing_jobs.id", ondelete="CASCADE"))
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    job = relationship("ProcessingJob", back_populates="products")


class BaselineVector(Base):
    __tablename__ = "baseline_vectors"

    id = Column(Integer, primary_key=True, autoincrement=True)
    time = Column(DateTime(timezone=True), nullable=False, index=True)
    satellite_1 = Column(String(50), nullable=False)
    satellite_2 = Column(String(50), nullable=False)
    range_rate = Column(Float)
    range_acceleration = Column(Float)
    baseline_length = Column(Float)
    meta_info = Column(JSONType())
    job_id = Column(UUID(), ForeignKey("processing_jobs.id", ondelete="CASCADE"))

    # Relationships
    job = relationship("ProcessingJob", back_populates="baseline_vectors")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(UUID(), primary_key=True, default=generate_uuid)
    timestamp = Column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    user_id = Column(UUID(), ForeignKey("users.id", ondelete="SET NULL"), index=True)
    action = Column(String(100), nullable=False, index=True)
    resource_type = Column(String(50))
    resource_id = Column(UUID())
    details = Column(JSONType())
    ip_address = Column(InetType())
    user_agent = Column(Text)

    # Relationships
    user = relationship("User", back_populates="audit_logs")


def init_db():
    """Create all database tables."""
    Base.metadata.create_all(bind=engine)
    print(f"Database initialized: {DATABASE_URL}")


if __name__ == "__main__":
    init_db()
