"""
Tests for Synthetic Data Generator

Validates deterministic outputs, schema compliance, and data integrity.
"""

import pytest
import numpy as np
import pandas as pd
import json
from pathlib import Path
from datetime import datetime
import tempfile
import shutil
from typing import Dict, Any

import sys
sys.path.append('/home/claude')

from sim.synthetic import (
    SimulationConfig, SatelliteConfig, SubsurfaceModel,
    ForwardModel, TelemetryGenerator, STACMetadataGenerator,
    SyntheticDataGenerator, Anomaly
)


class TestDeterministicOutput:
    """Test deterministic behavior with fixed seeds"""
    
    def test_subsurface_deterministic(self):
        """Test that subsurface model is deterministic with seed"""
        config = SimulationConfig(grid_size=(50, 50, 25), seed=42)
        
        # Generate two models with same seed
        model1 = SubsurfaceModel(config, seed=42)
        model1.add_void()
        model1.add_tunnel()
        model1.add_ore_body()
        
        model2 = SubsurfaceModel(config, seed=42)
        model2.add_void()
        model2.add_tunnel()
        model2.add_ore_body()
        
        # Density fields should be identical
        np.testing.assert_array_equal(
            model1.density_field,
            model2.density_field,
            "Density fields not identical with same seed"
        )
        
        # Anomalies should have same properties
        assert len(model1.anomalies) == len(model2.anomalies)
        for a1, a2 in zip(model1.anomalies, model2.anomalies):
            assert a1.type == a2.type
            np.testing.assert_array_almost_equal(a1.center, a2.center)
            np.testing.assert_array_almost_equal(a1.size, a2.size)
            assert a1.density_contrast == a2.density_contrast
            
    def test_forward_model_deterministic(self):
        """Test forward model determinism"""
        sim_config = SimulationConfig(grid_size=(30, 30, 15), seed=123)
        sat_config = SatelliteConfig()
        
        # Create identical subsurface models
        subsurface1 = SubsurfaceModel(sim_config, seed=123)
        subsurface1.add_void()
        
        subsurface2 = SubsurfaceModel(sim_config, seed=123)
        subsurface2.add_void()
        
        # Run forward models
        forward1 = ForwardModel(subsurface1, sat_config, sim_config)
        forward2 = ForwardModel(subsurface2, sat_config, sim_config)
        
        # Compare outputs
        g1 = forward1.density_to_gravity()
        g2 = forward2.density_to_gravity()
        np.testing.assert_array_almost_equal(g1, g2, decimal=10)
        
        baselines1 = forward1.gravity_to_baseline(g1, 10)
        baselines2 = forward2.gravity_to_baseline(g2, 10)
        np.testing.assert_array_almost_equal(baselines1, baselines2, decimal=10)
        
        phases1 = forward1.baseline_to_phase(baselines1)
        phases2 = forward2.baseline_to_phase(baselines2)
        np.testing.assert_array_almost_equal(phases1, phases2, decimal=10)
        
        # Even noise should be deterministic with seed
        noisy1 = forward1.add_noise(phases1)
        noisy2 = forward2.add_noise(phases2)
        np.testing.assert_array_almost_equal(noisy1, noisy2, decimal=10)
        
    def test_telemetry_deterministic(self):
        """Test telemetry generation determinism"""
        config = SimulationConfig(seed=456)
        gen1 = TelemetryGenerator(config)
        gen2 = TelemetryGenerator(config)
        
        # Create test phase data
        phases = np.random.randn(10, 20, 20)
        start_time = datetime(2024, 1, 1)
        
        # Generate telemetry
        telemetry1 = gen1.generate_telemetry(phases, start_time)
        telemetry2 = gen2.generate_telemetry(phases, start_time)
        
        # Should be identical
        pd.testing.assert_frame_equal(telemetry1, telemetry2)
        
    def test_full_pipeline_deterministic(self):
        """Test complete pipeline determinism"""
        sim_config = SimulationConfig(
            grid_size=(20, 20, 10),
            time_steps=5,
            seed=789
        )
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Run pipeline twice
            gen1 = SyntheticDataGenerator(sim_config)
            results1 = gen1.generate(tmpdir)
            
            gen2 = SyntheticDataGenerator(sim_config)
            results2 = gen2.generate(tmpdir)
            
            # Load and compare phase data
            data1 = np.load(results1['phase_path'])
            data2 = np.load(results2['phase_path'])
            
            for key in data1.files:
                np.testing.assert_array_almost_equal(
                    data1[key], data2[key], decimal=8,
                    err_msg=f"Array {key} not deterministic"
                )


