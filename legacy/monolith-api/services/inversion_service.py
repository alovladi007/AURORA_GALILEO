"""
Inversion Service for GeoSense Platform API

Provides business logic layer for geophysical inversion operations:
- Linear and nonlinear inversion solvers
- Gravity field modeling and anomaly computation
- Joint inversion with multiple data types
- Uncertainty quantification and resolution analysis

This service bridges API endpoints with core inversion modules.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict

# Import core inversion modules
from inversion.solvers import (
    TikhonovSolver,
    GaussNewtonSolver,
    BayesianMAPSolver,
    UncertaintyAnalysis
)
from inversion.regularizers import (
    SmoothnessRegularizer,
    TotalVariationRegularizer,
    SparsityRegularizer,
    GeologicPriorRegularizer,
    CrossGradientRegularizer
)
from geophysics.gravity_fields import (
    GravityFieldModel,
    load_egm96,
    load_egm2008,
    compute_gravity_anomaly,
    compute_normal_gravity,
    compute_gravity_gradient
)
from geophysics.joint_inversion import (
    JointInversionModel,
    setup_joint_inversion,
    perform_joint_inversion,
    integrate_gravity_seismic,
    add_magnetic_data
)


@dataclass
class InversionResult:
    """Container for inversion results."""
    model: np.ndarray
    predicted_data: np.ndarray
    residual: float
    iterations: int
    converged: bool
    uncertainties: Optional[np.ndarray] = None
    resolution_diagonal: Optional[np.ndarray] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to serializable dictionary."""
        return {
            'model': self.model.tolist(),
            'predicted_data': self.predicted_data.tolist(),
            'residual': float(self.residual),
            'iterations': self.iterations,
            'converged': self.converged,
            'uncertainties': self.uncertainties.tolist() if self.uncertainties is not None else None,
            'resolution_diagonal': self.resolution_diagonal.tolist() if self.resolution_diagonal is not None else None,
        }


