"""
Pytest configuration and fixtures for Inversion Service tests.
"""

import os
import sys
from pathlib import Path

import pytest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
GEN_DIR = SERVICE_ROOT / "src" / "gen"

for p in (str(SERVICE_ROOT), str(GEN_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

# No database / Kafka in tests.
os.environ.setdefault("DATABASE_URL", "")
os.environ.setdefault("KAFKA_BOOTSTRAP_SERVERS", "")


@pytest.fixture()
def servicer():
    from src.service import InversionServicer
    return InversionServicer()


class FakeContext:
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


@pytest.fixture()
def context():
    return FakeContext()
