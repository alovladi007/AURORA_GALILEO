"""
Emulator Service for GeoSense Platform API

Provides business logic layer for laboratory emulation operations:
- Optical bench emulator control and configuration
- Real-time signal generation and event injection
- Diagnostic data and performance metrics
- Integration with WebSocket streaming server

This service bridges API endpoints with emulator modules.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

import numpy as np
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import asyncio
import threading

# Import emulator modules
try:
    from emulator.optical_bench import (
        OpticalBenchEmulator,
        BenchParameters,
        NoiseProfile,
        SignalType
    )
    EMULATOR_IMPORTS_AVAILABLE = True
except ImportError as e:
    EMULATOR_IMPORTS_AVAILABLE = False
    print(f"Emulator imports not available: {e}")


@dataclass
class EmulatorState:
    """Container for emulator state snapshot."""
    timestamp: float
    interference_signal: Dict[str, float]
    thermal_data: Dict[str, float]
    vibration_data: Dict[str, float]
    laser_intensity: Dict[str, float]
    running: bool

    def to_dict(self) -> Dict[str, Any]:
        """Convert to serializable dictionary."""
        return asdict(self)


@dataclass
class EmulatorDiagnostics:
    """Container for emulator diagnostics."""
    uptime: float
    total_samples: int
    sampling_rate: float
    fringe_count: int
    thermal_drift_total: float
    signal_quality: Dict[str, float]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to serializable dictionary."""
        return asdict(self)


