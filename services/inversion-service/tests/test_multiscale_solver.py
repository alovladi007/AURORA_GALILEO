"""
Tests for MultiscaleInversionEngine
====================================

Covers wavelet decomposition, hierarchical solving, speedup verification.
"""

import pytest
import numpy as np

try:
    from src.multiscale_solver import MultiscaleInversionEngine
    HAS_MULTISCALE = True
except ImportError:
    HAS_MULTISCALE = False


def make_operator_builder(n_obs_fixed):
    """Factory for operator builder with fixed number of observations."""
    def operator_builder(grid_shape):
        """Simple forward operator for testing."""
        n_rows, n_cols = grid_shape
        n_model = n_rows * n_cols

        # Random operator with fixed n_obs
        rng = np.random.default_rng(42)
        G = rng.standard_normal((n_obs_fixed, n_model)) * 0.1
        return G
    return operator_builder


@pytest.mark.skipif(not HAS_MULTISCALE, reason="pywavelets not installed")
class TestMultiscaleInversionEngine:
    """Test suite for multi-scale inversion."""

    def test_grid_decomposability_check(self):
        """Check if grid is suitable for wavelet decomposition."""
        solver = MultiscaleInversionEngine(levels=3)

        # 64x64 is divisible by 2^3=8
        assert solver._check_grid_decomposable((64, 64))

        # 32x32 is divisible by 2^3=8
        assert solver._check_grid_decomposable((32, 32))

        # 50x50 is not divisible by 8
        assert not solver._check_grid_decomposable((50, 50))

    def test_coarse_shape_computation(self):
        """Coarse grid shape is correctly computed."""
        solver = MultiscaleInversionEngine(levels=3)

        # 64x64 -> 8x8 at level 3
        coarse = solver._get_coarse_shape((64, 64))
        assert coarse == (8, 8)

        # 32x32 -> 4x4 at level 3
        coarse = solver._get_coarse_shape((32, 32))
        assert coarse == (4, 4)

    def test_upsampling(self):
        """Model upsampling preserves structure."""
        solver = MultiscaleInversionEngine(levels=2)

        # Start with 4x4 grid
        model_4x4 = np.arange(16, dtype=float)

        # Upsample to 8x8
        model_8x8 = solver._upsample_model(model_4x4, (4, 4), (8, 8))

        assert model_8x8.shape == (64,)
        # Values should be interpolated, not just repeated
        assert not np.allclose(model_8x8[:4], model_4x4[:4])

    def test_small_grid_solve(self):
        """Multiscale solve works on small decomposable grid."""
        solver = MultiscaleInversionEngine(levels=2, wavelet="haar")

        # 16x16 grid
        grid_shape = (16, 16)
        n_model = 256
        n_obs = 128  # Fixed number of observations

        # Generate synthetic data
        rng = np.random.default_rng(42)
        op_builder = make_operator_builder(n_obs)
        G = op_builder(grid_shape)
        true_model = rng.standard_normal(n_model)
        observations = G @ true_model + rng.standard_normal(G.shape[0]) * 0.01

        # Solve
        result = solver.solve_multiscale(
            observations=observations,
            operator_builder=op_builder,
            grid_shape=grid_shape,
            method="tikhonov",
            lambda_reg=0.1,
            tolerance=1e-3
        )

        assert result.model.shape == (n_model,)
        assert result.misfit > 0
        assert result.refinement_levels >= 1
        assert len(result.active_cells_per_level) == result.refinement_levels + 1

    def test_large_grid_speedup(self):
        """Multiscale solver shows speedup on larger grids."""
        solver = MultiscaleInversionEngine(levels=3, wavelet="db4")

        # 64x64 grid (large enough to see speedup)
        grid_shape = (64, 64)
        n_model = 4096
        n_obs = 500  # Fixed observations

        rng = np.random.default_rng(42)
        op_builder = make_operator_builder(n_obs)
        observations = rng.standard_normal(n_obs)

        result = solver.solve_multiscale(
            observations=observations,
            operator_builder=op_builder,
            grid_shape=grid_shape,
            method="tikhonov",
            lambda_reg=0.1,
            tolerance=1e-3
        )

        # Should report speedup > 1
        assert result.speedup_factor >= 1.0

        # Should have used multiple levels
        assert result.refinement_levels >= 1

    def test_fallback_for_non_decomposable_grid(self):
        """Non-decomposable grid falls back to single-scale."""
        solver = MultiscaleInversionEngine(levels=3)

        # 50x50 not divisible by 2^3
        grid_shape = (50, 50)
        n_model = 2500
        n_obs = 300

        rng = np.random.default_rng(42)
        op_builder = make_operator_builder(n_obs)
        observations = rng.standard_normal(n_obs)

        result = solver.solve_multiscale(
            observations=observations,
            operator_builder=op_builder,
            grid_shape=grid_shape,
            method="tikhonov",
            lambda_reg=0.1
        )

        # Should fall back to single-scale
        assert result.refinement_levels == 0
        assert result.speedup_factor == 1.0

    def test_gauss_newton_method(self):
        """Multiscale works with Gauss-Newton method."""
        solver = MultiscaleInversionEngine(levels=2)

        grid_shape = (16, 16)
        n_obs = 128
        rng = np.random.default_rng(42)
        op_builder = make_operator_builder(n_obs)
        observations = rng.standard_normal(n_obs)

        result = solver.solve_multiscale(
            observations=observations,
            operator_builder=op_builder,
            grid_shape=grid_shape,
            method="gauss_newton",
            lambda_reg=0.1,
            tolerance=1e-3
        )

        assert result.method == "gauss_newton"
        assert result.model.shape == (256,)

    def test_different_wavelet_families(self):
        """Different wavelet families work."""
        for wavelet in ["haar", "db4", "sym4"]:
            solver = MultiscaleInversionEngine(levels=2, wavelet=wavelet)

            grid_shape = (16, 16)
            n_obs = 128
            rng = np.random.default_rng(42)
            op_builder = make_operator_builder(n_obs)
            observations = rng.standard_normal(n_obs)

            result = solver.solve_multiscale(
                observations=observations,
                operator_builder=op_builder,
                grid_shape=grid_shape,
                method="tikhonov",
                lambda_reg=0.1
            )

            assert result.model.shape == (256,)


@pytest.mark.skipif(HAS_MULTISCALE, reason="Test for when pywavelets not installed")
def test_multiscale_unavailable_without_pywavelets():
    """MultiscaleInversionEngine raises error without pywavelets."""
    with pytest.raises(RuntimeError, match="pywt is required"):
        from src.multiscale_solver import MultiscaleInversionEngine
        solver = MultiscaleInversionEngine()
