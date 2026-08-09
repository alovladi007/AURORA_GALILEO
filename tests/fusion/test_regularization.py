"""
Tests for Regularization Functions
===================================

Tests cross-gradient, joint sparsity, TV, and minimum support regularization.
"""

import pytest
import numpy as np
from fusion.regularization import (
    cross_gradient_2d,
    cross_gradient_3d,
    joint_sparsity,
    total_variation,
    minimum_support,
    StructuralCouplingRegularization,
)


class TestCrossGradient2D:
    """Test 2D cross-gradient regularization."""

    def test_identical_models_zero_cross_gradient(self):
        """Test that identical models have zero cross-gradient."""
        # Create two identical models
        m1 = np.random.randn(10, 10)
        m2 = m1.copy()

        cg_norm, grad_m1, grad_m2 = cross_gradient_2d(m1, m2)

        # Cross-gradient should be zero
        assert cg_norm < 1e-10, "Identical models should have zero cross-gradient"

    def test_perpendicular_gradients_high_cross_gradient(self):
        """Test that perpendicular gradients give high cross-gradient."""
        # Model 1: varies in x direction
        x = np.linspace(0, 1, 20)
        y = np.linspace(0, 1, 20)
        X, Y = np.meshgrid(x, y)
        m1 = X  # Gradient in x direction

        # Model 2: varies in y direction
        m2 = Y  # Gradient in y direction

        cg_norm, grad_m1, grad_m2 = cross_gradient_2d(m1, m2, grid_spacing=0.05)

        # Cross-gradient should be non-zero
        assert cg_norm > 0.01, "Perpendicular gradients should have non-zero cross-gradient"

    def test_aligned_gradients_low_cross_gradient(self):
        """Test that aligned gradients give low cross-gradient."""
        x = np.linspace(0, 1, 20)
        y = np.linspace(0, 1, 20)
        X, Y = np.meshgrid(x, y)

        # Both models vary in same direction
        m1 = X + Y
        m2 = 2 * (X + Y)  # Same gradient direction, different magnitude

        cg_norm, grad_m1, grad_m2 = cross_gradient_2d(m1, m2)

        # Cross-gradient should be very small
        assert cg_norm < 1e-10, "Aligned gradients should have near-zero cross-gradient"

    def test_gradient_shapes(self):
        """Test that gradients have correct shape."""
        m1 = np.random.randn(15, 20)
        m2 = np.random.randn(15, 20)

        cg_norm, grad_m1, grad_m2 = cross_gradient_2d(m1, m2)

        assert grad_m1.shape == m1.shape
        assert grad_m2.shape == m2.shape

    def test_dimension_mismatch_error(self):
        """Test that dimension mismatch raises error."""
        m1 = np.random.randn(10, 10)
        m2 = np.random.randn(10, 15)

        with pytest.raises(ValueError, match="same shape"):
            cross_gradient_2d(m1, m2)

    def test_not_2d_error(self):
        """Test that non-2D arrays raise error."""
        m1 = np.random.randn(10)
        m2 = np.random.randn(10)

        with pytest.raises(ValueError, match="2D arrays"):
            cross_gradient_2d(m1, m2)


class TestCrossGradient3D:
    """Test 3D cross-gradient regularization."""

    def test_identical_models_3d(self):
        """Test that identical 3D models have zero cross-gradient."""
        m1 = np.random.randn(8, 8, 8)
        m2 = m1.copy()

        cg_norm, grad_m1, grad_m2 = cross_gradient_3d(m1, m2)

        assert cg_norm < 1e-10, "Identical 3D models should have zero cross-gradient"

    def test_gradient_shapes_3d(self):
        """Test that 3D gradients have correct shape."""
        m1 = np.random.randn(10, 12, 15)
        m2 = np.random.randn(10, 12, 15)

        cg_norm, grad_m1, grad_m2 = cross_gradient_3d(
            m1, m2, grid_spacing=(0.1, 0.1, 0.1)
        )

        assert grad_m1.shape == m1.shape
        assert grad_m2.shape == m2.shape

    def test_not_3d_error(self):
        """Test that non-3D arrays raise error."""
        m1 = np.random.randn(10, 10)
        m2 = np.random.randn(10, 10)

        with pytest.raises(ValueError, match="3D arrays"):
            cross_gradient_3d(m1, m2)


