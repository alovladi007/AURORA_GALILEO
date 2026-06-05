"""
Pytest configuration and fixtures for Control Service tests.
"""

import sys
from pathlib import Path

import pytest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
GEN_DIR = SERVICE_ROOT / "src" / "gen"

for p in (str(SERVICE_ROOT), str(GEN_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)


@pytest.fixture()
def servicer():
    from src.service import ControlServicer
    return ControlServicer()


class FakeContext:
    def __init__(self):
        self.code = None
        self.details_msg = None

    def set_code(self, code):
        self.code = code

    def set_details(self, details):
        self.details_msg = details


@pytest.fixture()
def context():
    return FakeContext()
