"""
Data Preprocessing Utilities
=============================

Preprocessing functions for satellite geophysical data.
"""

import numpy as np
from typing import Tuple, Optional, Dict
from scipy import interpolate, ndimage


def normalize_gravity(
    gravity: np.ndarray,
    method: str = 'standardize',
    stats: Optional[Dict] = None,
) -> Tuple[np.ndarray, Dict]:
    """
    Normalize gravity data.
    
    Args:
        gravity: Gravity anomaly in mGal
        method: Normalization method ('standardize', 'minmax', 'robust')
        stats: Pre-computed statistics (for applying same normalization)
    
    Returns:
        Tuple of (normalized_gravity, stats_dict)
    """
    if stats is None:
        if method == 'standardize':
            mean = np.mean(gravity)
            std = np.std(gravity)
            normalized = (gravity - mean) / (std + 1e-8)
            stats = {'mean': mean, 'std': std, 'method': method}
        
        elif method == 'minmax':
            vmin = np.min(gravity)
            vmax = np.max(gravity)
            normalized = (gravity - vmin) / (vmax - vmin + 1e-8)
            stats = {'min': vmin, 'max': vmax, 'method': method}
        
        elif method == 'robust':
            median = np.median(gravity)
            q25, q75 = np.percentile(gravity, [25, 75])
            iqr = q75 - q25
            normalized = (gravity - median) / (iqr + 1e-8)
            stats = {'median': median, 'iqr': iqr, 'method': method}
        
        else:
            raise ValueError(f"Unknown normalization method: {method}")
    
    else:
        # Apply pre-computed normalization
        if stats['method'] == 'standardize':
            normalized = (gravity - stats['mean']) / (stats['std'] + 1e-8)
        elif stats['method'] == 'minmax':
            normalized = (gravity - stats['min']) / (stats['max'] - stats['min'] + 1e-8)
        elif stats['method'] == 'robust':
            normalized = (gravity - stats['median']) / (stats['iqr'] + 1e-8)
    
    return normalized, stats


def denormalize_gravity(
    normalized: np.ndarray,
    stats: Dict,
) -> np.ndarray:
    """
    Reverse normalization.
    
    Args:
        normalized: Normalized data
        stats: Statistics from normalization
    
    Returns:
        Original scale data
    """
    method = stats['method']
    
    if method == 'standardize':
        return normalized * stats['std'] + stats['mean']
    elif method == 'minmax':
        return normalized * (stats['max'] - stats['min']) + stats['min']
    elif method == 'robust':
        return normalized * stats['iqr'] + stats['median']
    else:
        raise ValueError(f"Unknown method: {method}")


def normalize_magnetic(
    magnetic: np.ndarray,
    method: str = 'standardize',
    stats: Optional[Dict] = None,
) -> Tuple[np.ndarray, Dict]:
    """Normalize magnetic data (nT)."""
    return normalize_gravity(magnetic, method, stats)


def denormalize_model(
    normalized: np.ndarray,
    stats: Dict,
) -> np.ndarray:
    """Denormalize model parameters (density, susceptibility)."""
    return denormalize_gravity(normalized, stats)


def grid_to_observations(
    grid: np.ndarray,
    observation_points: np.ndarray,
    method: str = 'linear',
) -> np.ndarray:
    """
    Interpolate grid values at observation points.
    
    Args:
        grid: Regular grid, shape (ny, nx)
        observation_points: Points to sample, shape (n_points, 2) with (y, x) coords
        method: Interpolation method
    
    Returns:
        Observations at points, shape (n_points,)
    """
    ny, nx = grid.shape
    
    # Create grid coordinates
    y_grid = np.linspace(0, ny-1, ny)
    x_grid = np.linspace(0, nx-1, nx)
    
    # Interpolate
    interp = interpolate.RegularGridInterpolator(
        (y_grid, x_grid),
        grid,
        method=method,
        bounds_error=False,
        fill_value=0.0,
    )
    
    observations = interp(observation_points)
    
    return observations


def observations_to_grid(
    observations: np.ndarray,
    observation_points: np.ndarray,
    grid_shape: Tuple[int, int],
    method: str = 'cubic',
) -> np.ndarray:
    """
    Interpolate observations onto regular grid.
    
    Args:
        observations: Observation values, shape (n_points,)
        observation_points: Observation locations, shape (n_points, 2)
        grid_shape: Output grid shape (ny, nx)
        method: Interpolation method
    
    Returns:
        Gridded data, shape (ny, nx)
    """
    ny, nx = grid_shape
    
    # Create output grid
    y_grid = np.linspace(0, ny-1, ny)
    x_grid = np.linspace(0, nx-1, nx)
    X, Y = np.meshgrid(x_grid, y_grid)
    
    # Interpolate
    grid = interpolate.griddata(
        observation_points,
        observations,
        (Y, X),
        method=method,
        fill_value=0.0,
    )
    
    return grid