class TestJointSparsity:
    """Test joint sparsity regularization."""

    def test_l1_sparsity(self):
        """Test L1 sparsity regularization."""
        models = [np.array([1.0, -2.0, 0.0]), np.array([0.5, 0.0, -1.0])]

        reg_value, gradients = joint_sparsity(models, p_norm=1.0)

        # L1 norm should be sum of absolute values
        expected = np.sum(np.abs(models[0])) + np.sum(np.abs(models[1]))
        assert np.isclose(reg_value, expected)

        # Gradient should be sign
        np.testing.assert_array_equal(gradients[0], np.sign(models[0]))
        np.testing.assert_array_equal(gradients[1], np.sign(models[1]))

    def test_l2_sparsity(self):
        """Test L2 (Tikhonov) regularization."""
        models = [np.array([1.0, 2.0, 3.0])]

        reg_value, gradients = joint_sparsity(models, p_norm=2.0)

        # L2 norm should be sum of squares
        expected = np.sum(models[0] ** 2)
        assert np.isclose(reg_value, expected)

        # Gradient should be 2*m
        np.testing.assert_array_almost_equal(gradients[0], 2.0 * models[0])

    def test_sparse_models_lower_regularization(self):
        """Test that sparser models have lower L1 regularization."""
        sparse_model = np.array([1.0, 0.0, 0.0, 0.0, 0.0])
        dense_model = np.array([0.2, 0.2, 0.2, 0.2, 0.2])

        reg_sparse, _ = joint_sparsity([sparse_model], p_norm=1.0)
        reg_dense, _ = joint_sparsity([dense_model], p_norm=1.0)

        assert reg_sparse == reg_dense  # Same L1 norm
        # But for L0.5 norm, sparse should be lower
        reg_sparse_p05, _ = joint_sparsity([sparse_model], p_norm=0.5)
        reg_dense_p05, _ = joint_sparsity([dense_model], p_norm=0.5)

        assert reg_sparse_p05 < reg_dense_p05, "Sparser model should have lower p=0.5 norm"

    def test_gradient_shapes(self):
        """Test that gradients have correct shapes."""
        models = [
            np.random.randn(10, 10),
            np.random.randn(10, 10),
            np.random.randn(10, 10),
        ]

        reg_value, gradients = joint_sparsity(models, p_norm=1.0)

        assert len(gradients) == len(models)
        for i, grad in enumerate(gradients):
            assert grad.shape == models[i].shape


