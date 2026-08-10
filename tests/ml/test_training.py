"""
Tests for ML Training Framework.
"""

import pytest
import numpy as np
from pathlib import Path

try:
    import torch
    import torch.nn as nn
    from torch.utils.data import TensorDataset, DataLoader
    from ml.training.trainer import Trainer, TrainingConfig, PINNTrainer
    from ml.training.losses import DataMisfitLoss, CrossGradientLoss, JointInversionLoss
    from ml.training.metrics import rmse, r2_score, correlation, compute_all_metrics
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False


@pytest.mark.skipif(not HAS_TORCH, reason="PyTorch not available")
class TestLossFunctions:
    """Test loss functions."""
    
    def test_data_misfit_loss(self):
        """Test data misfit loss."""
        loss_fn = DataMisfitLoss()
        
        predictions = torch.randn(10, 100)
        observations = torch.randn(10, 100)
        
        loss = loss_fn(predictions, observations)
        
        assert loss.shape == ()
        assert loss.item() >= 0
    
    def test_cross_gradient_loss(self):
        """Test cross-gradient structural coupling."""
        loss_fn = CrossGradientLoss(weight=1.0)
        
        model1 = torch.randn(5, 30, 30)
        model2 = torch.randn(5, 30, 30)
        
        loss = loss_fn(model1, model2)
        
        assert loss.shape == ()
        assert loss.item() >= 0
    
    def test_joint_inversion_loss(self):
        """Test joint inversion loss."""
        loss_fn = JointInversionLoss(
            lambda_data1=1.0,
            lambda_data2=1.0,
            lambda_cross_grad=0.1,
        )
        
        gravity_pred = torch.randn(10, 100)
        gravity_obs = torch.randn(10, 100)
        magnetic_pred = torch.randn(10, 100)
        magnetic_obs = torch.randn(10, 100)
        density = torch.randn(10, 30, 30)
        susceptibility = torch.randn(10, 30, 30)
        
        losses = loss_fn(
            gravity_pred, gravity_obs,
            magnetic_pred, magnetic_obs,
            density, susceptibility,
        )
        
        assert 'total' in losses
        assert 'gravity_data' in losses
        assert 'magnetic_data' in losses
        assert 'cross_gradient' in losses


@pytest.mark.skipif(not HAS_TORCH, reason="PyTorch not available")
class TestMetrics:
    """Test evaluation metrics."""
    
    def test_rmse(self):
        """Test RMSE metric."""
        predictions = np.array([1.0, 2.0, 3.0, 4.0])
        targets = np.array([1.1, 2.1, 2.9, 4.1])
        
        result = rmse(predictions, targets)
        
        assert result > 0
        assert result < 0.2
    
    def test_r2_score(self):
        """Test R² score."""
        predictions = np.array([1.0, 2.0, 3.0, 4.0])
        targets = np.array([1.1, 2.1, 2.9, 4.1])
        
        result = r2_score(predictions, targets)
        
        assert result > 0.9  # Good fit
        assert result <= 1.0
    
    def test_correlation(self):
        """Test correlation coefficient."""
        predictions = np.array([1.0, 2.0, 3.0, 4.0])
        targets = np.array([1.1, 2.1, 2.9, 4.1])
        
        result = correlation(predictions, targets)
        
        assert result > 0.99  # Strong correlation
        assert result <= 1.0
    
    def test_compute_all_metrics(self):
        """Test comprehensive metrics."""
        predictions = np.random.randn(100)
        targets = predictions + np.random.randn(100) * 0.1
        
        metrics = compute_all_metrics(predictions, targets)
        
        assert 'rmse' in metrics
        assert 'r2' in metrics
        assert 'correlation' in metrics
        assert 'precision' in metrics
        assert 'recall' in metrics


