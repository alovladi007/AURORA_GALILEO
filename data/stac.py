"""
STAC (SpatioTemporal Asset Catalog) Implementation
===================================================

Manage geospatial data using STAC specification.
"""

import json
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Any
from datetime import datetime, timezone
import hashlib


@dataclass
class STACAsset:
    """
    STAC Asset (individual file).

    Attributes:
        href: URL or path to the asset
        title: Human-readable title
        description: Asset description
        type: Media type (e.g., 'image/tiff')
        roles: List of asset roles
    """
    href: str
    title: Optional[str] = None
    description: Optional[str] = None
    type: Optional[str] = None
    roles: Optional[List[str]] = None

    def to_dict(self) -> dict:
        """Convert to STAC JSON format."""
        result = {'href': self.href}
        if self.title:
            result['title'] = self.title
        if self.description:
            result['description'] = self.description
        if self.type:
            result['type'] = self.type
        if self.roles:
            result['roles'] = self.roles
        return result


@dataclass
class STACItem:
    """
    STAC Item (single spatiotemporal asset).

    Follows STAC spec v1.0.0.
    """
    id: str
    geometry: dict
    bbox: List[float]
    properties: dict
    assets: Dict[str, STACAsset]
    collection: Optional[str] = None
    links: Optional[List[dict]] = None

    def to_dict(self) -> dict:
        """Convert to STAC JSON format."""
        item = {
            'type': 'Feature',
            'stac_version': '1.0.0',
            'id': self.id,
            'geometry': self.geometry,
            'bbox': self.bbox,
            'properties': self.properties,
            'assets': {k: v.to_dict() for k, v in self.assets.items()},
        }

        if self.collection:
            item['collection'] = self.collection

        if self.links:
            item['links'] = self.links
        else:
            item['links'] = []

        return item

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: dict) -> 'STACItem':
        """Create from STAC JSON dict."""
        assets = {
            k: STACAsset(**v) for k, v in data['assets'].items()
        }

        return cls(
            id=data['id'],
            geometry=data['geometry'],
            bbox=data['bbox'],
            properties=data['properties'],
            assets=assets,
            collection=data.get('collection'),
            links=data.get('links'),
        )


@dataclass
class STACCollection:
    """
    STAC Collection (group of related items).
    """
    id: str
    description: str
    license: str
    extent: dict
    title: Optional[str] = None
    keywords: Optional[List[str]] = None
    providers: Optional[List[dict]] = None
    summaries: Optional[dict] = None
    links: Optional[List[dict]] = None

    def to_dict(self) -> dict:
        """Convert to STAC JSON format."""
        collection = {
            'type': 'Collection',
            'stac_version': '1.0.0',
            'id': self.id,
            'description': self.description,
            'license': self.license,
            'extent': self.extent,
        }

        if self.title:
            collection['title'] = self.title
        if self.keywords:
            collection['keywords'] = self.keywords
        if self.providers:
            collection['providers'] = self.providers
        if self.summaries:
            collection['summaries'] = self.summaries
        if self.links:
            collection['links'] = self.links
        else:
            collection['links'] = []

        return collection

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)


