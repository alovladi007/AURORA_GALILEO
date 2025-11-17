"""
Performance Benchmarks: Fusion Module
======================================

Gold standard validation and regression tests for fusion algorithms.
"""

import time
import numpy as np
from fusion.joint_inversion import JointInversionProblem, solve_joint_inversion
from fusion.regularization import (
    cross_gradient_2d,
    joint_sparsity,
    total_variation,
    StructuralCouplingRegularization,
)


class FusionBenchmarks:
    """Performance benchmarks for fusion module."""

    @staticmethod
    def benchmark_joint_inversion_small():
        """
        Benchmark: Small-scale joint inversion (100 parameters).

        Gold standard:
        - Runtime: < 1.0 seconds
        - Convergence: < 20 iterations
        - Accuracy: RMS error < 5%
        """
        n_params = 100
        n_data1 = 50
        n_data2 = 50

        # Setup
        np.random.seed(42)
        G1 = np.random.randn(n_data1, n_params) * 0.1
        G2 = np.random.randn(n_data2, n_params) * 0.1

        m_true = np.random.randn(n_params) * 10.0
        d1 = G1 @ m_true + np.random.randn(n_data1) * 0.1
        d2 = G2 @ m_true + np.random.randn(n_data2) * 0.1

        problem = JointInversionProblem(n_params, n_data1, n_data2)
        problem.set_initial_model(np.zeros(n_params))
        problem.set_forward_operator1(G1)
        problem.set_forward_operator2(G2)

        # Benchmark
        start_time = time.time()

        result = solve_joint_inversion(
            problem=problem,
            data1=d1,
            data2=d2,
            max_iterations=50,
            tolerance=1e-4,
        )

        runtime = time.time() - start_time

        # Validate
        m_recovered = result['model']
        rms_error = np.sqrt(np.mean((m_recovered - m_true)**2))
        relative_error = rms_error / np.sqrt(np.mean(m_true**2))

        # Gold standards
        assert runtime < 1.0, f"Runtime {runtime:.3f}s exceeds 1.0s threshold"
        assert result['n_iterations'] < 20, \
            f"Iterations {result['n_iterations']} exceeds 20"
        assert relative_error < 0.05, \
            f"Relative error {relative_error:.3f} exceeds 5%"

        return {
            'name': 'joint_inversion_small',
            'runtime': runtime,
            'iterations': result['n_iterations'],
            'relative_error': relative_error,
            'converged': result['converged'],
            'status': 'PASS',
        }

    @staticmethod
    def benchmark_joint_inversion_medium():
        """
        Benchmark: Medium-scale joint inversion (1,000 parameters).

        Gold standard:
        - Runtime: < 10.0 seconds
        - Convergence: < 30 iterations
        - Accuracy: RMS error < 10%
        """
        n_params = 1000
        n_data1 = 300
        n_data2 = 300

        # Setup
        np.random.seed(42)
        G1 = np.random.randn(n_data1, n_params) * 0.05
        G2 = np.random.randn(n_data2, n_params) * 0.05

        # Sparse true model
        m_true = np.zeros(n_params)
        m_true[100:200] = 10.0
        m_true[500:600] = -5.0

        d1 = G1 @ m_true + np.random.randn(n_data1) * 0.2
        d2 = G2 @ m_true + np.random.randn(n_data2) * 0.2

        problem = JointInversionProblem(n_params, n_data1, n_data2)
        problem.set_initial_model(np.zeros(n_params))
        problem.set_forward_operator1(G1)
        problem.set_forward_operator2(G2)

        # Benchmark
        start_time = time.time()

        result = solve_joint_inversion(
            problem=problem,
            data1=d1,
            data2=d2,
            max_iterations=50,
            tolerance=1e-3,
        )

        runtime = time.time() - start_time

        # Validate
        m_recovered = result['model']
        rms_error = np.sqrt(np.mean((m_recovered - m_true)**2))
        relative_error = rms_error / np.sqrt(np.mean(m_true**2))

        # Gold standards
        assert runtime < 10.0, f"Runtime {runtime:.3f}s exceeds 10.0s threshold"
        assert result['n_iterations'] < 30, \
            f"Iterations {result['n_iterations']} exceeds 30"
        assert relative_error < 0.10, \
            f"Relative error {relative_error:.3f} exceeds 10%"

        return {
            'name': 'joint_inversion_medium',
            'runtime': runtime,
            'iterations': result['n_iterations'],
            'relative_error': relative_error,
            'converged': result['converged'],
            'status': 'PASS',
        }

    @staticmethod
    def benchmark_cross_gradient_2d():
        """
        Benchmark: Cross-gradient computation (2D).

        Gold standard:
        - Runtime: < 0.1 seconds for 100x100 grid
        - Numerical accuracy: orthogonal models → high cross-gradient
        """
        grid_size = 100

        # Create models
        x = np.linspace(0, 1, grid_size)
        y = np.linspace(0, 1, grid_size)
        X, Y = np.meshgrid(x, y)

        # Model 1: varies in x
        m1 = X

        # Model 2: varies in y (orthogonal)
        m2 = Y

        # Benchmark
        start_time = time.time()

        cg_norm, grad1, grad2 = cross_gradient_2d(m1, m2, grid_spacing=1.0/grid_size)

        runtime = time.time() - start_time

        # Validate
        assert runtime < 0.1, f"Runtime {runtime:.3f}s exceeds 0.1s threshold"
        assert cg_norm > 0.01, "Cross-gradient should be significant for orthogonal models"
        assert grad1.shape == m1.shape
        assert grad2.shape == m2.shape

        return {
            'name': 'cross_gradient_2d',
            'runtime': runtime,
            'cross_gradient_norm': cg_norm,
            'grid_size': f'{grid_size}x{grid_size}',
            'status': 'PASS',
        }

    @staticmethod
    def benchmark_total_variation():
        """
        Benchmark: Total Variation regularization.

        Gold standard:
        - Runtime: < 0.05 seconds for 100x100 grid
        - Sharp edges → high TV
        - Smooth models → low TV
        """
        grid_size = 100

        # Sharp edge model
        sharp_model = np.zeros((grid_size, grid_size))
        sharp_model[:grid_size//2, :] = 1.0

        # Smooth model
        x = np.linspace(-1, 1, grid_size)
        y = np.linspace(-1, 1, grid_size)
        X, Y = np.meshgrid(x, y)
        smooth_model = X**2 + Y**2

        # Benchmark sharp model
        start_time = time.time()
        tv_sharp, grad_sharp = total_variation(sharp_model)
        runtime_sharp = time.time() - start_time

        # Benchmark smooth model
        start_time = time.time()
        tv_smooth, grad_smooth = total_variation(smooth_model)
        runtime_smooth = time.time() - start_time

        # Validate
        assert runtime_sharp < 0.05, f"Sharp runtime {runtime_sharp:.3f}s exceeds 0.05s"
        assert runtime_smooth < 0.05, f"Smooth runtime {runtime_smooth:.3f}s exceeds 0.05s"
        assert tv_sharp > tv_smooth, "Sharp edges should have higher TV than smooth"

        return {
            'name': 'total_variation',
            'runtime_sharp': runtime_sharp,
            'runtime_smooth': runtime_smooth,
            'tv_sharp': tv_sharp,
            'tv_smooth': tv_smooth,
            'tv_ratio': tv_sharp / tv_smooth,
            'status': 'PASS',
        }

    @staticmethod
    def benchmark_structural_coupling():
        """
        Benchmark: Combined structural coupling regularization.

        Gold standard:
        - Runtime: < 0.5 seconds for 50x50 dual models
        """
        grid_size = 50

        # Create two models
        np.random.seed(42)
        m1 = np.random.randn(grid_size, grid_size)
        m2 = np.random.randn(grid_size, grid_size)

        # Create regularization
        reg = StructuralCouplingRegularization(
            lambda_cross_grad=1.0,
            lambda_sparsity=0.1,
            lambda_tv=0.1,
        )

        # Benchmark
        start_time = time.time()

        total_reg, gradients = reg([m1, m2])

        runtime = time.time() - start_time

        # Validate
        assert runtime < 0.5, f"Runtime {runtime:.3f}s exceeds 0.5s threshold"
        assert total_reg > 0, "Total regularization should be positive"
        assert len(gradients) == 2
        assert gradients[0].shape == m1.shape
        assert gradients[1].shape == m2.shape

        return {
            'name': 'structural_coupling',
            'runtime': runtime,
            'total_regularization': total_reg,
            'grid_size': f'{grid_size}x{grid_size}',
            'status': 'PASS',
        }


def run_all_benchmarks():
    """Run all fusion benchmarks and return results."""
    benchmarks = FusionBenchmarks()

    results = []

    print("Running Fusion Benchmarks...")
    print("=" * 70)

    # Small-scale joint inversion
    try:
        result = benchmarks.benchmark_joint_inversion_small()
        results.append(result)
        print(f"✓ {result['name']}: {result['runtime']:.3f}s, "
              f"{result['iterations']} iter, "
              f"error={result['relative_error']:.2%}")
    except AssertionError as e:
        print(f"✗ joint_inversion_small: FAILED - {e}")
        results.append({'name': 'joint_inversion_small', 'status': 'FAIL', 'error': str(e)})

    # Medium-scale joint inversion
    try:
        result = benchmarks.benchmark_joint_inversion_medium()
        results.append(result)
        print(f"✓ {result['name']}: {result['runtime']:.3f}s, "
              f"{result['iterations']} iter, "
              f"error={result['relative_error']:.2%}")
    except AssertionError as e:
        print(f"✗ joint_inversion_medium: FAILED - {e}")
        results.append({'name': 'joint_inversion_medium', 'status': 'FAIL', 'error': str(e)})

    # Cross-gradient
    try:
        result = benchmarks.benchmark_cross_gradient_2d()
        results.append(result)
        print(f"✓ {result['name']}: {result['runtime']:.4f}s, "
              f"CG norm={result['cross_gradient_norm']:.4f}")
    except AssertionError as e:
        print(f"✗ cross_gradient_2d: FAILED - {e}")
        results.append({'name': 'cross_gradient_2d', 'status': 'FAIL', 'error': str(e)})

    # Total Variation
    try:
        result = benchmarks.benchmark_total_variation()
        results.append(result)
        print(f"✓ {result['name']}: sharp={result['runtime_sharp']:.4f}s, "
              f"smooth={result['runtime_smooth']:.4f}s, "
              f"ratio={result['tv_ratio']:.2f}")
    except AssertionError as e:
        print(f"✗ total_variation: FAILED - {e}")
        results.append({'name': 'total_variation', 'status': 'FAIL', 'error': str(e)})

    # Structural coupling
    try:
        result = benchmarks.benchmark_structural_coupling()
        results.append(result)
        print(f"✓ {result['name']}: {result['runtime']:.4f}s")
    except AssertionError as e:
        print(f"✗ structural_coupling: FAILED - {e}")
        results.append({'name': 'structural_coupling', 'status': 'FAIL', 'error': str(e)})

    print("=" * 70)

    # Summary
    passed = sum(1 for r in results if r.get('status') == 'PASS')
    total = len(results)
    print(f"\nSummary: {passed}/{total} benchmarks passed ({100*passed/total:.0f}%)")

    return results


if __name__ == "__main__":
    run_all_benchmarks()
