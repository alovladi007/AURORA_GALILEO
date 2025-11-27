"""
Satellite Data Loaders
======================

Data loaders for GRACE, GOCE, and GRACE-FO satellite missions.
"""

import numpy as np
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Union
from dataclasses import dataclass
import json

try:
    import torch
    from torch.utils.data import Dataset, DataLoader
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False


@dataclass
class SatelliteMetadata:
    """Metadata for satellite observations."""
    mission: str
    date: str
    altitude: float  # km
    resolution: float  # km
    noise_level: float  # mGal or nT
    sensor_type: str
    coverage: str  # 'global', 'regional', etc.


class GRACEDataLoader:
    """
    Data loader for GRACE (Gravity Recovery and Climate Experiment) data.
    
    GRACE provides monthly gravity field solutions as spherical harmonic coefficients.
    """
    
    def __init__(
        self,
        data_dir: Union[str, Path],
        max_degree: int = 120,
        product: str = 'RL06',
    ):
        """
        Args:
            data_dir: Directory containing GRACE data files
            max_degree: Maximum spherical harmonic degree
            product: GRACE product version (RL05, RL06, etc.)
        """
        self.data_dir = Path(data_dir)
        self.max_degree = max_degree
        self.product = product
        
        if not self.data_dir.exists():
            print(f"Warning: GRACE data directory {data_dir} does not exist")
    
    def load_spherical_harmonics(
        self,
        filename: str,
    ) -> Dict[str, np.ndarray]:
        """
        Load GRACE spherical harmonic coefficients.
        
        Args:
            filename: Name of GRACE data file
        
        Returns:
            Dictionary with 'C' (cosine) and 'S' (sine) coefficients
        """
        filepath = self.data_dir / filename
        
        if not filepath.exists():
            raise FileNotFoundError(f"GRACE file not found: {filepath}")
        
        # Initialize coefficient arrays
        C = np.zeros((self.max_degree + 1, self.max_degree + 1))
        S = np.zeros((self.max_degree + 1, self.max_degree + 1))
        
        # Parse GRACE format (simplified - real format is more complex)
        with open(filepath, 'r') as f:
            for line in f:
                if line.startswith('#') or line.startswith('END'):
                    continue
                
                parts = line.split()
                if len(parts) >= 6:
                    keyword = parts[0]
                    if keyword in ['GRCOF2', 'GCOEF']:
                        l = int(parts[1])  # degree
                        m = int(parts[2])  # order
                        c_lm = float(parts[3])
                        s_lm = float(parts[4])
                        
                        if l <= self.max_degree:
                            C[l, m] = c_lm
                            S[l, m] = s_lm
        
        return {'C': C, 'S': S}
    
    def spherical_harmonics_to_grid(
        self,
        C: np.ndarray,
        S: np.ndarray,
        lat_grid: np.ndarray,
        lon_grid: np.ndarray,
        gm: float = 3.986004418e14,  # Earth's GM (m^3/s^2)
        radius: float = 6.3781364e6,  # Earth's radius (m)
    ) -> np.ndarray:
        """
        Convert spherical harmonic coefficients to gravity anomaly grid.
        
        Args:
            C: Cosine coefficients
            S: Sine coefficients
            lat_grid: Latitude grid (degrees)
            lon_grid: Longitude grid (degrees)
            gm: Gravitational constant times Earth mass
            radius: Earth reference radius
        
        Returns:
            Gravity anomaly grid in mGal
        """
        lat_rad = np.deg2rad(lat_grid)
        lon_rad = np.deg2rad(lon_grid)
        
        # Initialize output
        gravity = np.zeros_like(lat_grid)
        
        # Sum over spherical harmonics
        for l in range(self.max_degree + 1):
            for m in range(l + 1):
                # Legendre polynomial (simplified - should use scipy)
                P_lm = self._legendre(l, m, np.sin(lat_rad))
                
                # Spherical harmonic synthesis
                cos_term = C[l, m] * np.cos(m * lon_rad)
                sin_term = S[l, m] * np.sin(m * lon_rad)
                
                # Add to gravity field
                factor = (l + 1) * (radius ** l)
                gravity += factor * P_lm * (cos_term + sin_term)
        
        # Convert to mGal (1 mGal = 1e-5 m/s^2)
        gravity_mgal = gravity * gm / (radius ** 2) * 1e5
        
        return gravity_mgal
    
    def _legendre(self, l: int, m: int, x: np.ndarray) -> np.ndarray:
        """Simplified Legendre polynomial (should use scipy in production)."""
        # Placeholder - use scipy.special.lpmv in production
        return np.ones_like(x)
    
    def load_monthly_data(
        self,
        year: int,
        month: int,
        grid_shape: Tuple[int, int] = (180, 360),
    ) -> Tuple[np.ndarray, SatelliteMetadata]:
        """
        Load GRACE monthly gravity field.
        
        Args:
            year: Year
            month: Month (1-12)
            grid_shape: Output grid shape (lat, lon)
        
        Returns:
            Tuple of (gravity_grid, metadata)
        """
        # Construct filename
        filename = f'GRACE_{self.product}_{year}_{month:02d}.gfc'
        
        # Create lat/lon grids
        lat = np.linspace(-90, 90, grid_shape[0])
        lon = np.linspace(-180, 180, grid_shape[1])
        lon_grid, lat_grid = np.meshgrid(lon, lat)
        
        try:
            # Load spherical harmonics
            coeffs = self.load_spherical_harmonics(filename)
            
            # Convert to grid
            gravity_grid = self.spherical_harmonics_to_grid(
                coeffs['C'], coeffs['S'],
                lat_grid, lon_grid,
            )
            
        except FileNotFoundError:
            # Generate synthetic data if file not found
            print(f"Warning: Using synthetic data for {year}-{month:02d}")
            gravity_grid = np.random.randn(*grid_shape) * 10  # ±10 mGal noise
        
        # Metadata
        metadata = SatelliteMetadata(
            mission='GRACE',
            date=f'{year}-{month:02d}',
            altitude=400.0,  # km
            resolution=300.0,  # km
            noise_level=0.5,  # mGal
            sensor_type='accelerometer',
            coverage='global',
        )
        
        return gravity_grid, metadata


