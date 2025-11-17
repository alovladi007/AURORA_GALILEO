"""
GALILEO V2.0 - Data Management Module
======================================

STAC catalogs, data pipelines, and provenance tracking.

Modules:
    stac: STAC catalog management
    pipelines: Batch processing pipelines (Celery/Dask)
    tiles: COG/PMTiles generation
    provenance: End-to-end lineage tracking
    registry: Run registry with configs and seeds
"""

__version__ = "0.1.0"

__all__ = [
    "STACCatalog",
    "BatchPipeline",
    "TileGenerator",
    "ProvenanceTracker",
    "RunRegistry",
]