class TestSchemaValidation:
    """Test data schema compliance"""
    
    def test_telemetry_schema(self):
        """Validate telemetry DataFrame schema"""
        config = SimulationConfig(grid_size=(10, 10, 5), time_steps=3)
        gen = TelemetryGenerator(config)
        
        phases = np.random.randn(3, 10, 10)
        telemetry = gen.generate_telemetry(phases, datetime.now())
        
        # Required columns
        required_columns = [
            'timestamp', 'pixel_x', 'pixel_y', 'phase',
            'coherence', 'snr', 'satellite_id', 
            'pass_direction', 'incidence_angle', 'quality_flag'
        ]
        
        assert all(col in telemetry.columns for col in required_columns), \
            f"Missing columns. Expected: {required_columns}, Got: {list(telemetry.columns)}"
        
        # Data types
        assert pd.api.types.is_datetime64_any_dtype(telemetry['timestamp'])
        assert pd.api.types.is_integer_dtype(telemetry['pixel_x'])
        assert pd.api.types.is_integer_dtype(telemetry['pixel_y'])
        assert pd.api.types.is_float_dtype(telemetry['phase'])
        assert pd.api.types.is_float_dtype(telemetry['coherence'])
        assert pd.api.types.is_float_dtype(telemetry['snr'])
        # pandas >= 3 infers a dedicated 'str' dtype; pandas 2 uses object
        def _is_stringlike(col):
            return (pd.api.types.is_object_dtype(col)
                    or pd.api.types.is_string_dtype(col))

        assert _is_stringlike(telemetry['satellite_id'])
        assert _is_stringlike(telemetry['pass_direction'])
        assert pd.api.types.is_float_dtype(telemetry['incidence_angle'])
        assert pd.api.types.is_integer_dtype(telemetry['quality_flag'])
        
        # Value ranges
        assert telemetry['coherence'].between(0, 1).all()
        assert telemetry['snr'].min() > 0
        assert telemetry['quality_flag'].isin([0, 1, 2]).all()
        assert telemetry['pass_direction'].isin(['ascending', 'descending']).all()
        
    def test_stac_collection_schema(self):
        """Validate STAC Collection metadata"""
        stac = STACMetadataGenerator("test_sim")
        config = SimulationConfig()
        anomalies = [
            Anomaly('void', np.array([0, 0, 0]), np.array([1, 1, 1]), -1000, {})
        ]
        
        collection = stac.generate_collection(config, anomalies)
        
        # Required STAC fields
        assert collection['stac_version'] == "1.0.0"
        assert collection['type'] == "Collection"
        assert 'id' in collection
        assert 'title' in collection
        assert 'description' in collection
        assert 'license' in collection
        assert 'extent' in collection
        assert 'summaries' in collection
        assert 'links' in collection
        
        # Extent structure
        assert 'spatial' in collection['extent']
        assert 'temporal' in collection['extent']
        assert 'bbox' in collection['extent']['spatial']
        assert 'interval' in collection['extent']['temporal']
        
        # Summaries content
        assert 'anomaly_count' in collection['summaries']
        assert collection['summaries']['anomaly_count'] == len(anomalies)
        
    def test_stac_item_schema(self):
        """Validate STAC Item metadata"""
        stac = STACMetadataGenerator("test_sim")
        item = stac.generate_item(
            "data.parquet",
            datetime.now(),
            [-180.0, -90.0, 180.0, 90.0]
        )
        
        # Required STAC Item fields
        assert item['stac_version'] == "1.0.0"
        assert item['type'] == "Feature"
        assert 'id' in item
        assert 'geometry' in item
        assert 'bbox' in item
        assert 'properties' in item
        assert 'assets' in item
        assert 'links' in item
        
        # Geometry validation
        assert item['geometry']['type'] == "Polygon"
        assert 'coordinates' in item['geometry']
        
        # Properties validation
        props = item['properties']
        assert 'datetime' in props
        assert 'platform' in props
        assert 'instruments' in props
        assert 'sar:frequency_band' in props
        assert 'sar:polarizations' in props
        
        # Assets validation
        assert 'data' in item['assets']
        assert 'href' in item['assets']['data']
        assert 'type' in item['assets']['data']
        
    def test_dataset_card_schema(self):
        """Validate dataset card structure"""
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = SyntheticDataGenerator(
                SimulationConfig(grid_size=(10, 10, 5), time_steps=3)
            )
            results = gen.generate(tmpdir)
            
            # Load dataset card
            with open(results['card_path'], 'r') as f:
                card = json.load(f)
                
            # Required fields
            assert 'name' in card
            assert 'version' in card
            assert 'created' in card
            assert 'description' in card
            assert 'configuration' in card
            assert 'anomalies' in card
            assert 'statistics' in card
            assert 'schema' in card
            
            # Configuration structure
            assert 'simulation' in card['configuration']
            assert 'satellite' in card['configuration']
            
            # Statistics structure
            stats = card['statistics']
            assert 'telemetry' in stats
            assert 'num_records' in stats['telemetry']
            assert 'time_range' in stats['telemetry']
            assert 'phase_range' in stats['telemetry']


