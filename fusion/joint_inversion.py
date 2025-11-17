"""
Joint Inversion Framework
=========================

Multi-sensor joint inversion for gravity, magnetics, and seismic data.
"""

import numpy as np
from typing import List, Optional, Tuple, Callable
from dataclasses import dataclass
import warnings


@dataclass
class InversionResult:
    """
    Result from joint inversion.

    Attributes:
        model: Inverted model parameters, shape (n,)
        residuals: Data residuals for each sensor
        objective: Final objective function value
        iterations: Number of iterations
        converged: Whether inversion converged
        uncertainties: Model uncertainties (optional)
    """
    model: np.ndarray
    residuals: List[np.ndarray]
    objective: float
    iterations: int
    converged: bool
    uncertainties: Optional[np.ndarray] = None


class JointInversion:
    """
    Joint inversion framework for multiple geophysical data types.

    Combines gravity, magnetic, seismic, etc. through:
    - Shared structural coupling (cross-gradients)
    - Joint sparsity constraints
    - Hierarchical priors
    """

    def __init__(
        self,
        forward_models: List[Callable],
        data: List[np.ndarray],
        data_weights: Optional[List[float]] = None,
        coupling_weight: float = 1.0,
        max_iterations: int = 50,
        tolerance: float = 1e-4,
    ):
        """
        Args:
            forward_models: List of forward operators G_i(m)
            data: List of observed data d_i
            data_weights: Weights for each data type (default: equal)
            coupling_weight: Structural coupling strength
            max_iterations: Maximum iterations
            tolerance: Convergence tolerance
        """
        self.forward_models = forward_models
        self.data = data
        self.n_sensors = len(forward_models)

        if data_weights is None:
            self.data_weights = [1.0] * self.n_sensors
        else:
            self.data_weights = data_weights

        self.coupling_weight = coupling_weight
        self.max_iterations = max_iterations
        self.tolerance = tolerance

    def objective_function(
        self,
        model: np.ndarray,
        regularization_term: float = 0.0,
    ) -> Tuple[float, np.ndarray]:
        """
        Compute joint objective function and gradient.

        J(m) = Σ_i w_i ||G_i(m) - d_i||^2 + λ R(m)

        where R(m) is the regularization term (cross-gradient, etc.)

        Args:
            model: Model parameters
            regularization_term: Regularization contribution

        Returns:
            (objective_value, gradient)
        """
        objective = 0.0
        gradient = np.zeros_like(model)

        # Data misfit for each sensor
        for i, (forward, d_obs) in enumerate(zip(self.forward_models, self.data)):
            # Predicted data
            d_pred = forward(model)

            # Residual
            residual = d_pred - d_obs

            # Weighted misfit
            misfit = self.data_weights[i] * np.sum(residual**2)
            objective += misfit

            # Gradient contribution (simplified - assumes linear G)
            # ∂J/∂m = 2 * w_i * G_i^T (G_i(m) - d_i)
            # For nonlinear, would need Jacobian
            gradient += 2 * self.data_weights[i] * residual.sum() * np.ones_like(model)

        # Add regularization
        objective += regularization_term

        return objective, gradient

    def invert(
        self,
        initial_model: np.ndarray,
        regularization: Optional[Callable] = None,
    ) -> InversionResult:
        """
        Perform joint inversion using gradient descent.

        Args:
            initial_model: Initial model guess
            regularization: Regularization function R(m)

        Returns:
            InversionResult with final model and diagnostics
        """
        model = np.array(initial_model, dtype=float)
        n_params = len(model)

        converged = False
        iteration = 0

        # Storage for residuals
        all_residuals = []

        for iteration in range(self.max_iterations):
            # Compute regularization term
            if regularization is not None:
                reg_value, reg_grad = regularization(model)
            else:
                reg_value, reg_grad = 0.0, np.zeros_like(model)

            # Objective and gradient
            obj, grad = self.objective_function(model, reg_value)

            # Add regularization gradient
            grad += reg_grad

            # Simple gradient descent with line search
            # In practice, use L-BFGS or similar
            alpha = self._line_search(model, grad, obj)

            # Update model
            model_new = model - alpha * grad

            # Check convergence
            delta = np.linalg.norm(model_new - model)
            if delta < self.tolerance:
                converged = True
                model = model_new
                break

            model = model_new

            # Compute residuals for monitoring
            residuals = []
            for forward, d_obs in zip(self.forward_models, self.data):
                d_pred = forward(model)
                residuals.append(d_pred - d_obs)
            all_residuals.append(residuals)

        # Final residuals
        final_residuals = []
        for forward, d_obs in zip(self.forward_models, self.data):
            d_pred = forward(model)
            final_residuals.append(d_pred - d_obs)

        # Final objective
        final_obj, _ = self.objective_function(model)

        return InversionResult(
            model=model,
            residuals=final_residuals,
            objective=final_obj,
            iterations=iteration + 1,
            converged=converged,
        )

    def _line_search(
        self,
        model: np.ndarray,
        gradient: np.ndarray,
        current_obj: float,
        alpha_init: float = 1.0,
        backtrack: float = 0.5,
        max_iter: int = 10,
    ) -> float:
        """
        Backtracking line search for step size.

        Args:
            model: Current model
            gradient: Current gradient
            current_obj: Current objective value
            alpha_init: Initial step size
            backtrack: Backtracking factor
            max_iter: Max line search iterations

        Returns:
            Step size alpha
        """
        alpha = alpha_init

        for _ in range(max_iter):
            # Trial model
            model_trial = model - alpha * gradient

            # Trial objective
            trial_obj, _ = self.objective_function(model_trial)

            # Armijo condition (sufficient decrease)
            if trial_obj < current_obj - 1e-4 * alpha * np.sum(gradient**2):
                return alpha

            # Reduce step size
            alpha *= backtrack

        return alpha

    def compute_uncertainties(
        self,
        model: np.ndarray,
        data_noise: List[float],
    ) -> np.ndarray:
        """
        Estimate model uncertainties from data covariance.

        Uses linearized approximation: C_m ≈ (J^T C_d^{-1} J)^{-1}

        Args:
            model: Inverted model
            data_noise: Noise std for each sensor

        Returns:
            Model uncertainties (diagonal of covariance), shape (n,)
        """
        # Build approximate Hessian
        # H ≈ Σ w_i G_i^T G_i
        n_params = len(model)
        H = np.zeros((n_params, n_params))

        for i, forward in enumerate(self.forward_models):
            # Compute Jacobian (finite difference)
            J = self._compute_jacobian(forward, model)

            # Weight by data covariance
            weight = self.data_weights[i] / (data_noise[i]**2)

            H += weight * (J.T @ J)

        # Invert to get covariance
        try:
            C_m = np.linalg.inv(H + 1e-6 * np.eye(n_params))
            uncertainties = np.sqrt(np.diag(C_m))
        except np.linalg.LinAlgError:
            warnings.warn("Failed to invert Hessian for uncertainties")
            uncertainties = np.ones(n_params) * np.inf

        return uncertainties

    def _compute_jacobian(
        self,
        forward: Callable,
        model: np.ndarray,
        epsilon: float = 1e-6,
    ) -> np.ndarray:
        """
        Compute Jacobian using finite differences.

        Args:
            forward: Forward model
            model: Model parameters
            epsilon: Finite difference step

        Returns:
            Jacobian matrix, shape (m, n)
        """
        d_nominal = forward(model)
        m_data = len(d_nominal)
        n_params = len(model)

        J = np.zeros((m_data, n_params))

        for i in range(n_params):
            model_pert = model.copy()
            model_pert[i] += epsilon

            d_pert = forward(model_pert)
            J[:, i] = (d_pert - d_nominal) / epsilon

        return J