class GOCEDataLoader:
    """
    Data loader for GOCE (Gravity field and steady-state Ocean Circulation Explorer) data.
    
    GOCE provides high-resolution gravity gradients.
    """
    
    def __init__(
        self,
        data_dir: Union[str, Path],
        product: str = 'TIM_R6',
    ):
        """
        Args:
            data_dir: Directory containing GOCE data files
            product: GOCE product type (TIM, DIR, SPW)
        """
        self.data_dir = Path(data_dir)
        self.product = product
        
        if not self.data_dir.exists():
            print(f"Warning: GOCE data directory {data_dir} does not exist")
    
    def load_gravity_gradients(
        self,
        filename: str,
    ) -> Dict[str, np.ndarray]:
        """
        Load GOCE gravity gradient tensor.
        
        Args:
            filename: GOCE data file
        
        Returns:
            Dictionary with gradient components (Txx, Tyy, Tzz, Txy, Txz, Tyz)
        """
        filepath = self.data_dir / filename
        
        if not filepath.exists():
            # Generate synthetic gradients
            print(f"Warning: Using synthetic GOCE data")
            n_points = 10000
            gradients = {
                'Txx': np.random.randn(n_points) * 0.1,  # Eotvos units
                'Tyy': np.random.randn(n_points) * 0.1,
                'Tzz': np.random.randn(n_points) * 0.1,
                'Txy': np.random.randn(n_points) * 0.05,
                'Txz': np.random.randn(n_points) * 0.05,
                'Tyz': np.random.randn(n_points) * 0.05,
            }
            return gradients
        
        # Load real data (format depends on product)
        # Placeholder implementation
        gradients = {}
        with open(filepath, 'r') as f:
            # Parse GOCE format
            pass
        
        return gradients
    
    def load_gridded_data(
        self,
        grid_shape: Tuple[int, int] = (180, 360),
    ) -> Tuple[np.ndarray, SatelliteMetadata]:
        """
        Load GOCE gravity data on regular grid.
        
        Args:
            grid_shape: Output grid shape
        
        Returns:
            Tuple of (gravity_grid, metadata)
        """
        # Generate synthetic data for demo
        gravity_grid = np.random.randn(*grid_shape) * 5  # ±5 mGal
        
        metadata = SatelliteMetadata(
            mission='GOCE',
            date='2011-06',
            altitude=255.0,  # km
            resolution=80.0,  # km
            noise_level=0.1,  # mGal
            sensor_type='gradiometer',
            coverage='global',
        )
        
        return gravity_grid, metadata