class TestDataIntegrity:
    """Test data consistency and physical validity"""
    
    def test_anomaly_placement(self):
        """Test that anomalies are placed within grid bounds"""
        config = SimulationConfig(grid_size=(50, 50, 25))
        model = SubsurfaceModel(config, seed=42)
        
        # Add multiple anomalies
        for _ in range(10):
            model.add_void()
            model.add_ore_body()
            
        # Check all anomalies are within bounds
        grid_max = np.array(config.grid_size) * config.grid_spacing
        
        for anomaly in model.anomalies:
            assert all(anomaly.center >= 0), "Anomaly center has negative coordinates"
            assert all(anomaly.center <= grid_max), "Anomaly center outside grid"
            
    def test_density_field_validity(self):
        """Test density field physical validity"""
        config = SimulationConfig(grid_size=(30, 30, 15))
        model = SubsurfaceModel(config, seed=42)
        
        # Add anomalies
        model.add_void()  # Should decrease density
        model.add_ore_body()  # Should increase density
        
        # Check density ranges
        assert model.density_field.min() > 0, "Negative density found"
        assert model.density_field.max() < 10000, "Unrealistic high density"
        
        # Check that voids decrease density
        baseline = SubsurfaceModel(config, seed=42)
        void_mask = model.density_field < baseline.density_field
        assert void_mask.any(), "Void didn't decrease density"
        
    def test_phase_continuity(self):
        """Test phase measurements are continuous in time"""
        sim_config = SimulationConfig(
            grid_size=(20, 20, 10),
            time_steps=10,
            noise_level=0.01  # Low noise for testing
        )
        
        subsurface = SubsurfaceModel(sim_config, seed=42)
        subsurface.add_void()
        
        forward = ForwardModel(subsurface, SatelliteConfig(), sim_config)
        g_field = forward.density_to_gravity()
        baselines = forward.gravity_to_baseline(g_field, sim_config.time_steps)
        phases = forward.baseline_to_phase(baselines)
        
        # Check phase continuity (no huge jumps)
        phase_diff = np.diff(phases, axis=0)
        max_jump = np.abs(phase_diff).max()
        
        assert max_jump < np.pi, "Phase jumps detected (possible unwrapping issue)"
        
    def test_telemetry_consistency(self):
        """Test telemetry data internal consistency"""
        config = SimulationConfig(grid_size=(10, 10, 5), time_steps=5)
        gen = TelemetryGenerator(config)
        
        phases = np.random.randn(5, 10, 10) * 0.5
        telemetry = gen.generate_telemetry(phases, datetime(2024, 1, 1))
        
        # Check pixel coordinates are valid
        assert telemetry['pixel_x'].min() >= 0
        assert telemetry['pixel_x'].max() < 10
        assert telemetry['pixel_y'].min() >= 0
        assert telemetry['pixel_y'].max() < 10
        
        # Check timestamps are sequential
        unique_times = telemetry['timestamp'].unique()
        assert len(unique_times) == 5
        time_diffs = np.diff(sorted(unique_times))
        expected_diff = pd.Timedelta(days=1)
        assert all(td == expected_diff for td in time_diffs)
        
    def test_gravity_field_symmetry(self):
        """Test gravity field has expected symmetries"""
        # Disable random layer noise so the test isolates the symmetry
        # of the forward kernel's response to a symmetric source.
        config = SimulationConfig(grid_size=(40, 40, 20), layer_variation=0.0)
        model = SubsurfaceModel(config, seed=42)

        # Add centered spherical void
        center = np.array([20, 20, 10]) * config.grid_spacing
        model.add_void(center=center, size=np.array([20, 20, 20]))
        
        forward = ForwardModel(model, SatelliteConfig(), config)
        g_field = forward.density_to_gravity()
        
        # Should be approximately symmetric around center
        mid = 20
        tolerance = 0.1  # 10% tolerance
        
        # Check x-symmetry
        left = g_field[:mid, mid]
        right = g_field[mid:, mid][::-1]
        assert np.allclose(left, right, rtol=tolerance), "Gravity field not x-symmetric"
        
        # Check y-symmetry
        top = g_field[mid, :mid]
        bottom = g_field[mid, mid:][::-1]
        assert np.allclose(top, bottom, rtol=tolerance), "Gravity field not y-symmetric"


