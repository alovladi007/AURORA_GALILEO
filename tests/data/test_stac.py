"""
Tests for STAC Implementation
==============================

Tests SpatioTemporal Asset Catalog (STAC) functionality.
"""

import pytest
import json
import os
import tempfile
import shutil
from datetime import datetime
from data.stac import (
    STACAsset,
    STACItem,
    STACCollection,
    STACCatalog,
    create_gravity_map_item,
    create_gravity_collection,
)


class TestSTACAsset:
    """Test STACAsset dataclass."""

    def test_basic_asset(self):
        """Test basic asset creation."""
        asset = STACAsset(href="http://example.com/data.tif")

        assert asset.href == "http://example.com/data.tif"
        assert asset.title is None
        assert asset.description is None
        assert asset.type is None
        assert asset.roles is None

    def test_full_asset(self):
        """Test asset with all fields."""
        asset = STACAsset(
            href="s3://bucket/data.tif",
            title="Data File",
            description="Test data",
            type="image/tiff",
            roles=["data", "metadata"],
        )

        assert asset.href == "s3://bucket/data.tif"
        assert asset.title == "Data File"
        assert asset.description == "Test data"
        assert asset.type == "image/tiff"
        assert asset.roles == ["data", "metadata"]

    def test_to_dict_minimal(self):
        """Test converting minimal asset to dict."""
        asset = STACAsset(href="data.tif")
        asset_dict = asset.to_dict()

        assert asset_dict == {'href': 'data.tif'}

    def test_to_dict_full(self):
        """Test converting full asset to dict."""
        asset = STACAsset(
            href="data.tif",
            title="Data",
            description="Description",
            type="image/tiff",
            roles=["data"],
        )
        asset_dict = asset.to_dict()

        assert 'href' in asset_dict
        assert 'title' in asset_dict
        assert 'description' in asset_dict
        assert 'type' in asset_dict
        assert 'roles' in asset_dict


class TestSTACItem:
    """Test STACItem dataclass."""

    def test_basic_item(self):
        """Test basic item creation."""
        geometry = {
            'type': 'Point',
            'coordinates': [0.0, 0.0],
        }
        bbox = [-1.0, -1.0, 1.0, 1.0]
        properties = {'datetime': '2024-01-01T00:00:00Z'}
        assets = {
            'data': STACAsset(href='data.tif'),
        }

        item = STACItem(
            id='test-item-1',
            geometry=geometry,
            bbox=bbox,
            properties=properties,
            assets=assets,
        )

        assert item.id == 'test-item-1'
        assert item.geometry == geometry
        assert item.bbox == bbox
        assert item.properties == properties
        assert item.assets == assets
        assert item.collection is None

    def test_item_with_collection(self):
        """Test item with collection."""
        item = STACItem(
            id='test-item',
            geometry={'type': 'Point', 'coordinates': [0.0, 0.0]},
            bbox=[0.0, 0.0, 0.0, 0.0],
            properties={'datetime': '2024-01-01T00:00:00Z'},
            assets={'data': STACAsset(href='data.tif')},
            collection='test-collection',
        )

        assert item.collection == 'test-collection'

    def test_to_dict(self):
        """Test converting item to dict."""
        item = STACItem(
            id='test-item',
            geometry={'type': 'Point', 'coordinates': [0.0, 0.0]},
            bbox=[0.0, 0.0, 0.0, 0.0],
            properties={'datetime': '2024-01-01T00:00:00Z'},
            assets={'data': STACAsset(href='data.tif')},
        )

        item_dict = item.to_dict()

        assert item_dict['type'] == 'Feature'
        assert item_dict['stac_version'] == '1.0.0'
        assert item_dict['id'] == 'test-item'
        assert 'geometry' in item_dict
        assert 'bbox' in item_dict
        assert 'properties' in item_dict
        assert 'assets' in item_dict
        assert 'links' in item_dict

    def test_to_json(self):
        """Test converting item to JSON string."""
        item = STACItem(
            id='test-item',
            geometry={'type': 'Point', 'coordinates': [0.0, 0.0]},
            bbox=[0.0, 0.0, 0.0, 0.0],
            properties={'datetime': '2024-01-01T00:00:00Z'},
            assets={'data': STACAsset(href='data.tif')},
        )

        json_str = item.to_json()

        # Should be valid JSON
        parsed = json.loads(json_str)
        assert parsed['id'] == 'test-item'

    def test_from_dict(self):
        """Test creating item from dict."""
        item_dict = {
            'id': 'test-item',
            'geometry': {'type': 'Point', 'coordinates': [0.0, 0.0]},
            'bbox': [0.0, 0.0, 0.0, 0.0],
            'properties': {'datetime': '2024-01-01T00:00:00Z'},
            'assets': {
                'data': {'href': 'data.tif', 'title': 'Data'},
            },
            'collection': 'test-collection',
        }

        item = STACItem.from_dict(item_dict)

        assert item.id == 'test-item'
        assert item.collection == 'test-collection'
        assert 'data' in item.assets
        assert item.assets['data'].href == 'data.tif'

    def test_roundtrip(self):
        """Test item can be serialized and deserialized."""
        original_item = STACItem(
            id='test-item',
            geometry={'type': 'Point', 'coordinates': [1.0, 2.0]},
            bbox=[0.5, 1.5, 1.5, 2.5],
            properties={'datetime': '2024-01-01T00:00:00Z', 'key': 'value'},
            assets={'data': STACAsset(href='data.tif', title='Data')},
            collection='test-collection',
        )

        # Serialize to dict
        item_dict = original_item.to_dict()

        # Deserialize from dict
        restored_item = STACItem.from_dict(item_dict)

        assert restored_item.id == original_item.id
        assert restored_item.geometry == original_item.geometry
        assert restored_item.collection == original_item.collection