class GRACEFODataLoader(GRACEDataLoader):
    """
    Data loader for GRACE-FO (GRACE Follow-On) data.
    
    Similar to GRACE but with improved instrumentation.
    """
    
    def __init__(
        self,
        data_dir: Union[str, Path],
        max_degree: int = 120,
        product: str = 'RL06',
    ):
        super().__init__(data_dir, max_degree, product)
        self.mission = 'GRACE-FO'
    
    def load_monthly_data(
        self,
        year: int,
        month: int,
        grid_shape: Tuple[int, int] = (180, 360),
    ) -> Tuple[np.ndarray, SatelliteMetadata]:
        """Load GRACE-FO monthly data."""
        gravity_grid, metadata = super().load_monthly_data(year, month, grid_shape)
        
        # Update metadata for GRACE-FO
        metadata.mission = 'GRACE-FO'
        metadata.altitude = 490.0  # km
        metadata.noise_level = 0.3  # mGal (improved)
        
        return gravity_grid, metadata


if HAS_TORCH:
    class SatelliteDataset(Dataset):
        """
        PyTorch Dataset for satellite geophysical data.
        
        Supports GRACE, GOCE, and GRACE-FO data.
        """
        
        def __init__(
            self,
            gravity_data: List[np.ndarray],
            density_models: Optional[List[np.ndarray]] = None,
            metadata: Optional[List[SatelliteMetadata]] = None,
            transform: Optional[callable] = None,
        ):
            """
            Args:
                gravity_data: List of gravity observation grids
                density_models: List of density model grids (for supervised learning)
                metadata: List of metadata for each sample
                transform: Optional transform to apply
            """
            self.gravity_data = gravity_data
            self.density_models = density_models
            self.metadata = metadata
            self.transform = transform
        
        def __len__(self) -> int:
            return len(self.gravity_data)
        
        def __getitem__(self, idx: int) -> Union[torch.Tensor, Tuple[torch.Tensor, torch.Tensor]]:
            # Load gravity data
            gravity = torch.tensor(self.gravity_data[idx], dtype=torch.float32)
            
            if self.transform:
                gravity = self.transform(gravity)
            
            # If supervised, return (gravity, density)
            if self.density_models is not None:
                density = torch.tensor(self.density_models[idx], dtype=torch.float32)
                if self.transform:
                    density = self.transform(density)
                return gravity, density
            
            return gravity
    
    
    def create_dataloaders(
        gravity_data: List[np.ndarray],
        density_models: Optional[List[np.ndarray]] = None,
        batch_size: int = 32,
        train_split: float = 0.8,
        val_split: float = 0.1,
        shuffle: bool = True,
    ) -> Dict[str, DataLoader]:
        """
        Create train/val/test dataloaders from satellite data.
        
        Args:
            gravity_data: List of gravity grids
            density_models: List of density grids
            batch_size: Batch size
            train_split: Fraction for training
            val_split: Fraction for validation
            shuffle: Whether to shuffle data
        
        Returns:
            Dictionary with 'train', 'val', 'test' dataloaders
        """
        n_samples = len(gravity_data)
        indices = np.random.permutation(n_samples) if shuffle else np.arange(n_samples)
        
        n_train = int(n_samples * train_split)
        n_val = int(n_samples * val_split)
        
        train_idx = indices[:n_train]
        val_idx = indices[n_train:n_train+n_val]
        test_idx = indices[n_train+n_val:]
        
        # Create datasets
        train_dataset = SatelliteDataset(
            [gravity_data[i] for i in train_idx],
            [density_models[i] for i in train_idx] if density_models else None,
        )
        
        val_dataset = SatelliteDataset(
            [gravity_data[i] for i in val_idx],
            [density_models[i] for i in val_idx] if density_models else None,
        )
        
        test_dataset = SatelliteDataset(
            [gravity_data[i] for i in test_idx],
            [density_models[i] for i in test_idx] if density_models else None,
        )
        
        # Create dataloaders
        dataloaders = {
            'train': DataLoader(train_dataset, batch_size=batch_size, shuffle=True),
            'val': DataLoader(val_dataset, batch_size=batch_size, shuffle=False),
            'test': DataLoader(test_dataset, batch_size=batch_size, shuffle=False),
        }
        
        return dataloaders

else:
    # Fallback classes
    class SatelliteDataset:
        def __init__(self, *args, **kwargs):
            raise ImportError("PyTorch required for SatelliteDataset")
    
    def create_dataloaders(*args, **kwargs):
        raise ImportError("PyTorch required for dataloaders")
