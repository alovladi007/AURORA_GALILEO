"""
Evaluation Metrics
==================

Metrics for assessing geophysical inversion quality.
"""

import numpy as np
from typing import Dict, Tuple

try:
    import torch
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False


def rmse(predictions: np.ndarray, targets: np.ndarray) -> float:
    """
    Root Mean Squared Error.
    
    Args:
        predictions: Model predictions
        targets: True values
    
    Returns:
        RMSE
    """
    return np.sqrt(np.mean((predictions - targets) ** 2))


def nrmse(predictions: np.ndarray, targets: np.ndarray) -> float:
    """
    Normalized RMSE (by target range).
    
    Args:
        predictions: Model predictions
        targets: True values
    
    Returns:
        Normalized RMSE (0-1)
    """
    rmse_val = rmse(predictions, targets)
    target_range = np.ptp(targets)
    return rmse_val / (target_range + 1e-8)


def r2_score(predictions: np.ndarray, targets: np.ndarray) -> float:
    """
    R² coefficient of determination.
    
    Args:
        predictions: Model predictions
        targets: True values
    
    Returns:
        R² score (-inf to 1, 1 is perfect)
    """
    ss_res = np.sum((targets - predictions) ** 2)
    ss_tot = np.sum((targets - np.mean(targets)) ** 2)
    return 1 - (ss_res / (ss_tot + 1e-8))


def correlation(predictions: np.ndarray, targets: np.ndarray) -> float:
    """
    Pearson correlation coefficient.
    
    Args:
        predictions: Model predictions
        targets: True values
    
    Returns:
        Correlation coefficient (-1 to 1)
    """
    return np.corrcoef(predictions.flatten(), targets.flatten())[0, 1]


def structural_similarity(
    model1: np.ndarray,
    model2: np.ndarray,
) -> float:
    """
    Structural similarity between two models (e.g., density and susceptibility).
    
    Measures correlation of gradients.
    
    Args:
        model1: First model
        model2: Second model
    
    Returns:
        Structural similarity score (0-1)
    """
    # Compute gradients
    dx1 = np.gradient(model1, axis=-1)
    dy1 = np.gradient(model1, axis=-2)
    
    dx2 = np.gradient(model2, axis=-1)
    dy2 = np.gradient(model2, axis=-2)
    
    # Correlation of gradients
    corr_dx = correlation(dx1, dx2)
    corr_dy = correlation(dy1, dy2)
    
    return (corr_dx + corr_dy) / 2


def data_misfit(
    predictions: np.ndarray,
    observations: np.ndarray,
    weights: np.ndarray = None,
) -> float:
    """
    Weighted data misfit (chi-squared).
    
    Args:
        predictions: Model predictions
        observations: True observations
        weights: Observation weights (inverse variances)
    
    Returns:
        Data misfit
    """
    residuals = predictions - observations
    
    if weights is None:
        return np.sum(residuals ** 2)
    else:
        return np.sum(weights * residuals ** 2)


def anomaly_recovery(
    predictions: np.ndarray,
    targets: np.ndarray,
    threshold: float = 0.5,
) -> Dict[str, float]:
    """
    Anomaly detection metrics.
    
    Args:
        predictions: Predicted model
        targets: True model
        threshold: Threshold for defining anomaly (fraction of max)
    
    Returns:
        Dictionary with precision, recall, F1 score
    """
    # Define anomalies
    pred_anomaly = np.abs(predictions) > threshold * np.abs(predictions).max()
    true_anomaly = np.abs(targets) > threshold * np.abs(targets).max()
    
    # True/False positives/negatives
    tp = np.sum(pred_anomaly & true_anomaly)
    fp = np.sum(pred_anomaly & ~true_anomaly)
    fn = np.sum(~pred_anomaly & true_anomaly)
    
    # Metrics
    precision = tp / (tp + fp + 1e-8)
    recall = tp / (tp + fn + 1e-8)
    f1 = 2 * precision * recall / (precision + recall + 1e-8)
    
    return {
        'precision': precision,
        'recall': recall,
        'f1': f1,
    }


def convergence_metrics(
    loss_history: list,
    window: int = 10,
) -> Dict[str, float]:
    """
    Training convergence metrics.
    
    Args:
        loss_history: List of loss values over epochs
        window: Window size for smoothing
    
    Returns:
        Dictionary with convergence metrics
    """
    losses = np.array(loss_history)
    
    # Final loss
    final_loss = losses[-1]
    
    # Improvement over initial
    improvement = (losses[0] - final_loss) / losses[0]
    
    # Smoothed convergence rate (last window)
    if len(losses) > window:
        recent_losses = losses[-window:]
        slope = (recent_losses[-1] - recent_losses[0]) / window
        relative_slope = slope / (recent_losses[0] + 1e-8)
    else:
        relative_slope = 0
    
    # Oscillation (variance in recent losses)
    if len(losses) > window:
        oscillation = np.std(losses[-window:]) / (np.mean(losses[-window:]) + 1e-8)
    else:
        oscillation = 0
    
    return {
        'final_loss': final_loss,
        'improvement': improvement,
        'convergence_rate': -relative_slope,  # Negative slope means decreasing
        'oscillation': oscillation,
    }


if HAS_TORCH:
    def torch_rmse(predictions: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        """Torch version of RMSE."""
        return torch.sqrt(torch.mean((predictions - targets) ** 2))
    
    
    def torch_r2_score(predictions: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        """Torch version of R² score."""
        ss_res = torch.sum((targets - predictions) ** 2)
        ss_tot = torch.sum((targets - torch.mean(targets)) ** 2)
        return 1 - (ss_res / (ss_tot + 1e-8))
    
    
    def torch_correlation(predictions: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        """Torch version of correlation."""
        pred_flat = predictions.flatten()
        target_flat = targets.flatten()
        
        pred_centered = pred_flat - torch.mean(pred_flat)
        target_centered = target_flat - torch.mean(target_flat)
        
        corr = torch.sum(pred_centered * target_centered) / (
            torch.sqrt(torch.sum(pred_centered ** 2)) *
            torch.sqrt(torch.sum(target_centered ** 2)) + 1e-8
        )
        
        return corr


else:
    def torch_rmse(*args, **kwargs):
        raise ImportError("PyTorch required")
    
    def torch_r2_score(*args, **kwargs):
        raise ImportError("PyTorch required")
    
    def torch_correlation(*args, **kwargs):
        raise ImportError("PyTorch required")


def compute_all_metrics(
    predictions: np.ndarray,
    targets: np.ndarray,
) -> Dict[str, float]:
    """
    Compute comprehensive set of metrics.
    
    Args:
        predictions: Model predictions
        targets: True values
    
    Returns:
        Dictionary with all metrics
    """
    return {
        'rmse': rmse(predictions, targets),
        'nrmse': nrmse(predictions, targets),
        'r2': r2_score(predictions, targets),
        'correlation': correlation(predictions, targets),
        **anomaly_recovery(predictions, targets),
    }
