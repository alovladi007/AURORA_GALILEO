"""
Database models and connection for Data Service
"""

from sqlalchemy import create_engine, Column, String, Float, DateTime, Integer, JSON, Index, text
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
    """Gravity measurement data model (aligned with data_service.proto)."""
    __tablename__ = "gravity_measurements"

    id = Column(Integer, primary_key=True, autoincrement=True)
    measurement_id = Column(String(128), index=True)
    satellite_id = Column(String(100), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)

    # Position
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    altitude = Column(Float, nullable=False)

    # Gravity measurement (scalar anomaly in mGal) and its uncertainty.
    gravity_value = Column(Float, nullable=False)
    uncertainty = Column(Float)

    # Quality flag is a free-form string per proto (e.g. "good", "outlier").
    quality_flag = Column(String(64))

    # Additional metadata (map<string, double> in proto).
    measurement_metadata = Column(JSON)

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

        # Best-effort TimescaleDB optimization (no-op on plain PostgreSQL).
        self._setup_timescaledb()

    def _setup_timescaledb(self):
        """Convert time-series tables to TimescaleDB hypertables with
        compression and retention. Silently skips if the extension is
        unavailable (e.g. vanilla PostgreSQL)."""
        statements = [
            "CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;",
            # create_hypertable is idempotent with if_not_exists.
            "SELECT create_hypertable('satellite_telemetry', 'timestamp', "
            "if_not_exists => TRUE, migrate_data => TRUE);",
            "SELECT create_hypertable('gravity_measurements', 'timestamp', "
            "if_not_exists => TRUE, migrate_data => TRUE);",
            # Enable columnar compression on data older than 7 days.
            "ALTER TABLE satellite_telemetry SET "
            "(timescaledb.compress, timescaledb.compress_segmentby = 'satellite_id');",
            "ALTER TABLE gravity_measurements SET "
            "(timescaledb.compress, timescaledb.compress_segmentby = 'satellite_id');",
            "SELECT add_compression_policy('satellite_telemetry', INTERVAL '7 days', "
            "if_not_exists => TRUE);",
            "SELECT add_compression_policy('gravity_measurements', INTERVAL '7 days', "
            "if_not_exists => TRUE);",
        ]
        with self.engine.connect() as conn:
            for stmt in statements:
                try:
                    conn.execute(text(stmt))
                    conn.commit()
                except Exception as exc:  # noqa: BLE001
                    conn.rollback()
                    logger.debug("TimescaleDB step skipped: %s (%s)", stmt[:48], exc)
        logger.info("TimescaleDB optimization attempted (skipped if unavailable)")

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
