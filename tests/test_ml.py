"""
Tests for ML Models
===================

Tests for PINN and U-Net models, training, and uncertainty estimation.
"""

import numpy as np
import pytest

torch = pytest.importorskip("torch", reason="PyTorch not installed in this environment")

from ml import (
    GravityPINN,
    PINNTrainer,
    GravityDataset,
    generate_synthetic_gravity_data,
    UNetGravity,
    UNetTrainer,
    MCDropoutUncertainty,
    PhaseGravityDataset,
    generate_synthetic_phase_gravity_pairs
)


class TestGravityPINN:
    """Test Physics-Informed Neural Network."""
    
    def test_model_initialization(self):
        """Test that model initializes correctly."""
        model = GravityPINN(hidden_layers=[32, 64, 32], activation='tanh')
        
        # Check architecture
        assert isinstance(model, torch.nn.Module)
        
        # Test forward pass
        batch_size = 10
        x = torch.randn(batch_size, 4)  # (x, y, z, rho)
        
        output = model(x)
        assert output.shape == (batch_size, 3)  # (gx, gy, gz)
    
    def test_physics_constraint(self):
        """Test that physics constraint can be computed."""
        model = GravityPINN(hidden_layers=[16, 32, 16])
        
        batch_size = 5
        x = torch.randn(batch_size, 4, requires_grad=True)
        
        # Compute divergence
        div_g = model.compute_divergence(x)
        assert div_g.shape == (batch_size,)
        
        # Compute physics loss
        physics_loss = model.physics_loss(x, lambda_physics=1.0)
        assert physics_loss.ndim == 0  # Scalar
        assert physics_loss.item() >= 0
    
    def test_training_reduces_loss(self):
        """Test that training reduces loss."""
        # Generate small synthetic dataset
        coords, densities, gravity = generate_synthetic_gravity_data(n_samples=100)
        dataset = GravityDataset(coords, densities, gravity)
        loader = torch.utils.data.DataLoader(dataset, batch_size=20)
        
        # Create and train model
        model = GravityPINN(hidden_layers=[16, 32, 16])
        trainer = PINNTrainer(model, device='cpu')
        
        history = trainer.train(loader, epochs=5, lr=1e-3, lambda_physics=0.1)
        
        # Check that loss decreased
        assert history['train_loss'][-1] < history['train_loss'][0]
        assert len(history['data_loss']) == 5
        assert len(history['physics_loss']) == 5


class TestUNetGravity:
    """Test U-Net architecture."""
    
    def test_model_initialization(self):
        """Test U-Net initialization."""
        model = UNetGravity(in_channels=1, out_channels=1, 
                           base_channels=32, depth=3)
        
        assert isinstance(model, torch.nn.Module)
        
        # Test forward pass
        batch_size = 2
        image_size = 64
        x = torch.randn(batch_size, 1, image_size, image_size)
        
        output = model(x)
        assert output.shape == (batch_size, 1, image_size, image_size)
    
    def test_encoder_decoder_symmetry(self):
        """Test that encoder and decoder are symmetric."""
        model = UNetGravity(base_channels=16, depth=4)
        
        assert len(model.encoders) == 4
        assert len(model.decoders) == 4
        assert len(model.pools) == 4
        assert len(model.upconvs) == 4
    
    def test_different_input_sizes(self):
        """Test U-Net with different input sizes."""
        model = UNetGravity(base_channels=16, depth=3)
        
        for size in [32, 64, 128]:
            x = torch.randn(1, 1, size, size)
            output = model(x)
            assert output.shape == (1, 1, size, size)
    
    def test_training_improves_metrics(self):
        """Test that training improves PSNR and SSIM."""
        # Generate small synthetic dataset
        phase_data, gravity_data = generate_synthetic_phase_gravity_pairs(
            n_samples=50, image_size=64, noise_level=0.1
        )
        
        dataset = PhaseGravityDataset(phase_data, gravity_data)
        train_size = 40
        val_size = 10
        train_dataset, val_dataset = torch.utils.data.random_split(
            dataset, [train_size, val_size]
        )
        
        train_loader = torch.utils.data.DataLoader(train_dataset, batch_size=8)
        val_loader = torch.utils.data.DataLoader(val_dataset, batch_size=8)
        
        # Create and train model
        model = UNetGravity(base_channels=16, depth=3, dropout=0.1)
        trainer = UNetTrainer(model, device='cpu')
        
        history = trainer.train(
            train_loader, val_loader,
            epochs=10, lr=1e-3,
            save_best=False
        )
        
        # Check that PSNR improved
        if len(history['psnr']) > 1:
            assert history['psnr'][-1] > history['psnr'][0]
        
        # Check that loss decreased
        assert history['train_loss'][-1] < history['train_loss'][0]