class TestSTACCollection:
    """Test STACCollection dataclass."""

    def test_basic_collection(self):
        """Test basic collection creation."""
        extent = {
            'spatial': {'bbox': [[-180, -90, 180, 90]]},
            'temporal': {'interval': [[None, None]]},
        }

        collection = STACCollection(
            id='test-collection',
            description='Test collection',
            license='MIT',
            extent=extent,
        )

        assert collection.id == 'test-collection'
        assert collection.description == 'Test collection'
        assert collection.license == 'MIT'
        assert collection.extent == extent

    def test_full_collection(self):
        """Test collection with all fields."""
        extent = {
            'spatial': {'bbox': [[-180, -90, 180, 90]]},
            'temporal': {'interval': [['2024-01-01T00:00:00Z', '2024-12-31T23:59:59Z']]},
        }

        collection = STACCollection(
            id='test-collection',
            description='Test collection',
            license='MIT',
            extent=extent,
            title='Test Collection',
            keywords=['test', 'data'],
            providers=[{'name': 'Test Provider', 'roles': ['producer']}],
        )

        assert collection.title == 'Test Collection'
        assert collection.keywords == ['test', 'data']
        assert len(collection.providers) == 1

    def test_to_dict(self):
        """Test converting collection to dict."""
        extent = {
            'spatial': {'bbox': [[-180, -90, 180, 90]]},
            'temporal': {'interval': [[None, None]]},
        }

        collection = STACCollection(
            id='test-collection',
            description='Test collection',
            license='MIT',
            extent=extent,
        )

        coll_dict = collection.to_dict()

        assert coll_dict['type'] == 'Collection'
        assert coll_dict['stac_version'] == '1.0.0'
        assert coll_dict['id'] == 'test-collection'
        assert 'description' in coll_dict
        assert 'license' in coll_dict
        assert 'extent' in coll_dict

    def test_to_json(self):
        """Test converting collection to JSON string."""
        extent = {
            'spatial': {'bbox': [[-180, -90, 180, 90]]},
            'temporal': {'interval': [[None, None]]},
        }

        collection = STACCollection(
            id='test-collection',
            description='Test collection',
            license='MIT',
            extent=extent,
        )

        json_str = collection.to_json()

        # Should be valid JSON
        parsed = json.loads(json_str)
        assert parsed['id'] == 'test-collection'


