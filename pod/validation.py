"""
Orbit Validation and Residual Analysis
=======================================

Orbit overlap tests, residual analysis, and outlier rejection.
"""

import numpy as np
from typing import List, Tuple, Optional
from dataclasses import dataclass
import warnings

from pod.estimators import OrbitEstimate


@dataclass
class OrbitOverlapResult:
    """
    Result of orbit overlap comparison.

    Attributes:
        overlap_rms: RMS of position differences (m)
        overlap_mean: Mean position difference (m)
        overlap_max: Maximum position difference (m)
        overlapping_epochs: Number of overlapping epochs
        passed: Whether overlap meets threshold
    """
    overlap_rms: float
    overlap_mean: float
    overlap_max: float
    overlapping_epochs: int
    passed: bool


def compute_orbit_overlap(
    orbit1: List[OrbitEstimate],
    orbit2: List[OrbitEstimate],
    threshold: float = 0.05,
    time_tolerance: float = 0.01,
) -> OrbitOverlapResult:
    """
    Compute orbit overlap statistics between two orbit solutions.

    Orbit overlap is a key validation metric: two independent solutions
    over the same period should agree to within ~cm for precise orbits.

    Args:
        orbit1: First orbit solution (list of estimates)
        orbit2: Second orbit solution (list of estimates)
        threshold: Pass/fail threshold for RMS (m)
        time_tolerance: Time matching tolerance (s)

    Returns:
        OrbitOverlapResult with statistics
    """
    # Find overlapping epochs
    differences = []
    overlapping_epochs = 0

    for est1 in orbit1:
        # Find matching estimate in orbit2
        for est2 in orbit2:
            if abs(est1.time - est2.time) < time_tolerance:
                # Compute position difference
                diff = np.linalg.norm(est1.position - est2.position)
                differences.append(diff)
                overlapping_epochs += 1
                break

    if overlapping_epochs == 0:
        warnings.warn("No overlapping epochs found")
        return OrbitOverlapResult(
            overlap_rms=np.inf,
            overlap_mean=np.inf,
            overlap_max=np.inf,
            overlapping_epochs=0,
            passed=False,
        )

    differences = np.array(differences)

    overlap_rms = np.sqrt(np.mean(differences**2))
    overlap_mean = np.mean(differences)
    overlap_max = np.max(differences)
    passed = overlap_rms < threshold

    return OrbitOverlapResult(
        overlap_rms=overlap_rms,
        overlap_mean=overlap_mean,
        overlap_max=overlap_max,
        overlapping_epochs=overlapping_epochs,
        passed=passed,
    )


def analyze_residuals(
    residuals: np.ndarray,
    expected_sigma: float = 1.0,
) -> dict:
    """
    Analyze measurement residuals.

    Args:
        residuals: Measurement residuals (m), shape (n,)
        expected_sigma: Expected residual std (m)

    Returns:
        Dictionary with residual statistics
    """
    residuals = np.asarray(residuals)

    # Remove NaN values
    residuals = residuals[~np.isnan(residuals)]

    if len(residuals) == 0:
        return {
            'mean': np.nan,
            'std': np.nan,
            'rms': np.nan,
            'max_abs': np.nan,
            'chi_squared': np.nan,
            'whitened': False,
        }

    mean = np.mean(residuals)
    std = np.std(residuals)
    rms = np.sqrt(np.mean(residuals**2))
    max_abs = np.max(np.abs(residuals))

    # Chi-squared test: residuals should be ~ N(0, σ^2)
    chi_squared = np.sum((residuals / expected_sigma)**2)
    dof = len(residuals)
    chi_squared_per_dof = chi_squared / dof

    # Whiteness test: chi^2/dof should be ~1
    whitened = (0.8 < chi_squared_per_dof < 1.2)

    return {
        'mean': mean,
        'std': std,
        'rms': rms,
        'max_abs': max_abs,
        'chi_squared': chi_squared,
        'chi_squared_per_dof': chi_squared_per_dof,
        'whitened': whitened,
        'num_residuals': len(residuals),
    }


def outlier_rejection(
    residuals: np.ndarray,
    threshold: float = 3.0,
    method: str = 'sigma',
) -> np.ndarray:
    """
    Detect outliers in residuals.

    Args:
        residuals: Measurement residuals (m), shape (n,)
        threshold: Outlier threshold
        method: 'sigma' (n-sigma test) or 'mad' (median absolute deviation)

    Returns:
        Boolean mask: True = inlier, False = outlier
    """
    residuals = np.asarray(residuals)

    if method == 'sigma':
        # n-sigma test
        std = np.std(residuals)
        outliers = np.abs(residuals) > threshold * std

    elif method == 'mad':
        # Median Absolute Deviation (more robust)
        median = np.median(residuals)
        mad = np.median(np.abs(residuals - median))

        # Scale MAD to approximate std (for Gaussian)
        mad_std = 1.4826 * mad

        outliers = np.abs(residuals - median) > threshold * mad_std

    else:
        raise ValueError(f"Unknown outlier detection method: {method}")

    # Inlier mask
    inliers = ~outliers

    return inliers


def compute_residual_histogram(
    residuals: np.ndarray,
    bins: int = 50,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Compute histogram of residuals.

    Args:
        residuals: Measurement residuals (m)
        bins: Number of histogram bins

    Returns:
        (counts, bin_edges)
    """
    residuals = residuals[~np.isnan(residuals)]

    counts, bin_edges = np.histogram(residuals, bins=bins)

    return counts, bin_edges


def validate_orbit_quality(
    estimates: List[OrbitEstimate],
    residuals: Optional[np.ndarray] = None,
) -> dict:
    """
    Comprehensive orbit quality validation.

    Args:
        estimates: List of orbit estimates
        residuals: Measurement residuals (optional)

    Returns:
        Dictionary with quality metrics
    """
    metrics = {}

    # Position uncertainty
    position_uncertainties = []
    velocity_uncertainties = []

    for est in estimates:
        # Position 1-sigma
        pos_cov = est.covariance[:3, :3]
        pos_sigma = np.sqrt(np.trace(pos_cov))
        position_uncertainties.append(pos_sigma)

        # Velocity 1-sigma
        vel_cov = est.covariance[3:6, 3:6]
        vel_sigma = np.sqrt(np.trace(vel_cov))
        velocity_uncertainties.append(vel_sigma)

    metrics['mean_position_uncertainty'] = np.mean(position_uncertainties)
    metrics['max_position_uncertainty'] = np.max(position_uncertainties)
    metrics['mean_velocity_uncertainty'] = np.mean(velocity_uncertainties)
    metrics['max_velocity_uncertainty'] = np.max(velocity_uncertainties)

    # Residual analysis (if provided)
    if residuals is not None:
        residual_stats = analyze_residuals(residuals)
        metrics.update(residual_stats)

    # Convergence
    converged_count = sum(1 for est in estimates if est.converged)
    metrics['convergence_rate'] = converged_count / len(estimates)

    return metrics