@pytest.mark.skipif(not HAS_TORCH, reason="PyTorch not available")
class TestTrainer:
    """Test training framework."""
    
    def test_trainer_initialization(self):
        """Test trainer initialization."""
        model = nn.Sequential(
            nn.Linear(10, 50),
            nn.ReLU(),
            nn.Linear(50, 1),
        )
        
        config = TrainingConfig(max_epochs=10, batch_size=16)
        trainer = Trainer(model, config)
        
        assert trainer.model == model
        assert trainer.config == config
        assert trainer.epoch == 0
    
    def test_training_loop(self):
        """Test basic training loop."""
        # Simple model
        model = nn.Sequential(
            nn.Linear(10, 50),
            nn.ReLU(),
            nn.Linear(50, 1),
        )
        
        # Config
        config = TrainingConfig(
            max_epochs=5,
            batch_size=16,
            learning_rate=1e-2,
            verbose=False,
        )
        
        trainer = Trainer(model, config)
        
        # Synthetic data
        X = torch.randn(100, 10)
        y = torch.randn(100, 1)
        dataset = TensorDataset(X, y)
        train_loader = DataLoader(dataset, batch_size=16)
        
        # Loss function
        def loss_fn(batch, model):
            X_batch, y_batch = batch
            y_pred = model(X_batch)
            return nn.functional.mse_loss(y_pred, y_batch)
        
        # Train
        history = trainer.fit(train_loader, None, loss_fn)
        
        assert len(history['train_losses']) == 5
        assert history['train_losses'][-1] < history['train_losses'][0]  # Loss decreased
    
    def test_early_stopping(self):
        """Test early stopping."""
        # Random labels mean early stopping fires at an RNG-dependent
        # epoch; seed so the test is independent of execution order.
        torch.manual_seed(0)
        model = nn.Sequential(nn.Linear(10, 1))
        
        # High learning rate so the model converges (and the val loss
        # plateaus) well inside max_epochs - at the default 1e-3 a
        # Linear(10,1) can keep improving by more than min_delta for
        # all 100 epochs, which is not an early-stopping failure.
        config = TrainingConfig(
            max_epochs=100,
            patience=5,
            learning_rate=1e-1,
            verbose=False,
        )
        
        trainer = Trainer(model, config)
        
        # Data
        X_train = torch.randn(100, 10)
        y_train = torch.randn(100, 1)
        X_val = torch.randn(50, 10)
        y_val = torch.randn(50, 1)
        
        train_loader = DataLoader(TensorDataset(X_train, y_train), batch_size=16)
        val_loader = DataLoader(TensorDataset(X_val, y_val), batch_size=16)
        
        def loss_fn(batch, model):
            X_batch, y_batch = batch
            return nn.functional.mse_loss(model(X_batch), y_batch)
        
        # Train
        history = trainer.fit(train_loader, val_loader, loss_fn)
        
        # Should stop early (before 100 epochs)
        assert len(history['train_losses']) < 100


@pytest.mark.skipif(not HAS_TORCH, reason="PyTorch not available")
def test_integration():
    """Integration test: train and evaluate inversion network."""
    from ml.models.inversion import GravityInversionNN
    
    # Create model
    model = GravityInversionNN(
        n_gravity_obs=50,
        grid_shape=(10, 10),
        hidden_layers=[64, 64],
    )
    
    # Config
    config = TrainingConfig(
        max_epochs=10,
        learning_rate=1e-3,
        verbose=False,
    )
    
    trainer = Trainer(model, config)
    
    # Synthetic data
    gravity_obs = torch.randn(100, 50)
    true_density = torch.randn(100, 10, 10)
    
    dataset = TensorDataset(gravity_obs, true_density)
    train_loader = DataLoader(dataset, batch_size=16)
    
    # Loss
    def loss_fn(batch, model):
        obs, target = batch
        pred = model(obs)
        return nn.functional.mse_loss(pred, target)
    
    # Train
    history = trainer.fit(train_loader, None, loss_fn)
    
    # Evaluate
    model.eval()
    with torch.no_grad():
        predictions = model(gravity_obs[:10])
    
    # Compute metrics
    pred_np = predictions.cpu().numpy().flatten()
    target_np = true_density[:10].cpu().numpy().flatten()
    
    metrics = compute_all_metrics(pred_np, target_np)
    
    assert 'rmse' in metrics
    assert 'r2' in metrics
