"""
Database models and connection for Data Service
"""

from sqlalchemy import create_engine, Column, String, Float, DateTime, Integer, JSON, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import logging

from .config import settings

logger = logging.getLogger(__name__)

Base = declarative_base()


class SatelliteTelemetryModel(Base):
    """Satellite telemetry data model"""
    __tablename__ = "satellite_telemetry"

    id = Column(Integer, primary_key=True, autoincrement=True)
    satellite_id = Column(String(100), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)

    # Position (ECEF coordinates)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    altitude = Column(Float, nullable=False)

    # Velocity
    velocity_x = Column(Float)
    velocity_y = Column(Float)
    velocity_z = Column(Float)

    # Spacecraft health
    temperature = Column(Float)
    battery_level = Column(Float)

    # Additional sensors (JSON)
    sensors = Column(JSON)

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('idx_satellite_time', 'satellite_id', 'timestamp'),
    )


class GravityMeasurementModel(Base):
    """Gravity measurement data model"""
    __tablename__ = "gravity_measurements"

    id = Column(Integer, primary_key=True, autoincrement=True)
    satellite_id = Column(String(100), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)

    # Position
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    altitude = Column(Float, nullable=False)

    # Gravity measurements
    gravity_x = Column(Float, nullable=False)
    gravity_y = Column(Float, nullable=False)
    gravity_z = Column(Float, nullable=False)
    gravity_magnitude = Column(Float, nullable=False)

    # Quality
    accuracy = Column(Float)
    quality_flag = Column(Integer)

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('idx_gravity_location', 'latitude', 'longitude'),
        Index('idx_gravity_time', 'satellite_id', 'timestamp'),
    )


class Database:
    """Database connection manager"""

    def __init__(self):
        self.engine = None
        self.SessionLocal = None

    def connect(self):
        """Connect to database"""
        logger.info(f"Connecting to database: {settings.database_url}")

        self.engine = create_engine(
            settings.database_url,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            echo=False
        )

        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine
        )

        # Create tables
        Base.metadata.create_all(bind=self.engine)
        logger.info("Database tables created/verified")

    def get_session(self):
        """Get database session"""
        return self.SessionLocal()

    def close(self):
        """Close database connection"""
        if self.engine:
            self.engine.dispose()
            logger.info("Database connection closed")


# Global database instance
db = Database()
