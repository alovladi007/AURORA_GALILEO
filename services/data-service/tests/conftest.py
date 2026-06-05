"""
Pytest configuration and fixtures for Data Service tests.

Sets up sys.path so `from src.gen import ...` resolves (and the flat internal
imports inside the generated stubs work), and provides an isolated SQLite
database for each test session.
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

# --- Path setup -------------------------------------------------------------
SERVICE_ROOT = Path(__file__).resolve().parents[1]
GEN_DIR = SERVICE_ROOT / "src" / "gen"

# Service root (so `import src.xxx` works) and the gen dir (so the stubs'
# flat `import common_pb2` works).
for p in (str(SERVICE_ROOT), str(GEN_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

# --- Isolated database ------------------------------------------------------
# Point the service at a throwaway SQLite file before importing the service.
_DB_FD, _DB_PATH = tempfile.mkstemp(suffix=".db")
os.close(_DB_FD)
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_PATH}"
# Avoid Kafka in tests (in-process streaming only).
os.environ.setdefault("KAFKA_BOOTSTRAP_SERVERS", "")


@pytest.fixture(scope="session", autouse=True)
def _database():
    """Connect the global db to the SQLite file and create tables."""
    from src.database import db
    db.connect()
    yield db
    db.close()
    try:
        os.unlink(_DB_PATH)
    except OSError:
        pass


@pytest.fixture()
def servicer():
    """A fresh DataServicer instance."""
    from src.service import DataServicer
    return DataServicer()


class FakeContext:
    """Minimal gRPC context stub for unit-testing servicer methods."""

    def __init__(self):
        self.code = None
        self.details_msg = None
        self._callbacks = []

    def set_code(self, code):
        self.code = code

    def set_details(self, details):
        self.details_msg = details

    def add_callback(self, cb):
        self._callbacks.append(cb)

    def trigger_cancel(self):
        for cb in self._callbacks:
            cb()


@pytest.fixture()
def context():
    return FakeContext()
