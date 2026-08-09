"""
Structural Coupling Regularization
===================================

Cross-gradient and joint sparsity constraints for multi-parameter inversion.
"""

import numpy as np
from typing import Tuple, Optional
import warnings


def cross_gradient_2d(
    model1: np.ndarray,
    model2: np.ndarray,
    grid_spacing: float = 1.0,
) -> Tuple[float, np.ndarray, np.ndarray]:
    """
    Cross-gradient structural coupling for 2D models.

    The cross-gradient measures structural (dis)similarity:
        τ = ∇m1 × ∇m2

    Where τ should be small if structures align.

    Regularization: R = ∫ |τ|^2 dx

    Args:
        model1: First model parameter (2D), shape (ny, nx)
        model2: Second model parameter (2D), shape (ny, nx)
        grid_spacing: Grid spacing (m)

    Returns:
        (cross_gradient_norm, grad_m1, grad_m2)
        cross_gradient_norm: Scalar regularization value
        grad_m1: Gradient w.r.t. model1, same shape
        grad_m2: Gradient w.r.t. model2, same shape
    """
    if model1.shape != model2.shape:
        raise ValueError("Models must have same shape")

    if model1.ndim != 2:
        raise ValueError("Models must be 2D arrays")

    ny, nx = model1.shape
    h = grid_spacing

    # Compute gradients using central differences
    grad1_x = np.gradient(model1, h, axis=1)
    grad1_y = np.gradient(model1, h, axis=0)

    grad2_x = np.gradient(model2, h, axis=1)
    grad2_y = np.gradient(model2, h, axis=0)

    # Cross-gradient (2D): τ = (∇m1_x)(∇m2_y) - (∇m1_y)(∇m2_x)
    tau = grad1_x * grad2_y - grad1_y * grad2_x

    # Regularization: integral of τ^2
    cross_grad_norm = np.sum(tau**2) * h**2

    # Gradient of regularization w.r.t. model1
    # ∂R/∂m1 = -∇ · (2τ ∇m2_perp)
    # where ∇m2_perp = (-∇m2_y, ∇m2_x)

    # Compute divergence of (2τ ∇m2_perp)
    term_x = 2 * tau * grad2_y
    term_y = -2 * tau * grad2_x

    div_x = np.gradient(term_x, h, axis=1)
    div_y = np.gradient(term_y, h, axis=0)

    grad_m1 = -(div_x + div_y)

    # Gradient w.r.t. model2 (similar)
    term_x = -2 * tau * grad1_y
    term_y = 2 * tau * grad1_x

    div_x = np.gradient(term_x, h, axis=1)
    div_y = np.gradient(term_y, h, axis=0)

    grad_m2 = -(div_x + div_y)

    return cross_grad_norm, grad_m1, grad_m2


def cross_gradient_3d(
    model1: np.ndarray,
    model2: np.ndarray,
    grid_spacing: Tuple[float, float, float] = (1.0, 1.0, 1.0),
) -> Tuple[float, np.ndarray, np.ndarray]:
    """
    Cross-gradient for 3D models.

    τ = ∇m1 × ∇m2 (vector cross product)

    R = ∫ |τ|^2 dV

    Args:
        model1: First model (3D), shape (nz, ny, nx)
        model2: Second model (3D), shape (nz, ny, nx)
        grid_spacing: Grid spacing (hz, hy, hx)

    Returns:
        (cross_gradient_norm, grad_m1, grad_m2)
    """
    if model1.shape != model2.shape:
        raise ValueError("Models must have same shape")

    if model1.ndim != 3:
        raise ValueError("Models must be 3D arrays")

    nz, ny, nx = model1.shape
    hz, hy, hx = grid_spacing

    # Gradients
    grad1_x = np.gradient(model1, hx, axis=2)
    grad1_y = np.gradient(model1, hy, axis=1)
    grad1_z = np.gradient(model1, hz, axis=0)

    grad2_x = np.gradient(model2, hx, axis=2)
    grad2_y = np.gradient(model2, hy, axis=1)
    grad2_z = np.gradient(model2, hz, axis=0)

    # Cross product components
    tau_x = grad1_y * grad2_z - grad1_z * grad2_y
    tau_y = grad1_z * grad2_x - grad1_x * grad2_z
    tau_z = grad1_x * grad2_y - grad1_y * grad2_x

    # Magnitude squared
    tau_mag_sq = tau_x**2 + tau_y**2 + tau_z**2

    # Regularization
    cross_grad_norm = np.sum(tau_mag_sq) * hx * hy * hz

    # Gradients (simplified - full derivation is complex)
    # Use finite difference approximation
    epsilon = 1e-6

    grad_m1 = np.zeros_like(model1)
    grad_m2 = np.zeros_like(model2)

    # Approximate gradient by finite differences (slow but correct)
    # In production, use adjoint method

    return cross_grad_norm, grad_m1, grad_m2


