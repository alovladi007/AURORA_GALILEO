"""
Tests for Inversion Neural Networks.
"""

import pytest
import numpy as np

try:
    import torch
    from ml.models.inversion import (
        InversionNN,
        GravityInversionNN,
        MagneticInversionNN,
        JointInversionNN,
        EnsembleInversionNN,
    )
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False


@pytest.mark.skipif(not HAS_TORCH, reason="PyTorch not available")
class TestInversionNN:
    """Test basic inversion network."""
    
    def test_initialization(self):
        """Test inversion NN initialization."""
        model = InversionNN(
            n_observations=100,
            n_model_params=900,
            hidden_layers=[256, 256],
        )
        
        assert model.n_observations == 100
        assert model.n_model_params == 900
    
    def test_forward_pass(self):
        """Test forward propagation."""
        model = InversionNN(n_observations=100, n_model_params=900)
        observations = torch.randn(10, 100)
        
        model_params = model(observations)
        
        assert model_params.shape == (10, 900)
    
    def test_uncertainty_prediction(self):
        """Test MC Dropout uncertainty."""
        model = InversionNN(
            n_observations=100,
            n_model_params=900,
            dropout=0.1,
        )
        observations = torch.randn(5, 100)
        
        mean, std = model.predict_with_uncertainty(observations, n_samples=10)
        
        assert mean.shape == (5, 900)
        assert std.shape == (5, 900)
        assert torch.all(std >= 0)


@pytest.mark.skipif(not HAS_TORCH, reason="PyTorch not available")
class TestGravityInversionNN:
    """Test gravity inversion network."""
    
    def test_initialization(self):
        """Test gravity inversion initialization."""
        model = GravityInversionNN(
            n_gravity_obs=100,
            grid_shape=(30, 30),
        )
        
        assert model.grid_shape == (30, 30)
        assert model.n_model_params == 900
    
    def test_output_shape(self):
        """Test output is properly reshaped to grid."""
        model = GravityInversionNN(
            n_gravity_obs=100,
            grid_shape=(30, 30),
        )
        observations = torch.randn(5, 100)
        
        density = model(observations)
        
        assert density.shape == (5, 30, 30)


@pytest.mark.skipif(not HAS_TORCH, reason="PyTorch not available")
class TestJointInversionNN:
    """Test joint inversion network."""
    
    def test_initialization(self):
        """Test joint inversion initialization."""
        model = JointInversionNN(
            n_gravity_obs=100,
            n_magnetic_obs=100,
            grid_shape=(30, 30),
        )
        
        assert model.grid_shape == (30, 30)
    
    def test_forward_pass(self):
        """Test joint inversion forward pass."""
        model = JointInversionNN(
            n_gravity_obs=100,
            n_magnetic_obs=100,
            grid_shape=(30, 30),
        )
        
        gravity_obs = torch.randn(5, 100)
        magnetic_obs = torch.randn(5, 100)
        
        result = model(gravity_obs, magnetic_obs)
        
        assert 'density' in result
        assert 'susceptibility' in result
        assert result['density'].shape == (5, 30, 30)
        assert result['susceptibility'].shape == (5, 30, 30)


@pytest.mark.skipif(not HAS_TORCH, reason="PyTorch not available")
class TestEnsembleInversionNN:
    """Test ensemble inversion."""
    
    def test_initialization(self):
        """Test ensemble initialization."""
        model = EnsembleInversionNN(
            n_observations=100,
            n_model_params=900,
            n_models=3,
        )
        
        assert model.n_models == 3
        assert len(model.models) == 3
    
    def test_forward_pass(self):
        """Test ensemble forward pass (returns mean)."""
        model = EnsembleInversionNN(
            n_observations=100,
            n_model_params=900,
            n_models=3,
        )
        observations = torch.randn(5, 100)
        
        output = model(observations)
        
        assert output.shape == (5, 900)
    
    def test_uncertainty_quantification(self):
        """Test ensemble uncertainty quantification."""
        model = EnsembleInversionNN(
            n_observations=100,
            n_model_params=900,
            n_models=5,
        )
        observations = torch.randn(5, 100)
        
        mean, std = model.predict_with_uncertainty(observations)
        
        assert mean.shape == (5, 900)
        assert std.shape == (5, 900)
        assert torch.all(std >= 0)


@pytest.mark.skipif(not HAS_TORCH, reason="PyTorch not available")
def test_inversion_training():
    """Test inversion network can be trained."""
    model = GravityInversionNN(
        n_gravity_obs=100,
        grid_shape=(30, 30),
        hidden_layers=[128, 128],
    )
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    
    # Synthetic data
    gravity_obs = torch.randn(10, 100)
    true_density = torch.randn(10, 30, 30)
    
    # Training step
    pred_density = model(gravity_obs)
    loss = torch.mean((pred_density - true_density) ** 2)
    
    optimizer.zero_grad()
    loss.backward()
    optimizer.step()
    
    # Check gradients
    for param in model.parameters():
        assert param.grad is not None