class TestFileIO:
    """Test file I/O operations"""
    
    def test_parquet_save_load(self):
        """Test Parquet file save/load cycle"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = SimulationConfig(grid_size=(10, 10, 5), time_steps=3)
            gen = SyntheticDataGenerator(config)
            results = gen.generate(tmpdir)
            
            # Load saved parquet file
            telemetry = pd.read_parquet(results['telemetry_path'])
            
            assert len(telemetry) > 0, "Empty telemetry data"
            assert 'phase' in telemetry.columns
            
    def test_npz_save_load(self):
        """Test NumPy compressed file save/load"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = SimulationConfig(grid_size=(10, 10, 5), time_steps=3)
            gen = SyntheticDataGenerator(config)
            results = gen.generate(tmpdir)
            
            # Load saved NPZ file
            data = np.load(results['phase_path'])
            
            assert 'phases' in data
            assert 'noisy_phases' in data
            assert 'gravity_field' in data
            assert 'baselines' in data
            assert 'density_field' in data
            
            # Check shapes
            assert data['phases'].shape[0] == config.time_steps
            assert data['density_field'].shape == config.grid_size
            
    def test_json_metadata_valid(self):
        """Test JSON metadata files are valid"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = SimulationConfig(grid_size=(10, 10, 5), time_steps=3)
            gen = SyntheticDataGenerator(config)
            results = gen.generate(tmpdir)
            
            # Load and validate each JSON file
            json_files = ['collection_path', 'item_path', 'card_path']
            
            for file_key in json_files:
                with open(results[file_key], 'r') as f:
                    data = json.load(f)  # Should not raise
                    assert isinstance(data, dict), f"{file_key} is not a dict"


class TestParameterValidation:
    """Test parameter validation and edge cases"""
    
    def test_invalid_grid_size(self):
        """Test handling of invalid grid sizes"""
        # Negative dimensions should be caught
        with pytest.raises(Exception):
            config = SimulationConfig(grid_size=(-10, 10, 10))
            model = SubsurfaceModel(config)
            
    def test_zero_timesteps(self):
        """Test handling of zero time steps"""
        config = SimulationConfig(time_steps=0)
        gen = TelemetryGenerator(config)
        
        phases = np.zeros((0, 10, 10))
        telemetry = gen.generate_telemetry(phases, datetime.now())
        
        assert len(telemetry) == 0, "Should handle zero timesteps gracefully"
        
    def test_extreme_noise_levels(self):
        """Test extreme noise levels"""
        # Very high noise
        config = SimulationConfig(noise_level=10.0, seed=42)
        model = SubsurfaceModel(config, seed=42)
        forward = ForwardModel(model, SatelliteConfig(), config)
        
        phases = np.ones((5, 10, 10))
        noisy = forward.add_noise(phases)
        
        # Should still be finite
        assert np.all(np.isfinite(noisy)), "Non-finite values with high noise"
        
        # Very low noise
        config.noise_level = 1e-10
        forward2 = ForwardModel(model, SatelliteConfig(), config)
        noisy2 = forward2.add_noise(phases)
        
        # Should be close to original
        assert np.allclose(noisy2, phases, rtol=1e-6), "Low noise not working"


class TestPhysicalRealism:
    """Test physical realism of generated data"""
    
    def test_gravity_magnitude(self):
        """Test gravity field magnitudes are realistic"""
        config = SimulationConfig(grid_size=(30, 30, 15))
        model = SubsurfaceModel(config, seed=42)
        
        # Add large void
        model.add_void(size=np.array([100, 100, 50]))
        
        forward = ForwardModel(model, SatelliteConfig(), config)
        g_field = forward.density_to_gravity()
        
        # Gravity anomalies should be in microGal range
        g_max = np.abs(g_field).max()
        assert g_max < 1e-3, f"Gravity anomaly too large: {g_max}"
        assert g_max > 1e-10, f"Gravity anomaly too small: {g_max}"
        
    def test_baseline_variations(self):
        """Test baseline variations are realistic"""
        config = SimulationConfig(time_steps=100)
        sat_config = SatelliteConfig(
            baseline_nominal=200.0,
            baseline_variation=10.0
        )
        
        model = SubsurfaceModel(config, seed=42)
        forward = ForwardModel(model, sat_config, config)
        
        g_field = forward.density_to_gravity()
        baselines = forward.gravity_to_baseline(g_field, config.time_steps)
        
        # Check baseline statistics
        mean_baseline = baselines.mean()
        std_baseline = baselines.std()
        
        assert abs(mean_baseline - 200.0) < 50, "Mean baseline too far from nominal"
        assert std_baseline < 50, "Baseline variations too large"
        assert std_baseline > 0.1, "Baseline variations too small"
        
    def test_coherence_distribution(self):
        """Test interferometric coherence has realistic distribution"""
        config = SimulationConfig(grid_size=(20, 20, 10), time_steps=10)
        gen = TelemetryGenerator(config)
        
        phases = np.random.randn(10, 20, 20)
        telemetry = gen.generate_telemetry(phases, datetime.now())
        
        coherence = telemetry['coherence']
        
        # Should be between 0 and 1
        assert coherence.min() >= 0.0
        assert coherence.max() <= 1.0
        
        # Most values should be high (good coherence)
        assert coherence.mean() > 0.7
        assert coherence.median() > 0.75


def run_all_tests():
    """Run all tests and report results"""
    import unittest
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test classes
    test_classes = [
        TestDeterministicOutput,
        TestSchemaValidation,
        TestDataIntegrity,
        TestFileIO,
        TestParameterValidation,
        TestPhysicalRealism
    ]
    
    for test_class in test_classes:
        tests = loader.loadTestsFromTestCase(test_class)
        suite.addTests(tests)
        
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Success rate: {100*(1-len(result.failures+result.errors)/result.testsRun):.1f}%")
    
    return result.wasSuccessful()


if __name__ == "__main__":
    # Run with pytest if available, otherwise use unittest
    try:
        import pytest
        pytest.main([__file__, "-v", "--tb=short"])
    except ImportError:
        success = run_all_tests()
        sys.exit(0 if success else 1)
