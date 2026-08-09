"""
Tests for Geophysical Inversion Engine
=======================================

Tests for solvers, regularizers, and uncertainty quantification.
"""

import numpy as np
from scipy.sparse import diags
import sys
sys.path.insert(0, '/home/claude/geophysics')

from inversion import (
    TikhonovSolver,
    GaussNewtonSolver,
    BayesianMAPSolver,
    UncertaintyAnalysis,
    SmoothnessRegularizer,
    TotalVariationRegularizer,
    SparsityRegularizer,
    GeologicPriorRegularizer
)


class TestTikhonovSolver:
    """Test linear Tikhonov regularization."""
    
    def test_simple_linear_problem(self):
        """Test on a simple linear inverse problem."""
        # Create synthetic problem: G*m = d
        n_data, n_model = 50, 30
        np.random.seed(42)
        
        # Forward matrix
        G = np.random.randn(n_data, n_model)
        
        # True model (sparse)
        m_true = np.zeros(n_model)
        m_true[5:10] = 1.0
        m_true[20:25] = -0.5
        
        # Data with noise
        d_true = G @ m_true
        noise = 0.1 * np.random.randn(n_data)
        d = d_true + noise
        
        # Solve with Tikhonov
        solver = TikhonovSolver(G)
        result = solver.solve(d, lambda_reg=0.1, compute_resolution=True)
        
        # Check that solution is reasonable
        assert result['model'].shape == (n_model,)
        assert result['residual'] < np.linalg.norm(noise) * 2  # Within 2x noise
        assert 'resolution_matrix' in result
        assert result['resolution_matrix'].shape == (n_model, n_model)
        
        # Resolution diagonal should be between 0 and 1
        r_diag = result['resolution_diagonal']
        assert np.all(r_diag >= 0) and np.all(r_diag <= 1.1)  # Allow small numerical error
    
    def test_l_curve(self):
        """Test L-curve computation."""
        n_data, n_model = 40, 25
        np.random.seed(42)
        
        G = np.random.randn(n_data, n_model)
        m_true = np.random.randn(n_model)
        d = G @ m_true + 0.1 * np.random.randn(n_data)
        
        solver = TikhonovSolver(G)
        lambdas = np.logspace(-3, 1, 20)
        residuals, model_norms = solver.l_curve(d, lambdas)
        
        # Check outputs
        assert len(residuals) == len(lambdas)
        assert len(model_norms) == len(lambdas)
        assert np.all(residuals > 0)
        assert np.all(model_norms > 0)
    
    def test_recovery_of_known_model(self):
        """Test that we can recover a known model with no noise."""
        n_data, n_model = 50, 30
        np.random.seed(42)
        
        G = np.random.randn(n_data, n_model)
        m_true = np.random.randn(n_model)
        d = G @ m_true  # No noise
        
        solver = TikhonovSolver(G)
        result = solver.solve(d, lambda_reg=1e-6)
        
        # With very small regularization and no noise, should recover true model
        relative_error = np.linalg.norm(result['model'] - m_true) / np.linalg.norm(m_true)
        assert relative_error < 1e-2


class TestGaussNewtonSolver:
    """Test nonlinear Gauss-Newton solver."""
    
    def test_simple_nonlinear_problem(self):
        """Test on a simple nonlinear problem."""
        # Nonlinear forward: d = m^2
        def forward(m):
            return m**2
        
        def jacobian(m):
            return np.diag(2 * m)
        
        # True model and data
        m_true = np.array([1.0, 2.0, 3.0])
        d = forward(m_true)
        
        # Initial guess
        m_init = np.array([0.5, 1.5, 2.5])
        
        # Solve. Regularization must be negligible for the residual to
        # reach the data: with lambda=0.01 the regularized optimum is
        # biased and a 1e-6 residual is mathematically unreachable.
        solver = GaussNewtonSolver(forward, jacobian)
        result = solver.solve(d, m_init, lambda_reg=1e-6, max_iter=50)

        # Check convergence
        assert result['converged']
        assert result['residual'] < 1e-6
        assert np.allclose(result['model'], m_true, rtol=1e-4)
    
    def test_convergence_history(self):
        """Test that convergence history is recorded."""
        def forward(m):
            return m**2
        
        def jacobian(m):
            return np.diag(2 * m)
        
        m_true = np.array([1.0, 2.0])
        d = forward(m_true)
        m_init = np.array([0.5, 1.5])
        
        solver = GaussNewtonSolver(forward, jacobian)
        result = solver.solve(d, m_init, lambda_reg=0.01)
        
        # Check history
        assert 'history' in result
        assert len(result['history']['models']) > 1
        assert len(result['history']['objective']) > 0
        
        # Objective should decrease
        obj = result['history']['objective']
        assert obj[-1] < obj[0]


