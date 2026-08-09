"""
Verification and Benchmarking Suite
====================================
Comprehensive testing and verification for geophysical processing pipeline.

Usage:
    from bench import BenchmarkRunner
    runner = BenchmarkRunner()
    runner.run_suite('all')
"""

from .result import BenchmarkResult
from .metrics import (
    SpatialResolutionMetrics,
    LocalizationMetrics,
    PerformanceMetrics,
    CoverageAnalyzer
)

from .datasets import (
    RegressionDatasets,
    create_sample_datasets
)

__version__ = '1.0.0'
__all__ = [
    'SpatialResolutionMetrics',
    'LocalizationMetrics',
    'BenchmarkResult',
    'PerformanceMetrics',
    'CoverageAnalyzer',
    'RegressionDatasets',
    'create_sample_datasets',
]