@dataclass
class GravityAnomalyResult:
    """Container for gravity anomaly computation results."""
    anomaly: np.ndarray
    normal_gravity: np.ndarray
    components: Dict[str, np.ndarray]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to serializable dictionary."""
        return {
            'anomaly': self.anomaly.tolist(),
            'normal_gravity': self.normal_gravity.tolist(),
            'components': {k: v.tolist() for k, v in self.components.items()}
        }


class InversionService:
    """
    Service for geophysical inversion operations.

    Provides high-level functions that wrap core inversion modules,
    handling data validation, type conversion, and error handling.
    """

    def __init__(self):
        """Initialize inversion service."""
        self._gravity_models = {}  # Cache loaded gravity models

    # =========================================================================
    # Linear Inversion Methods
    # =========================================================================

    def solve_tikhonov(
        self,
        forward_matrix: np.ndarray,
        data: np.ndarray,
        lambda_reg: float,
        regularization_type: str = 'smoothness',
        regularization_order: int = 2
    ) -> InversionResult:
        """
        Solve linear inverse problem using Tikhonov regularization.

        Args:
            forward_matrix: Forward operator matrix G (n_data x n_model)
            data: Observed data vector (n_data,)
            lambda_reg: Regularization parameter
            regularization_type: Type of regularization ('smoothness', 'identity')
            regularization_order: Derivative order for smoothness (1 or 2)

        Returns:
            InversionResult with model estimate and diagnostics
        """
        # Validate inputs
        if forward_matrix.shape[0] != len(data):
            raise ValueError(
                f"Data size ({len(data)}) doesn't match forward matrix rows ({forward_matrix.shape[0]})"
            )

        n_model = forward_matrix.shape[1]

        # Create regularization matrix
        if regularization_type == 'smoothness':
            regularizer = SmoothnessRegularizer(n_model, order=regularization_order)
            L = regularizer.matrix()
        elif regularization_type == 'identity':
            L = np.eye(n_model)
        else:
            raise ValueError(f"Unknown regularization type: {regularization_type}")

        # Create solver and solve
        solver = TikhonovSolver(forward_matrix, L)
        result = solver.solve(data, lambda_reg, compute_resolution=True)

        return InversionResult(
            model=result['model'],
            predicted_data=result['predicted_data'],
            residual=result['residual'],
            iterations=1,  # Linear solver is direct
            converged=True,
            resolution_diagonal=result['resolution_diagonal']
        )

    def compute_l_curve(
        self,
        forward_matrix: np.ndarray,
        data: np.ndarray,
        lambda_range: Optional[List[float]] = None
    ) -> Dict[str, Any]:
        """
        Compute L-curve for regularization parameter selection.

        Args:
            forward_matrix: Forward operator matrix
            data: Observed data
            lambda_range: Range of lambda values to test (auto if None)

        Returns:
            Dictionary with residuals, model_norms, and optimal lambda
        """
        n_model = forward_matrix.shape[1]
        L = np.eye(n_model)  # Simple regularization for L-curve

        # Auto-generate lambda range if not provided
        if lambda_range is None:
            lambda_range = np.logspace(-8, 2, 50)
        else:
            lambda_range = np.array(lambda_range)

        solver = TikhonovSolver(forward_matrix, L)
        residuals, model_norms = solver.l_curve(data, lambda_range)

        # Find corner of L-curve (simple approach)
        # Compute curvature
        log_residuals = np.log10(residuals + 1e-10)
        log_model_norms = np.log10(model_norms + 1e-10)

        # Second derivative approximation
        dx = np.gradient(log_residuals)
        dy = np.gradient(log_model_norms)
        curvature = np.abs(np.gradient(dy) * dx - np.gradient(dx) * dy)

        optimal_idx = np.argmax(curvature)
        optimal_lambda = lambda_range[optimal_idx]

        return {
            'lambda_values': lambda_range.tolist(),
            'residuals': residuals.tolist(),
            'model_norms': model_norms.tolist(),
            'optimal_lambda': float(optimal_lambda),
            'optimal_index': int(optimal_idx),
            'curvature': curvature.tolist()
        }

    # =========================================================================
    # Nonlinear Inversion Methods
    # =========================================================================

    def solve_gauss_newton(
        self,
        forward_func_code: str,
        jacobian_func_code: str,
        data: np.ndarray,
        m_init: np.ndarray,
        lambda_reg: float = 0.1,
        max_iter: int = 20,
        tol: float = 1e-6
    ) -> InversionResult:
        """
        Solve nonlinear inverse problem using Gauss-Newton method.

        Note: This is a simplified version. In production, forward_func and
        jacobian_func would be provided as actual Python functions or selected
        from a library of forward models.

        Args:
            forward_func_code: Forward model function identifier
            jacobian_func_code: Jacobian function identifier
            data: Observed data
            m_init: Initial model estimate
            lambda_reg: Regularization parameter
            max_iter: Maximum iterations
            tol: Convergence tolerance

        Returns:
            InversionResult with optimized model
        """
        # For now, use simple polynomial forward model as example
        # In production, would have library of forward models

        def forward_func(m):
            """Simple nonlinear forward model: d = G * exp(m)"""
            # Create a simple forward operator
            n_data = len(data)
            n_model = len(m)
            G_base = np.random.randn(n_data, n_model) * 0.1
            return G_base @ np.exp(m * 0.1)

        def jacobian_func(m):
            """Jacobian of forward model."""
            n_data = len(data)
            n_model = len(m)
            G_base = np.random.randn(n_data, n_model) * 0.1
            # J = G * diag(exp(m) * 0.1)
            return G_base * (np.exp(m * 0.1) * 0.1)

        # Create regularization
        n_model = len(m_init)
        regularizer = SmoothnessRegularizer(n_model, order=2)
        L = regularizer.matrix()

        # Create solver and solve
        solver = GaussNewtonSolver(forward_func, jacobian_func, L)
        result = solver.solve(
            data, m_init, lambda_reg,
            max_iter=max_iter,
            tol=tol,
            line_search=True
        )

        return InversionResult(
            model=result['model'],
            predicted_data=result['predicted_data'],
            residual=result['residual'],
            iterations=result['iterations'],
            converged=result['converged']
        )

    def solve_bayesian_map(
        self,
        forward_func_code: str,
        jacobian_func_code: str,
        data: np.ndarray,
        m_prior: np.ndarray,
        C_m: np.ndarray,
        C_d: np.ndarray,
        max_iter: int = 20,
        tol: float = 1e-6
    ) -> Dict[str, Any]:
        """
        Solve inverse problem using Bayesian MAP estimation.

        Provides uncertainty quantification via posterior covariance.

        Args:
            forward_func_code: Forward model identifier
            jacobian_func_code: Jacobian identifier
            data: Observed data
            m_prior: Prior mean model
            C_m: Prior model covariance
            C_d: Data covariance (measurement errors)
            max_iter: Maximum iterations
            tol: Convergence tolerance

        Returns:
            Dictionary with MAP estimate, uncertainties, and posterior covariance
        """
        # Simple forward models (same as Gauss-Newton for now)
        def forward_func(m):
            n_data = len(data)
            n_model = len(m)
            G_base = np.random.randn(n_data, n_model) * 0.1
            return G_base @ m

        def jacobian_func(m):
            n_data = len(data)
            n_model = len(m)
            return np.random.randn(n_data, n_model) * 0.1

        # Create solver
        solver = BayesianMAPSolver(forward_func, jacobian_func)

        # Solve
        result = solver.solve(data, m_prior, C_m, C_d, max_iter=max_iter, tol=tol)

        # Compute credible intervals
        lower, upper = solver.credible_intervals(
            result['model_map'],
            result['posterior_covariance'],
            confidence=0.95
        )

        return {
            'model_map': result['model_map'].tolist(),
            'uncertainties': result['uncertainties'].tolist(),
            'predicted_data': result['predicted_data'].tolist(),
            'iterations': result['iterations'],
            'resolution_diagonal': result['resolution_diagonal'].tolist(),
            'credible_intervals_lower': lower.tolist(),
            'credible_intervals_upper': upper.tolist(),
            'posterior_covariance_diagonal': np.diag(result['posterior_covariance']).tolist()
        }

    # =========================================================================
    # Gravity Field Operations
    # =========================================================================

    def load_gravity_model(
        self,
        model_name: str = 'EGM96',
        data_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Load reference gravity field model.

        Args:
            model_name: Model name ('EGM96' or 'EGM2008')
            data_path: Optional path to coefficient file

        Returns:
            Dictionary with model metadata
        """
        if model_name in self._gravity_models:
            model = self._gravity_models[model_name]
        else:
            if model_name == 'EGM96':
                model = load_egm96()
            elif model_name == 'EGM2008':
                model = load_egm2008()
            else:
                raise ValueError(f"Unknown gravity model: {model_name}")

            self._gravity_models[model_name] = model

        return {
            'name': model.name,
            'degree_max': model.degree_max,
            'reference_radius': model.reference_radius,
            'gm': model.gm,
            'metadata': model.metadata
        }

    def compute_gravity_anomaly(
        self,
        lat: np.ndarray,
        lon: np.ndarray,
        observed_gravity: np.ndarray,
        model_name: str = 'EGM96',
        correction_type: str = 'free_air',
        elevation: Optional[np.ndarray] = None
    ) -> GravityAnomalyResult:
        """
        Compute gravity anomaly relative to reference model.

        Args:
            lat: Latitude in degrees
            lon: Longitude in degrees
            observed_gravity: Observed gravity values in mGal
            model_name: Reference gravity model name
            correction_type: Type of anomaly ('free_air', 'bouguer', 'isostatic')
            elevation: Elevation in meters (required for Bouguer)

        Returns:
            GravityAnomalyResult with anomaly and components
        """
        # Load or retrieve cached model
        if model_name not in self._gravity_models:
            self.load_gravity_model(model_name)

        model = self._gravity_models[model_name]

        # Compute anomaly
        anomaly, components = compute_gravity_anomaly(
            lat, lon, observed_gravity, model,
            correction_type=correction_type,
            elevation=elevation
        )

        return GravityAnomalyResult(
            anomaly=anomaly,
            normal_gravity=components['normal_gravity'],
            components=components
        )

    def compute_geoid_height(
        self,
        lat: np.ndarray,
        lon: np.ndarray,
        model_name: str = 'EGM96',
        max_degree: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Compute geoid heights from spherical harmonic model.

        Args:
            lat: Latitude in degrees
            lon: Longitude in degrees
            model_name: Gravity model name
            max_degree: Maximum degree to use (None = use all)

        Returns:
            Dictionary with geoid heights and metadata
        """
        if model_name not in self._gravity_models:
            self.load_gravity_model(model_name)

        model = self._gravity_models[model_name]

        # Compute geoid heights
        geoid = model.compute_geoid_height(lat, lon, max_degree=max_degree)

        return {
            'geoid_height': geoid.tolist(),
            'latitude': lat.tolist(),
            'longitude': lon.tolist(),
            'model_name': model_name,
            'max_degree': max_degree or model.degree_max,
            'units': 'meters'
        }

    # =========================================================================
    # Joint Inversion Methods
    # =========================================================================

    def setup_joint_inversion_model(
        self,
        gravity_data: np.ndarray,
        lat: np.ndarray,
        lon: np.ndarray,
        depth: Optional[np.ndarray] = None,
        model_name: str = 'joint_model'
    ) -> str:
        """
        Set up joint inversion model configuration.

        Args:
            gravity_data: Gravity observations in mGal
            lat: Latitude points
            lon: Longitude points
            depth: Depth points (optional, for 3D)
            model_name: Name for the model

        Returns:
            Model ID for subsequent operations
        """
        # Create joint inversion model
        joint_model = setup_joint_inversion(
            gravity_data, lat, lon, depth, model_name
        )

        # In production, would store in database or cache
        # For now, store in memory
        if not hasattr(self, '_joint_models'):
            self._joint_models = {}

        self._joint_models[model_name] = joint_model

        return model_name

    def add_seismic_to_joint_inversion(
        self,
        model_id: str,
        seismic_data: np.ndarray,
        seismic_type: str = 'velocity',
        coupling_type: str = 'petrophysical'
    ) -> Dict[str, Any]:
        """
        Add seismic data to joint inversion model.

        Args:
            model_id: Joint inversion model ID
            seismic_data: Seismic observations
            seismic_type: Type of seismic data
            coupling_type: Coupling method ('petrophysical', 'structural', 'uncoupled')

        Returns:
            Updated model metadata
        """
        if not hasattr(self, '_joint_models') or model_id not in self._joint_models:
            raise ValueError(f"Joint model {model_id} not found")

        joint_model = self._joint_models[model_id]

        # Add seismic data with coupling
        updated_model = integrate_gravity_seismic(
            joint_model,
            seismic_data,
            seismic_type=seismic_type,
            coupling_type=coupling_type
        )

        self._joint_models[model_id] = updated_model

        return {
            'model_id': model_id,
            'data_types': updated_model.data_types,
            'coupling': coupling_type,
            'status': 'updated'
        }

    def run_joint_inversion(
        self,
        model_id: str,
        max_iterations: int = 100,
        convergence_tol: float = 1e-6
    ) -> Dict[str, Any]:
        """
        Execute joint inversion for configured model.

        Args:
            model_id: Joint inversion model ID
            max_iterations: Maximum iterations
            convergence_tol: Convergence tolerance

        Returns:
            Inversion results including all data types
        """
        if not hasattr(self, '_joint_models') or model_id not in self._joint_models:
            raise ValueError(f"Joint model {model_id} not found")

        joint_model = self._joint_models[model_id]

        # Run inversion
        results = perform_joint_inversion(
            joint_model,
            max_iterations=max_iterations,
            convergence_tol=convergence_tol
        )

        # Add model ID to results
        results['model_id'] = model_id
        results['model_name'] = joint_model.name

        # Convert numpy arrays to lists for JSON serialization
        serialized_results = {}
        for key, value in results.items():
            if isinstance(value, np.ndarray):
                serialized_results[key] = value.tolist()
            else:
                serialized_results[key] = value

        return serialized_results

    # =========================================================================
    # Resolution and Uncertainty Analysis
    # =========================================================================

    def analyze_resolution(
        self,
        resolution_matrix: np.ndarray,
        grid_shape: Optional[Tuple[int, int]] = None
    ) -> Dict[str, Any]:
        """
        Analyze resolution from resolution matrix.

        Args:
            resolution_matrix: Model resolution matrix
            grid_shape: Optional grid shape for 2D visualization

        Returns:
            Dictionary with resolution metrics
        """
        analysis = UncertaintyAnalysis()
        metrics = analysis.compute_resolution_metrics(resolution_matrix)

        # Convert numpy arrays to lists
        serialized_metrics = {}
        for key, value in metrics.items():
            if isinstance(value, np.ndarray):
                serialized_metrics[key] = value.tolist()
            else:
                serialized_metrics[key] = float(value)

        # Add resolution map if grid shape provided
        if grid_shape is not None:
            resolution_map = analysis.plot_resolution_map(
                resolution_matrix, grid_shape
            )
            serialized_metrics['resolution_map'] = resolution_map.tolist()
            serialized_metrics['grid_shape'] = grid_shape

        return serialized_metrics


# Singleton instance
_inversion_service = None


def get_inversion_service() -> InversionService:
    """Get or create inversion service singleton."""
    global _inversion_service
    if _inversion_service is None:
        _inversion_service = InversionService()
    return _inversion_service