class STACCatalog:
    """
    STAC Catalog management.

    Provides methods to create, query, and manage STAC catalogs.
    """

    def __init__(
        self,
        catalog_id: str = "galileo-catalog",
        description: str = "GALILEO V2.0 Data Catalog",
    ):
        self.catalog_id = catalog_id
        self.description = description
        self.collections: Dict[str, STACCollection] = {}
        self.items: Dict[str, STACItem] = {}

    def add_collection(self, collection: STACCollection):
        """Add a collection to the catalog."""
        self.collections[collection.id] = collection

    def add_item(self, item: STACItem):
        """Add an item to the catalog."""
        self.items[item.id] = item

    def get_collection(self, collection_id: str) -> Optional[STACCollection]:
        """Get collection by ID."""
        return self.collections.get(collection_id)

    def get_item(self, item_id: str) -> Optional[STACItem]:
        """Get item by ID."""
        return self.items.get(item_id)

    def search(
        self,
        bbox: Optional[List[float]] = None,
        datetime_range: Optional[tuple] = None,
        collections: Optional[List[str]] = None,
    ) -> List[STACItem]:
        """
        Search catalog for items matching criteria.

        Args:
            bbox: Bounding box [min_lon, min_lat, max_lon, max_lat]
            datetime_range: (start, end) datetime tuple
            collections: List of collection IDs to search

        Returns:
            List of matching STACItem objects
        """
        results = []

        for item in self.items.values():
            # Filter by collection
            if collections and item.collection not in collections:
                continue

            # Filter by bbox
            if bbox and not self._bbox_intersects(item.bbox, bbox):
                continue

            # Filter by datetime
            if datetime_range:
                item_datetime = item.properties.get('datetime')
                if item_datetime:
                    item_dt = datetime.fromisoformat(item_datetime.replace('Z', '+00:00'))
                    start, end = datetime_range
                    # Normalize to timezone-aware UTC so naive query
                    # bounds compare against stored aware datetimes
                    if item_dt.tzinfo is None:
                        item_dt = item_dt.replace(tzinfo=timezone.utc)
                    if start.tzinfo is None:
                        start = start.replace(tzinfo=timezone.utc)
                    if end.tzinfo is None:
                        end = end.replace(tzinfo=timezone.utc)
                    if not (start <= item_dt <= end):
                        continue

            results.append(item)

        return results

    def _bbox_intersects(self, bbox1: List[float], bbox2: List[float]) -> bool:
        """Check if two bounding boxes intersect."""
        # bbox format: [min_lon, min_lat, max_lon, max_lat]
        return not (
            bbox1[2] < bbox2[0] or  # bbox1 left of bbox2
            bbox1[0] > bbox2[2] or  # bbox1 right of bbox2
            bbox1[3] < bbox2[1] or  # bbox1 below bbox2
            bbox1[1] > bbox2[3]     # bbox1 above bbox2
        )

    def to_catalog_dict(self) -> dict:
        """Export catalog as STAC Catalog JSON."""
        return {
            'type': 'Catalog',
            'stac_version': '1.0.0',
            'id': self.catalog_id,
            'description': self.description,
            'links': [
                {
                    'rel': 'self',
                    'href': f'./{self.catalog_id}/catalog.json',
                },
                {
                    'rel': 'root',
                    'href': './catalog.json',
                },
            ],
        }

    def export(self, base_path: str = './stac-catalog'):
        """Export entire catalog to directory structure."""
        import os

        # Create base directory
        os.makedirs(base_path, exist_ok=True)

        # Write catalog.json
        catalog_path = os.path.join(base_path, 'catalog.json')
        with open(catalog_path, 'w') as f:
            json.dump(self.to_catalog_dict(), f, indent=2)

        # Write collections
        for collection_id, collection in self.collections.items():
            collection_dir = os.path.join(base_path, 'collections', collection_id)
            os.makedirs(collection_dir, exist_ok=True)

            collection_path = os.path.join(collection_dir, 'collection.json')
            with open(collection_path, 'w') as f:
                f.write(collection.to_json())

        # Write items
        for item_id, item in self.items.items():
            if item.collection:
                item_dir = os.path.join(base_path, 'collections', item.collection, 'items')
            else:
                item_dir = os.path.join(base_path, 'items')

            os.makedirs(item_dir, exist_ok=True)

            item_path = os.path.join(item_dir, f'{item_id}.json')
            with open(item_path, 'w') as f:
                f.write(item.to_json())


# ============================================================================
# Helper functions
# ============================================================================

def create_gravity_map_item(
    gravity_file: str,
    bbox: List[float],
    datetime_str: str,
    collection_id: str = "gravity-maps",
    metadata: Optional[dict] = None,
) -> STACItem:
    """
    Create STAC item for gravity map.

    Args:
        gravity_file: Path to gravity map file (GeoTIFF, etc.)
        bbox: Bounding box [min_lon, min_lat, max_lon, max_lat]
        datetime_str: ISO 8601 datetime string
        collection_id: Collection identifier
        metadata: Additional metadata

    Returns:
        STACItem
    """
    # Generate unique ID
    item_id = f"gravity-map-{hashlib.md5(gravity_file.encode()).hexdigest()[:8]}"

    # Geometry (bounding box polygon)
    geometry = {
        'type': 'Polygon',
        'coordinates': [[
            [bbox[0], bbox[1]],
            [bbox[2], bbox[1]],
            [bbox[2], bbox[3]],
            [bbox[0], bbox[3]],
            [bbox[0], bbox[1]],
        ]],
    }

    # Properties
    properties = {
        'datetime': datetime_str,
        'created': datetime.utcnow().isoformat() + 'Z',
    }

    if metadata:
        properties.update(metadata)

    # Assets
    assets = {
        'data': STACAsset(
            href=gravity_file,
            title="Gravity Map",
            type="image/tiff; application=geotiff; profile=cloud-optimized",
            roles=["data"],
        ),
    }

    return STACItem(
        id=item_id,
        geometry=geometry,
        bbox=bbox,
        properties=properties,
        assets=assets,
        collection=collection_id,
    )


def create_gravity_collection(
    collection_id: str = "gravity-maps",
    title: str = "Gravity Field Maps",
    description: str = "Derived gravity field maps from satellite gravimetry",
    temporal_extent: Optional[List[str]] = None,
    spatial_extent: Optional[List[float]] = None,
) -> STACCollection:
    """
    Create STAC collection for gravity maps.

    Args:
        collection_id: Collection identifier
        title: Collection title
        description: Collection description
        temporal_extent: [start_datetime, end_datetime] (ISO 8601)
        spatial_extent: Global bbox [min_lon, min_lat, max_lon, max_lat]

    Returns:
        STACCollection
    """
    if temporal_extent is None:
        temporal_extent = [None, None]

    if spatial_extent is None:
        spatial_extent = [-180.0, -90.0, 180.0, 90.0]

    extent = {
        'spatial': {
            'bbox': [spatial_extent],
        },
        'temporal': {
            'interval': [temporal_extent],
        },
    }

    return STACCollection(
        id=collection_id,
        title=title,
        description=description,
        license="proprietary",
        extent=extent,
        keywords=["gravity", "geophysics", "satellite"],
    )
