"""Data loading and preprocessing for satellite geophysical data."""

from .satellite_data import (
    GRACEDataLoader,
    GOCEDataLoader,
    GRACEFODataLoader,
    SatelliteDataset,
    create_dataloaders,
)

from .preprocessing import (
    normalize_gravity,
    normalize_magnetic,
    denormalize_model,
    grid_to_observations,
    observations_to_grid,
)

__all__ = [
    'GRACEDataLoader',
    'GOCEDataLoader',
    'GRACEFODataLoader',
    'SatelliteDataset',
    'create_dataloaders',
    'normalize_gravity',
    'normalize_magnetic',
    'denormalize_model',
    'grid_to_observations',
    'observations_to_grid',
]