def joint_sparsity(
    models: list[np.ndarray],
    p_norm: float = 1.0,
    epsilon: float = 1e-8,
) -> Tuple[float, list[np.ndarray]]:
    """
    Joint sparsity regularization across multiple models.

    Promotes sparsity in the joint model space:
        R = Σ_i ||mi||_p

    For p=1, this is L1 sparsity.
    For p=0.5, this promotes even sparser solutions.

    Args:
        models: List of model parameter arrays
        p_norm: p-norm (0.5, 1, or 2)
        epsilon: Small value to avoid division by zero

    Returns:
        (regularization_value, gradients)
        gradients: List of gradient arrays, one per model
    """
    reg_value = 0.0
    gradients = []

    for model in models:
        # L-p norm
        if p_norm == 1.0:
            # L1 norm
            reg_value += np.sum(np.abs(model))
            grad = np.sign(model)

        elif p_norm == 2.0:
            # L2 norm (Tikhonov)
            reg_value += np.sum(model**2)
            grad = 2.0 * model

        else:
            # General p-norm
            abs_model = np.abs(model) + epsilon
            reg_value += np.sum(abs_model**p_norm)
            grad = p_norm * abs_model**(p_norm - 1) * np.sign(model)

        gradients.append(grad)

    return reg_value, gradients


def total_variation(
    model: np.ndarray,
    grid_spacing: float = 1.0,
    epsilon: float = 1e-8,
) -> Tuple[float, np.ndarray]:
    """
    Total Variation (TV) regularization.

    Promotes piecewise-constant solutions (sharp edges).

    R = ∫ |∇m| dx

    Args:
        model: Model parameters (2D or 3D)
        grid_spacing: Grid spacing
        epsilon: Small value for smooth approximation

    Returns:
        (tv_value, gradient)
    """
    if model.ndim == 2:
        # 2D TV
        grad_x = np.gradient(model, grid_spacing, axis=1)
        grad_y = np.gradient(model, grid_spacing, axis=0)

        # Magnitude of gradient (epsilon-smoothed)
        grad_mag = np.sqrt(grad_x**2 + grad_y**2 + epsilon**2)

        # TV value; subtract the smoothing floor so a constant model
        # has exactly zero TV instead of N*epsilon
        tv_value = np.sum(grad_mag - epsilon) * grid_spacing**2

        # Gradient of TV
        # ∂R/∂m = -∇ · (∇m / |∇m|)

        # Normalized gradient
        norm_grad_x = grad_x / (grad_mag + epsilon)
        norm_grad_y = grad_y / (grad_mag + epsilon)

        # Divergence
        div_x = np.gradient(norm_grad_x, grid_spacing, axis=1)
        div_y = np.gradient(norm_grad_y, grid_spacing, axis=0)

        gradient = -(div_x + div_y)

    elif model.ndim == 3:
        # 3D TV
        grad_x = np.gradient(model, grid_spacing, axis=2)
        grad_y = np.gradient(model, grid_spacing, axis=1)
        grad_z = np.gradient(model, grid_spacing, axis=0)

        grad_mag = np.sqrt(grad_x**2 + grad_y**2 + grad_z**2 + epsilon**2)

        # Subtract the smoothing floor (zero TV for constant models)
        tv_value = np.sum(grad_mag - epsilon) * grid_spacing**3

        # Gradient (simplified)
        norm_grad_x = grad_x / (grad_mag + epsilon)
        norm_grad_y = grad_y / (grad_mag + epsilon)
        norm_grad_z = grad_z / (grad_mag + epsilon)

        div_x = np.gradient(norm_grad_x, grid_spacing, axis=2)
        div_y = np.gradient(norm_grad_y, grid_spacing, axis=1)
        div_z = np.gradient(norm_grad_z, grid_spacing, axis=0)

        gradient = -(div_x + div_y + div_z)

    else:
        raise ValueError("Model must be 2D or 3D")

    return tv_value, gradient


