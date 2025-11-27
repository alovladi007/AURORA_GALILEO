#!/usr/bin/env python3
"""
Database initialization script for GeoSense Platform

This script:
1. Creates the database if it doesn't exist
2. Runs all pending Alembic migrations
3. Creates a default admin user

Usage:
    python scripts/init_db.py

Environment Variables:
    DATABASE_URL: PostgreSQL connection string (default: postgresql://gravity:gravity_secret@localhost:5432/gravity_ops)
"""

import os
import sys
import subprocess

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
import uuid
from datetime import datetime


def get_database_url():
    """Get database URL from environment or use default."""
    return os.getenv(
        "DATABASE_URL",
        "postgresql://gravity:gravity_secret@localhost:5432/gravity_ops"
    )


def create_database_if_not_exists():
    """Create the database if it doesn't exist."""
    db_url = get_database_url()

    # Parse the URL to get database name
    # Format: postgresql://user:pass@host:port/dbname
    parts = db_url.rsplit('/', 1)
    base_url = parts[0]
    db_name = parts[1].split('?')[0]  # Remove query params if any

    # Connect to postgres database to create our database
    postgres_url = f"{base_url}/postgres"

    try:
        engine = create_engine(postgres_url, isolation_level='AUTOCOMMIT')
        with engine.connect() as conn:
            # Check if database exists
            result = conn.execute(
                text(f"SELECT 1 FROM pg_database WHERE datname = '{db_name}'")
            )
            exists = result.fetchone() is not None

            if not exists:
                print(f"Creating database: {db_name}")
                conn.execute(text(f'CREATE DATABASE "{db_name}"'))
                print(f"Database '{db_name}' created successfully!")
            else:
                print(f"Database '{db_name}' already exists.")

        engine.dispose()
        return True

    except OperationalError as e:
        print(f"Warning: Could not connect to PostgreSQL: {e}")
        print("Make sure PostgreSQL is running and accessible.")
        return False


def run_migrations():
    """Run Alembic migrations."""
    project_root = os.path.dirname(os.path.dirname(__file__))

    print("\nRunning database migrations...")
    try:
        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            cwd=project_root,
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            print("Migrations completed successfully!")
            if result.stdout:
                print(result.stdout)
        else:
            print(f"Migration failed: {result.stderr}")
            return False

    except FileNotFoundError:
        print("Alembic not found. Install with: pip install alembic")
        return False

    return True


def create_default_admin():
    """Create a default admin user if none exists."""
    from ops.models import SessionLocal, User
    import hashlib

    db = SessionLocal()
    try:
        # Check if admin user exists
        existing = db.query(User).filter(User.username == 'admin').first()

        if not existing:
            # Create admin user with hashed password
            password = "admin123"  # Default password - CHANGE IN PRODUCTION
            hashed = hashlib.sha256(password.encode()).hexdigest()

            admin = User(
                id=uuid.uuid4(),
                username='admin',
                email='admin@geosense.local',
                hashed_password=hashed,
                is_active=True,
                is_superuser=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )

            db.add(admin)
            db.commit()
            print("\nDefault admin user created:")
            print("  Username: admin")
            print("  Password: admin123")
            print("  WARNING: Change this password in production!")
        else:
            print("\nAdmin user already exists.")

    except Exception as e:
        print(f"Could not create admin user: {e}")
        db.rollback()
    finally:
        db.close()


def init_timescale_hypertables():
    """Initialize TimescaleDB hypertables for time-series data."""
    db_url = get_database_url()

    try:
        engine = create_engine(db_url)
        with engine.connect() as conn:
            # Check if TimescaleDB extension is available
            try:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE"))
                conn.commit()
                print("\nTimescaleDB extension enabled.")

                # Convert satellite_observations to hypertable
                try:
                    conn.execute(text("""
                        SELECT create_hypertable(
                            'satellite_observations',
                            'time',
                            if_not_exists => TRUE
                        )
                    """))
                    conn.commit()
                    print("satellite_observations converted to hypertable.")
                except Exception as e:
                    print(f"Note: satellite_observations hypertable: {e}")

                # Convert baseline_vectors to hypertable
                try:
                    conn.execute(text("""
                        SELECT create_hypertable(
                            'baseline_vectors',
                            'time',
                            if_not_exists => TRUE
                        )
                    """))
                    conn.commit()
                    print("baseline_vectors converted to hypertable.")
                except Exception as e:
                    print(f"Note: baseline_vectors hypertable: {e}")

            except Exception as e:
                print(f"TimescaleDB not available (optional): {e}")

        engine.dispose()

    except Exception as e:
        print(f"Could not initialize TimescaleDB: {e}")


def main():
    print("=" * 60)
    print("GeoSense Platform Database Initialization")
    print("=" * 60)

    # Step 1: Create database
    print("\n[1/4] Checking database...")
    if not create_database_if_not_exists():
        print("\nContinuing without database creation (may already exist)...")

    # Step 2: Run migrations
    print("\n[2/4] Running migrations...")
    if not run_migrations():
        print("\nMigration step had issues. Check errors above.")

    # Step 3: Initialize TimescaleDB (optional)
    print("\n[3/4] Initializing TimescaleDB (optional)...")
    init_timescale_hypertables()

    # Step 4: Create admin user
    print("\n[4/4] Creating default admin user...")
    try:
        create_default_admin()
    except Exception as e:
        print(f"Could not create admin user: {e}")

    print("\n" + "=" * 60)
    print("Database initialization complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