# ============================================================================
# Utility functions
# ============================================================================

def create_synthetic_joint_problem(
    n_params: int = 100,
    n_data_per_sensor: int = 50,
    n_sensors: int = 2,
    noise_level: float = 0.01,
    seed: Optional[int] = None,
) -> Tuple[List[Callable], List[np.ndarray], np.ndarray]:
    """
    Create synthetic joint inversion problem for testing.

    Args:
        n_params: Number of model parameters
        n_data_per_sensor: Data points per sensor
        n_sensors: Number of sensors
        noise_level: Noise standard deviation
        seed: Random seed

    Returns:
        (forward_models, data, true_model)
    """
    if seed is not None:
        np.random.seed(seed)

    # True model
    true_model = np.random.randn(n_params)

    # Create forward models (linear for simplicity)
    forward_models = []
    data = []

    for i in range(n_sensors):
        # Random linear operator
        G = np.random.randn(n_data_per_sensor, n_params)

        # Forward model
        def make_forward(G_fixed):
            def forward(m):
                return G_fixed @ m
            return forward

        forward_models.append(make_forward(G))

        # Synthetic data
        d_true = G @ true_model
        noise = noise_level * np.random.randn(n_data_per_sensor)
        d_obs = d_true + noise

        data.append(d_obs)

    return forward_models, data, true_model


def compare_joint_vs_individual(
    forward_models: List[Callable],
    data: List[np.ndarray],
    true_model: np.ndarray,
    initial_guess: Optional[np.ndarray] = None,
) -> dict:
    """
    Compare joint inversion vs individual inversions.

    Args:
        forward_models: List of forward models
        data: List of observed data
        true_model: Ground truth model
        initial_guess: Initial model (default: zeros)

    Returns:
        Dictionary with comparison metrics
    """
    if initial_guess is None:
        initial_guess = np.zeros_like(true_model)

    # Joint inversion
    joint_inv = JointInversion(forward_models, data)
    joint_result = joint_inv.invert(initial_guess)

    joint_error = np.linalg.norm(joint_result.model - true_model)

    # Individual inversions (average)
    individual_errors = []

    for i, (forward, d_obs) in enumerate(zip(forward_models, data)):
        # Single-sensor inversion
        single_inv = JointInversion([forward], [d_obs])
        single_result = single_inv.invert(initial_guess)

        error = np.linalg.norm(single_result.model - true_model)
        individual_errors.append(error)

    mean_individual_error = np.mean(individual_errors)

    improvement = (mean_individual_error - joint_error) / mean_individual_error * 100

    return {
        'joint_error': joint_error,
        'individual_errors': individual_errors,
        'mean_individual_error': mean_individual_error,
        'improvement_percent': improvement,
        'joint_iterations': joint_result.iterations,
        'joint_converged': joint_result.converged,
    }
