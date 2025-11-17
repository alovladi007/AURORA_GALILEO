"""
Optical Bench Emulator
======================

Software emulation of optical bench for inter-satellite laser ranging.
"""

import numpy as np
from dataclasses import dataclass
from typing import Optional, Tuple
import time


@dataclass
class LaserParameters:
    """Laser parameters for emulation."""
    wavelength: float = 1064e-9  # m (Nd:YAG)
    power: float = 1.0  # W
    frequency_noise: float = 1e3  # Hz/√Hz
    intensity_noise: float = 1e-7  # RIN (relative intensity noise)
    beam_divergence: float = 10e-6  # rad


@dataclass
class OpticalPath:
    """Optical path configuration."""
    baseline: float = 200000.0  # m (200 km)
    pointing_jitter: float = 1e-6  # rad RMS
    path_length_noise: float = 1e-12  # m/√Hz
    mirror_reflectivity: float = 0.99


class OpticalBenchEmulator:
    """
    Software emulator for optical bench.

    Simulates:
    - Laser phase measurements
    - Heterodyne detection
    - Pointing jitter
    - Frequency/intensity noise
    """

    def __init__(
        self,
        laser_params: Optional[LaserParameters] = None,
        optical_path: Optional[OpticalPath] = None,
        sampling_rate: float = 10.0,  # Hz
        seed: Optional[int] = None,
    ):
        """
        Args:
            laser_params: Laser parameters
            optical_path: Optical path configuration
            sampling_rate: Sampling rate (Hz)
            seed: Random seed
        """
        self.laser = laser_params or LaserParameters()
        self.path = optical_path or OpticalPath()
        self.sampling_rate = sampling_rate
        self.dt = 1.0 / sampling_rate

        if seed is not None:
            np.random.seed(seed)

        # Internal state
        self.time = 0.0
        self.phase_accumulated = 0.0

    def measure_phase(
        self,
        true_range: float,
        velocity: float = 0.0,
    ) -> Tuple[float, dict]:
        """
        Measure optical phase with realistic noise.

        Args:
            true_range: True inter-satellite range (m)
            velocity: Range rate (m/s)

        Returns:
            (measured_phase, diagnostics)
            measured_phase: Phase measurement (cycles)
            diagnostics: Dict with noise contributions
        """
        # Nominal phase (cycles)
        phase_nominal = true_range / self.laser.wavelength

        # Frequency noise (integrated to phase noise)
        freq_noise_psd = self.laser.frequency_noise  # Hz/√Hz
        phase_noise_std = freq_noise_psd * np.sqrt(1.0 / (2 * self.sampling_rate))
        phase_noise = np.random.randn() * phase_noise_std

        # Path length noise (m)
        path_noise_psd = self.path.path_length_noise  # m/√Hz
        path_noise_std = path_noise_psd * np.sqrt(1.0 / (2 * self.sampling_rate))
        path_noise = np.random.randn() * path_noise_std

        # Convert to phase (cycles)
        path_phase_noise = path_noise / self.laser.wavelength

        # Pointing jitter (causes amplitude modulation → phase coupling)
        pointing_jitter = np.random.randn() * self.path.pointing_jitter
        pointing_phase_error = (self.path.baseline / self.laser.wavelength *
                               pointing_jitter**2 / 2)  # Second-order effect

        # Shot noise (from photon statistics)
        # SNR ≈ √(N_photons) where N_photons ∝ power * time
        photon_rate = (self.laser.power * self.laser.wavelength /
                      (2 * np.pi * 2.998e8 * 1.055e-34))  # photons/s
        n_photons = photon_rate * self.dt
        shot_noise_phase = 1.0 / np.sqrt(n_photons) if n_photons > 0 else 1e-3

        shot_noise = np.random.randn() * shot_noise_phase

        # Total measured phase
        measured_phase = (phase_nominal +
                         phase_noise +
                         path_phase_noise +
                         pointing_phase_error +
                         shot_noise)

        # Accumulate phase for cycle continuity
        self.phase_accumulated += measured_phase - int(measured_phase)
        measured_phase = int(measured_phase) + self.phase_accumulated

        # Diagnostics
        diagnostics = {
            'phase_nominal': phase_nominal,
            'freq_noise': phase_noise,
            'path_noise': path_phase_noise,
            'pointing_error': pointing_phase_error,
            'shot_noise': shot_noise,
            'total_noise_rms': np.sqrt(phase_noise**2 + path_phase_noise**2 +
                                       pointing_phase_error**2 + shot_noise**2),
        }

        self.time += self.dt

        return measured_phase, diagnostics

    def measure_intensity(self) -> float:
        """
        Measure laser intensity with noise.

        Returns:
            Relative intensity (1.0 = nominal)
        """
        # Relative intensity noise (RIN)
        intensity_noise = np.random.randn() * self.laser.intensity_noise

        intensity = 1.0 + intensity_noise

        return intensity

    def heterodyne_beat(
        self,
        signal_freq: float,
        lo_freq: float,
        duration: float,
    ) -> np.ndarray:
        """
        Simulate heterodyne beat note.

        Args:
            signal_freq: Signal frequency (Hz)
            lo_freq: Local oscillator frequency (Hz)
            duration: Measurement duration (s)

        Returns:
            Beat note signal, shape (n_samples,)
        """
        n_samples = int(duration * self.sampling_rate)
        t = np.arange(n_samples) / self.sampling_rate

        # Beat frequency
        f_beat = np.abs(signal_freq - lo_freq)

        # Ideal beat signal
        beat = np.cos(2 * np.pi * f_beat * t)

        # Add phase noise
        phase_noise_psd = self.laser.frequency_noise
        phase_noise = np.cumsum(np.random.randn(n_samples)) * phase_noise_psd / np.sqrt(self.sampling_rate)

        beat_noisy = np.cos(2 * np.pi * f_beat * t + phase_noise)

        return beat_noisy

    def pll_tracking(
        self,
        beat_signal: np.ndarray,
        center_freq: float,
        bandwidth: float = 1.0,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Phase-Locked Loop (PLL) tracking of beat signal.

        Args:
            beat_signal: Input beat signal
            center_freq: Nominal beat frequency (Hz)
            bandwidth: PLL bandwidth (Hz)

        Returns:
            (phase, frequency)
            phase: Tracked phase (rad), shape (n,)
            frequency: Tracked frequency (Hz), shape (n,)
        """
        n = len(beat_signal)

        # PLL state
        phase = np.zeros(n)
        freq = np.zeros(n)
        vco_phase = 0.0
        vco_freq = center_freq

        # Loop filter parameters (PI controller)
        Kp = 2 * bandwidth  # Proportional gain
        Ki = bandwidth**2   # Integral gain

        integrator = 0.0

        for i in range(n):
            # Phase detector (multiply and low-pass)
            vco_signal = np.cos(vco_phase)
            phase_error = beat_signal[i] * vco_signal

            # Loop filter (PI)
            integrator += phase_error * self.dt
            correction = Kp * phase_error + Ki * integrator

            # VCO
            vco_freq = center_freq + correction
            vco_phase += 2 * np.pi * vco_freq * self.dt

            # Output
            phase[i] = vco_phase
            freq[i] = vco_freq

        return phase, freq

    def simulate_measurement_sequence(
        self,
        range_function: callable,
        duration: float,
    ) -> dict:
        """
        Simulate a measurement sequence over time.

        Args:
            range_function: Function returning range vs time: r(t)
            duration: Simulation duration (s)

        Returns:
            Dictionary with time series data
        """
        n_samples = int(duration * self.sampling_rate)
        times = np.arange(n_samples) * self.dt

        phases = np.zeros(n_samples)
        ranges = np.zeros(n_samples)
        noise_levels = np.zeros(n_samples)

        for i, t in enumerate(times):
            true_range = range_function(t)
            measured_phase, diag = self.measure_phase(true_range)

            phases[i] = measured_phase
            ranges[i] = true_range
            noise_levels[i] = diag['total_noise_rms']

        return {
            'times': times,
            'phases': phases,
            'true_ranges': ranges,
            'noise_levels': noise_levels,
        }


def simulate_orbital_ranging(
    baseline: float = 200e3,
    eccentricity: float = 0.01,
    period: float = 3600.0,
    duration: float = 100.0,
    sampling_rate: float = 10.0,
) -> dict:
    """
    Simulate optical ranging for satellites in formation.

    Args:
        baseline: Mean baseline (m)
        eccentricity: Orbit eccentricity
        period: Orbital period (s)
        duration: Simulation duration (s)
        sampling_rate: Sampling rate (Hz)

    Returns:
        Simulation results
    """
    # Range function: sinusoidal variation
    omega = 2 * np.pi / period

    def range_function(t):
        return baseline * (1 + eccentricity * np.cos(omega * t))

    # Create emulator
    path = OpticalPath(baseline=baseline)
    emulator = OpticalBenchEmulator(
        optical_path=path,
        sampling_rate=sampling_rate,
    )

    # Simulate
    results = emulator.simulate_measurement_sequence(range_function, duration)

    # Add range estimates from phase
    wavelength = emulator.laser.wavelength
    results['range_estimates'] = results['phases'] * wavelength

    # Range error
    results['range_errors'] = results['range_estimates'] - results['true_ranges']

    # Allan deviation of range
    from time.clock import allan_deviation
    dt = 1.0 / sampling_rate
    tau, sigma = allan_deviation(results['range_errors'], dt)
    results['allan_tau'] = tau
    results['allan_sigma'] = sigma

    return results