def apply_gaussian_filter(
    data: np.ndarray,
    sigma: float = 1.0,
) -> np.ndarray:
    """
    Apply Gaussian smoothing filter.
    
    Args:
        data: Input data
        sigma: Standard deviation for Gaussian kernel
    
    Returns:
        Smoothed data
    """
    return ndimage.gaussian_filter(data, sigma=sigma)


def remove_trend(
    data: np.ndarray,
    order: int = 1,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Remove polynomial trend from data.
    
    Args:
        data: Input data, shape (ny, nx)
        order: Polynomial order (1=linear, 2=quadratic)
    
    Returns:
        Tuple of (detrended_data, trend)
    """
    ny, nx = data.shape
    
    # Create coordinate grids
    y = np.arange(ny)
    x = np.arange(nx)
    Y, X = np.meshgrid(y, x, indexing='ij')
    
    # Flatten
    X_flat = X.flatten()
    Y_flat = Y.flatten()
    data_flat = data.flatten()
    
    # Build design matrix
    if order == 1:
        A = np.c_[np.ones_like(X_flat), X_flat, Y_flat]
    elif order == 2:
        A = np.c_[np.ones_like(X_flat), X_flat, Y_flat, X_flat**2, Y_flat**2, X_flat*Y_flat]
    else:
        raise ValueError(f"Order {order} not supported")
    
    # Least squares fit
    coeffs, _, _, _ = np.linalg.lstsq(A, data_flat, rcond=None)
    
    # Compute trend
    trend_flat = A @ coeffs
    trend = trend_flat.reshape(ny, nx)
    
    # Remove trend
    detrended = data - trend
    
    return detrended, trend


def upward_continuation(
    gravity: np.ndarray,
    delta_h: float,
    cell_size: float = 1.0,
) -> np.ndarray:
    """
    Upward continuation of gravity field.
    
    Simulates gravity at higher altitude.
    
    Args:
        gravity: Gravity anomaly, shape (ny, nx)
        delta_h: Height change (positive = upward)
        cell_size: Grid cell size in same units as delta_h
    
    Returns:
        Continued gravity field
    """
    # FFT-based upward continuation
    ny, nx = gravity.shape
    
    # Wavenumber grids
    ky = 2 * np.pi * np.fft.fftfreq(ny, d=cell_size)
    kx = 2 * np.pi * np.fft.fftfreq(nx, d=cell_size)
    KX, KY = np.meshgrid(kx, ky)
    K = np.sqrt(KX**2 + KY**2)
    
    # Fourier transform
    gravity_fft = np.fft.fft2(gravity)
    
    # Apply continuation filter
    continued_fft = gravity_fft * np.exp(-K * delta_h)
    
    # Inverse transform
    continued = np.real(np.fft.ifft2(continued_fft))
    
    return continued


def downward_continuation(
    gravity: np.ndarray,
    delta_h: float,
    cell_size: float = 1.0,
    regularization: float = 0.01,
) -> np.ndarray:
    """
    Downward continuation of gravity field (unstable - use with caution).
    
    Args:
        gravity: Gravity anomaly
        delta_h: Height change (positive = downward)
        cell_size: Grid cell size
        regularization: Tikhonov regularization parameter
    
    Returns:
        Continued gravity field
    """
    # FFT-based with regularization
    ny, nx = gravity.shape
    
    ky = 2 * np.pi * np.fft.fftfreq(ny, d=cell_size)
    kx = 2 * np.pi * np.fft.fftfreq(nx, d=cell_size)
    KX, KY = np.meshgrid(kx, ky)
    K = np.sqrt(KX**2 + KY**2)
    
    gravity_fft = np.fft.fft2(gravity)
    
    # Regularized continuation
    filter_term = np.exp(K * delta_h) / (1 + regularization * K**2)
    continued_fft = gravity_fft * filter_term
    
    continued = np.real(np.fft.ifft2(continued_fft))
    
    return continued


def add_noise(
    data: np.ndarray,
    noise_level: float,
    noise_type: str = 'gaussian',
) -> np.ndarray:
    """
    Add synthetic noise to data.
    
    Args:
        data: Clean data
        noise_level: Noise standard deviation
        noise_type: Type of noise ('gaussian', 'uniform')
    
    Returns:
        Noisy data
    """
    if noise_type == 'gaussian':
        noise = np.random.randn(*data.shape) * noise_level
    elif noise_type == 'uniform':
        noise = np.random.uniform(-noise_level, noise_level, data.shape)
    else:
        raise ValueError(f"Unknown noise type: {noise_type}")
    
    return data + noise


def compute_data_statistics(
    data_list: list,
) -> Dict:
    """
    Compute statistics over multiple data samples.
    
    Args:
        data_list: List of data arrays
    
    Returns:
        Dictionary with statistics
    """
    all_data = np.concatenate([d.flatten() for d in data_list])
    
    stats = {
        'mean': np.mean(all_data),
        'std': np.std(all_data),
        'min': np.min(all_data),
        'max': np.max(all_data),
        'median': np.median(all_data),
        'q25': np.percentile(all_data, 25),
        'q75': np.percentile(all_data, 75),
    }
    
    return stats
