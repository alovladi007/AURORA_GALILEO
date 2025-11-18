"""
Physics-Informed Neural Networks (PINNs)
=========================================

PINNs for geophysical inversion with physical constraints.
"""

import numpy as np
from typing import Optional, Callable, Dict, List, Tuple
from dataclasses import dataclass

try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False
    print("Warning: PyTorch not available. ML module will not work.")


if HAS_TORCH:
    class PhysicsInformedNN(nn.Module):
        """
        Base Physics-Informed Neural Network.
        
        Incorporates physical laws as soft constraints in the loss function.
        """
        
        def __init__(
            self,
            input_dim: int,
            output_dim: int,
            hidden_layers: List[int] = [64, 64, 64],
            activation: str = 'tanh',
        ):
            """
            Args:
                input_dim: Input dimension (spatial coordinates)
                output_dim: Output dimension (physical quantities)
                hidden_layers: List of hidden layer sizes
                activation: Activation function ('tanh', 'relu', 'silu')
            """
            super().__init__()
            
            self.input_dim = input_dim
            self.output_dim = output_dim
            
            # Build network
            layers = []
            prev_dim = input_dim
            
            for hidden_dim in hidden_layers:
                layers.append(nn.Linear(prev_dim, hidden_dim))
                
                if activation == 'tanh':
                    layers.append(nn.Tanh())
                elif activation == 'relu':
                    layers.append(nn.ReLU())
                elif activation == 'silu':
                    layers.append(nn.SiLU())
                
                prev_dim = hidden_dim
            
            # Output layer
            layers.append(nn.Linear(prev_dim, output_dim))
            
            self.network = nn.Sequential(*layers)
            
            # Initialize weights
            self.apply(self._init_weights)
        
        def _init_weights(self, module):
            """Xavier initialization for better convergence."""
            if isinstance(module, nn.Linear):
                nn.init.xavier_uniform_(module.weight)
                if module.bias is not None:
                    nn.init.zeros_(module.bias)
        
        def forward(self, x: torch.Tensor) -> torch.Tensor:
            """
            Forward pass.
            
            Args:
                x: Input coordinates, shape (batch, input_dim)
            
            Returns:
                Predicted physical quantities, shape (batch, output_dim)
            """
            return self.network(x)
        
        def physics_loss(
            self,
            x: torch.Tensor,
            predictions: torch.Tensor,
        ) -> torch.Tensor:
            """
            Compute physics-based loss (to be overridden by subclasses).
            
            Args:
                x: Input coordinates
                predictions: Network predictions
            
            Returns:
                Physics loss tensor
            """
            # Default: no physics loss
            return torch.tensor(0.0, device=x.device)
        
        def compute_gradients(
            self,
            predictions: torch.Tensor,
            x: torch.Tensor,
        ) -> Dict[str, torch.Tensor]:
            """
            Compute spatial gradients using automatic differentiation.
            
            Args:
                predictions: Network output
                x: Input coordinates (must have requires_grad=True)
            
            Returns:
                Dictionary of gradients {'dx': ..., 'dy': ..., 'dxx': ..., etc.}
            """
            gradients = {}
            
            # First derivatives
            for i, coord in enumerate(['x', 'y', 'z'][:x.shape[1]]):
                grad = torch.autograd.grad(
                    predictions,
                    x,
                    grad_outputs=torch.ones_like(predictions),
                    create_graph=True,
                    retain_graph=True,
                )[0][:, i:i+1]
                
                gradients[f'd{coord}'] = grad
                
                # Second derivatives
                for j, coord2 in enumerate(['x', 'y', 'z'][:x.shape[1]]):
                    if j >= i:  # Only compute unique second derivatives
                        grad2 = torch.autograd.grad(
                            grad,
                            x,
                            grad_outputs=torch.ones_like(grad),
                            create_graph=True,
                            retain_graph=True,
                        )[0][:, j:j+1]
                        
                        gradients[f'd{coord}{coord2}'] = grad2
            
            return gradients


    class GravityPINN(PhysicsInformedNN):
        """
        PINN for gravity field inversion.
        
        Incorporates Laplace's equation: ∇²φ = -4πGρ
        """
        
        def __init__(
            self,
            hidden_layers: List[int] = [128, 128, 128, 128],
            activation: str = 'tanh',
            G_constant: float = 6.674e-11,  # Gravitational constant
        ):
            """
            Args:
                hidden_layers: Hidden layer sizes
                activation: Activation function
                G_constant: Gravitational constant (m^3 kg^-1 s^-2)
            """
            super().__init__(
                input_dim=3,  # (x, y, z)
                output_dim=2,  # (potential, density)
                hidden_layers=hidden_layers,
                activation=activation,
            )
            
            self.G = G_constant
        
        def physics_loss(
            self,
            x: torch.Tensor,
            predictions: torch.Tensor,
        ) -> torch.Tensor:
            """
            Compute Poisson's equation residual: ∇²φ + 4πGρ = 0
            """
            # Ensure x requires gradients
            x.requires_grad_(True)
            
            # Get potential (first output)
            potential = predictions[:, 0:1]
            
            # Get density (second output)
            density = predictions[:, 1:2]
            
            # Compute gradients
            grads = self.compute_gradients(potential, x)
            
            # Laplacian: ∇²φ = ∂²φ/∂x² + ∂²φ/∂y² + ∂²φ/∂z²
            laplacian = grads['dxx'] + grads['dyy'] + grads['dzz']
            
            # Poisson's equation: ∇²φ = -4πGρ
            poisson_residual = laplacian + 4 * np.pi * self.G * density
            
            # Mean squared residual
            physics_loss = torch.mean(poisson_residual ** 2)
            
            return physics_loss


    class MagneticPINN(PhysicsInformedNN):
        """
        PINN for magnetic field inversion.
        
        Incorporates Maxwell's equations: ∇·B = 0, ∇×H = 0 (in free space)
        """
        
        def __init__(
            self,
            hidden_layers: List[int] = [128, 128, 128, 128],
            activation: str = 'tanh',
        ):
            """
            Args:
                hidden_layers: Hidden layer sizes
                activation: Activation function
            """
            super().__init__(
                input_dim=3,  # (x, y, z)
                output_dim=4,  # (Bx, By, Bz, susceptibility)
                hidden_layers=hidden_layers,
                activation=activation,
            )
        
        def physics_loss(
            self,
            x: torch.Tensor,
            predictions: torch.Tensor,
        ) -> torch.Tensor:
            """
            Compute Maxwell's equations residual: ∇·B = 0
            """
            # Ensure x requires gradients
            x.requires_grad_(True)
            
            # Get magnetic field components
            Bx = predictions[:, 0:1]
            By = predictions[:, 1:2]
            Bz = predictions[:, 2:3]
            
            # Compute divergence: ∇·B = ∂Bx/∂x + ∂By/∂y + ∂Bz/∂z
            dBx_dx = torch.autograd.grad(
                Bx, x,
                grad_outputs=torch.ones_like(Bx),
                create_graph=True,
                retain_graph=True,
            )[0][:, 0:1]
            
            dBy_dy = torch.autograd.grad(
                By, x,
                grad_outputs=torch.ones_like(By),
                create_graph=True,
                retain_graph=True,
            )[0][:, 1:2]
            
            dBz_dz = torch.autograd.grad(
                Bz, x,
                grad_outputs=torch.ones_like(Bz),
                create_graph=True,
                retain_graph=True,
            )[0][:, 2:3]
            
            divergence = dBx_dx + dBy_dy + dBz_dz
            
            # Divergence-free constraint
            physics_loss = torch.mean(divergence ** 2)
            
            return physics_loss


    class JointGravityMagneticPINN(nn.Module):
        """
        Joint PINN for simultaneous gravity and magnetic inversion.
        
        Learns coupled subsurface properties with structural constraints.
        """
        
        def __init__(
            self,
            hidden_layers: List[int] = [256, 256, 256, 256],
            activation: str = 'tanh',
        ):
            """
            Args:
                hidden_layers: Shared hidden layer sizes
                activation: Activation function
            """
            super().__init__()
            
            # Shared encoder
            encoder_layers = []
            prev_dim = 3  # (x, y, z)
            
            for i, hidden_dim in enumerate(hidden_layers[:-1]):
                encoder_layers.append(nn.Linear(prev_dim, hidden_dim))
                
                if activation == 'tanh':
                    encoder_layers.append(nn.Tanh())
                elif activation == 'relu':
                    encoder_layers.append(nn.ReLU())
                
                prev_dim = hidden_dim
            
            self.encoder = nn.Sequential(*encoder_layers)
            
            # Gravity branch
            self.gravity_head = nn.Sequential(
                nn.Linear(hidden_layers[-2], hidden_layers[-1]),
                nn.Tanh() if activation == 'tanh' else nn.ReLU(),
                nn.Linear(hidden_layers[-1], 2),  # (potential, density)
            )
            
            # Magnetic branch
            self.magnetic_head = nn.Sequential(
                nn.Linear(hidden_layers[-2], hidden_layers[-1]),
                nn.Tanh() if activation == 'tanh' else nn.ReLU(),
                nn.Linear(hidden_layers[-1], 4),  # (Bx, By, Bz, susceptibility)
            )
            
            # Structural coupling layer
            self.coupling = nn.Linear(2 + 4, 64)
            self.coupling_out = nn.Linear(64, 1)  # Cross-gradient penalty
        
        def forward(self, x: torch.Tensor) -> Dict[str, torch.Tensor]:
            """
            Forward pass.
            
            Args:
                x: Input coordinates, shape (batch, 3)
            
            Returns:
                Dictionary with 'gravity' and 'magnetic' predictions
            """
            # Shared features
            features = self.encoder(x)
            
            # Branch predictions
            gravity_pred = self.gravity_head(features)
            magnetic_pred = self.magnetic_head(features)
            
            # Structural coupling
            joint_features = torch.cat([gravity_pred, magnetic_pred], dim=-1)
            coupling_features = torch.relu(self.coupling(joint_features))
            coupling_penalty = self.coupling_out(coupling_features)
            
            return {
                'gravity': gravity_pred,
                'magnetic': magnetic_pred,
                'coupling': coupling_penalty,
            }
        
        def physics_loss(
            self,
            x: torch.Tensor,
            predictions: Dict[str, torch.Tensor],
        ) -> torch.Tensor:
            """
            Compute combined physics loss.
            """
            x.requires_grad_(True)
            
            # Gravity physics (Poisson's equation)
            potential = predictions['gravity'][:, 0:1]
            density = predictions['gravity'][:, 1:2]
            
            # Laplacian of potential
            grads_pot = {}
            for i, coord in enumerate(['x', 'y', 'z']):
                grad = torch.autograd.grad(
                    potential, x,
                    grad_outputs=torch.ones_like(potential),
                    create_graph=True,
                    retain_graph=True,
                )[0][:, i:i+1]
                
                grad2 = torch.autograd.grad(
                    grad, x,
                    grad_outputs=torch.ones_like(grad),
                    create_graph=True,
                    retain_graph=True,
                )[0][:, i:i+1]
                
                grads_pot[f'd{coord}{coord}'] = grad2
            
            laplacian = grads_pot['dxx'] + grads_pot['dyy'] + grads_pot['dzz']
            poisson_residual = laplacian + 4 * np.pi * 6.674e-11 * density
            gravity_loss = torch.mean(poisson_residual ** 2)
            
            # Magnetic physics (∇·B = 0)
            Bx = predictions['magnetic'][:, 0:1]
            By = predictions['magnetic'][:, 1:2]
            Bz = predictions['magnetic'][:, 2:3]
            
            dBx_dx = torch.autograd.grad(
                Bx, x,
                grad_outputs=torch.ones_like(Bx),
                create_graph=True,
                retain_graph=True,
            )[0][:, 0:1]
            
            dBy_dy = torch.autograd.grad(
                By, x,
                grad_outputs=torch.ones_like(By),
                create_graph=True,
                retain_graph=True,
            )[0][:, 1:2]
            
            dBz_dz = torch.autograd.grad(
                Bz, x,
                grad_outputs=torch.ones_like(Bz),
                create_graph=True,
                retain_graph=True,
            )[0][:, 2:3]
            
            divergence = dBx_dx + dBy_dy + dBz_dz
            magnetic_loss = torch.mean(divergence ** 2)
            
            # Structural coupling loss (cross-gradient)
            coupling_loss = torch.mean(predictions['coupling'] ** 2)
            
            # Total physics loss
            total_physics_loss = gravity_loss + magnetic_loss + 0.1 * coupling_loss
            
            return total_physics_loss


else:
    # Fallback classes if PyTorch not available
    class PhysicsInformedNN:
        def __init__(self, *args, **kwargs):
            raise ImportError("PyTorch required for PINN. Install with: pip install torch")
    
    class GravityPINN(PhysicsInformedNN):
        pass
    
    class MagneticPINN(PhysicsInformedNN):
        pass
    
    class JointGravityMagneticPINN(PhysicsInformedNN):
        pass
