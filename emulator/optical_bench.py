"""
Optical Bench Emulator - Short-Baseline Interferometer
Generates synthetic signals mimicking real optical bench behavior
"""

import numpy as np
import time
from dataclasses import dataclass
from typing import Dict, List, Optional
from enum import Enum


class SignalType(Enum):
    """Types of synthetic signals available"""
    INTERFERENCE = "interference"
    PHASE_NOISE = "phase_noise"
    THERMAL_DRIFT = "thermal_drift"
    VIBRATION = "vibration"
    LASER_INTENSITY = "laser_intensity"
    FRINGE_PATTERN = "fringe_pattern"


@dataclass
class BenchParameters:
    """Physical parameters of the optical bench"""
    baseline_length: float = 1.0  # meters
    wavelength: float = 632.8e-9  # He-Ne laser (632.8 nm)
    sampling_rate: float = 1000.0  # Hz
    temperature: float = 293.15  # Kelvin (20°C)
    pressure: float = 101325.0  # Pascal
    humidity: float = 0.45  # relative humidity


@dataclass
class NoiseProfile:
    """Noise characteristics for realistic simulation"""
    shot_noise_level: float = 0.01
    thermal_noise_level: float = 0.005
    vibration_amplitude: float = 1e-9  # meters
    vibration_frequency: float = 50.0  # Hz
    phase_stability: float = 0.1  # radians RMS
    intensity_fluctuation: float = 0.02  # relative