class TestSTACCatalog:
    """Test STACCatalog class."""

    def test_initialization(self):
        """Test catalog initialization."""
        catalog = STACCatalog(
            catalog_id='test-catalog',
            description='Test catalog',
        )

        assert catalog.catalog_id == 'test-catalog'
        assert catalog.description == 'Test catalog'
        assert len(catalog.collections) == 0
        assert len(catalog.items) == 0

    def test_add_collection(self):
        """Test adding collection to catalog."""
        catalog = STACCatalog()

        extent = {
            'spatial': {'bbox': [[-180, -90, 180, 90]]},
            'temporal': {'interval': [[None, None]]},
        }
        collection = STACCollection(
            id='test-collection',
            description='Test',
            license='MIT',
            extent=extent,
        )

        catalog.add_collection(collection)

        assert 'test-collection' in catalog.collections
        assert catalog.collections['test-collection'] is collection

    def test_add_item(self):
        """Test adding item to catalog."""
        catalog = STACCatalog()

        item = STACItem(
            id='test-item',
            geometry={'type': 'Point', 'coordinates': [0.0, 0.0]},
            bbox=[0.0, 0.0, 0.0, 0.0],
            properties={'datetime': '2024-01-01T00:00:00Z'},
            assets={'data': STACAsset(href='data.tif')},
        )

        catalog.add_item(item)

        assert 'test-item' in catalog.items
        assert catalog.items['test-item'] is item

    def test_get_collection(self):
        """Test getting collection by ID."""
        catalog = STACCatalog()

        extent = {
            'spatial': {'bbox': [[-180, -90, 180, 90]]},
            'temporal': {'interval': [[None, None]]},
        }
        collection = STACCollection(
            id='test-collection',
            description='Test',
            license='MIT',
            extent=extent,
        )
        catalog.add_collection(collection)

        retrieved = catalog.get_collection('test-collection')
        assert retrieved is collection

        # Non-existent collection
        assert catalog.get_collection('nonexistent') is None

    def test_get_item(self):
        """Test getting item by ID."""
        catalog = STACCatalog()

        item = STACItem(
            id='test-item',
            geometry={'type': 'Point', 'coordinates': [0.0, 0.0]},
            bbox=[0.0, 0.0, 0.0, 0.0],
            properties={'datetime': '2024-01-01T00:00:00Z'},
            assets={'data': STACAsset(href='data.tif')},
        )
        catalog.add_item(item)

        retrieved = catalog.get_item('test-item')
        assert retrieved is item

        # Non-existent item
        assert catalog.get_item('nonexistent') is None

    def test_search_no_filters(self):
        """Test search without filters returns all items."""
        catalog = STACCatalog()

        for i in range(3):
            item = STACItem(
                id=f'item-{i}',
                geometry={'type': 'Point', 'coordinates': [0.0, 0.0]},
                bbox=[0.0, 0.0, 0.0, 0.0],
                properties={'datetime': '2024-01-01T00:00:00Z'},
                assets={'data': STACAsset(href=f'data{i}.tif')},
            )
            catalog.add_item(item)

        results = catalog.search()

        assert len(results) == 3

    def test_search_by_collection(self):
        """Test searching by collection."""
        catalog = STACCatalog()

        # Add items to different collections
        for i in range(2):
            item = STACItem(
                id=f'item-a-{i}',
                geometry={'type': 'Point', 'coordinates': [0.0, 0.0]},
                bbox=[0.0, 0.0, 0.0, 0.0],
                properties={'datetime': '2024-01-01T00:00:00Z'},
                assets={'data': STACAsset(href=f'data{i}.tif')},
                collection='collection-a',
            )
            catalog.add_item(item)

        for i in range(3):
            item = STACItem(
                id=f'item-b-{i}',
                geometry={'type': 'Point', 'coordinates': [0.0, 0.0]},
                bbox=[0.0, 0.0, 0.0, 0.0],
                properties={'datetime': '2024-01-01T00:00:00Z'},
                assets={'data': STACAsset(href=f'data{i}.tif')},
                collection='collection-b',
            )
            catalog.add_item(item)

        # Search for collection-a
        results = catalog.search(collections=['collection-a'])
        assert len(results) == 2
        assert all(item.collection == 'collection-a' for item in results)

    def test_search_by_bbox(self):
        """Test searching by bounding box."""
        catalog = STACCatalog()

        # Item inside search bbox
        item1 = STACItem(
            id='item-inside',
            geometry={'type': 'Point', 'coordinates': [0.0, 0.0]},
            bbox=[-1.0, -1.0, 1.0, 1.0],
            properties={'datetime': '2024-01-01T00:00:00Z'},
            assets={'data': STACAsset(href='data1.tif')},
        )
        catalog.add_item(item1)

        # Item outside search bbox
        item2 = STACItem(
            id='item-outside',
            geometry={'type': 'Point', 'coordinates': [10.0, 10.0]},
            bbox=[9.0, 9.0, 11.0, 11.0],
            properties={'datetime': '2024-01-01T00:00:00Z'},
            assets={'data': STACAsset(href='data2.tif')},
        )
        catalog.add_item(item2)

        # Search within [-2, -2, 2, 2]
        results = catalog.search(bbox=[-2.0, -2.0, 2.0, 2.0])

        assert len(results) == 1
        assert results[0].id == 'item-inside'

    def test_search_by_datetime(self):
        """Test searching by datetime range."""
        catalog = STACCatalog()

        # Item in 2024
        item1 = STACItem(
            id='item-2024',
            geometry={'type': 'Point', 'coordinates': [0.0, 0.0]},
            bbox=[0.0, 0.0, 0.0, 0.0],
            properties={'datetime': '2024-06-01T00:00:00Z'},
            assets={'data': STACAsset(href='data1.tif')},
        )
        catalog.add_item(item1)

        # Item in 2025
        item2 = STACItem(
            id='item-2025',
            geometry={'type': 'Point', 'coordinates': [0.0, 0.0]},
            bbox=[0.0, 0.0, 0.0, 0.0],
            properties={'datetime': '2025-06-01T00:00:00Z'},
            assets={'data': STACAsset(href='data2.tif')},
        )
        catalog.add_item(item2)

        # Search for 2024 only
        start = datetime(2024, 1, 1)
        end = datetime(2024, 12, 31)
        results = catalog.search(datetime_range=(start, end))

        assert len(results) == 1
        assert results[0].id == 'item-2024'

    def test_to_catalog_dict(self):
        """Test exporting catalog to dict."""
        catalog = STACCatalog(
            catalog_id='test-catalog',
            description='Test catalog',
        )

        catalog_dict = catalog.to_catalog_dict()

        assert catalog_dict['type'] == 'Catalog'
        assert catalog_dict['stac_version'] == '1.0.0'
        assert catalog_dict['id'] == 'test-catalog'
        assert catalog_dict['description'] == 'Test catalog'
        assert 'links' in catalog_dict

    def test_export(self):
        """Test exporting catalog to filesystem."""
        catalog = STACCatalog(catalog_id='test-catalog')

        # Add a collection
        extent = {
            'spatial': {'bbox': [[-180, -90, 180, 90]]},
            'temporal': {'interval': [[None, None]]},
        }
        collection = STACCollection(
            id='test-collection',
            description='Test',
            license='MIT',
            extent=extent,
        )
        catalog.add_collection(collection)

        # Add an item
        item = STACItem(
            id='test-item',
            geometry={'type': 'Point', 'coordinates': [0.0, 0.0]},
            bbox=[0.0, 0.0, 0.0, 0.0],
            properties={'datetime': '2024-01-01T00:00:00Z'},
            assets={'data': STACAsset(href='data.tif')},
            collection='test-collection',
        )
        catalog.add_item(item)

        # Export to temp directory
        with tempfile.TemporaryDirectory() as tmpdir:
            catalog.export(tmpdir)

            # Check files exist
            assert os.path.exists(os.path.join(tmpdir, 'catalog.json'))
            assert os.path.exists(os.path.join(tmpdir, 'collections', 'test-collection', 'collection.json'))
            assert os.path.exists(os.path.join(tmpdir, 'collections', 'test-collection', 'items', 'test-item.json'))


