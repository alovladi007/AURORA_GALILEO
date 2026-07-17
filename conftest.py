"""Repo-root pytest configuration: make first-party packages importable."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))


def pytest_collection_modifyitems(config, items):
    """Skip benchmark-fixture tests when pytest-benchmark is absent."""
    if config.pluginmanager.hasplugin("benchmark"):
        return
    skip = pytest.mark.skip(reason="pytest-benchmark not installed")
    for item in items:
        if "benchmark" in getattr(item, "fixturenames", ()):
            item.add_marker(skip)
