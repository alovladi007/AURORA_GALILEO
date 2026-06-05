"""
Pytest configuration and fixtures for API Gateway tests.
"""

import sys
from pathlib import Path

SERVICE_SRC = Path(__file__).resolve().parents[1] / "src"
if str(SERVICE_SRC) not in sys.path:
    sys.path.insert(0, str(SERVICE_SRC))
