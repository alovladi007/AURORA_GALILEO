"""
E2E Integration Test: Fusion Pipeline
======================================

Tests complete fusion workflow from data generation through inversion.
"""

import pytest
import numpy as np
from fusion.joint_inversion import JointInversionProblem, solve_joint_inversion
from fusion.regularization import StructuralCouplingRegularization
from data.stac import (
    STACCatalog,
    create_gravity_map_item,
    create_gravity_collection,
)


class TestFusionPipeline:
    """Test complete fusion data processing pipeline."""

    def test_synthetic_gravity_magnetic_inversion(self):
        """
        E2E test: Generate synthetic gravity+magnetic data, perform joint
        inversion with structural coupling, validate results.
        """
        # Step 1: Generate synthetic true model
        nx, ny = 20, 20
        n_params = nx * ny

        # True density anomaly (compact feature)
        true_density = np.zeros((ny, nx))
        true_density[8:12, 8:12] = 500.0  # kg/m^3 anomaly

        # True magnetic susceptibility (aligned structure)
        true_susceptibility = np.zeros((ny, nx))
        true_susceptibility[8:12, 8:12] = 0.05  # SI units

        # Flatten for inversion
        true_model = np.hstack([
            true_density.flatten(),
            true_susceptibility.flatten()
        ])

        # Step 2: Create forward operators (simplified)
        n_grav_obs = 50
        n_mag_obs = 50

        # Simple downward continuation operator
        np.random.seed(42)
        G_gravity = np.random.randn(n_grav_obs, n_params) * 0.1
        G_magnetic = np.random.randn(n_mag_obs, n_params) * 0.1

        # Generate synthetic observations
        d_gravity_true = G_gravity @ true_density.flatten()
        d_magnetic_true = G_magnetic @ true_susceptibility.flatten()

        # Add realistic noise
        noise_gravity = np.random.randn(n_grav_obs) * 0.1
        noise_magnetic = np.random.randn(n_mag_obs) * 0.05

        d_gravity = d_gravity_true + noise_gravity
        d_magnetic = d_magnetic_true + noise_magnetic

        # Step 3: Set up joint inversion problem
        problem = JointInversionProblem(
            n_params=2 * n_params,  # density + susceptibility
            n_data1=n_grav_obs,
            n_data2=n_mag_obs,
        )

        # Initial model (homogeneous)
        m0 = np.zeros(2 * n_params)

        problem.set_initial_model(m0)
        problem.set_forward_operator1(G_gravity, operator_type='gravity')
        problem.set_forward_operator2(G_magnetic, operator_type='magnetic')

        # Step 4: Create structural coupling regularization
        regularization = StructuralCouplingRegularization(
            lambda_cross_grad=1.0,
            lambda_sparsity=0.1,
            lambda_tv=0.05,
        )

        # Step 5: Solve joint inversion
        result = solve_joint_inversion(
            problem=problem,
            data1=d_gravity,
            data2=d_magnetic,
            regularization=regularization,
            max_iterations=20,
            tolerance=1e-4,
        )

        # Step 6: Validate results
        assert result['converged'], "Inversion should converge"
        assert result['n_iterations'] <= 20, "Should converge within 20 iterations"

        # Check data misfit decreased
        assert result['final_misfit'] < result['initial_misfit'], \
            "Data misfit should decrease"

        # Extract inverted models
        m_final = result['model']
        density_inv = m_final[:n_params].reshape((ny, nx))
        susceptibility_inv = m_final[n_params:].reshape((ny, nx))

        # Validate recovery in anomaly region
        anomaly_region = (slice(8, 12), slice(8, 12))

        # Density should be elevated in anomaly region
        assert np.mean(density_inv[anomaly_region]) > 100.0, \
            "Should recover density anomaly"

        # Susceptibility should be elevated in anomaly region
        assert np.mean(susceptibility_inv[anomaly_region]) > 0.01, \
            "Should recover susceptibility anomaly"

        # Step 7: Create STAC catalog with results
        catalog = STACCatalog(catalog_id="fusion-results")

        # Add gravity collection
        grav_collection = create_gravity_collection(
            collection_id="joint-inversion-gravity",
            title="Joint Inversion Gravity Results",
        )
        catalog.add_collection(grav_collection)

        # Add gravity result item
        grav_item = create_gravity_map_item(
            gravity_file="results/density_map.tif",
            bbox=[-10.0, 30.0, 10.0, 50.0],
            datetime_str="2024-01-01T00:00:00Z",
            collection_id="joint-inversion-gravity",
            metadata={
                'inversion_iterations': result['n_iterations'],
                'final_misfit': float(result['final_misfit']),
                'regularization': 'structural_coupling',
            }
        )
        catalog.add_item(grav_item)

        # Validate catalog
        assert len(catalog.collections) == 1
        assert len(catalog.items) == 1

        # Search should find the item
        results = catalog.search(collections=['joint-inversion-gravity'])
        assert len(results) == 1
        assert results[0].id == grav_item.id

        # Step 8: Return comprehensive results
        return {
            'inversion_result': result,
            'density_recovered': density_inv,
            'susceptibility_recovered': susceptibility_inv,
            'catalog': catalog,
            'data_fit_improvement': (
                result['initial_misfit'] - result['final_misfit']
            ) / result['initial_misfit'],
        }

    def test_regularization_parameter_sweep(self):
        """
        E2E test: Sweep regularization parameters and validate L-curve behavior.
        """
        # Simple test problem
        n_params = 100
        n_data = 50

        # Forward operator
        np.random.seed(42)
        G = np.random.randn(n_data, n_params) * 0.1

        # True model (sparse)
        m_true = np.zeros(n_params)
        m_true[20:30] = 10.0

        # Synthetic data
        d_true = G @ m_true
        d_obs = d_true + np.random.randn(n_data) * 0.5

        # Sweep regularization parameters
        lambdas = [0.01, 0.1, 1.0, 10.0]
        results = []

        for lam in lambdas:
            problem = JointInversionProblem(
                n_params=n_params,
                n_data1=n_data,
                n_data2=0,
            )

            problem.set_initial_model(np.zeros(n_params))
            problem.set_forward_operator1(G)

            # Simple Tikhonov regularization
            from fusion.regularization import joint_sparsity

            def regularization_func(models, reference_models=None):
                reg_val, grads = joint_sparsity(models, p_norm=2.0)
                return lam * reg_val, [lam * g for g in grads]

            result = solve_joint_inversion(
                problem=problem,
                data1=d_obs,
                data2=np.array([]),
                regularization=regularization_func,
                max_iterations=30,
                tolerance=1e-5,
            )

            results.append({
                'lambda': lam,
                'misfit': result['final_misfit'],
                'model_norm': np.linalg.norm(result['model']),
                'converged': result['converged'],
            })

        # Validate L-curve behavior
        # As regularization increases, misfit should increase but model norm decrease
        misfits = [r['misfit'] for r in results]
        norms = [r['model_norm'] for r in results]

        # Model norm should generally decrease with stronger regularization
        assert norms[-1] < norms[0], "Model norm should decrease with regularization"

        # All should converge
        assert all(r['converged'] for r in results), "All inversions should converge"

        return results

    def test_multi_scale_inversion(self):
        """
        E2E test: Multi-scale inversion from coarse to fine grid.
        """
        # Coarse grid: 10x10
        nx_coarse, ny_coarse = 10, 10
        n_params_coarse = nx_coarse * ny_coarse

        # Fine grid: 20x20
        nx_fine, ny_fine = 20, 20
        n_params_fine = nx_fine * ny_fine

        # Create synthetic data on fine grid
        true_model_fine = np.zeros((ny_fine, nx_fine))
        true_model_fine[8:12, 8:12] = 100.0

        np.random.seed(42)
        n_obs = 30
        G_fine = np.random.randn(n_obs, n_params_fine) * 0.1
        d_obs = G_fine @ true_model_fine.flatten() + np.random.randn(n_obs) * 0.1

        # Stage 1: Coarse grid inversion
        # Create coarse forward operator (by averaging)
        G_coarse = np.zeros((n_obs, n_params_coarse))
        for i in range(n_obs):
            fine_row = G_fine[i, :].reshape((ny_fine, nx_fine))
            # Downsample by averaging 2x2 blocks
            for iy in range(ny_coarse):
                for ix in range(nx_coarse):
                    block = fine_row[2*iy:2*iy+2, 2*ix:2*ix+2]
                    G_coarse[i, iy*nx_coarse + ix] = np.mean(block)

        problem_coarse = JointInversionProblem(
            n_params=n_params_coarse,
            n_data1=n_obs,
            n_data2=0,
        )
        problem_coarse.set_initial_model(np.zeros(n_params_coarse))
        problem_coarse.set_forward_operator1(G_coarse)

        result_coarse = solve_joint_inversion(
            problem=problem_coarse,
            data1=d_obs,
            data2=np.array([]),
            max_iterations=20,
        )

        # Stage 2: Fine grid inversion (using coarse result as initial)
        # Upsample coarse result
        m_coarse = result_coarse['model'].reshape((ny_coarse, nx_coarse))
        m_initial_fine = np.zeros((ny_fine, nx_fine))
        for iy in range(ny_coarse):
            for ix in range(nx_coarse):
                m_initial_fine[2*iy:2*iy+2, 2*ix:2*ix+2] = m_coarse[iy, ix]

        problem_fine = JointInversionProblem(
            n_params=n_params_fine,
            n_data1=n_obs,
            n_data2=0,
        )
        problem_fine.set_initial_model(m_initial_fine.flatten())
        problem_fine.set_forward_operator1(G_fine)

        result_fine = solve_joint_inversion(
            problem=problem_fine,
            data1=d_obs,
            data2=np.array([]),
            max_iterations=20,
        )

        # Validation
        assert result_coarse['converged'], "Coarse inversion should converge"
        assert result_fine['converged'], "Fine inversion should converge"

        # Fine inversion should have lower misfit (better data fit)
        assert result_fine['final_misfit'] <= result_coarse['final_misfit'] * 1.5, \
            "Fine grid should not be much worse than coarse"

        return {
            'coarse_result': result_coarse,
            'fine_result': result_fine,
            'misfit_improvement': (
                result_coarse['final_misfit'] - result_fine['final_misfit']
            ),
        }


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
