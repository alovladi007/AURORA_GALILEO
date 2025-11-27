"""
Fourier Neural Operators (FNOs)
================================

FNOs for fast forward modeling of geophysical fields.
Learns solution operators in Fourier space for efficient predictions.
"""

import numpy as np
from typing import Optional, List, Tuple
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
    class SpectralConv2d(nn.Module):
        """
        2D Fourier layer - performs convolution in Fourier space.
        
        Faster than spatial convolution for large receptive fields.
        """
        
        def __init__(self, in_channels: int, out_channels: int, modes1: int, modes2: int):
            """
            Args:
                in_channels: Number of input channels
                out_channels: Number of output channels
                modes1: Number of Fourier modes to keep in x direction
                modes2: Number of Fourier modes to keep in y direction
            """
            super().__init__()
            
            self.in_channels = in_channels
            self.out_channels = out_channels
            self.modes1 = modes1  # Number of Fourier modes
            self.modes2 = modes2
            
            # Fourier weights for multiplication
            self.scale = 1 / (in_channels * out_channels)
            self.weights1 = nn.Parameter(
                self.scale * torch.rand(in_channels, out_channels, self.modes1, self.modes2, dtype=torch.cfloat)
            )
            self.weights2 = nn.Parameter(
                self.scale * torch.rand(in_channels, out_channels, self.modes1, self.modes2, dtype=torch.cfloat)
            )
        
        def compl_mul2d(self, input: torch.Tensor, weights: torch.Tensor) -> torch.Tensor:
            """Complex multiplication in Fourier space."""
            # (batch, in_channel, x, y), (in_channel, out_channel, x, y) -> (batch, out_channel, x, y)
            return torch.einsum("bixy,ioxy->boxy", input, weights)
        
        def forward(self, x: torch.Tensor) -> torch.Tensor:
            """
            Forward pass in Fourier space.
            
            Args:
                x: Input tensor, shape (batch, in_channels, height, width)
            
            Returns:
                Output tensor, shape (batch, out_channels, height, width)
            """
            batch_size = x.shape[0]
            
            # Compute Fourier coefficients
            x_ft = torch.fft.rfft2(x)
            
            # Multiply relevant Fourier modes
            out_ft = torch.zeros(
                batch_size, self.out_channels, x.size(-2), x.size(-1)//2 + 1,
                dtype=torch.cfloat, device=x.device
            )
            
            # Lower modes
            out_ft[:, :, :self.modes1, :self.modes2] = \
                self.compl_mul2d(x_ft[:, :, :self.modes1, :self.modes2], self.weights1)
            
            # Upper modes
            out_ft[:, :, -self.modes1:, :self.modes2] = \
                self.compl_mul2d(x_ft[:, :, -self.modes1:, :self.modes2], self.weights2)
            
            # Return to physical space
            x = torch.fft.irfft2(out_ft, s=(x.size(-2), x.size(-1)))
            
            return x
    
    
    class SpectralConv3d(nn.Module):
        """
        3D Fourier layer for volumetric data.
        """
        
        def __init__(self, in_channels: int, out_channels: int, modes1: int, modes2: int, modes3: int):
            """
            Args:
                in_channels: Number of input channels
                out_channels: Number of output channels
                modes1: Fourier modes in x direction
                modes2: Fourier modes in y direction
                modes3: Fourier modes in z direction
            """
            super().__init__()
            
            self.in_channels = in_channels
            self.out_channels = out_channels
            self.modes1 = modes1
            self.modes2 = modes2
            self.modes3 = modes3
            
            # Fourier weights
            self.scale = 1 / (in_channels * out_channels)
            self.weights1 = nn.Parameter(
                self.scale * torch.rand(in_channels, out_channels, self.modes1, self.modes2, self.modes3, dtype=torch.cfloat)
            )
            self.weights2 = nn.Parameter(
                self.scale * torch.rand(in_channels, out_channels, self.modes1, self.modes2, self.modes3, dtype=torch.cfloat)
            )
            self.weights3 = nn.Parameter(
                self.scale * torch.rand(in_channels, out_channels, self.modes1, self.modes2, self.modes3, dtype=torch.cfloat)
            )
            self.weights4 = nn.Parameter(
                self.scale * torch.rand(in_channels, out_channels, self.modes1, self.modes2, self.modes3, dtype=torch.cfloat)
            )
        
        def compl_mul3d(self, input: torch.Tensor, weights: torch.Tensor) -> torch.Tensor:
            """Complex multiplication in 3D Fourier space."""
            return torch.einsum("bixyz,ioxyz->boxyz", input, weights)
        
        def forward(self, x: torch.Tensor) -> torch.Tensor:
            """
            Forward pass in 3D Fourier space.
            
            Args:
                x: Input tensor, shape (batch, in_channels, depth, height, width)
            
            Returns:
                Output tensor, shape (batch, out_channels, depth, height, width)
            """
            batch_size = x.shape[0]
            
            # Compute 3D Fourier coefficients
            x_ft = torch.fft.rfftn(x, dim=[-3, -2, -1])
            
            # Multiply relevant Fourier modes
            out_ft = torch.zeros(
                batch_size, self.out_channels, x.size(-3), x.size(-2), x.size(-1)//2 + 1,
                dtype=torch.cfloat, device=x.device
            )
            
            # Mode multiplication (4 octants in 3D)
            out_ft[:, :, :self.modes1, :self.modes2, :self.modes3] = \
                self.compl_mul3d(x_ft[:, :, :self.modes1, :self.modes2, :self.modes3], self.weights1)
            
            out_ft[:, :, -self.modes1:, :self.modes2, :self.modes3] = \
                self.compl_mul3d(x_ft[:, :, -self.modes1:, :self.modes2, :self.modes3], self.weights2)
            
            out_ft[:, :, :self.modes1, -self.modes2:, :self.modes3] = \
                self.compl_mul3d(x_ft[:, :, :self.modes1, -self.modes2:, :self.modes3], self.weights3)
            
            out_ft[:, :, -self.modes1:, -self.modes2:, :self.modes3] = \
                self.compl_mul3d(x_ft[:, :, -self.modes1:, -self.modes2:, :self.modes3], self.weights4)
            
            # Return to physical space
            x = torch.fft.irfftn(out_ft, s=(x.size(-3), x.size(-2), x.size(-1)))
            
            return x
    
    
    class FNO2D(nn.Module):
        """
        2D Fourier Neural Operator.
        
        Fast surrogate model for 2D forward problems (e.g., gravity/magnetic maps).
        """
        
        def __init__(
            self,
            modes1: int = 12,
            modes2: int = 12,
            width: int = 64,
            n_layers: int = 4,
            input_channels: int = 1,
            output_channels: int = 1,
        ):
            """
            Args:
                modes1: Number of Fourier modes in x direction
                modes2: Number of Fourier modes in y direction
                width: Hidden channel dimension
                n_layers: Number of Fourier layers
                input_channels: Number of input channels (e.g., 1 for density)
                output_channels: Number of output channels (e.g., 1 for gravity)
            """
            super().__init__()
            
            self.modes1 = modes1
            self.modes2 = modes2
            self.width = width
            self.n_layers = n_layers
            
            # Input projection
            self.fc0 = nn.Linear(input_channels + 2, width)  # +2 for (x, y) coordinates
            
            # Fourier layers
            self.fourier_layers = nn.ModuleList([
                SpectralConv2d(width, width, modes1, modes2)
                for _ in range(n_layers)
            ])
            
            # Skip connections
            self.skip_layers = nn.ModuleList([
                nn.Conv2d(width, width, 1)
                for _ in range(n_layers)
            ])
            
            # Output projection
            self.fc1 = nn.Linear(width, 128)
            self.fc2 = nn.Linear(128, output_channels)
        
        def forward(self, x: torch.Tensor) -> torch.Tensor:
            """
            Forward pass.
            
            Args:
                x: Input tensor, shape (batch, height, width, input_channels)
                   or (batch, input_channels, height, width)
            
            Returns:
                Output tensor, shape (batch, output_channels, height, width)
            """
            # Handle both channel-last and channel-first formats
            if x.dim() == 4 and x.shape[-1] <= x.shape[1]:
                # Already channel-first
                pass
            elif x.dim() == 4:
                # Channel-last, need to permute
                x = x.permute(0, 3, 1, 2)
            
            batch_size, _, height, width = x.shape
            
            # Create coordinate grid
            grid_x = torch.linspace(0, 1, height, device=x.device)
            grid_y = torch.linspace(0, 1, width, device=x.device)
            grid_x, grid_y = torch.meshgrid(grid_x, grid_y, indexing='ij')
            grid = torch.stack([grid_x, grid_y], dim=-1)  # (height, width, 2)
            grid = grid.unsqueeze(0).repeat(batch_size, 1, 1, 1)  # (batch, height, width, 2)
            
            # Append coordinates to input
            x = x.permute(0, 2, 3, 1)  # (batch, height, width, channels)
            x = torch.cat([x, grid], dim=-1)  # (batch, height, width, channels+2)
            
            # Input projection
            x = self.fc0(x)  # (batch, height, width, width)
            x = x.permute(0, 3, 1, 2)  # (batch, width, height, width_dim)
            
            # Fourier layers with skip connections
            for fourier_layer, skip_layer in zip(self.fourier_layers, self.skip_layers):
                x1 = fourier_layer(x)
                x2 = skip_layer(x)
                x = x1 + x2
                x = F.gelu(x)
            
            # Output projection
            x = x.permute(0, 2, 3, 1)  # (batch, height, width, width)
            x = self.fc1(x)
            x = F.gelu(x)
            x = self.fc2(x)
            
            # Return channel-first
            x = x.permute(0, 3, 1, 2)  # (batch, output_channels, height, width)
            
            return x
    
    
    class FNO3D(nn.Module):
        """
        3D Fourier Neural Operator.
        
        Fast surrogate model for 3D subsurface modeling.
        """
        
        def __init__(
            self,
            modes1: int = 8,
            modes2: int = 8,
            modes3: int = 8,
            width: int = 32,
            n_layers: int = 4,
            input_channels: int = 1,
            output_channels: int = 1,
        ):
            """
            Args:
                modes1: Fourier modes in x direction
                modes2: Fourier modes in y direction
                modes3: Fourier modes in z direction
                width: Hidden channel dimension
                n_layers: Number of Fourier layers
                input_channels: Number of input channels
                output_channels: Number of output channels
            """
            super().__init__()
            
            self.modes1 = modes1
            self.modes2 = modes2
            self.modes3 = modes3
            self.width = width
            self.n_layers = n_layers
            
            # Input projection
            self.fc0 = nn.Linear(input_channels + 3, width)  # +3 for (x, y, z) coordinates
            
            # Fourier layers
            self.fourier_layers = nn.ModuleList([
                SpectralConv3d(width, width, modes1, modes2, modes3)
                for _ in range(n_layers)
            ])
            
            # Skip connections
            self.skip_layers = nn.ModuleList([
                nn.Conv3d(width, width, 1)
                for _ in range(n_layers)
            ])
            
            # Output projection
            self.fc1 = nn.Linear(width, 128)
            self.fc2 = nn.Linear(128, output_channels)
        
        def forward(self, x: torch.Tensor) -> torch.Tensor:
            """
            Forward pass.
            
            Args:
                x: Input tensor, shape (batch, input_channels, depth, height, width)
            
            Returns:
                Output tensor, shape (batch, output_channels, depth, height, width)
            """
            batch_size, _, depth, height, width = x.shape
            
            # Create coordinate grid
            grid_x = torch.linspace(0, 1, depth, device=x.device)
            grid_y = torch.linspace(0, 1, height, device=x.device)
            grid_z = torch.linspace(0, 1, width, device=x.device)
            grid_x, grid_y, grid_z = torch.meshgrid(grid_x, grid_y, grid_z, indexing='ij')
            grid = torch.stack([grid_x, grid_y, grid_z], dim=-1)  # (depth, height, width, 3)
            grid = grid.unsqueeze(0).repeat(batch_size, 1, 1, 1, 1)  # (batch, depth, height, width, 3)
            
            # Append coordinates to input
            x = x.permute(0, 2, 3, 4, 1)  # (batch, depth, height, width, channels)
            x = torch.cat([x, grid], dim=-1)  # (batch, depth, height, width, channels+3)
            
            # Input projection
            x = self.fc0(x)  # (batch, depth, height, width, width)
            x = x.permute(0, 4, 1, 2, 3)  # (batch, width, depth, height, width_dim)
            
            # Fourier layers with skip connections
            for fourier_layer, skip_layer in zip(self.fourier_layers, self.skip_layers):
                x1 = fourier_layer(x)
                x2 = skip_layer(x)
                x = x1 + x2
                x = F.gelu(x)
            
            # Output projection
            x = x.permute(0, 2, 3, 4, 1)  # (batch, depth, height, width, width)
            x = self.fc1(x)
            x = F.gelu(x)
            x = self.fc2(x)
            
            # Return channel-first
            x = x.permute(0, 4, 1, 2, 3)  # (batch, output_channels, depth, height, width)
            
            return x
    
    
    class GravityForwardFNO(FNO2D):
        """
        FNO specialized for gravity forward modeling.
        
        Maps density distribution to gravity anomaly.
        """
        
        def __init__(
            self,
            modes: int = 12,
            width: int = 64,
            n_layers: int = 4,
        ):
            """
            Args:
                modes: Number of Fourier modes (same for x and y)
                width: Hidden channel dimension
                n_layers: Number of Fourier layers
            """
            super().__init__(
                modes1=modes,
                modes2=modes,
                width=width,
                n_layers=n_layers,
                input_channels=1,  # Density
                output_channels=1,  # Gravity anomaly
            )
    
    
    class MagneticForwardFNO(FNO2D):
        """
        FNO specialized for magnetic forward modeling.
        
        Maps magnetic susceptibility to magnetic anomaly.
        """
        
        def __init__(
            self,
            modes: int = 12,
            width: int = 64,
            n_layers: int = 4,
        ):
            """
            Args:
                modes: Number of Fourier modes
                width: Hidden channel dimension
                n_layers: Number of Fourier layers
            """
            super().__init__(
                modes1=modes,
                modes2=modes,
                width=width,
                n_layers=n_layers,
                input_channels=1,  # Susceptibility
                output_channels=3,  # (Bx, By, Bz)
            )
    
    
    class JointForwardFNO(FNO2D):
        """
        FNO for joint gravity-magnetic forward modeling.
        
        Maps (density, susceptibility) to (gravity, magnetic) fields.
        """
        
        def __init__(
            self,
            modes: int = 12,
            width: int = 96,
            n_layers: int = 4,
        ):
            """
            Args:
                modes: Number of Fourier modes
                width: Hidden channel dimension
                n_layers: Number of Fourier layers
            """
            super().__init__(
                modes1=modes,
                modes2=modes,
                width=width,
                n_layers=n_layers,
                input_channels=2,  # (density, susceptibility)
                output_channels=4,  # (gravity, Bx, By, Bz)
            )


else:
    # Fallback classes if PyTorch not available
    class SpectralConv2d:
        def __init__(self, *args, **kwargs):
            raise ImportError("PyTorch required for FNO. Install with: pip install torch")
    
    class SpectralConv3d(SpectralConv2d):
        pass
    
    class FNO2D(SpectralConv2d):
        pass
    
    class FNO3D(SpectralConv2d):
        pass
    
    class GravityForwardFNO(SpectralConv2d):
        pass
    
    class MagneticForwardFNO(SpectralConv2d):
        pass
    
    class JointForwardFNO(SpectralConv2d):
        pass