class EmulatorService:
    """
    Service for laboratory emulation operations.

    Provides high-level functions that wrap emulator modules,
    handling configuration, control, and state management.
    """

    def __init__(self):
        """Initialize emulator service."""
        if not EMULATOR_IMPORTS_AVAILABLE:
            print("Warning: Emulator modules not available. Service will have limited functionality.")

        self._emulators = {}  # Cache emulator instances
        self._running_loops = {}  # Background tasks for continuous operation

    # =========================================================================
    # Emulator Lifecycle Methods
    # =========================================================================

    def create_emulator(
        self,
        emulator_id: str = 'default',
        baseline_length: float = 1.0,
        wavelength: float = 632.8e-9,
        sampling_rate: float = 1000.0,
        temperature: float = 293.15,
        shot_noise_level: float = 0.01,
        thermal_noise_level: float = 0.005,
        vibration_amplitude: float = 1e-9,
        phase_stability: float = 0.1
    ) -> Dict[str, Any]:
        """
        Create and configure optical bench emulator instance.

        Args:
            emulator_id: Unique identifier for this emulator
            baseline_length: Interferometer baseline in meters
            wavelength: Laser wavelength in meters
            sampling_rate: Data sampling rate in Hz
            temperature: Operating temperature in Kelvin
            shot_noise_level: Shot noise RMS level
            thermal_noise_level: Thermal noise RMS level
            vibration_amplitude: Vibration amplitude in meters
            phase_stability: Phase stability in radians RMS

        Returns:
            Dictionary with emulator configuration
        """
        if not EMULATOR_IMPORTS_AVAILABLE:
            raise RuntimeError("Emulator modules not available")

        # Create parameters
        params = BenchParameters(
            baseline_length=baseline_length,
            wavelength=wavelength,
            sampling_rate=sampling_rate,
            temperature=temperature
        )

        # Create noise profile
        noise = NoiseProfile(
            shot_noise_level=shot_noise_level,
            thermal_noise_level=thermal_noise_level,
            vibration_amplitude=vibration_amplitude,
            phase_stability=phase_stability
        )

        # Create emulator instance
        emulator = OpticalBenchEmulator(params=params, noise=noise)

        # Cache emulator
        self._emulators[emulator_id] = emulator

        return {
            'emulator_id': emulator_id,
            'status': 'created',
            'parameters': {
                'baseline_length': baseline_length,
                'wavelength': wavelength * 1e9,  # nm
                'sampling_rate': sampling_rate,
                'temperature': temperature - 273.15  # Celsius
            },
            'noise_profile': {
                'shot_noise_level': shot_noise_level,
                'thermal_noise_level': thermal_noise_level,
                'vibration_amplitude': vibration_amplitude * 1e9,  # nm
                'phase_stability': phase_stability
            }
        }

    def get_emulator_status(self, emulator_id: str = 'default') -> Dict[str, Any]:
        """
        Get emulator operational status.

        Args:
            emulator_id: Emulator identifier

        Returns:
            Dictionary with status information
        """
        if not EMULATOR_IMPORTS_AVAILABLE:
            raise RuntimeError("Emulator modules not available")

        if emulator_id not in self._emulators:
            raise ValueError(f"Emulator {emulator_id} not found")

        emulator = self._emulators[emulator_id]

        return {
            'emulator_id': emulator_id,
            'running': emulator.running,
            'timestamp': emulator.get_timestamp(),
            'fringe_count': emulator.fringe_count,
            'thermal_drift_offset': emulator.thermal_drift_offset * 1e9,  # nm
            'parameters': {
                'baseline_length': emulator.params.baseline_length,
                'wavelength': emulator.params.wavelength * 1e9,  # nm
                'sampling_rate': emulator.params.sampling_rate,
                'temperature': emulator.params.temperature - 273.15  # Celsius
            }
        }

    def start_emulator(self, emulator_id: str = 'default') -> Dict[str, Any]:
        """
        Start emulator data generation.

        Args:
            emulator_id: Emulator identifier

        Returns:
            Dictionary with start status
        """
        if not EMULATOR_IMPORTS_AVAILABLE:
            raise RuntimeError("Emulator modules not available")

        if emulator_id not in self._emulators:
            raise ValueError(f"Emulator {emulator_id} not found")

        emulator = self._emulators[emulator_id]
        emulator.running = True

        return {
            'emulator_id': emulator_id,
            'status': 'running',
            'message': 'Emulator started successfully'
        }

    def stop_emulator(self, emulator_id: str = 'default') -> Dict[str, Any]:
        """
        Stop emulator data generation.

        Args:
            emulator_id: Emulator identifier

        Returns:
            Dictionary with stop status
        """
        if not EMULATOR_IMPORTS_AVAILABLE:
            raise RuntimeError("Emulator modules not available")

        if emulator_id not in self._emulators:
            raise ValueError(f"Emulator {emulator_id} not found")

        emulator = self._emulators[emulator_id]
        emulator.running = False

        return {
            'emulator_id': emulator_id,
            'status': 'stopped',
            'message': 'Emulator stopped successfully'
        }

    # =========================================================================
    # Data Generation Methods
    # =========================================================================

    def get_current_state(self, emulator_id: str = 'default') -> EmulatorState:
        """
        Get current emulator state snapshot.

        Args:
            emulator_id: Emulator identifier

        Returns:
            EmulatorState with all current signals
        """
        if not EMULATOR_IMPORTS_AVAILABLE:
            raise RuntimeError("Emulator modules not available")

        if emulator_id not in self._emulators:
            raise ValueError(f"Emulator {emulator_id} not found")

        emulator = self._emulators[emulator_id]
        t = emulator.get_timestamp()

        # Generate all signal types
        interference = emulator.generate_interference_signal(t)
        thermal = emulator.generate_thermal_drift(t)
        vibration = emulator.generate_vibration_signal(t)
        laser = emulator.generate_laser_intensity(t)

        return EmulatorState(
            timestamp=t,
            interference_signal=interference,
            thermal_data=thermal,
            vibration_data=vibration,
            laser_intensity=laser,
            running=emulator.running
        )

    def get_signal_history(
        self,
        emulator_id: str = 'default',
        duration: float = 1.0,
        signal_type: str = 'interference'
    ) -> Dict[str, Any]:
        """
        Generate time series of specified signal type.

        Args:
            emulator_id: Emulator identifier
            duration: Duration in seconds
            signal_type: Type of signal to generate

        Returns:
            Dictionary with time series data
        """
        if not EMULATOR_IMPORTS_AVAILABLE:
            raise RuntimeError("Emulator modules not available")

        if emulator_id not in self._emulators:
            raise ValueError(f"Emulator {emulator_id} not found")

        emulator = self._emulators[emulator_id]

        # Generate time array
        n_samples = int(duration * emulator.params.sampling_rate)
        times = np.linspace(0, duration, n_samples)

        # Generate signal based on type
        if signal_type == 'interference':
            signals = [emulator.generate_interference_signal(t) for t in times]
            # Extract specific field for time series
            values = [s['intensity'] for s in signals]
            phase_values = [s['phase'] for s in signals]

            return {
                'times': times.tolist(),
                'intensity': values,
                'phase': phase_values,
                'duration': duration,
                'n_samples': n_samples,
                'signal_type': signal_type
            }

        elif signal_type == 'thermal':
            signals = [emulator.generate_thermal_drift(t) for t in times]
            temps = [s['temperature'] for s in signals]
            drifts = [s['thermal_drift'] for s in signals]

            return {
                'times': times.tolist(),
                'temperature': temps,
                'thermal_drift': drifts,
                'duration': duration,
                'n_samples': n_samples,
                'signal_type': signal_type
            }

        elif signal_type == 'vibration':
            signals = [emulator.generate_vibration_signal(t) for t in times]
            displacements = [s['vibration_displacement'] for s in signals]

            return {
                'times': times.tolist(),
                'vibration_displacement': displacements,
                'duration': duration,
                'n_samples': n_samples,
                'signal_type': signal_type
            }

        else:
            raise ValueError(f"Unknown signal type: {signal_type}")

    # =========================================================================
    # Event Injection Methods
    # =========================================================================

    def inject_vibration_spike(
        self,
        emulator_id: str = 'default',
        magnitude: float = 10.0,
        duration: float = 0.1
    ) -> Dict[str, Any]:
        """
        Inject sudden vibration spike event.

        Args:
            emulator_id: Emulator identifier
            magnitude: Spike magnitude multiplier
            duration: Spike duration in seconds

        Returns:
            Dictionary with event details
        """
        if not EMULATOR_IMPORTS_AVAILABLE:
            raise RuntimeError("Emulator modules not available")

        if emulator_id not in self._emulators:
            raise ValueError(f"Emulator {emulator_id} not found")

        emulator = self._emulators[emulator_id]

        # Modify noise profile temporarily
        original_amplitude = emulator.noise.vibration_amplitude
        emulator.noise.vibration_amplitude *= magnitude

        return {
            'event_type': 'vibration_spike',
            'magnitude': magnitude,
            'duration': duration,
            'original_amplitude': original_amplitude * 1e9,  # nm
            'spike_amplitude': emulator.noise.vibration_amplitude * 1e9,  # nm
            'status': 'injected',
            'note': 'Vibration amplitude temporarily increased'
        }

    def inject_thermal_jump(
        self,
        emulator_id: str = 'default',
        delta_temp: float = 1.0
    ) -> Dict[str, Any]:
        """
        Inject sudden temperature change.

        Args:
            emulator_id: Emulator identifier
            delta_temp: Temperature change in Kelvin

        Returns:
            Dictionary with event details
        """
        if not EMULATOR_IMPORTS_AVAILABLE:
            raise RuntimeError("Emulator modules not available")

        if emulator_id not in self._emulators:
            raise ValueError(f"Emulator {emulator_id} not found")

        emulator = self._emulators[emulator_id]

        # Apply temperature jump
        old_temp = emulator.params.temperature
        emulator.params.temperature += delta_temp

        # Calculate expected thermal expansion effect
        alpha = 23e-6  # Thermal expansion coefficient
        length_change = alpha * emulator.params.baseline_length * delta_temp

        return {
            'event_type': 'thermal_jump',
            'delta_temp': delta_temp,
            'old_temperature': old_temp - 273.15,  # Celsius
            'new_temperature': emulator.params.temperature - 273.15,  # Celsius
            'expected_length_change': length_change * 1e9,  # nm
            'status': 'injected'
        }

    # =========================================================================
    # Configuration Methods
    # =========================================================================

    def update_parameters(
        self,
        emulator_id: str = 'default',
        baseline_length: Optional[float] = None,
        temperature: Optional[float] = None,
        sampling_rate: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Update emulator parameters dynamically.

        Args:
            emulator_id: Emulator identifier
            baseline_length: New baseline length in meters
            temperature: New temperature in Kelvin
            sampling_rate: New sampling rate in Hz

        Returns:
            Dictionary with updated parameters
        """
        if not EMULATOR_IMPORTS_AVAILABLE:
            raise RuntimeError("Emulator modules not available")

        if emulator_id not in self._emulators:
            raise ValueError(f"Emulator {emulator_id} not found")

        emulator = self._emulators[emulator_id]

        # Update parameters if provided
        if baseline_length is not None:
            emulator.params.baseline_length = baseline_length

        if temperature is not None:
            emulator.params.temperature = temperature

        if sampling_rate is not None:
            emulator.params.sampling_rate = sampling_rate

        return {
            'emulator_id': emulator_id,
            'status': 'updated',
            'parameters': {
                'baseline_length': emulator.params.baseline_length,
                'wavelength': emulator.params.wavelength * 1e9,  # nm
                'sampling_rate': emulator.params.sampling_rate,
                'temperature': emulator.params.temperature - 273.15  # Celsius
            }
        }

    def update_noise_profile(
        self,
        emulator_id: str = 'default',
        shot_noise_level: Optional[float] = None,
        vibration_amplitude: Optional[float] = None,
        phase_stability: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Update noise characteristics.

        Args:
            emulator_id: Emulator identifier
            shot_noise_level: Shot noise RMS level
            vibration_amplitude: Vibration amplitude in meters
            phase_stability: Phase stability in radians RMS

        Returns:
            Dictionary with updated noise profile
        """
        if not EMULATOR_IMPORTS_AVAILABLE:
            raise RuntimeError("Emulator modules not available")

        if emulator_id not in self._emulators:
            raise ValueError(f"Emulator {emulator_id} not found")

        emulator = self._emulators[emulator_id]

        # Update noise parameters if provided
        if shot_noise_level is not None:
            emulator.noise.shot_noise_level = shot_noise_level

        if vibration_amplitude is not None:
            emulator.noise.vibration_amplitude = vibration_amplitude

        if phase_stability is not None:
            emulator.noise.phase_stability = phase_stability

        return {
            'emulator_id': emulator_id,
            'status': 'updated',
            'noise_profile': {
                'shot_noise_level': emulator.noise.shot_noise_level,
                'thermal_noise_level': emulator.noise.thermal_noise_level,
                'vibration_amplitude': emulator.noise.vibration_amplitude * 1e9,  # nm
                'phase_stability': emulator.noise.phase_stability
            }
        }

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def list_emulators(self) -> Dict[str, List[str]]:
        """List all active emulator instances."""
        return {
            'emulator_ids': list(self._emulators.keys()),
            'count': len(self._emulators)
        }

    def reset_emulator(self, emulator_id: str = 'default') -> Dict[str, Any]:
        """
        Reset emulator to initial state.

        Args:
            emulator_id: Emulator identifier

        Returns:
            Dictionary with reset status
        """
        if not EMULATOR_IMPORTS_AVAILABLE:
            raise RuntimeError("Emulator modules not available")

        if emulator_id not in self._emulators:
            raise ValueError(f"Emulator {emulator_id} not found")

        emulator = self._emulators[emulator_id]

        # Reset state
        emulator.time_offset = 0.0
        emulator.fringe_count = 0
        emulator.thermal_drift_offset = 0.0
        emulator.start_time = None

        return {
            'emulator_id': emulator_id,
            'status': 'reset',
            'message': 'Emulator state reset to initial conditions'
        }


# Singleton instance
_emulator_service = None


def get_emulator_service() -> EmulatorService:
    """Get or create emulator service singleton."""
    global _emulator_service
    if _emulator_service is None:
        _emulator_service = EmulatorService()
    return _emulator_service