class TestHelperFunctions:
    """Test helper functions."""

    def test_create_gravity_map_item(self):
        """Test creating gravity map STAC item."""
        item = create_gravity_map_item(
            gravity_file='/data/gravity.tif',
            bbox=[-10.0, 30.0, 10.0, 50.0],
            datetime_str='2024-01-01T00:00:00Z',
        )

        assert item.id.startswith('gravity-map-')
        assert item.bbox == [-10.0, 30.0, 10.0, 50.0]
        assert item.properties['datetime'] == '2024-01-01T00:00:00Z'
        assert 'data' in item.assets
        assert item.collection == 'gravity-maps'

    def test_create_gravity_map_item_with_metadata(self):
        """Test creating gravity map item with metadata."""
        metadata = {
            'resolution': 1000.0,
            'units': 'mGal',
        }

        item = create_gravity_map_item(
            gravity_file='/data/gravity.tif',
            bbox=[-10.0, 30.0, 10.0, 50.0],
            datetime_str='2024-01-01T00:00:00Z',
            metadata=metadata,
        )

        assert item.properties['resolution'] == 1000.0
        assert item.properties['units'] == 'mGal'

    def test_create_gravity_collection(self):
        """Test creating gravity collection."""
        collection = create_gravity_collection(
            collection_id='my-gravity',
            title='My Gravity Maps',
            description='Custom gravity maps',
        )

        assert collection.id == 'my-gravity'
        assert collection.title == 'My Gravity Maps'
        assert collection.description == 'Custom gravity maps'
        assert collection.license == 'proprietary'
        assert 'spatial' in collection.extent
        assert 'temporal' in collection.extent

    def test_create_gravity_collection_with_extent(self):
        """Test creating collection with custom extent."""
        temporal_extent = ['2024-01-01T00:00:00Z', '2024-12-31T23:59:59Z']
        spatial_extent = [-180.0, -90.0, 180.0, 90.0]

        collection = create_gravity_collection(
            temporal_extent=temporal_extent,
            spatial_extent=spatial_extent,
        )

        assert collection.extent['temporal']['interval'][0] == temporal_extent
        assert collection.extent['spatial']['bbox'][0] == spatial_extent

    def test_create_gravity_collection_keywords(self):
        """Test that gravity collection has keywords."""
        collection = create_gravity_collection()

        assert collection.keywords is not None
        assert 'gravity' in collection.keywords
        assert 'geophysics' in collection.keywords


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
