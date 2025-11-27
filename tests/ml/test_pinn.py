"""
Tests for Physics-Informed Neural Networks (PINNs).
"""

import pytest
import numpy as np

try:
    import torch
    from ml.models.pinn import (
        PhysicsInformedNN,
        GravityPINN,
        MagneticPINN,
        JointGravityMagneticPINN,
    )
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False


@pytest.mark.skipif(not HAS_TORCH, reason="PyTorch not available")
class TestPhysicsInformedNN:
    """Test base PINN class."""
    
    def test_initialization(self):
        """Test PINN initialization."""
        model = PhysicsInformedNN(
            input_dim=3,
            output_dim=2,
            hidden_layers=[64, 64],
            activation='tanh',
        )
        
        assert model.input_dim == 3
        assert model.output_dim == 2
    
    def test_forward_pass(self):
        """Test forward propagation."""
        model = PhysicsInformedNN(input_dim=3, output_dim=2)
        x = torch.randn(10, 3)
        
        output = model(x)
        
        assert output.shape == (10, 2)
    
    def test_gradient_computation(self):
        """Test automatic differentiation for gradients."""
        model = PhysicsInformedNN(input_dim=3, output_dim=1)
        x = torch.randn(10, 3, requires_grad=True)
        
        predictions = model(x)
        gradients = model.compute_gradients(predictions, x)
        
        # Check first derivatives
        assert 'dx' in gradients
        assert 'dy' in gradients
        assert 'dz' in gradients
        
        # Check second derivatives
        assert 'dxx' in gradients
        assert 'dyy' in gradients
        assert 'dzz' in gradients
        
        assert gradients['dx'].shape == (10, 1)


@pytest.mark.skipif(not HAS_TORCH, reason="PyTorch not available")
class TestGravityPINN:
    """Test gravity PINN."""
    
    def test_initialization(self):
        """Test gravity PINN initialization."""
        model = GravityPINN(
            hidden_layers=[128, 128],
            activation='tanh',
        )
        
        assert model.input_dim == 3  # (x, y, z)
        assert model.output_dim == 2  # (potential, density)
    
    def test_physics_loss(self):
        """Test Poisson's equation physics loss."""
        model = GravityPINN()
        x = torch.randn(10, 3, requires_grad=True)
        
        predictions = model(x)
        physics_loss = model.physics_loss(x, predictions)
        
        assert physics_loss.shape == ()
        assert physics_loss.item() >= 0


@pytest.mark.skipif(not HAS_TORCH, reason="PyTorch not available")
class TestMagneticPINN:
    """Test magnetic PINN."""
    
    def test_initialization(self):
        """Test magnetic PINN initialization."""
        model = MagneticPINN()
        
        assert model.input_dim == 3  # (x, y, z)
        assert model.output_dim == 4  # (Bx, By, Bz, susceptibility)
    
    def test_physics_loss(self):
        """Test divergence-free constraint."""
        model = MagneticPINN()
        x = torch.randn(10, 3, requires_grad=True)
        
        predictions = model(x)
        physics_loss = model.physics_loss(x, predictions)
        
        assert physics_loss.shape == ()
        assert physics_loss.item() >= 0


@pytest.mark.skipif(not HAS_TORCH, reason="PyTorch not available")
class TestJointGravityMagneticPINN:
    """Test joint PINN."""
    
    def test_initialization(self):
        """Test joint PINN initialization."""
        model = JointGravityMagneticPINN()
        
        assert hasattr(model, 'encoder')
        assert hasattr(model, 'gravity_head')
        assert hasattr(model, 'magnetic_head')
    
    def test_forward_pass(self):
        """Test joint forward pass."""
        model = JointGravityMagneticPINN()
        x = torch.randn(10, 3)
        
        output = model(x)
        
        assert 'gravity' in output
        assert 'magnetic' in output
        assert 'coupling' in output
        
        assert output['gravity'].shape == (10, 2)  # (potential, density)
        assert output['magnetic'].shape == (10, 4)  # (Bx, By, Bz, suscept)
    
    def test_physics_loss(self):
        """Test combined physics loss."""
        model = JointGravityMagneticPINN()
        x = torch.randn(10, 3, requires_grad=True)
        
        predictions = model(x)
        physics_loss = model.physics_loss(x, predictions)
        
        assert physics_loss.shape == ()
        assert physics_loss.item() >= 0


@pytest.mark.skipif(not HAS_TORCH, reason="PyTorch not available")
def test_pinn_training():
    """Test PINN can be trained."""
    model = GravityPINN(hidden_layers=[32, 32])
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    
    # Generate synthetic data
    x = torch.randn(50, 3, requires_grad=True)
    y = torch.randn(50, 2)
    
    # Training step
    predictions = model(x)
    data_loss = torch.mean((predictions - y) ** 2)
    physics_loss = model.physics_loss(x, predictions)
    total_loss = data_loss + 0.1 * physics_loss
    
    optimizer.zero_grad()
    total_loss.backward()
    optimizer.step()
    
    # Check gradients were computed
    for param in model.parameters():
        assert param.grad is not None
