"""
Transfer Learning Framework
============================

Utilities for transfer learning and fine-tuning on real satellite data.
"""

import numpy as np
from pathlib import Path
from typing import Optional, List, Dict, Callable

try:
    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False


if HAS_TORCH:
    class TransferLearner:
        """
        Transfer learning manager.
        
        Handles pre-training on synthetic data and fine-tuning on real data.
        """
        
        def __init__(
            self,
            model: nn.Module,
            device: str = 'cpu',
        ):
            """
            Args:
                model: Neural network model
                device: Device for training
            """
            self.model = model
            self.device = torch.device(device)
            self.model.to(self.device)
        
        def freeze_encoder(self, freeze: bool = True):
            """
            Freeze/unfreeze encoder layers.
            
            Args:
                freeze: Whether to freeze
            """
            # Identify encoder layers (first half of network)
            n_layers = len(list(self.model.parameters()))
            n_encoder = n_layers // 2
            
            for idx, param in enumerate(self.model.parameters()):
                if idx < n_encoder:
                    param.requires_grad = not freeze
        
        def freeze_layers_by_name(self, layer_names: List[str], freeze: bool = True):
            """
            Freeze/unfreeze specific layers by name.
            
            Args:
                layer_names: List of layer names to freeze
                freeze: Whether to freeze
            """
            for name, param in self.model.named_parameters():
                if any(layer_name in name for layer_name in layer_names):
                    param.requires_grad = not freeze
        
        def get_trainable_params(self) -> List[nn.Parameter]:
            """Get list of trainable parameters."""
            return [p for p in self.model.parameters() if p.requires_grad]
        
        def pretrain(
            self,
            synthetic_loader: DataLoader,
            loss_fn: Callable,
            n_epochs: int = 50,
            learning_rate: float = 1e-3,
            verbose: bool = True,
        ) -> List[float]:
            """
            Pre-train on synthetic data.
            
            Args:
                synthetic_loader: DataLoader with synthetic data
                loss_fn: Loss function
                n_epochs: Number of epochs
                learning_rate: Learning rate
                verbose: Print progress
            
            Returns:
                List of training losses
            """
            optimizer = torch.optim.Adam(
                self.model.parameters(),
                lr=learning_rate,
            )
            
            losses = []
            
            if verbose:
                print("Pre-training on synthetic data...")
            
            for epoch in range(n_epochs):
                self.model.train()
                epoch_loss = 0
                n_batches = 0
                
                for batch in synthetic_loader:
                    if isinstance(batch, (list, tuple)):
                        batch = [b.to(self.device) for b in batch]
                    else:
                        batch = batch.to(self.device)
                    
                    optimizer.zero_grad()
                    loss = loss_fn(batch, self.model)
                    loss.backward()
                    optimizer.step()
                    
                    epoch_loss += loss.item()
                    n_batches += 1
                
                avg_loss = epoch_loss / n_batches
                losses.append(avg_loss)
                
                if verbose and (epoch + 1) % 10 == 0:
                    print(f"Epoch {epoch+1}/{n_epochs}, Loss: {avg_loss:.6f}")
            
            if verbose:
                print("✓ Pre-training complete")
            
            return losses
        
        def finetune(
            self,
            real_loader: DataLoader,
            val_loader: Optional[DataLoader],
            loss_fn: Callable,
            n_epochs: int = 20,
            learning_rate: float = 1e-4,
            freeze_encoder: bool = True,
            early_stopping_patience: int = 5,
            verbose: bool = True,
        ) -> Dict[str, List[float]]:
            """
            Fine-tune on real data.
            
            Args:
                real_loader: DataLoader with real satellite data
                val_loader: Validation data
                loss_fn: Loss function
                n_epochs: Number of epochs
                learning_rate: Learning rate (typically lower than pre-training)
                freeze_encoder: Whether to freeze encoder during fine-tuning
                early_stopping_patience: Patience for early stopping
                verbose: Print progress
            
            Returns:
                Dictionary with training history
            """
            if freeze_encoder:
                self.freeze_encoder(freeze=True)
                if verbose:
                    print("Encoder frozen for fine-tuning")
            
            optimizer = torch.optim.Adam(
                self.get_trainable_params(),
                lr=learning_rate,
            )
            
            scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
                optimizer,
                mode='min',
                factor=0.5,
                patience=early_stopping_patience // 2,
            )
            
            train_losses = []
            val_losses = []
            best_val_loss = float('inf')
            patience_counter = 0
            
            if verbose:
                print("Fine-tuning on real data...")
            
            for epoch in range(n_epochs):
                # Training
                self.model.train()
                epoch_loss = 0
                n_batches = 0
                
                for batch in real_loader:
                    if isinstance(batch, (list, tuple)):
                        batch = [b.to(self.device) for b in batch]
                    else:
                        batch = batch.to(self.device)
                    
                    optimizer.zero_grad()
                    loss = loss_fn(batch, self.model)
                    loss.backward()
                    optimizer.step()
                    
                    epoch_loss += loss.item()
                    n_batches += 1
                
                avg_train_loss = epoch_loss / n_batches
                train_losses.append(avg_train_loss)
                
                # Validation
                if val_loader is not None:
                    self.model.eval()
                    val_loss = 0
                    n_val_batches = 0
                    
                    with torch.no_grad():
                        for batch in val_loader:
                            if isinstance(batch, (list, tuple)):
                                batch = [b.to(self.device) for b in batch]
                            else:
                                batch = batch.to(self.device)
                            
                            loss = loss_fn(batch, self.model)
                            val_loss += loss.item()
                            n_val_batches += 1
                    
                    avg_val_loss = val_loss / n_val_batches
                    val_losses.append(avg_val_loss)
                    
                    # Learning rate scheduling
                    scheduler.step(avg_val_loss)
                    
                    # Early stopping
                    if avg_val_loss < best_val_loss:
                        best_val_loss = avg_val_loss
                        patience_counter = 0
                    else:
                        patience_counter += 1
                    
                    if patience_counter >= early_stopping_patience:
                        if verbose:
                            print(f"Early stopping at epoch {epoch+1}")
                        break
                    
                    if verbose:
                        print(f"Epoch {epoch+1}/{n_epochs}, "
                              f"Train Loss: {avg_train_loss:.6f}, "
                              f"Val Loss: {avg_val_loss:.6f}")
                else:
                    if verbose:
                        print(f"Epoch {epoch+1}/{n_epochs}, Loss: {avg_train_loss:.6f}")
            
            if verbose:
                print("✓ Fine-tuning complete")
            
            return {
                'train_losses': train_losses,
                'val_losses': val_losses,
            }
    
    
    class DomainAdaptation:
        """
        Domain adaptation for transferring from synthetic to real data.
        
        Uses adversarial training to learn domain-invariant features.
        """
        
        def __init__(
            self,
            feature_extractor: nn.Module,
            task_predictor: nn.Module,
            domain_discriminator: Optional[nn.Module] = None,
        ):
            """
            Args:
                feature_extractor: Feature extraction network
                task_predictor: Task-specific prediction network
                domain_discriminator: Domain classifier network
            """
            self.feature_extractor = feature_extractor
            self.task_predictor = task_predictor
            
            if domain_discriminator is None:
                # Create simple discriminator
                feature_dim = 512  # Assume feature dimension
                self.domain_discriminator = nn.Sequential(
                    nn.Linear(feature_dim, 256),
                    nn.ReLU(),
                    nn.Linear(256, 2),  # Binary: synthetic or real
                )
            else:
                self.domain_discriminator = domain_discriminator
        
        def train_step(
            self,
            source_batch,
            target_batch,
            task_optimizer: torch.optim.Optimizer,
            domain_optimizer: torch.optim.Optimizer,
            task_loss_fn: Callable,
            lambda_domain: float = 0.1,
        ) -> Dict[str, float]:
            """
            Single training step with domain adaptation.
            
            Args:
                source_batch: Batch from source domain (synthetic)
                target_batch: Batch from target domain (real)
                task_optimizer: Optimizer for task networks
                domain_optimizer: Optimizer for domain discriminator
                task_loss_fn: Task loss function
                lambda_domain: Weight for domain adversarial loss
            
            Returns:
                Dictionary with losses
            """
            # Extract features
            source_features = self.feature_extractor(source_batch[0])
            target_features = self.feature_extractor(target_batch[0])
            
            # Task loss (only on source, since we have labels)
            source_predictions = self.task_predictor(source_features)
            task_loss = task_loss_fn(source_predictions, source_batch[1])
            
            # Domain classification
            source_domain = torch.zeros(source_features.shape[0], dtype=torch.long)
            target_domain = torch.ones(target_features.shape[0], dtype=torch.long)
            
            all_features = torch.cat([source_features, target_features], dim=0)
            all_domains = torch.cat([source_domain, target_domain], dim=0)
            
            domain_predictions = self.domain_discriminator(all_features.detach())
            domain_loss = nn.functional.cross_entropy(domain_predictions, all_domains)
            
            # Adversarial loss (confuse domain discriminator)
            domain_predictions_adv = self.domain_discriminator(all_features)
            adversarial_loss = -nn.functional.cross_entropy(domain_predictions_adv, all_domains)
            
            # Total loss
            total_loss = task_loss + lambda_domain * adversarial_loss
            
            # Update task networks
            task_optimizer.zero_grad()
            total_loss.backward(retain_graph=True)
            task_optimizer.step()
            
            # Update domain discriminator
            domain_optimizer.zero_grad()
            domain_loss.backward()
            domain_optimizer.step()
            
            return {
                'task_loss': task_loss.item(),
                'domain_loss': domain_loss.item(),
                'adversarial_loss': adversarial_loss.item(),
                'total_loss': total_loss.item(),
            }


else:
    # Fallback classes
    class TransferLearner:
        def __init__(self, *args, **kwargs):
            raise ImportError("PyTorch required for transfer learning")
    
    class DomainAdaptation(TransferLearner):
        pass
