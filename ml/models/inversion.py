"""
Neural Network Inversion Models
================================

Direct data-to-model inversion using neural networks.
Learns inverse mapping from observations to subsurface properties.
"""

import numpy as np
from typing import Optional, List, Tuple, Dict
from dataclasses import dataclass

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False
    print("Warning: PyTorch not available. ML module will not work.")


if HAS_TORCH:
    class InversionNN(nn.Module):
        """
        Basic neural network for geophysical inversion.
        
        Maps observations (gravity/magnetic) to subsurface properties (density/susceptibility).
        """
        
        def __init__(
            self,
            n_observations: int,
            n_model_params: int,
            hidden_layers: List[int] = [512, 512, 512],
            dropout: float = 0.1,
            activation: str = 'relu',
        ):
            """
            Args:
                n_observations: Number of input observations
                n_model_params: Number of output model parameters
                hidden_layers: List of hidden layer sizes
                dropout: Dropout probability for regularization
                activation: Activation function ('relu', 'elu', 'gelu')
            """
            super().__init__()
            
            self.n_observations = n_observations
            self.n_model_params = n_model_params
            
            # Build encoder
            layers = []
            prev_dim = n_observations
            
            for hidden_dim in hidden_layers:
                layers.append(nn.Linear(prev_dim, hidden_dim))
                layers.append(nn.BatchNorm1d(hidden_dim))
                
                if activation == 'relu':
                    layers.append(nn.ReLU())
                elif activation == 'elu':
                    layers.append(nn.ELU())
                elif activation == 'gelu':
                    layers.append(nn.GELU())
                
                if dropout > 0:
                    layers.append(nn.Dropout(dropout))
                
                prev_dim = hidden_dim
            
            # Output layer
            layers.append(nn.Linear(prev_dim, n_model_params))
            
            self.network = nn.Sequential(*layers)
            
            # Initialize weights
            self.apply(self._init_weights)
        
        def _init_weights(self, module):
            """He initialization for ReLU networks."""
            if isinstance(module, nn.Linear):
                nn.init.kaiming_normal_(module.weight, mode='fan_in', nonlinearity='relu')
                if module.bias is not None:
                    nn.init.zeros_(module.bias)
        
        def forward(self, observations: torch.Tensor) -> torch.Tensor:
            """
            Forward pass.
            
            Args:
                observations: Input observations, shape (batch, n_observations)
            
            Returns:
                Inverted model parameters, shape (batch, n_model_params)
            """
            return self.network(observations)
        
        def predict_with_uncertainty(
            self,
            observations: torch.Tensor,
            n_samples: int = 100,
        ) -> Tuple[torch.Tensor, torch.Tensor]:
            """
            Predict with MC Dropout uncertainty estimation.
            
            Args:
                observations: Input observations
                n_samples: Number of MC samples
            
            Returns:
                Tuple of (mean_prediction, std_prediction)
            """
            self.train()  # Enable dropout
            
            predictions = []
            for _ in range(n_samples):
                with torch.no_grad():
                    pred = self.forward(observations)
                    predictions.append(pred)
            
            predictions = torch.stack(predictions, dim=0)
            
            mean_pred = predictions.mean(dim=0)
            std_pred = predictions.std(dim=0)
            
            self.eval()  # Disable dropout
            
            return mean_pred, std_pred
    
    
    class ConditionalInversionNN(nn.Module):
        """
        Conditional inversion network with metadata conditioning.
        
        Incorporates acquisition parameters (altitude, sensor specs, etc.) for improved inversion.
        """
        
        def __init__(
            self,
            n_observations: int,
            n_model_params: int,
            n_condition_params: int,
            hidden_layers: List[int] = [512, 512, 512],
            dropout: float = 0.1,
        ):
            """
            Args:
                n_observations: Number of observations
                n_model_params: Number of model parameters
                n_condition_params: Number of conditioning parameters
                hidden_layers: Hidden layer sizes
                dropout: Dropout probability
            """
            super().__init__()
            
            self.n_observations = n_observations
            self.n_model_params = n_model_params
            self.n_condition_params = n_condition_params
            
            # Condition encoder
            self.condition_encoder = nn.Sequential(
                nn.Linear(n_condition_params, 128),
                nn.ReLU(),
                nn.Linear(128, 256),
                nn.ReLU(),
            )
            
            # Main network (with concatenated condition embedding)
            layers = []
            prev_dim = n_observations + 256  # observations + condition embedding
            
            for hidden_dim in hidden_layers:
                layers.append(nn.Linear(prev_dim, hidden_dim))
                layers.append(nn.BatchNorm1d(hidden_dim))
                layers.append(nn.ReLU())
                
                if dropout > 0:
                    layers.append(nn.Dropout(dropout))
                
                prev_dim = hidden_dim
            
            layers.append(nn.Linear(prev_dim, n_model_params))
            
            self.network = nn.Sequential(*layers)
        
        def forward(
            self,
            observations: torch.Tensor,
            conditions: torch.Tensor,
        ) -> torch.Tensor:
            """
            Forward pass with conditioning.
            
            Args:
                observations: Input observations, shape (batch, n_observations)
                conditions: Conditioning parameters, shape (batch, n_condition_params)
                            e.g., [altitude, sensor_noise_level, magnetic_field_strength]
            
            Returns:
                Inverted model parameters, shape (batch, n_model_params)
            """
            # Encode conditions
            condition_emb = self.condition_encoder(conditions)
            
            # Concatenate observations and conditions
            x = torch.cat([observations, condition_emb], dim=-1)
            
            # Invert
            return self.network(x)
    
    
    class ResidualInversionNN(nn.Module):
        """
        Residual inversion network for iterative refinement.
        
        Uses skip connections and residual learning for better gradient flow.
        """
        
        def __init__(
            self,
            n_observations: int,
            n_model_params: int,
            hidden_dim: int = 512,
            n_blocks: int = 6,
            dropout: float = 0.1,
        ):
            """
            Args:
                n_observations: Number of observations
                n_model_params: Number of model parameters
                hidden_dim: Hidden dimension (same for all blocks)
                n_blocks: Number of residual blocks
                dropout: Dropout probability
            """
            super().__init__()
            
            self.n_observations = n_observations
            self.n_model_params = n_model_params
            
            # Input projection
            self.input_proj = nn.Linear(n_observations, hidden_dim)
            
            # Residual blocks
            self.blocks = nn.ModuleList([
                ResidualBlock(hidden_dim, dropout)
                for _ in range(n_blocks)
            ])
            
            # Output projection
            self.output_proj = nn.Sequential(
                nn.Linear(hidden_dim, hidden_dim // 2),
                nn.ReLU(),
                nn.Linear(hidden_dim // 2, n_model_params),
            )
        
        def forward(self, observations: torch.Tensor) -> torch.Tensor:
            """
            Forward pass with residual connections.
            
            Args:
                observations: Input observations
            
            Returns:
                Inverted model parameters
            """
            x = self.input_proj(observations)
            
            for block in self.blocks:
                x = block(x)
            
            return self.output_proj(x)
    
    
    class ResidualBlock(nn.Module):
        """Residual block with skip connection."""
        
        def __init__(self, hidden_dim: int, dropout: float = 0.1):
            super().__init__()
            
            self.block = nn.Sequential(
                nn.Linear(hidden_dim, hidden_dim),
                nn.BatchNorm1d(hidden_dim),
                nn.ReLU(),
                nn.Dropout(dropout),
                nn.Linear(hidden_dim, hidden_dim),
                nn.BatchNorm1d(hidden_dim),
            )
            
            self.activation = nn.ReLU()
        
        def forward(self, x: torch.Tensor) -> torch.Tensor:
            return self.activation(x + self.block(x))
    
    
    class EnsembleInversionNN(nn.Module):
        """
        Ensemble of inversion networks for uncertainty quantification.
        
        Trains multiple models with different initializations for robust predictions.
        """
        
        def __init__(
            self,
            n_observations: int,
            n_model_params: int,
            n_models: int = 5,
            hidden_layers: List[int] = [512, 512, 512],
            dropout: float = 0.1,
        ):
            """
            Args:
                n_observations: Number of observations
                n_model_params: Number of model parameters
                n_models: Number of models in ensemble
                hidden_layers: Hidden layer sizes for each model
                dropout: Dropout probability
            """
            super().__init__()
            
            self.n_models = n_models
            
            # Create ensemble of models
            self.models = nn.ModuleList([
                InversionNN(
                    n_observations=n_observations,
                    n_model_params=n_model_params,
                    hidden_layers=hidden_layers,
                    dropout=dropout,
                )
                for _ in range(n_models)
            ])
        
        def forward(self, observations: torch.Tensor) -> torch.Tensor:
            """
            Forward pass - returns ensemble mean.
            
            Args:
                observations: Input observations
            
            Returns:
                Mean prediction across ensemble
            """
            predictions = [model(observations) for model in self.models]
            predictions = torch.stack(predictions, dim=0)
            return predictions.mean(dim=0)
        
        def predict_with_uncertainty(
            self,
            observations: torch.Tensor,
        ) -> Tuple[torch.Tensor, torch.Tensor]:
            """
            Predict with epistemic uncertainty from ensemble.
            
            Args:
                observations: Input observations
            
            Returns:
                Tuple of (mean_prediction, std_prediction)
            """
            self.eval()
            
            with torch.no_grad():
                predictions = [model(observations) for model in self.models]
                predictions = torch.stack(predictions, dim=0)
            
            mean_pred = predictions.mean(dim=0)
            std_pred = predictions.std(dim=0)
            
            return mean_pred, std_pred
    
    
    class GravityInversionNN(InversionNN):
        """
        Specialized inversion network for gravity data.
        
        Maps gravity anomalies to density distribution.
        """
        
        def __init__(
            self,
            n_gravity_obs: int,
            grid_shape: Tuple[int, int],
            hidden_layers: List[int] = [512, 512, 512],
            dropout: float = 0.1,
        ):
            """
            Args:
                n_gravity_obs: Number of gravity observations
                grid_shape: Output grid shape (ny, nx)
                hidden_layers: Hidden layer sizes
                dropout: Dropout probability
            """
            ny, nx = grid_shape
            n_model_params = ny * nx
            
            super().__init__(
                n_observations=n_gravity_obs,
                n_model_params=n_model_params,
                hidden_layers=hidden_layers,
                dropout=dropout,
            )
            
            self.grid_shape = grid_shape
        
        def forward(self, gravity_obs: torch.Tensor) -> torch.Tensor:
            """
            Invert gravity to density.
            
            Args:
                gravity_obs: Gravity observations, shape (batch, n_gravity_obs)
            
            Returns:
                Density model, shape (batch, ny, nx)
            """
            density_flat = super().forward(gravity_obs)
            ny, nx = self.grid_shape
            return density_flat.view(-1, ny, nx)
    
    
    class MagneticInversionNN(InversionNN):
        """
        Specialized inversion network for magnetic data.
        
        Maps magnetic anomalies to susceptibility distribution.
        """
        
        def __init__(
            self,
            n_magnetic_obs: int,
            grid_shape: Tuple[int, int],
            hidden_layers: List[int] = [512, 512, 512],
            dropout: float = 0.1,
        ):
            """
            Args:
                n_magnetic_obs: Number of magnetic observations
                grid_shape: Output grid shape (ny, nx)
                hidden_layers: Hidden layer sizes
                dropout: Dropout probability
            """
            ny, nx = grid_shape
            n_model_params = ny * nx
            
            super().__init__(
                n_observations=n_magnetic_obs,
                n_model_params=n_model_params,
                hidden_layers=hidden_layers,
                dropout=dropout,
            )
            
            self.grid_shape = grid_shape
        
        def forward(self, magnetic_obs: torch.Tensor) -> torch.Tensor:
            """
            Invert magnetic to susceptibility.
            
            Args:
                magnetic_obs: Magnetic observations, shape (batch, n_magnetic_obs)
            
            Returns:
                Susceptibility model, shape (batch, ny, nx)
            """
            susceptibility_flat = super().forward(magnetic_obs)
            ny, nx = self.grid_shape
            return susceptibility_flat.view(-1, ny, nx)
    
    
    class JointInversionNN(nn.Module):
        """
        Joint inversion network for gravity and magnetic data.
        
        Maps (gravity, magnetic) observations to (density, susceptibility) models.
        Uses shared encoder for structural coupling.
        """
        
        def __init__(
            self,
            n_gravity_obs: int,
            n_magnetic_obs: int,
            grid_shape: Tuple[int, int],
            shared_layers: List[int] = [512, 512],
            branch_layers: List[int] = [256, 256],
            dropout: float = 0.1,
        ):
            """
            Args:
                n_gravity_obs: Number of gravity observations
                n_magnetic_obs: Number of magnetic observations
                grid_shape: Output grid shape (ny, nx)
                shared_layers: Shared encoder layer sizes
                branch_layers: Branch-specific layer sizes
                dropout: Dropout probability
            """
            super().__init__()
            
            self.grid_shape = grid_shape
            ny, nx = grid_shape
            n_model_params = ny * nx
            
            # Shared encoder
            shared_encoder = []
            prev_dim = n_gravity_obs + n_magnetic_obs
            
            for hidden_dim in shared_layers:
                shared_encoder.append(nn.Linear(prev_dim, hidden_dim))
                shared_encoder.append(nn.BatchNorm1d(hidden_dim))
                shared_encoder.append(nn.ReLU())
                shared_encoder.append(nn.Dropout(dropout))
                prev_dim = hidden_dim
            
            self.shared_encoder = nn.Sequential(*shared_encoder)
            
            # Gravity branch (density)
            gravity_branch = []
            prev_dim = shared_layers[-1]
            
            for hidden_dim in branch_layers:
                gravity_branch.append(nn.Linear(prev_dim, hidden_dim))
                gravity_branch.append(nn.ReLU())
                gravity_branch.append(nn.Dropout(dropout))
                prev_dim = hidden_dim
            
            gravity_branch.append(nn.Linear(prev_dim, n_model_params))
            self.gravity_branch = nn.Sequential(*gravity_branch)
            
            # Magnetic branch (susceptibility)
            magnetic_branch = []
            prev_dim = shared_layers[-1]
            
            for hidden_dim in branch_layers:
                magnetic_branch.append(nn.Linear(prev_dim, hidden_dim))
                magnetic_branch.append(nn.ReLU())
                magnetic_branch.append(nn.Dropout(dropout))
                prev_dim = hidden_dim
            
            magnetic_branch.append(nn.Linear(prev_dim, n_model_params))
            self.magnetic_branch = nn.Sequential(*magnetic_branch)
        
        def forward(
            self,
            gravity_obs: torch.Tensor,
            magnetic_obs: torch.Tensor,
        ) -> Dict[str, torch.Tensor]:
            """
            Joint inversion.
            
            Args:
                gravity_obs: Gravity observations, shape (batch, n_gravity_obs)
                magnetic_obs: Magnetic observations, shape (batch, n_magnetic_obs)
            
            Returns:
                Dictionary with keys:
                - 'density': Density model, shape (batch, ny, nx)
                - 'susceptibility': Susceptibility model, shape (batch, ny, nx)
            """
            # Concatenate observations
            observations = torch.cat([gravity_obs, magnetic_obs], dim=-1)
            
            # Shared encoding
            features = self.shared_encoder(observations)
            
            # Branch predictions
            density_flat = self.gravity_branch(features)
            susceptibility_flat = self.magnetic_branch(features)
            
            # Reshape to grid
            ny, nx = self.grid_shape
            density = density_flat.view(-1, ny, nx)
            susceptibility = susceptibility_flat.view(-1, ny, nx)
            
            return {
                'density': density,
                'susceptibility': susceptibility,
            }


else:
    # Fallback classes if PyTorch not available
    class InversionNN:
        def __init__(self, *args, **kwargs):
            raise ImportError("PyTorch required for ML inversion. Install with: pip install torch")
    
    class ConditionalInversionNN(InversionNN):
        pass
    
    class ResidualInversionNN(InversionNN):
        pass
    
    class ResidualBlock(InversionNN):
        pass
    
    class EnsembleInversionNN(InversionNN):
        pass
    
    class GravityInversionNN(InversionNN):
        pass
    
    class MagneticInversionNN(InversionNN):
        pass
    
    class JointInversionNN(InversionNN):
        pass
