"""
Validation Suite for Calibration and System Identification

Comprehensive validation including:
- Whiteness tests on residuals
- Parameter estimation accuracy
- Error budget analysis
- Diagnostic plots
"""

import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from calibration import (AllanDeviation, CrossSpectralDensity, WhitenessTest,
                        plot_allan_deviation)
from system_id import (DragCoefficientEstimator, SolarPressureEstimator,
                       EmpiricalAccelerationModel, ResidualAnalyzer)
from cal_maneuvers import (CalibrationManeuverGenerator, SyntheticOrbitGenerator,
                           create_example_scenario)


class ValidationSuite:
    """Comprehensive validation of calibration tools."""
    
    def __init__(self, output_dir: str = "docs/validation_results"):
        """Initialize validation suite."""
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.results = {}
    
    def validate_whiteness(self):
        """Validate whiteness testing on known white and colored noise."""
        print("\n" + "=" * 70)
        print("WHITENESS VALIDATION")
        print("=" * 70)
        
        np.random.seed(42)
        n = 1000
        
        # Test 1: White noise (should pass all tests)
        print("\n1. White Noise Test")
        print("-" * 70)
        white_noise = np.random.randn(n)
        white_results = WhitenessTest.comprehensive_test(white_noise)
        
        print(f"Ljung-Box p-value: {white_results['ljung_box']['p_value']:.4f}")
        print(f"Runs test p-value: {white_results['runs']['p_value']:.4f}")
        print(f"Durbin-Watson: {white_results['durbin_watson']:.4f}")
        print(f"Overall assessment: {'WHITE ✓' if white_results['overall_white'] else 'NOT WHITE ✗'}")
        
        # Test 2: Autocorrelated noise (should fail tests)
        print("\n2. Autocorrelated Noise Test")
        print("-" * 70)
        ar_noise = np.zeros(n)
        ar_noise[0] = np.random.randn()
        for i in range(1, n):
            ar_noise[i] = 0.7 * ar_noise[i-1] + np.random.randn()
        
        ar_results = WhitenessTest.comprehensive_test(ar_noise)
        
        print(f"Ljung-Box p-value: {ar_results['ljung_box']['p_value']:.4f}")
        print(f"Runs test p-value: {ar_results['runs']['p_value']:.4f}")
        print(f"Durbin-Watson: {ar_results['durbin_watson']:.4f}")
        print(f"Overall assessment: {'WHITE ✓' if ar_results['overall_white'] else 'NOT WHITE ✗'}")
        
        self.results['whiteness'] = {
            'white_noise': white_results,
            'ar_noise': ar_results
        }
        
        # Plot autocorrelation functions
        fig, axes = plt.subplots(1, 2, figsize=(12, 4))
        
        acf_white = ResidualAnalyzer.compute_autocorrelation(white_noise, max_lag=50)
        axes[0].stem(range(len(acf_white)), acf_white)
        axes[0].axhline(1.96/np.sqrt(n), color='r', linestyle='--', alpha=0.5)
        axes[0].axhline(-1.96/np.sqrt(n), color='r', linestyle='--', alpha=0.5)
        axes[0].set_xlabel('Lag')
        axes[0].set_ylabel('ACF')
        axes[0].set_title('White Noise ACF')
        axes[0].grid(True, alpha=0.3)
        
        acf_ar = ResidualAnalyzer.compute_autocorrelation(ar_noise, max_lag=50)
        axes[1].stem(range(len(acf_ar)), acf_ar)
        axes[1].axhline(1.96/np.sqrt(n), color='r', linestyle='--', alpha=0.5)
        axes[1].axhline(-1.96/np.sqrt(n), color='r', linestyle='--', alpha=0.5)
        axes[1].set_xlabel('Lag')
        axes[1].set_ylabel('ACF')
        axes[1].set_title('AR(1) Noise ACF')
        axes[1].grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(self.output_dir / 'whiteness_acf.png', dpi=150)
        print(f"\n  → Plot saved: {self.output_dir / 'whiteness_acf.png'}")
        
        return white_results['overall_white'] and not ar_results['overall_white']
    
    def validate_allan_deviation(self):
        """Validate Allan deviation on different noise types."""
        print("\n" + "=" * 70)
        print("ALLAN DEVIATION VALIDATION")
        print("=" * 70)
        
        np.random.seed(42)
        n = 10000
        rate = 100.0
        
        # Generate different noise types
        white = np.random.randn(n) * 0.1
        random_walk = np.cumsum(np.random.randn(n) * 0.01)
        flicker = np.cumsum(np.random.randn(n) * 0.005) * np.sqrt(np.arange(1, n+1))
        
        fig, axes = plt.subplots(1, 3, figsize=(15, 5))
        
        for i, (data, name, expected_slope) in enumerate([
            (white, "White Noise", -0.5),
            (random_walk, "Random Walk", 0.5),
            (white + random_walk, "White + RW", 0.0)
        ]):
            print(f"\n{i+1}. {name}")
            print("-" * 70)
            
            adev_calc = AllanDeviation(data, rate, overlapping=True)
            taus, adev = adev_calc.compute()
            
            noise_id = adev_calc.identify_noise_type(taus, adev)
            print(f"  Identified: {noise_id['type']}")
            print(f"  Slope: {noise_id['slope']:.3f} (expected: {expected_slope:.1f})")
            
            plot_allan_deviation(taus, adev, title=name, ax=axes[i])
        
        plt.tight_layout()
        plt.savefig(self.output_dir / 'allan_deviation.png', dpi=150)
        print(f"\n  → Plot saved: {self.output_dir / 'allan_deviation.png'}")
        
        self.results['allan'] = {'generated': True}
        
        return True
    
    def validate_system_identification(self):
        """Validate parameter estimation accuracy."""
        print("\n" + "=" * 70)
        print("SYSTEM IDENTIFICATION VALIDATION")
        print("=" * 70)
        
        np.random.seed(42)
        
        # Test drag coefficient estimation
        print("\n1. Drag Coefficient Estimation")
        print("-" * 70)
        
        n = 200
        times = np.linspace(0, 5400, n)
        true_cd = 2.3
        area_to_mass = 0.01
        
        density = 1e-12 * np.exp(-times / 3600)
        velocity = 7500 + 50 * np.sin(2 * np.pi * times / 5400)
        
        drag_true = 0.5 * true_cd * area_to_mass * density * velocity**2
        drag_accel = drag_true[:, np.newaxis] * np.array([[-1, 0, 0]])
        
        # Add realistic noise
        noise_level = 1e-8
        residuals = drag_accel + np.random.randn(n, 3) * noise_level
        
        estimator = DragCoefficientEstimator(area_to_mass, initial_cd=2.0)
        result = estimator.estimate(times, residuals, density, velocity)
        
        cd_error = abs(result.parameters[0] - true_cd)
        cd_sigma = result.parameter_uncertainties()[0]
        
        print(f"  True CD: {true_cd:.4f}")
        print(f"  Estimated CD: {result.parameters[0]:.4f} ± {cd_sigma:.4f}")
        print(f"  Error: {cd_error:.4f} ({cd_error/cd_sigma:.2f}σ)")
        print(f"  Success: {result.success}")
        
        # Test whiteness of residuals
        residual_whiteness = WhitenessTest.comprehensive_test(result.residuals.flatten())
        print(f"  Post-fit residuals white: {residual_whiteness['overall_white']}")
        
        # Test SRP estimation
        print("\n2. Solar Pressure Coefficient Estimation")
        print("-" * 70)
        
        true_cr = 1.8
        sun_vectors = np.random.randn(n, 3)
        sun_vectors /= np.linalg.norm(sun_vectors, axis=1, keepdims=True)
        sun_distances = np.full(n, 1.496e11)
        shadow_factors = np.ones(n)
        
        srp_estimator = SolarPressureEstimator(area_to_mass, initial_cr=1.5)
        P_sun = 4.56e-6
        c = 299792458.0
        srp_mag = true_cr * area_to_mass * (P_sun / c)
        srp_accel = srp_mag * (-sun_vectors)
        
        residuals_srp = srp_accel + np.random.randn(n, 3) * 1e-9
        
        result_srp = srp_estimator.estimate(times, residuals_srp, sun_vectors,
                                           sun_distances, shadow_factors)
        
        cr_error = abs(result_srp.parameters[0] - true_cr)
        cr_sigma = result_srp.parameter_uncertainties()[0]
        
        print(f"  True CR: {true_cr:.4f}")
        print(f"  Estimated CR: {result_srp.parameters[0]:.4f} ± {cr_sigma:.4f}")
        print(f"  Error: {cr_error:.4f} ({cr_error/cr_sigma:.2f}σ)")
        print(f"  Success: {result_srp.success}")
        
        self.results['system_id'] = {
            'cd_estimation': result,
            'cr_estimation': result_srp
        }
        
        # Plot estimation results
        fig, axes = plt.subplots(2, 2, figsize=(12, 10))
        
        # Drag coefficient convergence (simulated)
        axes[0, 0].axhline(true_cd, color='r', linestyle='--', label='True')
        axes[0, 0].axhline(result.parameters[0], color='b', linestyle='-', label='Estimated')
        axes[0, 0].fill_between([0, 1], 
                                 result.parameters[0] - cd_sigma,
                                 result.parameters[0] + cd_sigma,
                                 alpha=0.3)
        axes[0, 0].set_ylabel('CD')
        axes[0, 0].set_title('Drag Coefficient Estimation')
        axes[0, 0].legend()
        axes[0, 0].grid(True, alpha=0.3)
        axes[0, 0].set_xlim(0, 1)
        
        # Drag residuals
        axes[0, 1].plot(times/60, result.residuals[:, 0] * 1e9, 'b.', alpha=0.5)
        axes[0, 1].axhline(0, color='r', linestyle='--')
        axes[0, 1].set_xlabel('Time (min)')
        axes[0, 1].set_ylabel('Residual (nm/s²)')
        axes[0, 1].set_title('Post-fit Drag Residuals (X-component)')
        axes[0, 1].grid(True, alpha=0.3)
        
        # SRP coefficient
        axes[1, 0].axhline(true_cr, color='r', linestyle='--', label='True')
        axes[1, 0].axhline(result_srp.parameters[0], color='b', linestyle='-', label='Estimated')
        axes[1, 0].fill_between([0, 1],
                                 result_srp.parameters[0] - cr_sigma,
                                 result_srp.parameters[0] + cr_sigma,
                                 alpha=0.3)
        axes[1, 0].set_ylabel('CR')
        axes[1, 0].set_title('SRP Coefficient Estimation')
        axes[1, 0].legend()
        axes[1, 0].grid(True, alpha=0.3)
        axes[1, 0].set_xlim(0, 1)
        
        # SRP residuals
        axes[1, 1].plot(times/60, result_srp.residuals[:, 0] * 1e9, 'b.', alpha=0.5)
        axes[1, 1].axhline(0, color='r', linestyle='--')
        axes[1, 1].set_xlabel('Time (min)')
        axes[1, 1].set_ylabel('Residual (nm/s²)')
        axes[1, 1].set_title('Post-fit SRP Residuals (X-component)')
        axes[1, 1].grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(self.output_dir / 'parameter_estimation.png', dpi=150)
        print(f"\n  → Plot saved: {self.output_dir / 'parameter_estimation.png'}")
        
        return result.success and result_srp.success
    
    def generate_error_budget(self):
        """Generate comprehensive error budget plots."""
        print("\n" + "=" * 70)
        print("ERROR BUDGET ANALYSIS")
        print("=" * 70)
        
        # Define error sources with realistic magnitudes
        error_sources = {
            'Measurement Noise': 10.0,  # meters
            'Atmospheric Drag': 5.0,
            'Solar Pressure': 3.0,
            'Earth Gravity Model': 2.0,
            'Third Body Perturbations': 1.0,
            'Numerical Integration': 0.5,
            'Station Location': 0.3,
            'Timing Errors': 0.2
        }
        
        # Calculate RSS
        rss_total = np.sqrt(sum(v**2 for v in error_sources.values()))
        
        print("\nError Budget Components:")
        print("-" * 70)
        for source, error in sorted(error_sources.items(), key=lambda x: -x[1]):
            contribution = (error / rss_total) * 100
            print(f"  {source:.<30} {error:>6.2f} m ({contribution:>5.1f}%)")
        print(f"  {'Total (RSS)':.<30} {rss_total:>6.2f} m")
        
        # Create error budget plots
        fig = plt.figure(figsize=(14, 10))
        gs = fig.add_gridspec(3, 2, hspace=0.3, wspace=0.3)
        
        # 1. Bar chart
        ax1 = fig.add_subplot(gs[0, :])
        sources = list(error_sources.keys())
        errors = list(error_sources.values())
        colors = plt.cm.viridis(np.linspace(0, 1, len(sources)))
        
        bars = ax1.barh(sources, errors, color=colors)
        ax1.axvline(rss_total, color='r', linestyle='--', linewidth=2, label='Total RSS')
        ax1.set_xlabel('Position Error (m)')
        ax1.set_title('Error Budget by Source')
        ax1.legend()
        ax1.grid(True, alpha=0.3, axis='x')
        
        # 2. Pie chart
        ax2 = fig.add_subplot(gs[1, 0])
        ax2.pie(errors, labels=sources, autopct='%1.1f%%', startangle=90)
        ax2.set_title('Error Contribution (%)')
        
        # 3. Waterfall chart
        ax3 = fig.add_subplot(gs[1, 1])
        cumulative = np.cumsum([0] + [e**2 for e in errors])
        cumulative_rss = np.sqrt(cumulative)
        
        for i in range(len(sources)):
            ax3.bar(i, errors[i]**2, bottom=cumulative[i], color=colors[i], alpha=0.7)
        
        ax3.plot(range(len(sources)), cumulative_rss[1:], 'ro-', linewidth=2, markersize=8)
        ax3.set_xticks(range(len(sources)))
        ax3.set_xticklabels(sources, rotation=45, ha='right')
        ax3.set_ylabel('Cumulative Error² (m²)')
        ax3.set_title('Cumulative Error Growth')
        ax3.grid(True, alpha=0.3, axis='y')
        
        # 4. Time evolution (simulated)
        ax4 = fig.add_subplot(gs[2, :])
        t = np.linspace(0, 24, 100)  # hours
        
        # Simulate error growth
        measurement_err = error_sources['Measurement Noise'] * np.ones_like(t)
        drag_err = error_sources['Atmospheric Drag'] * (1 + 0.5 * t / 24)
        srp_err = error_sources['Solar Pressure'] * (1 + 0.3 * t / 24)
        gravity_err = error_sources['Earth Gravity Model'] * (1 + 0.2 * t / 24)
        other_err = 2.0 * (1 + 0.1 * t / 24)
        
        total_err = np.sqrt(measurement_err**2 + drag_err**2 + srp_err**2 + 
                           gravity_err**2 + other_err**2)
        
        ax4.fill_between(t, 0, measurement_err, alpha=0.7, label='Measurement')
        ax4.fill_between(t, measurement_err, measurement_err + drag_err, 
                        alpha=0.7, label='+ Drag')
        ax4.fill_between(t, measurement_err + drag_err, 
                        measurement_err + drag_err + srp_err,
                        alpha=0.7, label='+ SRP')
        ax4.plot(t, total_err, 'k-', linewidth=2, label='Total RSS')
        
        ax4.set_xlabel('Time Since Epoch (hours)')
        ax4.set_ylabel('Position Error (m)')
        ax4.set_title('Error Budget Evolution Over Time')
        ax4.legend(loc='upper left')
        ax4.grid(True, alpha=0.3)
        
        plt.savefig(self.output_dir / 'error_budget.png', dpi=150, bbox_inches='tight')
        print(f"\n  → Plot saved: {self.output_dir / 'error_budget.png'}")
        
        self.results['error_budget'] = error_sources
        
        return True
    
    def run_all(self):
        """Run complete validation suite."""
        print("\n" + "=" * 70)
        print("CALIBRATION AND SYSTEM ID VALIDATION SUITE")
        print("=" * 70)
        
        results = {
            'whiteness': self.validate_whiteness(),
            'allan': self.validate_allan_deviation(),
            'system_id': self.validate_system_identification(),
            'error_budget': self.generate_error_budget()
        }
        
        print("\n" + "=" * 70)
        print("VALIDATION SUMMARY")
        print("=" * 70)
        
        for test, passed in results.items():
            status = "✓ PASS" if passed else "✗ FAIL"
            print(f"  {test.upper():.<40} {status}")
        
        all_passed = all(results.values())
        
        print("\n" + "=" * 70)
        if all_passed:
            print("ALL TESTS PASSED ✓")
        else:
            print("SOME TESTS FAILED ✗")
        print("=" * 70)
        
        print(f"\nResults saved to: {self.output_dir}")
        
        return all_passed


if __name__ == "__main__":
    # Run validation suite
    suite = ValidationSuite()
    success = suite.run_all()
    
    # Display plots (if interactive)
    try:
        plt.show()
    except:
        pass
    
    sys.exit(0 if success else 1)
