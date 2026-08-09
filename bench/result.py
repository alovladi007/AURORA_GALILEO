"""Benchmark result record."""

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class BenchmarkResult:
    """Structured result of a single benchmark run.

    Attributes:
        name: Human-readable benchmark name.
        suite: Suite the benchmark belongs to (e.g. 'spatial',
            'frequency', 'noise').
        status: 'PASS', 'WARN', or 'FAIL'.
        metrics: Measured metric values keyed by name.
        runtime: Wall-clock runtime in seconds.
        timestamp: ISO-8601 timestamp of the run.
    """

    name: str
    suite: str
    status: str
    metrics: Dict[str, Any] = field(default_factory=dict)
    runtime: float = 0.0
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "suite": self.suite,
            "status": self.status,
            "metrics": self.metrics,
            "runtime": self.runtime,
            "timestamp": self.timestamp,
        }