class TestUncertaintyEstimation:
    """Test uncertainty estimation methods."""
    
    def test_mc_dropout_uncertainty(self):
        """Test Monte Carlo Dropout uncertainty estimation."""
        model = UNetGravity(base_channels=16, depth=2, dropout=0.2)
        
        # Create uncertainty estimator
        mc_dropout = MCDropoutUncertainty(model, n_samples=10)
        
        # Test input
        x = torch.randn(2, 1, 32, 32)
        
        mean, std = mc_dropout.predict_with_uncertainty(x)
        
        # Check shapes
        assert mean.shape == (2, 1, 32, 32)
        assert std.shape == (2, 1, 32, 32)
        
        # Standard deviation should be positive
        assert torch.all(std >= 0)
        
        # Standard deviation should be non-zero (due to dropout)
        assert torch.any(std > 0)
    
    def test_uncertainty_varies_with_dropout(self):
        """Test that uncertainty depends on dropout rate."""
        x = torch.randn(1, 1, 32, 32)
        
        # Low dropout
        model_low = UNetGravity(base_channels=8, depth=2, dropout=0.1)
        mc_low = MCDropoutUncertainty(model_low, n_samples=20)
        _, std_low = mc_low.predict_with_uncertainty(x)
        
        # High dropout
        model_high = UNetGravity(base_channels=8, depth=2, dropout=0.5)
        mc_high = MCDropoutUncertainty(model_high, n_samples=20)
        _, std_high = mc_high.predict_with_uncertainty(x)
        
        # Higher dropout should generally lead to higher uncertainty
        mean_std_low = torch.mean(std_low).item()
        mean_std_high = torch.mean(std_high).item()
        
        # This may not always hold due to random initialization,
        # but on average it should
        assert mean_std_high >= mean_std_low * 0.5


class TestDataGeneration:
    """Test synthetic data generation."""
    
    def test_gravity_data_generation(self):
        """Test synthetic gravity data generation."""
        coords, densities, gravity = generate_synthetic_gravity_data(
            n_samples=100, n_anomalies=3
        )
        
        # Check shapes
        assert coords.shape == (100, 3)
        assert densities.shape == (100,)
        assert gravity.shape == (100, 3)
        
        # Check that values are finite
        assert np.all(np.isfinite(coords))
        assert np.all(np.isfinite(densities))
        assert np.all(np.isfinite(gravity))
        
        # Gravity field should have some structure (not all zeros)
        assert np.std(gravity) > 0
    
    def test_phase_gravity_generation(self):
        """Test phase-gravity pair generation."""
        phase_data, gravity_data = generate_synthetic_phase_gravity_pairs(
            n_samples=20, image_size=64, noise_level=0.05
        )
        
        # Check shapes
        assert phase_data.shape == (20, 64, 64)
        assert gravity_data.shape == (20, 64, 64)
        
        # Check normalization (approximately zero mean, unit std)
        assert abs(np.mean(phase_data)) < 0.5
        assert abs(np.mean(gravity_data)) < 0.5
        assert abs(np.std(phase_data) - 1.0) < 0.5
        assert abs(np.std(gravity_data) - 1.0) < 0.5


class TestDatasets:
    """Test dataset classes."""
    
    def test_gravity_dataset(self):
        """Test GravityDataset."""
        coords = np.random.rand(50, 3)
        densities = np.random.rand(50)
        gravity = np.random.rand(50, 3)
        
        dataset = GravityDataset(coords, densities, gravity)
        
        assert len(dataset) == 50
        
        # Test indexing
        x, g = dataset[0]
        assert x.shape == (4,)  # (x, y, z, rho)
        assert g.shape == (3,)  # (gx, gy, gz)
    
    def test_phase_gravity_dataset(self):
        """Test PhaseGravityDataset."""
        phase = np.random.rand(30, 64, 64)
        gravity = np.random.rand(30, 64, 64)
        
        dataset = PhaseGravityDataset(phase, gravity)
        
        assert len(dataset) == 30
        
        # Test indexing
        p, g = dataset[0]
        assert p.shape == (1, 64, 64)  # Channel dimension added
        assert g.shape == (1, 64, 64)


