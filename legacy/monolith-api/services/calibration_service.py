"""
Calibration Service for GeoSense Platform API

Provides business logic for sensor calibration and characterization:
- Allan deviation analysis for frequency stability
- Phase model calibration for laser interferometry
- Noise budget calculation and characterization
- System identification and parameter estimation

This service bridges API endpoints with sensing/calibration modules.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

import numpy as np
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

# Import sensing modules
try:
    import jax.numpy as jnp
    from sensing.allan import allan_deviation, overlapping_allan_deviation, modified_allan_deviation
    from sensing.phase_model import compute_phase, compute_phase_rate, range_to_phase
    from sensing.noise import total_phase_noise_std, shot_noise_std, laser_frequency_noise_std
    SENSING_IMPORTS_AVAILABLE = True
except ImportError as e:
    print(f"Sensing imports not available: {e}")
    SENSING_IMPORTS_AVAILABLE = False


@dataclass
class AllanDeviationResult:
    """Container for Allan deviation results."""
    tau_values: np.ndarray
    adev_values: np.ndarray
    confidence_intervals: Optional[np.ndarray] = None

    def to_dict(self) -> Dict[str, Any]:
        # Replace NaN and Inf with None for JSON compliance
        def sanitize_values(arr):
            result = []
            for val in arr:
                if np.isnan(val) or np.isinf(val):
                    result.append(None)
                else:
                    result.append(float(val))
            return result

        return {
            'tau_values': sanitize_values(self.tau_values),
            'adev_values': sanitize_values(self.adev_values),
            'confidence_intervals': sanitize_values(self.confidence_intervals) if self.confidence_intervals is not None else None
        }


class CalibrationService:
    """Service for sensor calibration and characterization."""

    def __init__(self):
        """Initialize calibration service."""
        if not SENSING_IMPORTS_AVAILABLE:
            print("Warning: Sensing modules not available.")
        else:
            # Warm up JAX to avoid 5+ second delay on first call
            import jax.numpy as jnp
            try:
                # Trigger JAX compilation with simple operations
                _ = jnp.array([1.0, 2.0, 3.0])
                _ = jnp.logspace(0, 1, 10)
                _ = jnp.mean(_)
                print("✓ JAX initialized and warmed up for calibration service")
            except Exception as e:
                print(f"Warning: JAX warm-up failed: {e}")

    # =================================================================
    # Allan Deviation Analysis
    # =================================================================

    def compute_allan_deviation(
        self,
        data: np.ndarray,
        sample_rate: float,
        tau_min: float = 0.1,
        tau_max: float = 100.0,
        n_taus: int = 20,
        method: str = 'overlapping'
    ) -> AllanDeviationResult:
        """
        Compute Allan deviation for frequency stability analysis.

        Args:
            data: Time series data (phase measurements)
            sample_rate: Sampling rate in Hz
            tau_min: Minimum averaging time in seconds
            tau_max: Maximum averaging time in seconds
            n_taus: Number of tau values
            method: 'standard', 'overlapping', or 'modified'

        Returns:
            AllanDeviationResult with stability metrics
        """
        if not SENSING_IMPORTS_AVAILABLE:
            raise RuntimeError("Sensing modules not available")

        # Generate tau values
        tau_values = jnp.logspace(
            jnp.log10(tau_min),
            jnp.log10(tau_max),
            n_taus
        )

        # Convert data to JAX array
        data_jax = jnp.array(data)

        # Compute Allan deviation
        if method == 'standard':
            adev = allan_deviation(data_jax, sample_rate, tau_values)
        elif method == 'overlapping':
            adev = overlapping_allan_deviation(data_jax, sample_rate, tau_values)
        elif method == 'modified':
            adev = modified_allan_deviation(data_jax, sample_rate, tau_values)
        else:
            raise ValueError(f"Unknown method: {method}")

        return AllanDeviationResult(
            tau_values=np.array(tau_values),
            adev_values=np.array(adev)
        )

    # =================================================================
    # Phase Calibration
    # =================================================================

    def calibrate_phase_from_range(
        self,
        range_data: np.ndarray,
        wavelength: float = 1064e-9,
        phase_offset: float = 0.0
    ) -> Dict[str, Any]:
        """
        Convert range measurements to phase.

        Args:
            range_data: Range measurements in km
            wavelength: Laser wavelength in meters
            phase_offset: Initial phase offset in radians

        Returns:
            Dictionary with phase data and calibration info
        """
        if not SENSING_IMPORTS_AVAILABLE:
            raise RuntimeError("Sensing modules not available")

        # Convert wavelength to km
        wavelength_km = wavelength * 1e-6

        # Compute phase for each range value
        phase_data = []
        for r in range_data:
            phase = compute_phase(r, wavelength_km, phase_offset)
            phase_data.append(float(phase))

        # Compute phase rate if we have multiple points
        phase_rates = []
        if len(range_data) > 1:
            dt = 1.0  # Assume 1 second spacing
            range_rates = np.diff(range_data) / dt
            for rr in range_rates:
                phase_rate = compute_phase_rate(rr, wavelength_km)
                phase_rates.append(float(phase_rate))

        return {
            'phase_measurements': phase_data,
            'phase_rates': phase_rates,
            'wavelength_nm': wavelength * 1e9,
            'n_measurements': len(range_data),
            'range_span_km': float(np.max(range_data) - np.min(range_data))
        }

    def compute_phase_noise_budget(
        self,
        power: float,
        range_km: float,
        range_rate_km_s: float,
        frequency_stability: float = 1e-13,
        wavelength: float = 1064e-9
    ) -> Dict[str, Any]:
        """
        Compute comprehensive phase noise budget.

        Args:
            power: Laser power in Watts
            range_km: Range between satellites in km
            range_rate_km_s: Range rate in km/s
            frequency_stability: Laser frequency stability
            wavelength: Laser wavelength in meters

        Returns:
            Dictionary with noise budget breakdown
        """
        if not SENSING_IMPORTS_AVAILABLE:
            raise RuntimeError("Sensing modules not available")

        # Compute total noise
        total_noise, breakdown = total_phase_noise_std(
            power=power,
            range_km=range_km,
            range_rate_km_s=range_rate_km_s,
            frequency_stability=frequency_stability,
            wavelength=wavelength
        )

        # Convert JAX arrays to floats
        breakdown_dict = {k: float(v) for k, v in breakdown.items()}

        # Compute equivalent range error
        wavelength_km = wavelength * 1e-6
        k = 2 * np.pi / wavelength_km
        range_error = total_noise / (2 * k)  # Two-way path

        return {
            'total_phase_noise_rad': float(total_noise),
            'equivalent_range_error_m': float(range_error * 1e6),  # m
            'breakdown': breakdown_dict,
            'snr_db': float(10 * np.log10(1 / total_noise**2)) if total_noise > 0 else np.inf,
            'power_W': power,
            'range_km': range_km,
            'wavelength_nm': wavelength * 1e9
        }

    # =================================================================
    # System Identification
    # =================================================================

    def analyze_measurement_quality(
        self,
        measurements: np.ndarray,
        timestamps: np.ndarray,
        reference: Optional[np.ndarray] = None
    ) -> Dict[str, Any]:
        """
        Analyze measurement quality metrics.

        Args:
            measurements: Measured values
            timestamps: Measurement timestamps
            reference: Reference/truth values (optional)

        Returns:
            Dictionary with quality metrics
        """
        # Compute basic statistics
        mean_val = float(np.mean(measurements))
        std_val = float(np.std(measurements))
        rms_val = float(np.sqrt(np.mean(measurements**2)))

        # Compute sampling statistics
        dt = np.diff(timestamps)
        sample_rate = 1.0 / np.mean(dt) if len(dt) > 0 else 0.0

        # Compute errors if reference provided
        metrics = {
            'mean': mean_val,
            'std': std_val,
            'rms': rms_val,
            'min': float(np.min(measurements)),
            'max': float(np.max(measurements)),
            'sample_rate_hz': float(sample_rate),
            'n_measurements': len(measurements),
            'duration_s': float(timestamps[-1] - timestamps[0]) if len(timestamps) > 1 else 0.0
        }

        if reference is not None:
            errors = measurements - reference
            metrics.update({
                'mean_error': float(np.mean(errors)),
                'rms_error': float(np.sqrt(np.mean(errors**2))),
                'max_error': float(np.max(np.abs(errors))),
                'correlation': float(np.corrcoef(measurements, reference)[0, 1])
            })

        return metrics

    def identify_noise_types(
        self,
        tau_values: np.ndarray,
        adev_values: np.ndarray
    ) -> Dict[str, Any]:
        """
        Identify dominant noise types from Allan deviation slope.

        Args:
            tau_values: Averaging times
            adev_values: Allan deviation values

        Returns:
            Dictionary with noise type identification
        """
        # Remove NaN values
        valid_mask = ~np.isnan(adev_values)
        tau_clean = tau_values[valid_mask]
        adev_clean = adev_values[valid_mask]

        if len(tau_clean) < 2:
            return {'error': 'Insufficient valid data points'}

        # Fit log-log slope
        log_tau = np.log10(tau_clean)
        log_adev = np.log10(adev_clean)

        # Linear fit
        slope, intercept = np.polyfit(log_tau, log_adev, 1)

        # Identify noise type based on slope
        noise_types = []
        if abs(slope - (-1.0)) < 0.2:
            noise_types.append('white_phase_noise')
        if abs(slope - (-0.5)) < 0.2:
            noise_types.append('white_frequency_noise')
        if abs(slope - 0.0) < 0.2:
            noise_types.append('flicker_frequency_noise')
        if abs(slope - 0.5) < 0.2:
            noise_types.append('random_walk_frequency')

        return {
            'slope': float(slope),
            'intercept': float(intercept),
            'dominant_noise_types': noise_types,
            'interpretation': self._interpret_slope(slope)
        }

    def _interpret_slope(self, slope: float) -> str:
        """Interpret Allan deviation slope."""
        if abs(slope - (-1.0)) < 0.2:
            return "White phase noise (slope ≈ -1): Random measurement noise"
        elif abs(slope - (-0.5)) < 0.2:
            return "White frequency noise (slope ≈ -0.5): Shot noise, thermal noise"
        elif abs(slope - 0.0) < 0.2:
            return "Flicker frequency noise (slope ≈ 0): 1/f noise, often electronics"
        elif abs(slope - 0.5) < 0.2:
            return "Random walk frequency (slope ≈ +0.5): Drift, environmental effects"
        elif abs(slope - 1.0) < 0.2:
            return "Random run frequency (slope ≈ +1): Temperature drift"
        else:
            return f"Unusual slope {slope:.2f}: May indicate measurement issues or complex noise"


# Singleton
_calibration_service = None

def get_calibration_service() -> CalibrationService:
    """Get or create calibration service singleton."""
    global _calibration_service
    if _calibration_service is None:
        _calibration_service = CalibrationService()
    return _calibration_service
