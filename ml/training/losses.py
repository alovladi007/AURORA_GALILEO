"""
Loss Functions for ML Models
==============================

Physics-informed and data-driven loss functions for geophysical inversion.
"""

import numpy as np
from typing import Optional, Callable, Dict

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False


if HAS_TORCH:
    class DataMisfitLoss(nn.Module):
        """
        Data misfit loss for supervised learning.
        
        L2 norm of (predictions - observations).
        """
        
        def __init__(self, reduction: str = 'mean'):
            """
            Args:
                reduction: Reduction method ('mean', 'sum', 'none')
            """
            super().__init__()
            self.reduction = reduction
        
        def forward(
            self,
            predictions: torch.Tensor,
            observations: torch.Tensor,
            weights: Optional[torch.Tensor] = None,
        ) -> torch.Tensor:
            """
            Compute data misfit.
            
            Args:
                predictions: Model predictions
                observations: True observations
                weights: Optional observation weights
            
            Returns:
                Data misfit loss
            """
            residuals = predictions - observations
            squared_residuals = residuals ** 2
            
            if weights is not None:
                squared_residuals = squared_residuals * weights
            
            if self.reduction == 'mean':
                return torch.mean(squared_residuals)
            elif self.reduction == 'sum':
                return torch.sum(squared_residuals)
            else:
                return squared_residuals
    
    
    class PhysicsLoss(nn.Module):
        """
        Physics-based loss for PINNs.
        
        Enforces physical constraints (PDEs, conservation laws, etc.).
        """
        
        def __init__(self, physics_function: Callable):
            """
            Args:
                physics_function: Function that computes physics residual
            """
            super().__init__()
            self.physics_function = physics_function
        
        def forward(
            self,
            x: torch.Tensor,
            predictions: torch.Tensor,
        ) -> torch.Tensor:
            """
            Compute physics loss.
            
            Args:
                x: Input coordinates
                predictions: Model predictions
            
            Returns:
                Physics residual loss
            """
            return self.physics_function(x, predictions)
    
    
    class TotalVariationLoss(nn.Module):
        """
        Total Variation regularization.
        
        Promotes piecewise smooth solutions with sharp edges.
        """
        
        def __init__(self, weight: float = 1.0):
            """
            Args:
                weight: Regularization weight
            """
            super().__init__()
            self.weight = weight
        
        def forward(self, model: torch.Tensor) -> torch.Tensor:
            """
            Compute TV loss.
            
            Args:
                model: Model parameters, shape (batch, height, width) or (batch, 1, height, width)
            
            Returns:
                TV loss
            """
            if model.dim() == 3:
                model = model.unsqueeze(1)  # Add channel dimension
            
            # Gradients in x and y
            dx = model[:, :, :, 1:] - model[:, :, :, :-1]
            dy = model[:, :, 1:, :] - model[:, :, :-1, :]
            
            # TV norm
            tv = torch.mean(torch.abs(dx)) + torch.mean(torch.abs(dy))
            
            return self.weight * tv
    
    
    class SparsityLoss(nn.Module):
        """
        L1 sparsity regularization.
        
        Promotes sparse (compact) solutions.
        """
        
        def __init__(self, weight: float = 1.0):
            """
            Args:
                weight: Regularization weight
            """
            super().__init__()
            self.weight = weight
        
        def forward(self, model: torch.Tensor) -> torch.Tensor:
            """
            Compute L1 sparsity loss.
            
            Args:
                model: Model parameters
            
            Returns:
                L1 loss
            """
            return self.weight * torch.mean(torch.abs(model))
    
    
    class CrossGradientLoss(nn.Module):
        """
        Cross-gradient structural coupling loss.
        
        Promotes structural similarity between two models (e.g., density and susceptibility).
        """
        
        def __init__(self, weight: float = 1.0):
            """
            Args:
                weight: Regularization weight
            """
            super().__init__()
            self.weight = weight
        
        def forward(
            self,
            model1: torch.Tensor,
            model2: torch.Tensor,
        ) -> torch.Tensor:
            """
            Compute cross-gradient loss.
            
            Args:
                model1: First model (e.g., density), shape (batch, height, width)
                model2: Second model (e.g., susceptibility), same shape
            
            Returns:
                Cross-gradient loss
            """
            if model1.dim() == 3:
                model1 = model1.unsqueeze(1)
                model2 = model2.unsqueeze(1)
            
            # Gradients of model1
            dx1 = model1[:, :, :, 1:] - model1[:, :, :, :-1]
            dy1 = model1[:, :, 1:, :] - model1[:, :, :-1, :]
            
            # Gradients of model2
            dx2 = model2[:, :, :, 1:] - model2[:, :, :, :-1]
            dy2 = model2[:, :, 1:, :] - model2[:, :, :-1, :]
            
            # Align shapes (take minimum)
            min_h = min(dx1.shape[2], dx2.shape[2])
            min_w_dx = min(dx1.shape[3], dx2.shape[3])
            min_w_dy = min(dy1.shape[3], dy2.shape[3])
            
            dx1 = dx1[:, :, :min_h, :min_w_dx]
            dx2 = dx2[:, :, :min_h, :min_w_dx]
            dy1 = dy1[:, :, :min_h, :min_w_dy]
            dy2 = dy2[:, :, :min_h, :min_w_dy]
            
            # Cross-gradient: (∇m1 × ∇m2)^2
            # In 2D: (dx1*dy2 - dy1*dx2)^2
            cross_grad = (dx1 * dy2[:, :, :, :min_w_dx] - dy1[:, :, :, :min_w_dy] * dx2) ** 2
            
            return self.weight * torch.mean(cross_grad)
    
    
    class JointInversionLoss(nn.Module):
        """
        Combined loss for joint geophysical inversion.
        
        Combines data misfit, physics constraints, and structural coupling.
        """
        
        def __init__(
            self,
            lambda_data1: float = 1.0,
            lambda_data2: float = 1.0,
            lambda_physics: float = 0.1,
            lambda_cross_grad: float = 0.1,
            lambda_tv: float = 0.01,
            lambda_sparsity: float = 0.001,
        ):
            """
            Args:
                lambda_data1: Weight for first data term (gravity)
                lambda_data2: Weight for second data term (magnetic)
                lambda_physics: Weight for physics constraints
                lambda_cross_grad: Weight for cross-gradient coupling
                lambda_tv: Weight for total variation
                lambda_sparsity: Weight for sparsity
            """
            super().__init__()
            
            self.lambda_data1 = lambda_data1
            self.lambda_data2 = lambda_data2
            self.lambda_physics = lambda_physics
            self.lambda_cross_grad = lambda_cross_grad
            self.lambda_tv = lambda_tv
            self.lambda_sparsity = lambda_sparsity
            
            # Individual loss components
            self.data_loss = DataMisfitLoss()
            self.tv_loss = TotalVariationLoss()
            self.sparsity_loss = SparsityLoss()
            self.cross_grad_loss = CrossGradientLoss()
        
        def forward(
            self,
            gravity_pred: torch.Tensor,
            gravity_obs: torch.Tensor,
            magnetic_pred: torch.Tensor,
            magnetic_obs: torch.Tensor,
            density_model: torch.Tensor,
            susceptibility_model: torch.Tensor,
            physics_loss: Optional[torch.Tensor] = None,
        ) -> Dict[str, torch.Tensor]:
            """
            Compute joint loss.
            
            Args:
                gravity_pred: Predicted gravity observations
                gravity_obs: True gravity observations
                magnetic_pred: Predicted magnetic observations
                magnetic_obs: True magnetic observations
                density_model: Inverted density model
                susceptibility_model: Inverted susceptibility model
                physics_loss: Optional physics constraint loss
            
            Returns:
                Dictionary with individual and total losses
            """
            # Data misfit terms
            loss_gravity = self.data_loss(gravity_pred, gravity_obs)
            loss_magnetic = self.data_loss(magnetic_pred, magnetic_obs)
            
            # Regularization terms
            loss_tv_density = self.tv_loss(density_model)
            loss_tv_suscept = self.tv_loss(susceptibility_model)
            
            loss_sparse_density = self.sparsity_loss(density_model)
            loss_sparse_suscept = self.sparsity_loss(susceptibility_model)
            
            # Structural coupling
            loss_cross_grad = self.cross_grad_loss(density_model, susceptibility_model)
            
            # Total loss
            total_loss = (
                self.lambda_data1 * loss_gravity +
                self.lambda_data2 * loss_magnetic +
                self.lambda_tv * (loss_tv_density + loss_tv_suscept) +
                self.lambda_sparsity * (loss_sparse_density + loss_sparse_suscept) +
                self.lambda_cross_grad * loss_cross_grad
            )
            
            if physics_loss is not None:
                total_loss += self.lambda_physics * physics_loss
            
            # Return detailed losses
            losses = {
                'total': total_loss,
                'gravity_data': loss_gravity,
                'magnetic_data': loss_magnetic,
                'tv_density': loss_tv_density,
                'tv_susceptibility': loss_tv_suscept,
                'sparsity_density': loss_sparse_density,
                'sparsity_susceptibility': loss_sparse_suscept,
                'cross_gradient': loss_cross_grad,
            }
            
            if physics_loss is not None:
                losses['physics'] = physics_loss
            
            return losses
    
    
    class BayesianLoss(nn.Module):
        """
        ELBO loss for Bayesian neural networks.
        
        Combines negative log-likelihood and KL divergence.
        """
        
        def __init__(self, kl_weight: float = 1.0, n_samples: int = 1):
            """
            Args:
                kl_weight: Weight for KL divergence term
                n_samples: Number of data samples (for KL weighting)
            """
            super().__init__()
            self.kl_weight = kl_weight / n_samples
        
        def forward(
            self,
            predictions: torch.Tensor,
            targets: torch.Tensor,
            kl_divergence: torch.Tensor,
        ) -> Dict[str, torch.Tensor]:
            """
            Compute ELBO loss.
            
            Args:
                predictions: Model predictions
                targets: True targets
                kl_divergence: KL divergence from model
            
            Returns:
                Dictionary with NLL, KL, and ELBO losses
            """
            # Negative log-likelihood (MSE for regression)
            nll = F.mse_loss(predictions, targets)
            
            # ELBO = NLL + β * KL
            elbo = nll + self.kl_weight * kl_divergence
            
            return {
                'elbo': elbo,
                'nll': nll,
                'kl': kl_divergence,
            }


else:
    # Fallback classes
    class DataMisfitLoss:
        def __init__(self, *args, **kwargs):
            raise ImportError("PyTorch required for loss functions")
    
    class PhysicsLoss(DataMisfitLoss):
        pass
    
    class TotalVariationLoss(DataMisfitLoss):
        pass
    
    class SparsityLoss(DataMisfitLoss):
        pass
    
    class CrossGradientLoss(DataMisfitLoss):
        pass
    
    class JointInversionLoss(DataMisfitLoss):
        pass
    
    class BayesianLoss(DataMisfitLoss):
        pass