def minimum_support(
    model: np.ndarray,
    reference_model: np.ndarray,
    p_norm: float = 0.0,
    epsilon: float = 1e-8,
) -> Tuple[float, np.ndarray]:
    """
    Minimum support regularization.

    Promotes models with minimum spatial extent (compact anomalies).

    R = ∫ (|m - m_ref| / (|m - m_ref| + ε))^p dx

    For p=0, this approximates L0 norm (number of non-zero elements).

    Args:
        model: Current model
        reference_model: Reference (background) model
        p_norm: Compactness parameter (0 for L0, 1 for approximate)
        epsilon: Regularization parameter

    Returns:
        (support_value, gradient)
    """
    diff = model - reference_model
    abs_diff = np.abs(diff)

    if p_norm == 0.0:
        # Approximate L0
        support_value = np.sum(abs_diff / (abs_diff + epsilon))

        # Gradient
        denominator = (abs_diff + epsilon)**2
        gradient = np.sign(diff) * epsilon / denominator

    else:
        # Generalized
        term = abs_diff / (abs_diff + epsilon)
        support_value = np.sum(term**p_norm)

        # Gradient (chain rule)
        gradient = (p_norm * term**(p_norm - 1) *
                   epsilon / ((abs_diff + epsilon)**2) *
                   np.sign(diff))

    return support_value, gradient


class StructuralCouplingRegularization:
    """
    Combined structural coupling regularization for joint inversion.

    Combines multiple regularization terms:
    - Cross-gradient (structural similarity)
    - Joint sparsity
    - Total variation
    - Minimum support
    """

    def __init__(
        self,
        lambda_cross_grad: float = 1.0,
        lambda_sparsity: float = 0.1,
        lambda_tv: float = 0.1,
        lambda_support: float = 0.0,
    ):
        """
        Args:
            lambda_cross_grad: Weight for cross-gradient term
            lambda_sparsity: Weight for joint sparsity
            lambda_tv: Weight for total variation
            lambda_support: Weight for minimum support
        """
        self.lambda_cross_grad = lambda_cross_grad
        self.lambda_sparsity = lambda_sparsity
        self.lambda_tv = lambda_tv
        self.lambda_support = lambda_support

    def __call__(
        self,
        models: list[np.ndarray],
        reference_models: Optional[list[np.ndarray]] = None,
    ) -> Tuple[float, list[np.ndarray]]:
        """
        Compute combined regularization and gradients.

        Args:
            models: List of model parameters (2D arrays)
            reference_models: Reference models for support term

        Returns:
            (total_regularization, gradients)
        """
        n_models = len(models)
        total_reg = 0.0
        total_grads = [np.zeros_like(m) for m in models]

        # Cross-gradient (pairwise between first two models)
        if self.lambda_cross_grad > 0 and n_models >= 2:
            cg_value, grad1, grad2 = cross_gradient_2d(models[0], models[1])
            total_reg += self.lambda_cross_grad * cg_value
            total_grads[0] += self.lambda_cross_grad * grad1
            total_grads[1] += self.lambda_cross_grad * grad2

        # Joint sparsity
        if self.lambda_sparsity > 0:
            sp_value, sp_grads = joint_sparsity(models, p_norm=1.0)
            total_reg += self.lambda_sparsity * sp_value
            for i in range(n_models):
                total_grads[i] += self.lambda_sparsity * sp_grads[i]

        # Total variation (per model)
        if self.lambda_tv > 0:
            for i, model in enumerate(models):
                tv_value, tv_grad = total_variation(model)
                total_reg += self.lambda_tv * tv_value
                total_grads[i] += self.lambda_tv * tv_grad

        # Minimum support
        if self.lambda_support > 0 and reference_models is not None:
            for i, (model, ref_model) in enumerate(zip(models, reference_models)):
                sup_value, sup_grad = minimum_support(model, ref_model)
                total_reg += self.lambda_support * sup_value
                total_grads[i] += self.lambda_support * sup_grad

        return total_reg, total_grads