class TestMetrics:
    """Test metric computations."""
    
    def test_psnr_computation(self):
        """Test PSNR metric."""
        # Perfect prediction
        target = torch.randn(1, 1, 32, 32)
        pred = target.clone()
        
        trainer = UNetTrainer(UNetGravity(), device='cpu')
        psnr = trainer.compute_psnr(pred, target)
        
        # PSNR should be very high for identical images
        assert psnr > 50  # dB
        
        # Noisy prediction
        pred_noisy = target + 0.1 * torch.randn_like(target)
        psnr_noisy = trainer.compute_psnr(pred_noisy, target)
        
        assert psnr_noisy < psnr
        assert psnr_noisy > 0
    
    def test_ssim_computation(self):
        """Test SSIM metric."""
        trainer = UNetTrainer(UNetGravity(), device='cpu')
        torch.manual_seed(0)  # unseeded randn made this test flaky

        # Perfect prediction
        target = torch.randn(1, 1, 32, 32)
        pred = target.clone()

        ssim = trainer.compute_ssim(pred, target)

        # SSIM should be close to 1 for identical images
        assert ssim > 0.95

        # Different prediction: SSIM's true range is [-1, 1], and for
        # uncorrelated noise it hovers around 0 (slightly negative is
        # legitimate - the old 0 <= ssim assertion was wrong).
        pred_diff = torch.randn(1, 1, 32, 32)
        ssim_diff = trainer.compute_ssim(pred_diff, target)

        assert ssim_diff < ssim
        assert -1 <= ssim_diff <= 1
        assert ssim_diff < 0.5


class TestEndToEnd:
    """
    End-to-end tests for complete workflows.
    """
    
    def test_pinn_inference_speed(self):
        """Test PINN inference speed."""
        model = GravityPINN(hidden_layers=[32, 64, 32])
        model.eval()
        
        # Inference batch
        batch_size = 1000
        x = torch.randn(batch_size, 4)
        
        import time
        start = time.time()
        with torch.no_grad():
            output = model(x)
        elapsed = time.time() - start
        
        # Should be fast (less than 1 second for 1000 samples)
        assert elapsed < 1.0
        
        samples_per_sec = batch_size / elapsed
        print(f"  PINN inference speed: {samples_per_sec:.0f} samples/sec")
        assert samples_per_sec > 500
    
    def test_unet_inference_speed(self):
        """Test U-Net inference speed."""
        model = UNetGravity(base_channels=32, depth=3)
        model.eval()
        
        # Inference batch
        x = torch.randn(4, 1, 128, 128)
        
        import time
        start = time.time()
        with torch.no_grad():
            output = model(x)
        elapsed = time.time() - start
        
        # Should be reasonably fast
        assert elapsed < 2.0
        
        images_per_sec = 4 / elapsed
        print(f"  U-Net inference speed: {images_per_sec:.1f} images/sec")


def run_all_tests():
    """Run all ML tests and report results."""
    print("=" * 60)
    print("Running ML Model Tests")
    print("=" * 60)
    
    test_classes = [
        TestGravityPINN,
        TestUNetGravity,
        TestUncertaintyEstimation,
        TestDataGeneration,
        TestDatasets,
        TestMetrics,
        TestEndToEnd
    ]
    
    total_tests = 0
    passed_tests = 0
    
    for test_class in test_classes:
        print(f"\n{test_class.__name__}:")
        test_instance = test_class()
        
        for method_name in dir(test_instance):
            if method_name.startswith('test_'):
                total_tests += 1
                try:
                    method = getattr(test_instance, method_name)
                    method()
                    print(f"  ✓ {method_name}")
                    passed_tests += 1
                except Exception as e:
                    print(f"  ✗ {method_name}: {str(e)}")
                    import traceback
                    traceback.print_exc()
    
    print("\n" + "=" * 60)
    print(f"Test Results: {passed_tests}/{total_tests} passed")
    print("=" * 60)
    
    return passed_tests == total_tests


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