class TestBayesianMAPSolver:
    """Test Bayesian MAP estimation."""
    
    def test_linear_case_with_gaussian_prior(self):
        """Test MAP estimation on a linear problem."""
        # Linear forward model
        n_data, n_model = 40, 25
        np.random.seed(42)
        
        G = np.random.randn(n_data, n_model)
        
        def forward(m):
            return G @ m
        
        def jacobian(m):
            return G
        
        # True model and data
        m_true = np.random.randn(n_model)
        d_true = forward(m_true)
        d = d_true + 0.1 * np.random.randn(n_data)
        
        # Prior
        m_prior = np.zeros(n_model)
        C_m = np.eye(n_model)
        C_d = 0.01 * np.eye(n_data)
        
        # Solve
        solver = BayesianMAPSolver(forward, jacobian)
        result = solver.solve(d, m_prior, C_m, C_d, max_iter=20)
        
        # Check outputs
        assert 'model_map' in result
        assert 'posterior_covariance' in result
        assert 'uncertainties' in result
        assert result['model_map'].shape == (n_model,)
        assert result['posterior_covariance'].shape == (n_model, n_model)
        
        # Posterior covariance should be symmetric and positive definite
        C_post = result['posterior_covariance']
        assert np.allclose(C_post, C_post.T)
        eigenvalues = np.linalg.eigvalsh(C_post)
        assert np.all(eigenvalues > 0)
    
    def test_credible_intervals(self):
        """Test credible interval computation."""
        n_model = 10
        m_map = np.random.randn(n_model)
        C_post = np.eye(n_model) * 0.1
        
        def forward(m):
            return m
        
        def jacobian(m):
            return np.eye(n_model)
        
        solver = BayesianMAPSolver(forward, jacobian)
        lower, upper = solver.credible_intervals(m_map, C_post, confidence=0.95)
        
        # Check bounds
        assert len(lower) == n_model
        assert len(upper) == n_model
        assert np.all(lower < upper)
        assert np.all(lower <= m_map)
        assert np.all(upper >= m_map)


class TestRegularizers:
    """Test regularization operators."""
    
    def test_smoothness_regularizer(self):
        """Test smoothness regularizer."""
        n = 20
        reg = SmoothnessRegularizer(n, order=2)
        
        # Get matrix
        L = reg.matrix()
        assert L.shape[0] == n - 2
        assert L.shape[1] == n
        
        # Test penalty on smooth vs rough model
        m_smooth = np.sin(np.linspace(0, 2*np.pi, n))
        m_rough = np.random.randn(n)
        
        penalty_smooth = reg.penalty(m_smooth)
        penalty_rough = reg.penalty(m_rough)
        
        # Smooth model should have smaller penalty
        assert penalty_smooth < penalty_rough
    
    def test_total_variation(self):
        """Test total variation regularizer."""
        n = 30
        reg = TotalVariationRegularizer(n, epsilon=1e-6)
        
        # Smooth model vs stepwise model
        m_smooth = np.sin(np.linspace(0, 2*np.pi, n))
        m_step = np.ones(n)
        m_step[15:] = -1
        
        tv_smooth = reg.penalty(m_smooth)
        tv_step = reg.penalty(m_step)
        
        # Both should have finite TV
        assert tv_smooth > 0
        assert tv_step > 0
    
    def test_sparsity_regularizer(self):
        """Test L1 sparsity regularizer."""
        n = 20
        reg = SparsityRegularizer(n, epsilon=1e-8)
        
        # Sparse vs dense model with the SAME L2 energy: for equal L2,
        # the L1 norm is minimized by concentration (sparsity) and
        # maximized by spreading, so L1(sparse) < L1(dense) is the
        # property an L1 regularizer must exhibit.
        m_sparse = np.zeros(n)
        m_sparse[[5, 10, 15]] = [1.0, -0.5, 0.8]
        l2 = np.linalg.norm(m_sparse)

        m_dense = np.full(n, l2 / np.sqrt(n))  # same L2, fully spread

        penalty_sparse = reg.penalty(m_sparse)
        penalty_dense = reg.penalty(m_dense)

        assert abs(np.linalg.norm(m_dense) - l2) < 1e-12
        assert penalty_sparse < penalty_dense
    
    def test_geologic_prior(self):
        """Test geologic prior regularizer."""
        n = 15
        m_ref = np.ones(n) * 2.5
        weights = np.ones(n)
        
        reg = GeologicPriorRegularizer(n, m_ref, weights)
        
        # Model close to reference
        m_close = m_ref + 0.1 * np.random.randn(n)
        m_far = m_ref + 5.0 * np.random.randn(n)
        
        penalty_close = reg.penalty(m_close)
        penalty_far = reg.penalty(m_far)
        
        # Model close to reference should have smaller penalty
        assert penalty_close < penalty_far


