"""
3D Geophysical Inversion Models
================================

Extended models for full 3D subsurface modeling.
"""

import numpy as np
from typing import Optional, List, Tuple, Dict

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False


if HAS_TORCH:
    class Gravity3DPINN(nn.Module):
        """
        3D Physics-Informed Neural Network for gravity inversion.
        
        Maps 3D spatial coordinates to (potential, density).
        """
        
        def __init__(
            self,
            hidden_layers: List[int] = [256, 256, 256, 256],
            activation: str = 'tanh',
            G: float = 6.674e-11,  # Gravitational constant
        ):
            super().__init__()
            
            self.input_dim = 3  # (x, y, z)
            self.output_dim = 2  # (potential, density)
            self.G = G
            
            # Build network
            layers = []
            prev_dim = self.input_dim
            
            for hidden_dim in hidden_layers:
                layers.append(nn.Linear(prev_dim, hidden_dim))
                
                if activation == 'tanh':
                    layers.append(nn.Tanh())
                elif activation == 'relu':
                    layers.append(nn.ReLU())
                elif activation == 'gelu':
                    layers.append(nn.GELU())
                
                prev_dim = hidden_dim
            
            layers.append(nn.Linear(prev_dim, self.output_dim))
            
            self.network = nn.Sequential(*layers)
            
            # Initialize
            self.apply(self._init_weights)
        
        def _init_weights(self, module):
            if isinstance(module, nn.Linear):
                nn.init.xavier_normal_(module.weight)
                if module.bias is not None:
                    nn.init.zeros_(module.bias)
        
        def forward(self, coords: torch.Tensor) -> torch.Tensor:
            """
            Forward pass.
            
            Args:
                coords: 3D coordinates, shape (batch, 3) with (x, y, z)
            
            Returns:
                Predictions, shape (batch, 2) with (potential, density)
            """
            return self.network(coords)
        
        def compute_gradients_3d(
            self,
            output: torch.Tensor,
            coords: torch.Tensor,
        ) -> Dict[str, torch.Tensor]:
            """
            Compute spatial gradients for physics loss.
            
            Args:
                output: Network output
                coords: Input coordinates
            
            Returns:
                Dictionary with gradients
            """
            # First derivatives
            dx = torch.autograd.grad(
                output, coords,
                grad_outputs=torch.ones_like(output),
                create_graph=True,
                retain_graph=True,
            )[0]
            
            dx_x = dx[:, 0:1]
            dx_y = dx[:, 1:2]
            dx_z = dx[:, 2:3]
            
            # Second derivatives
            dxx = torch.autograd.grad(
                dx_x, coords,
                grad_outputs=torch.ones_like(dx_x),
                create_graph=True,
                retain_graph=True,
            )[0][:, 0:1]
            
            dyy = torch.autograd.grad(
                dx_y, coords,
                grad_outputs=torch.ones_like(dx_y),
                create_graph=True,
                retain_graph=True,
            )[0][:, 1:2]
            
            dzz = torch.autograd.grad(
                dx_z, coords,
                grad_outputs=torch.ones_like(dx_z),
                create_graph=True,
                retain_graph=True,
            )[0][:, 2:3]
            
            return {
                'dx': dx_x, 'dy': dx_y, 'dz': dx_z,
                'dxx': dxx, 'dyy': dyy, 'dzz': dzz,
            }
        
        def physics_loss(
            self,
            coords: torch.Tensor,
            predictions: torch.Tensor,
        ) -> torch.Tensor:
            """
            3D Poisson's equation: ∇²φ = -4πGρ
            
            Args:
                coords: Spatial coordinates
                predictions: Network predictions (potential, density)
            
            Returns:
                Physics loss
            """
            coords.requires_grad_(True)
            
            potential = predictions[:, 0:1]
            density = predictions[:, 1:2]
            
            # Compute Laplacian
            grads = self.compute_gradients_3d(potential, coords)
            laplacian = grads['dxx'] + grads['dyy'] + grads['dzz']
            
            # Poisson's equation residual
            poisson_residual = laplacian + 4 * np.pi * self.G * density
            
            return torch.mean(poisson_residual ** 2)
    
    
    class UNet3D(nn.Module):
        """
        3D U-Net for volumetric inversion.
        
        Encoder-decoder architecture for 3D density reconstruction.
        """
        
        def __init__(
            self,
            in_channels: int = 1,
            out_channels: int = 1,
            features: List[int] = [32, 64, 128, 256],
        ):
            super().__init__()
            
            self.in_channels = in_channels
            self.out_channels = out_channels
            
            # Encoder
            self.encoder = nn.ModuleList()
            self.pool = nn.MaxPool3d(kernel_size=2, stride=2)
            
            for feature in features:
                self.encoder.append(
                    self._block(in_channels, feature)
                )
                in_channels = feature
            
            # Bottleneck
            self.bottleneck = self._block(features[-1], features[-1] * 2)
            
            # Decoder
            self.decoder = nn.ModuleList()
            self.upconv = nn.ModuleList()
            
            for feature in reversed(features):
                self.upconv.append(
                    nn.ConvTranspose3d(feature * 2, feature, kernel_size=2, stride=2)
                )
                self.decoder.append(
                    self._block(feature * 2, feature)
                )
            
            # Final convolution
            self.final_conv = nn.Conv3d(features[0], out_channels, kernel_size=1)
        
        def _block(self, in_channels: int, out_channels: int) -> nn.Sequential:
            """3D convolution block."""
            return nn.Sequential(
                nn.Conv3d(in_channels, out_channels, kernel_size=3, padding=1, bias=False),
                nn.BatchNorm3d(out_channels),
                nn.ReLU(inplace=True),
                nn.Conv3d(out_channels, out_channels, kernel_size=3, padding=1, bias=False),
                nn.BatchNorm3d(out_channels),
                nn.ReLU(inplace=True),
            )
        
        def forward(self, x: torch.Tensor) -> torch.Tensor:
            """
            Forward pass.
            
            Args:
                x: Input volume, shape (batch, channels, depth, height, width)
            
            Returns:
                Output volume, same shape as input
            """
            # Encoder
            skip_connections = []
            
            for encode in self.encoder:
                x = encode(x)
                skip_connections.append(x)
                x = self.pool(x)
            
            # Bottleneck
            x = self.bottleneck(x)
            
            # Decoder
            skip_connections = skip_connections[::-1]
            
            for idx in range(len(self.decoder)):
                x = self.upconv[idx](x)
                skip = skip_connections[idx]
                
                # Handle size mismatch
                if x.shape != skip.shape:
                    x = F.interpolate(x, size=skip.shape[2:])
                
                x = torch.cat([skip, x], dim=1)
                x = self.decoder[idx](x)
            
            return self.final_conv(x)
    
    
    class Volumetric3DInversion(nn.Module):
        """
        3D volumetric inversion network.
        
        Maps surface observations to 3D subsurface density.
        """
        
        def __init__(
            self,
            n_observations: int,
            volume_shape: Tuple[int, int, int],
            hidden_dim: int = 512,
            n_layers: int = 4,
        ):
            """
            Args:
                n_observations: Number of surface observations
                volume_shape: 3D output shape (depth, height, width)
                hidden_dim: Hidden dimension
                n_layers: Number of layers
            """
            super().__init__()
            
            self.volume_shape = volume_shape
            n_voxels = np.prod(volume_shape)
            
            # Encoder: observations -> latent
            layers = []
            prev_dim = n_observations
            
            for _ in range(n_layers):
                layers.append(nn.Linear(prev_dim, hidden_dim))
                layers.append(nn.ReLU())
                layers.append(nn.Dropout(0.1))
                prev_dim = hidden_dim
            
            layers.append(nn.Linear(hidden_dim, n_voxels))
            
            self.network = nn.Sequential(*layers)
            
            # 3D refinement with U-Net
            self.refine = UNet3D(in_channels=1, out_channels=1, features=[16, 32, 64])
        
        def forward(self, observations: torch.Tensor) -> torch.Tensor:
            """
            Invert observations to 3D density.
            
            Args:
                observations: Surface observations, shape (batch, n_observations)
            
            Returns:
                3D density volume, shape (batch, depth, height, width)
            """
            # Initial inversion
            density_flat = self.network(observations)
            
            # Reshape to volume
            batch_size = observations.shape[0]
            d, h, w = self.volume_shape
            density_volume = density_flat.view(batch_size, 1, d, h, w)
            
            # Refine with U-Net
            density_refined = self.refine(density_volume)
            
            return density_refined.squeeze(1)
    
    
    class MultiScale3DInversion(nn.Module):
        """
        Multi-scale 3D inversion with progressive refinement.
        
        Starts with coarse resolution and progressively refines.
        """
        
        def __init__(
            self,
            n_observations: int,
            base_shape: Tuple[int, int, int] = (8, 8, 8),
            n_scales: int = 3,
        ):
            """
            Args:
                n_observations: Number of observations
                base_shape: Coarsest resolution
                n_scales: Number of scales (each doubles resolution)
            """
            super().__init__()
            
            self.n_scales = n_scales
            self.base_shape = base_shape
            
            # Coarse prediction
            n_voxels_base = np.prod(base_shape)
            self.coarse_predictor = nn.Sequential(
                nn.Linear(n_observations, 512),
                nn.ReLU(),
                nn.Linear(512, 512),
                nn.ReLU(),
                nn.Linear(512, n_voxels_base),
            )
            
            # Refinement networks
            self.refiners = nn.ModuleList()
            for i in range(n_scales - 1):
                self.refiners.append(
                    nn.Sequential(
                        nn.Conv3d(1, 32, 3, padding=1),
                        nn.ReLU(),
                        nn.Conv3d(32, 32, 3, padding=1),
                        nn.ReLU(),
                        nn.Conv3d(32, 8, 3, padding=1),  # 8 channels for 2x2x2 upsampling
                    )
                )
        
        def forward(self, observations: torch.Tensor) -> torch.Tensor:
            """
            Multi-scale inversion.
            
            Args:
                observations: Surface observations
            
            Returns:
                Fine-scale 3D density
            """
            batch_size = observations.shape[0]
            
            # Coarse prediction
            density = self.coarse_predictor(observations)
            d, h, w = self.base_shape
            density = density.view(batch_size, 1, d, h, w)
            
            # Progressive refinement
            for refiner in self.refiners:
                # Apply refinement
                refinement = refiner(density)
                
                # Upsample 2x with learned upsampling
                b, c, d, h, w = refinement.shape
                refinement = refinement.view(b, 2, 2, 2, d, h, w)
                refinement = refinement.permute(0, 4, 1, 5, 2, 6, 3)
                refinement = refinement.contiguous().view(b, 1, d*2, h*2, w*2)
                
                density = refinement
            
            return density.squeeze(1)


else:
    # Fallback classes
    class Gravity3DPINN:
        def __init__(self, *args, **kwargs):
            raise ImportError("PyTorch required for 3D models")
    
    class UNet3D(Gravity3DPINN):
        pass
    
    class Volumetric3DInversion(Gravity3DPINN):
        pass
    
    class MultiScale3DInversion(Gravity3DPINN):
        pass
