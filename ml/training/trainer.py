"""
Training Framework
==================

Flexible trainer for ML models with checkpointing, early stopping, and logging.
"""

import numpy as np
from pathlib import Path
from typing import Optional, Dict, List, Callable
from dataclasses import dataclass
import time

try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    from torch.utils.data import DataLoader
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False


@dataclass
class TrainingConfig:
    """Training configuration."""
    max_epochs: int = 100
    learning_rate: float = 1e-3
    weight_decay: float = 0.0
    batch_size: int = 32
    patience: int = 10
    min_delta: float = 1e-4
    checkpoint_dir: Optional[str] = None
    save_best_only: bool = True
    verbose: bool = True


if HAS_TORCH:
    class Trainer:
        """
        Generic trainer for ML models.
        
        Handles training loop, validation, checkpointing, and early stopping.
        """
        
        def __init__(
            self,
            model: nn.Module,
            config: TrainingConfig,
            device: str = 'cpu',
        ):
            """
            Args:
                model: Neural network model
                config: Training configuration
                device: Device for training ('cpu' or 'cuda')
            """
            self.model = model
            self.config = config
            self.device = torch.device(device)
            self.model.to(self.device)
            
            # Optimizer
            self.optimizer = optim.Adam(
                self.model.parameters(),
                lr=config.learning_rate,
                weight_decay=config.weight_decay,
            )
            
            # Learning rate scheduler
            self.scheduler = optim.lr_scheduler.ReduceLROnPlateau(
                self.optimizer,
                mode='min',
                factor=0.5,
                patience=config.patience // 2,
                verbose=config.verbose,
            )
            
            # Training state
            self.epoch = 0
            self.best_loss = float('inf')
            self.patience_counter = 0
            
            # History
            self.train_losses = []
            self.val_losses = []
            
            # Checkpoint directory
            if config.checkpoint_dir:
                self.checkpoint_dir = Path(config.checkpoint_dir)
                self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
            else:
                self.checkpoint_dir = None
        
        def train_epoch(
            self,
            train_loader: DataLoader,
            loss_fn: Callable,
        ) -> float:
            """
            Train for one epoch.
            
            Args:
                train_loader: DataLoader for training data
                loss_fn: Loss function
            
            Returns:
                Average training loss
            """
            self.model.train()
            total_loss = 0
            n_batches = 0
            
            for batch in train_loader:
                # Move to device
                if isinstance(batch, (list, tuple)):
                    batch = [b.to(self.device) if isinstance(b, torch.Tensor) else b for b in batch]
                else:
                    batch = batch.to(self.device)
                
                # Forward pass
                self.optimizer.zero_grad()
                loss = loss_fn(batch, self.model)
                
                # Backward pass
                loss.backward()
                self.optimizer.step()
                
                total_loss += loss.item()
                n_batches += 1
            
            return total_loss / n_batches
        
        def validate(
            self,
            val_loader: DataLoader,
            loss_fn: Callable,
        ) -> float:
            """
            Validate model.
            
            Args:
                val_loader: DataLoader for validation data
                loss_fn: Loss function
            
            Returns:
                Average validation loss
            """
            self.model.eval()
            total_loss = 0
            n_batches = 0
            
            with torch.no_grad():
                for batch in val_loader:
                    # Move to device
                    if isinstance(batch, (list, tuple)):
                        batch = [b.to(self.device) if isinstance(b, torch.Tensor) else b for b in batch]
                    else:
                        batch = batch.to(self.device)
                    
                    # Forward pass
                    loss = loss_fn(batch, self.model)
                    
                    total_loss += loss.item()
                    n_batches += 1
            
            return total_loss / n_batches
        
        def fit(
            self,
            train_loader: DataLoader,
            val_loader: Optional[DataLoader],
            loss_fn: Callable,
        ) -> Dict[str, List[float]]:
            """
            Train model.
            
            Args:
                train_loader: Training data loader
                val_loader: Validation data loader (optional)
                loss_fn: Loss function
            
            Returns:
                Dictionary with training history
            """
            if self.config.verbose:
                print(f"Training on {self.device}")
                print(f"Max epochs: {self.config.max_epochs}")
                print(f"Patience: {self.config.patience}")
            
            start_time = time.time()
            
            for epoch in range(self.config.max_epochs):
                self.epoch = epoch
                epoch_start = time.time()
                
                # Train
                train_loss = self.train_epoch(train_loader, loss_fn)
                self.train_losses.append(train_loss)
                
                # Validate
                if val_loader is not None:
                    val_loss = self.validate(val_loader, loss_fn)
                    self.val_losses.append(val_loss)
                    
                    # Learning rate scheduling
                    self.scheduler.step(val_loss)
                    
                    # Early stopping
                    if val_loss < self.best_loss - self.config.min_delta:
                        self.best_loss = val_loss
                        self.patience_counter = 0
                        
                        # Save best model
                        if self.checkpoint_dir:
                            self.save_checkpoint('best_model.pt')
                    else:
                        self.patience_counter += 1
                    
                    if self.patience_counter >= self.config.patience:
                        if self.config.verbose:
                            print(f"\nEarly stopping at epoch {epoch}")
                        break
                    
                    monitor_loss = val_loss
                else:
                    monitor_loss = train_loss
                    
                    if train_loss < self.best_loss:
                        self.best_loss = train_loss
                        if self.checkpoint_dir:
                            self.save_checkpoint('best_model.pt')
                
                # Logging
                if self.config.verbose:
                    epoch_time = time.time() - epoch_start
                    lr = self.optimizer.param_groups[0]['lr']
                    
                    if val_loader is not None:
                        print(f"Epoch {epoch+1}/{self.config.max_epochs} - "
                              f"{epoch_time:.2f}s - "
                              f"loss: {train_loss:.6f} - "
                              f"val_loss: {val_loss:.6f} - "
                              f"lr: {lr:.2e}")
                    else:
                        print(f"Epoch {epoch+1}/{self.config.max_epochs} - "
                              f"{epoch_time:.2f}s - "
                              f"loss: {train_loss:.6f} - "
                              f"lr: {lr:.2e}")
                
                # Save checkpoint
                if self.checkpoint_dir and not self.config.save_best_only:
                    self.save_checkpoint(f'checkpoint_epoch_{epoch+1}.pt')
            
            total_time = time.time() - start_time
            
            if self.config.verbose:
                print(f"\nTraining complete in {total_time:.2f}s")
                print(f"Best loss: {self.best_loss:.6f}")
            
            return {
                'train_losses': self.train_losses,
                'val_losses': self.val_losses,
            }
        
        def save_checkpoint(self, filename: str):
            """Save model checkpoint."""
            if self.checkpoint_dir is None:
                return
            
            checkpoint = {
                'epoch': self.epoch,
                'model_state_dict': self.model.state_dict(),
                'optimizer_state_dict': self.optimizer.state_dict(),
                'scheduler_state_dict': self.scheduler.state_dict(),
                'best_loss': self.best_loss,
                'train_losses': self.train_losses,
                'val_losses': self.val_losses,
            }
            
            path = self.checkpoint_dir / filename
            torch.save(checkpoint, path)
        
        def load_checkpoint(self, filename: str):
            """Load model checkpoint."""
            if self.checkpoint_dir is None:
                raise ValueError("No checkpoint directory specified")
            
            path = self.checkpoint_dir / filename
            checkpoint = torch.load(path, map_location=self.device)
            
            self.model.load_state_dict(checkpoint['model_state_dict'])
            self.optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
            self.scheduler.load_state_dict(checkpoint['scheduler_state_dict'])
            self.epoch = checkpoint['epoch']
            self.best_loss = checkpoint['best_loss']
            self.train_losses = checkpoint['train_losses']
            self.val_losses = checkpoint['val_losses']
    
    
    class PINNTrainer(Trainer):
        """
        Specialized trainer for Physics-Informed Neural Networks.
        
        Combines data loss and physics loss.
        """
        
        def __init__(
            self,
            model: nn.Module,
            config: TrainingConfig,
            lambda_data: float = 1.0,
            lambda_physics: float = 0.1,
            device: str = 'cpu',
        ):
            """
            Args:
                model: PINN model
                config: Training configuration
                lambda_data: Weight for data loss
                lambda_physics: Weight for physics loss
                device: Device for training
            """
            super().__init__(model, config, device)
            self.lambda_data = lambda_data
            self.lambda_physics = lambda_physics
            
            # Physics loss history
            self.physics_losses = []
        
        def train_epoch(
            self,
            train_loader: DataLoader,
            loss_fn: Callable,
        ) -> float:
            """
            Train PINN for one epoch.
            
            Args:
                train_loader: DataLoader with (x, observations)
                loss_fn: Loss function
            
            Returns:
                Average total loss
            """
            self.model.train()
            total_loss = 0
            total_physics_loss = 0
            n_batches = 0
            
            for batch in train_loader:
                x, obs = batch
                x = x.to(self.device)
                obs = obs.to(self.device)
                
                x.requires_grad_(True)
                
                # Forward pass
                self.optimizer.zero_grad()
                predictions = self.model(x)
                
                # Data loss
                data_loss = loss_fn(predictions, obs)
                
                # Physics loss
                physics_loss = self.model.physics_loss(x, predictions)
                
                # Total loss
                loss = self.lambda_data * data_loss + self.lambda_physics * physics_loss
                
                # Backward pass
                loss.backward()
                self.optimizer.step()
                
                total_loss += loss.item()
                total_physics_loss += physics_loss.item()
                n_batches += 1
            
            self.physics_losses.append(total_physics_loss / n_batches)
            
            return total_loss / n_batches
    
    
    class EnsembleTrainer:
        """
        Trainer for ensemble of models.
        
        Trains multiple models independently with different initializations.
        """
        
        def __init__(
            self,
            model_class: type,
            model_kwargs: Dict,
            n_models: int,
            config: TrainingConfig,
            device: str = 'cpu',
        ):
            """
            Args:
                model_class: Model class to instantiate
                model_kwargs: Kwargs for model instantiation
                n_models: Number of models in ensemble
                config: Training configuration
                device: Device for training
            """
            self.n_models = n_models
            self.config = config
            self.device = device
            
            # Create models
            self.models = [model_class(**model_kwargs) for _ in range(n_models)]
            
            # Create trainers
            self.trainers = [
                Trainer(model, config, device)
                for model in self.models
            ]
        
        def fit(
            self,
            train_loader: DataLoader,
            val_loader: Optional[DataLoader],
            loss_fn: Callable,
        ) -> List[Dict[str, List[float]]]:
            """
            Train all models in ensemble.
            
            Args:
                train_loader: Training data
                val_loader: Validation data
                loss_fn: Loss function
            
            Returns:
                List of training histories for each model
            """
            histories = []
            
            for i, trainer in enumerate(self.trainers):
                if self.config.verbose:
                    print(f"\nTraining model {i+1}/{self.n_models}")
                
                history = trainer.fit(train_loader, val_loader, loss_fn)
                histories.append(history)
            
            return histories


else:
    # Fallback classes
    class Trainer:
        def __init__(self, *args, **kwargs):
            raise ImportError("PyTorch required for training")
    
    class PINNTrainer(Trainer):
        pass
    
    class EnsembleTrainer(Trainer):
        pass
