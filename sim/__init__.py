"""
GALILEO Simulation Package

Geospatial Analytics, Learning, and Intelligence for Land, Environment & Oceanography

This package contains simulation modules for orbital dynamics and gravity field modeling.
"""

from .gravity import (
    GravityModel,
    SphericalHarmonics,
    load_egm2008_model,
    compute_geoid_height,
)

# Session 4: Synthetic Data Generation
try:
    from .synthetic import (
        SyntheticDataGenerator,
        SimulationConfig,
        SatelliteConfig,
        Anomaly,
        SubsurfaceModel,
        ForwardModel,
        TelemetryGenerator,
    )
    __all__ = [
        'GravityModel',
        'SphericalHarmonics',
        'load_egm2008_model',
        'compute_geoid_height',
        # Synthetic data generation (Session 4)
        'SyntheticDataGenerator',
        'SimulationConfig',
        'SatelliteConfig',
        'Anomaly',
        'SubsurfaceModel',
        'ForwardModel',
        'TelemetryGenerator',
    ]
except ImportError:
    # Synthetic module requires pandas, pyarrow
    __all__ = [
        'GravityModel',
        'SphericalHarmonics',
        'load_egm2008_model',
        'compute_geoid_height',
    ]

__version__ = '0.4.0'