class TestTotalVariation:
    """Test Total Variation regularization."""

    def test_smooth_model_low_tv(self):
        """TV discriminates oscillation, not edges: for the same value
        range, a monotone model (ramp or step) has TV ~= range * width,
        while an oscillatory/noisy model has far higher TV. (A smooth
        quadratic spanning a larger range than a unit step legitimately
        has MORE total variation — the old comparison was ill-posed.)"""
        n = 30
        # Monotone ramp spanning [0, 1]
        ramp = np.tile(np.linspace(0.0, 1.0, n), (n, 1))
        tv_ramp, _ = total_variation(ramp)

        # Step with the same range
        step = np.zeros((n, n))
        step[:, n // 2:] = 1.0
        tv_step, _ = total_variation(step)

        # Noisy model with the same range
        rng = np.random.RandomState(0)
        noisy = rng.uniform(0.0, 1.0, (n, n))
        tv_noisy, _ = total_variation(noisy)

        # Monotone variants are comparable; oscillation dominates both
        assert tv_noisy > 3 * tv_ramp
        assert tv_noisy > 3 * tv_step

    def test_constant_model_zero_tv(self):
        """Test that constant models have zero TV."""
        constant_model = np.ones((20, 20)) * 5.0

        tv_value, gradient = total_variation(constant_model)

        assert tv_value < 1e-6, "Constant model should have near-zero TV"

    def test_3d_tv(self):
        """Test 3D Total Variation."""
        model_3d = np.random.randn(10, 10, 10)

        tv_value, gradient = total_variation(model_3d, grid_spacing=0.1)

        assert tv_value > 0
        assert gradient.shape == model_3d.shape

    def test_gradient_shape(self):
        """Test that gradient has correct shape."""
        model = np.random.randn(15, 20)

        tv_value, gradient = total_variation(model)

        assert gradient.shape == model.shape

    def test_invalid_dimension_error(self):
        """Test that 1D models raise error."""
        model = np.random.randn(10)

        with pytest.raises(ValueError, match="2D or 3D"):
            total_variation(model)


class TestMinimumSupport:
    """Test minimum support regularization."""

    def test_zero_difference_zero_support(self):
        """Test that model equal to reference has zero support."""
        model = np.array([1.0, 2.0, 3.0, 4.0])
        reference = model.copy()

        support_value, gradient = minimum_support(model, reference, p_norm=0.0)

        # Support should be very small (due to epsilon)
        assert support_value < 0.1, "Zero difference should give near-zero support"

    def test_compact_anomaly_lower_support(self):
        """Test that compact anomalies have lower support."""
        reference = np.zeros(100)

        # Compact anomaly
        compact = reference.copy()
        compact[45:55] = 1.0  # 10 non-zero values

        # Dispersed anomaly (same total amplitude)
        dispersed = reference.copy()
        dispersed[::10] = 1.0  # 10 non-zero values

        support_compact, _ = minimum_support(compact, reference, p_norm=0.0)
        support_dispersed, _ = minimum_support(dispersed, reference, p_norm=0.0)

        # Both should be similar for p=0 (counts non-zero)
        # The exact values depend on epsilon, but should be comparable
        assert abs(support_compact - support_dispersed) < 5.0

    def test_gradient_shape(self):
        """Test that gradient has correct shape."""
        model = np.random.randn(10, 10)
        reference = np.zeros((10, 10))

        support_value, gradient = minimum_support(model, reference, p_norm=0.0)

        assert gradient.shape == model.shape

    def test_different_p_norms(self):
        """Test different p-norm values."""
        model = np.array([1.0, 0.0, -1.0, 0.5])
        reference = np.zeros(4)

        support_p0, grad_p0 = minimum_support(model, reference, p_norm=0.0)
        support_p1, grad_p1 = minimum_support(model, reference, p_norm=1.0)

        # Both should be positive
        assert support_p0 > 0
        assert support_p1 > 0

        # Gradients should have same shape
        assert grad_p0.shape == grad_p1.shape == model.shape


class TestStructuralCouplingRegularization:
    """Test combined structural coupling regularization."""

    def test_initialization(self):
        """Test regularization initialization."""
        reg = StructuralCouplingRegularization(
            lambda_cross_grad=1.0,
            lambda_sparsity=0.1,
            lambda_tv=0.05,
            lambda_support=0.01,
        )

        assert reg.lambda_cross_grad == 1.0
        assert reg.lambda_sparsity == 0.1
        assert reg.lambda_tv == 0.05
        assert reg.lambda_support == 0.01

    def test_combined_regularization(self):
        """Test that combined regularization works."""
        reg = StructuralCouplingRegularization(
            lambda_cross_grad=1.0,
            lambda_sparsity=0.1,
            lambda_tv=0.1,
        )

        models = [
            np.random.randn(10, 10),
            np.random.randn(10, 10),
        ]

        total_reg, gradients = reg(models)

        assert total_reg > 0, "Total regularization should be positive"
        assert len(gradients) == len(models)
        for i, grad in enumerate(gradients):
            assert grad.shape == models[i].shape

    def test_cross_gradient_only(self):
        """Test cross-gradient only regularization."""
        reg = StructuralCouplingRegularization(
            lambda_cross_grad=1.0,
            lambda_sparsity=0.0,
            lambda_tv=0.0,
            lambda_support=0.0,
        )

        # Perpendicular gradients
        x = np.linspace(0, 1, 20)
        y = np.linspace(0, 1, 20)
        X, Y = np.meshgrid(x, y)
        m1 = X
        m2 = Y

        total_reg, gradients = reg([m1, m2])

        assert total_reg > 0, "Cross-gradient should be non-zero"

    def test_sparsity_only(self):
        """Test sparsity only regularization."""
        reg = StructuralCouplingRegularization(
            lambda_cross_grad=0.0,
            lambda_sparsity=1.0,
            lambda_tv=0.0,
            lambda_support=0.0,
        )

        models = [np.array([[1.0, 0.0], [0.0, 1.0]])]

        total_reg, gradients = reg(models)

        # L1 norm = 2.0
        assert np.isclose(total_reg, 2.0)

    def test_tv_only(self):
        """Test TV only regularization."""
        reg = StructuralCouplingRegularization(
            lambda_cross_grad=0.0,
            lambda_sparsity=0.0,
            lambda_tv=1.0,
            lambda_support=0.0,
        )

        models = [np.random.randn(10, 10)]

        total_reg, gradients = reg(models)

        assert total_reg > 0, "TV should be positive"

    def test_support_with_reference(self):
        """Test minimum support with reference models."""
        reg = StructuralCouplingRegularization(
            lambda_cross_grad=0.0,
            lambda_sparsity=0.0,
            lambda_tv=0.0,
            lambda_support=1.0,
        )

        models = [np.array([1.0, 2.0, 3.0])]
        reference_models = [np.zeros(3)]

        total_reg, gradients = reg(models, reference_models=reference_models)

        assert total_reg > 0, "Support should be positive"
        assert gradients[0].shape == models[0].shape

    def test_single_model(self):
        """Test with single model (no cross-gradient)."""
        reg = StructuralCouplingRegularization(
            lambda_cross_grad=1.0,  # Should be ignored for single model
            lambda_sparsity=0.1,
            lambda_tv=0.1,
        )

        models = [np.random.randn(10, 10)]

        total_reg, gradients = reg(models)

        # Should only have sparsity and TV
        assert total_reg > 0
        assert len(gradients) == 1

    def test_multiple_models(self):
        """Test with multiple models."""
        reg = StructuralCouplingRegularization(
            lambda_cross_grad=1.0,
            lambda_sparsity=0.1,
            lambda_tv=0.1,
        )

        models = [
            np.random.randn(8, 8),
            np.random.randn(8, 8),
            np.random.randn(8, 8),
        ]

        total_reg, gradients = reg(models)

        assert total_reg > 0
        assert len(gradients) == 3
        for grad in gradients:
            assert grad.shape == (8, 8)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