class TestUncertaintyAnalysis:
    """Test uncertainty analysis tools."""
    
    def test_resolution_metrics(self):
        """Test resolution matrix metrics."""
        n = 20
        
        # Create a mock resolution matrix (diagonal-dominant)
        R = 0.7 * np.eye(n) + 0.1 * np.random.randn(n, n)
        R = (R + R.T) / 2  # Symmetrize
        
        metrics = UncertaintyAnalysis.compute_resolution_metrics(R)
        
        assert 'resolution_diagonal' in metrics
        assert 'mean_resolution' in metrics
        assert 'spread' in metrics
        assert 'effective_rank' in metrics
        
        assert metrics['mean_resolution'] >= 0
        assert metrics['effective_rank'] > 0
    
    def test_resolution_map(self):
        """Test resolution map creation."""
        n = 25
        R = np.random.rand(n, n)
        
        # 1D map
        r_map = UncertaintyAnalysis.plot_resolution_map(R)
        assert len(r_map) == n
        
        # 2D map
        r_map_2d = UncertaintyAnalysis.plot_resolution_map(R, grid_shape=(5, 5))
        assert r_map_2d.shape == (5, 5)


class TestSyntheticRecovery:
    """
    Test recovery of synthetic anomalies within tolerance.
    
    This is the main acceptance test for the inversion engine.
    """
    
    def test_recover_gaussian_anomaly(self):
        """Test recovery of Gaussian anomaly."""
        # Create 1D synthetic model
        n_model = 100
        x = np.linspace(0, 10, n_model)
        
        # True model: Gaussian anomaly
        m_true = np.exp(-((x - 5)**2) / 2)
        
        # Forward operator: simple averaging/smoothing
        n_data = 80
        G = np.zeros((n_data, n_model))
        for i in range(n_data):
            idx_start = int(i * n_model / n_data)
            idx_end = int((i + 1) * n_model / n_data)
            G[i, idx_start:idx_end] = 1.0 / (idx_end - idx_start)
        
        # Generate data
        d_true = G @ m_true
        d = d_true + 0.05 * np.random.randn(n_data)
        
        # Invert with Tikhonov
        solver = TikhonovSolver(G)
        result = solver.solve(d, lambda_reg=0.01)
        
        # Check recovery accuracy
        m_recovered = result['model']
        
        # Anomaly should be recovered at correct location
        peak_true = np.argmax(m_true)
        peak_recovered = np.argmax(m_recovered)
        assert abs(peak_true - peak_recovered) < 5  # Within 5% of domain
        
        # Amplitude should be reasonable
        amp_true = np.max(m_true)
        amp_recovered = np.max(m_recovered)
        assert abs(amp_recovered - amp_true) / amp_true < 0.3  # Within 30%
    
    def test_recover_multiple_anomalies(self):
        """Test recovery of multiple anomalies."""
        n_model = 150
        x = np.linspace(0, 15, n_model)
        
        # True model: three Gaussians
        m_true = (np.exp(-((x - 3)**2) / 1) + 
                 0.5 * np.exp(-((x - 8)**2) / 2) +
                 -0.8 * np.exp(-((x - 12)**2) / 1.5))
        
        # Forward operator
        n_data = 120
        G = np.random.randn(n_data, n_model) * 0.1
        for i in range(n_data):
            center = int((i / n_data) * n_model)
            width = 10
            for j in range(max(0, center-width), min(n_model, center+width)):
                G[i, j] += np.exp(-((j - center)**2) / (2 * width**2))
        
        # Data
        d = G @ m_true + 0.1 * np.random.randn(n_data)
        
        # Solve with TV regularization (better for multiple anomalies)
        L = SmoothnessRegularizer(n_model, order=1).matrix()
        solver = TikhonovSolver(G, L)
        result = solver.solve(d, lambda_reg=0.05)
        
        m_recovered = result['model']
        
        # Check that we recovered something reasonable
        correlation = np.corrcoef(m_true, m_recovered)[0, 1]
        assert correlation > 0.7  # At least 70% correlation
        
        # Check residual is reasonable
        assert result['residual'] < 2 * np.linalg.norm(d) * 0.1  # Within 2x noise


def run_all_tests():
    """Run all tests and report results."""
    print("=" * 60)
    print("Running Inversion Engine Tests")
    print("=" * 60)
    
    test_classes = [
        TestTikhonovSolver,
        TestGaussNewtonSolver,
        TestBayesianMAPSolver,
        TestRegularizers,
        TestUncertaintyAnalysis,
        TestSyntheticRecovery
    ]
    
    total_tests = 0
    passed_tests = 0
    
    for test_class in test_classes:
        print(f"\n{test_class.__name__}:")
        test_instance = test_class()
        
        for method_name in dir(test_instance):
            if method_name.startswith('test_'):
                total_tests += 1
                try:
                    method = getattr(test_instance, method_name)
                    method()
                    print(f"  ✓ {method_name}")
                    passed_tests += 1
                except Exception as e:
                    print(f"  ✗ {method_name}: {str(e)}")
    
    print("\n" + "=" * 60)
    print(f"Test Results: {passed_tests}/{total_tests} passed")
    print("=" * 60)
    
    return passed_tests == total_tests


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