class OpticalBenchEmulator:
    """
    Emulates a short-baseline optical interferometer with realistic signal characteristics
    """
    
    def __init__(self, params: Optional[BenchParameters] = None, 
                 noise: Optional[NoiseProfile] = None):
        self.params = params or BenchParameters()
        self.noise = noise or NoiseProfile()
        
        self.time_offset = 0.0
        self.fringe_count = 0
        self.thermal_drift_offset = 0.0
        self._env_cache_t = None
        self._env_cache = None
        self._last_visibility = 0.95
        
        # State tracking
        self.running = False
        self.start_time = None
        
    def get_timestamp(self) -> float:
        """Get current simulation timestamp"""
        if self.start_time is None:
            self.start_time = time.time()
        return time.time() - self.start_time + self.time_offset
    
    def _environment(self, t: float) -> Dict[str, Dict[str, float]]:
        """Compute (and cache per-timestamp) the environmental channels
        so every consumer sees ONE consistent physical state and the
        thermal random walk advances exactly once per timestamp."""
        if self._env_cache_t == t and self._env_cache is not None:
            return self._env_cache
        env = {
            "thermal": self.generate_thermal_drift(t),
            "vibration": self.generate_vibration_signal(t),
            "laser": self.generate_laser_intensity(t),
        }
        self._env_cache_t = t
        self._env_cache = env
        return env

    def generate_interference_signal(self, t: float) -> Dict[str, float]:
        """
        Generate the interference signal with PHYSICAL coupling: the
        optical path difference is the sum of the piezo scan, thermal
        expansion/drift, and vibration displacement; the intensity
        envelope follows the laser power; visibility degrades with
        vibration jitter. An injected vibration or thermal event
        therefore shows up in the fringes, not just in its own channel.

        Args:
            t: Time in seconds

        Returns:
            Dictionary with signal components
        """
        env = self._environment(t)
        k = 2 * np.pi / self.params.wavelength

        # Piezo scan: a few wavelengths at 0.5 Hz - resolvable at the
        # 1 kHz sampling rate (the old +/-1 m sweep was ~3e6 fringes/s,
        # pure aliasing noise).
        opd_scan = 2.0 * self.params.wavelength * np.sin(2 * np.pi * 0.5 * t)

        # Thermal contribution: expansion + slow random-walk drift (m)
        opd_thermal = (env["thermal"]["thermal_expansion"] * 1e-9
                       + env["thermal"]["thermal_drift"] * 1e-9)

        # Vibration displacement enters the path directly (m)
        opd_vibration = env["vibration"]["vibration_displacement"] * 1e-9

        optical_path_diff = opd_scan + opd_thermal + opd_vibration

        # Phase from optical path difference plus laser phase noise
        phase_noise = np.random.normal(0, self.noise.phase_stability)
        total_phase = k * optical_path_diff + phase_noise

        # Visibility degrades with unresolved vibration jitter:
        # V = V0 exp(-(k sigma_vib)^2 / 2)
        sigma_vib = 0.1 * self.noise.vibration_amplitude
        visibility = 0.95 * float(np.exp(-0.5 * (k * sigma_vib) ** 2))
        self._last_visibility = visibility

        # Interference intensity, scaled by the laser power envelope
        laser_level = env["laser"]["intensity"]
        intensity = 0.5 * laser_level * (1 + visibility * np.cos(total_phase))

        # Add shot noise
        intensity += np.random.normal(0, self.noise.shot_noise_level)
        intensity = np.clip(intensity, 0, 1.5)

        return {
            "intensity": float(intensity),
            "phase": float(total_phase % (2 * np.pi)),
            "optical_path_diff": float(optical_path_diff * 1e9),  # nm
            "visibility": float(visibility)
        }
    
    def generate_thermal_drift(self, t: float) -> Dict[str, float]:
        """Generate thermal drift effects"""
        # Slow thermal drift with random walk
        drift_rate = 1e-10  # m/s
        self.thermal_drift_offset += np.random.normal(0, drift_rate / self.params.sampling_rate)
        
        # Temperature variation
        temp_variation = 0.01 * np.sin(2 * np.pi * t / 300)  # 5-minute cycle
        current_temp = self.params.temperature + temp_variation
        
        # Thermal expansion coefficient (typical for aluminum)
        alpha = 23e-6  # 1/K
        thermal_length_change = (alpha * self.params.baseline_length * 
                                temp_variation * 1e9)  # nm
        
        return {
            "temperature": float(current_temp),
            "thermal_drift": float(self.thermal_drift_offset * 1e9),  # nm
            "thermal_expansion": float(thermal_length_change)
        }
    
    def generate_vibration_signal(self, t: float) -> Dict[str, float]:
        """Generate environmental vibration"""
        # Multiple vibration modes
        v1 = self.noise.vibration_amplitude * np.sin(2 * np.pi * 50 * t)  # 50 Hz mains
        v2 = 0.5 * self.noise.vibration_amplitude * np.sin(2 * np.pi * 120 * t)  # Pump
        v3 = 0.3 * self.noise.vibration_amplitude * np.sin(2 * np.pi * 17 * t)  # Building
        
        total_vibration = v1 + v2 + v3
        
        # Random vibration component
        random_vib = np.random.normal(0, 0.1 * self.noise.vibration_amplitude)
        
        return {
            "vibration_displacement": float((total_vibration + random_vib) * 1e9),  # nm
            "rms_vibration": float(np.sqrt(np.mean((total_vibration)**2)) * 1e9)
        }
    
    def generate_laser_intensity(self, t: float) -> Dict[str, float]:
        """Generate laser source intensity with fluctuations"""
        # Base intensity with slow drift
        base_intensity = 1.0 + 0.05 * np.sin(2 * np.pi * t / 600)  # 10-minute cycle
        
        # Mode hopping (occasional jumps)
        if np.random.random() < 0.001:  # Rare events
            base_intensity *= 0.98
        
        # High-frequency noise
        noise = np.random.normal(0, self.noise.intensity_fluctuation)
        intensity = base_intensity * (1 + noise)
        intensity = max(0.5, min(1.5, intensity))  # Clamp
        
        # Beam quality metric (M²)
        beam_quality = 1.05 + 0.02 * np.random.randn()
        
        return {
            "intensity": float(intensity),
            "intensity_stability": float(self.noise.intensity_fluctuation),
            "beam_quality_m2": float(beam_quality),
            "power_mw": float(intensity * 5.0)  # Assume 5mW nominal
        }
    
    def generate_fringe_pattern(self, t: float) -> Dict[str, List[float]]:
        """Generate 2D fringe pattern data"""
        # Simulate a line scan across fringes
        num_points = 50
        positions = np.linspace(-np.pi, np.pi, num_points)
        
        # Fringe pattern with phase from time
        phase_offset = 2 * np.pi * 0.5 * t  # Scanning
        visibility = 0.9
        
        pattern = []
        for pos in positions:
            intensity = 0.5 * (1 + visibility * np.cos(pos + phase_offset))
            intensity += np.random.normal(0, 0.02)
            pattern.append(float(np.clip(intensity, 0, 1)))
        
        return {
            "pattern": pattern,
            "positions": positions.tolist(),
            "visibility": float(visibility),
            "fringe_spacing": float(self.params.wavelength / 2 * 1e6)  # μm
        }
    
    def get_full_state(self, t: Optional[float] = None) -> Dict:
        """Get complete emulator state at given time"""
        if t is None:
            t = self.get_timestamp()
        
        # Compute the shared environment once; interference couples to
        # it and the per-channel telemetry reports the SAME values.
        interference = self.generate_interference_signal(t)
        env = self._environment(t)
        return {
            "timestamp": float(t),
            "interference": interference,
            "thermal": env["thermal"],
            "vibration": env["vibration"],
            "laser": env["laser"],
            "fringes": self.generate_fringe_pattern(t),
            "parameters": {
                "baseline_m": self.params.baseline_length,
                "wavelength_nm": self.params.wavelength * 1e9,
                "temperature_k": self.params.temperature,
                "sampling_rate_hz": self.params.sampling_rate
            }
        }
    
    def inject_event(self, event_type: str, magnitude: float = 1.0):
        """
        Inject synthetic events for demonstration
        
        Args:
            event_type: Type of event (vibration_spike, thermal_jump, laser_dropout)
            magnitude: Event magnitude multiplier
        """
        if event_type == "vibration_spike":
            self.noise.vibration_amplitude *= magnitude
        elif event_type == "thermal_jump":
            self.params.temperature += magnitude
        elif event_type == "laser_dropout":
            self.noise.intensity_fluctuation *= magnitude
        elif event_type == "phase_step":
            self.time_offset += magnitude / 1000.0
    
    def reset(self):
        """Reset emulator to initial state"""
        self.time_offset = 0.0
        self.fringe_count = 0
        self.thermal_drift_offset = 0.0
        self._env_cache_t = None
        self._env_cache = None
        self._last_visibility = 0.95
        self.start_time = None
        self.params = BenchParameters()
        self.noise = NoiseProfile()
    
    def get_diagnostics(self) -> Dict:
        """Get system diagnostics and health metrics"""
        t = self.get_timestamp()
        
        # Calculate running statistics
        stability_score = 1.0 - (self.noise.phase_stability / 0.5)  # 0-1 scale
        alignment_quality = 0.95 - abs(np.sin(t * 0.1)) * 0.1  # Drift simulation
        
        return {
            "uptime_seconds": float(t),
            "stability_score": float(max(0, min(1, stability_score))),
            "alignment_quality": float(alignment_quality),
            "thermal_stable": abs(self.params.temperature - 293.15) < 0.5,
            "laser_locked": self.noise.intensity_fluctuation < 0.05,
            "fringe_contrast": float(self._last_visibility),
            "data_quality": "good" if stability_score > 0.7 else "marginal"
        }


if __name__ == "__main__":
    # Quick test
    emulator = OpticalBenchEmulator()
    print("Optical Bench Emulator - Test Run")
    print("=" * 50)
    
    for i in range(5):
        state = emulator.get_full_state()
        print(f"\nTimestamp: {state['timestamp']:.3f}s")
        print(f"Interference Intensity: {state['interference']['intensity']:.4f}")
        print(f"Phase: {state['interference']['phase']:.3f} rad")
        print(f"Temperature: {state['thermal']['temperature']:.2f} K")
        print(f"Laser Power: {state['laser']['power_mw']:.3f} mW")
        time.sleep(0.1)
    
    print("\n" + "=" * 50)
    print("Diagnostics:")
    diag = emulator.get_diagnostics()
    for key, value in diag.items():
        print(f"  {key}: {value}")
