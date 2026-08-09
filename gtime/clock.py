"""
Clock Models and Stability Analysis
====================================

Clock noise models and stability metrics (Allan deviation, Hadamard variance).

Clock noise types:
- White phase noise (quantization, thermal)
- Flicker phase noise
- White frequency noise
- Flicker frequency noise (1/f)
- Random walk frequency noise (drift)
"""

import numpy as np
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Tuple
import json


@dataclass
class ClockModel(ABC):
    """Base class for clock models."""

    @abstractmethod
    def generate_phase(self, t: np.ndarray, seed: Optional[int] = None) -> np.ndarray:
        """
        Generate clock phase realization.

        Args:
            t: Time samples (s), shape (n,)
            seed: Random seed for reproducibility

        Returns:
            Phase (s), shape (n,)
        """
        pass

    @abstractmethod
    def power_spectral_density(self, f: np.ndarray) -> np.ndarray:
        """
        Power spectral density of phase fluctuations.

        Args:
            f: Frequency (Hz), shape (m,)

        Returns:
            PSD (s^2/Hz), shape (m,)
        """
        pass


class WhiteNoiseClock(ClockModel):
    """
    White FREQUENCY noise clock (e.g. passive atomic standards).

    The generated time-error is a random walk in phase: x = integral of
    white fractional-frequency noise y with one-sided PSD S_y(f) = h0.

    PSD: S_y(f) = h0 (flat, 1/Hz)
    Allan deviation: sigma_y(tau) = sqrt(h0 / (2 tau))
    """

    def __init__(self, h0: float):
        """
        Args:
            h0: White frequency noise level, one-sided PSD (1/Hz)
        """
        self.h0 = h0

    def generate_phase(self, t: np.ndarray, seed: Optional[int] = None) -> np.ndarray:
        if seed is not None:
            np.random.seed(seed)

        dt = np.diff(t)
        dt_mean = np.mean(dt)
        fs = 1.0 / dt_mean

        # Per-sample fractional-frequency deviations for one-sided PSD
        # h0: var(y) = h0 * fs / 2. Time error x = cumsum(y) * dt.
        y = np.sqrt(self.h0 * fs / 2.0) * np.random.randn(len(t))
        phase = np.cumsum(y) * dt_mean

        return phase

    def power_spectral_density(self, f: np.ndarray) -> np.ndarray:
        """One-sided fractional-frequency PSD S_y(f)."""
        return self.h0 * np.ones_like(f)

    def allan_deviation(self, tau: np.ndarray) -> np.ndarray:
        """Theoretical Allan deviation (white FM)."""
        return np.sqrt(self.h0 / (2.0 * tau))


class FlickerNoiseClock(ClockModel):
    """
    Flicker FREQUENCY noise clock (the "flicker floor" of oscillators).

    The fractional frequency y has a 1/f PSD; the generated time error
    is its integral.

    PSD: S_y(f) = h_{-1} / f
    Allan deviation: sigma_y(tau) ~ sqrt(2 ln(2) h_{-1}) (constant)
    """

    def __init__(self, h_minus1: float, f_low: float = 1e-4, f_high: float = 1e2):
        """
        Args:
            h_minus1: Flicker frequency noise level (dimensionless)
            f_low: Low-frequency cutoff (Hz)
            f_high: High-frequency cutoff (Hz)
        """
        self.h_minus1 = h_minus1
        self.f_low = f_low
        self.f_high = f_high

    def generate_phase(self, t: np.ndarray, seed: Optional[int] = None) -> np.ndarray:
        """Generate the time error of a flicker-FM clock: synthesize a
        1/f fractional-frequency series spectrally, then integrate."""
        if seed is not None:
            np.random.seed(seed)

        n = len(t)
        dt = t[1] - t[0]
        fs = 1.0 / dt

        # Frequency bins
        freqs = np.fft.rfftfreq(n, dt)
        freqs[0] = self.f_low  # Avoid division by zero

        # Fractional-frequency PSD: S_y = h-1 / f
        psd = self.h_minus1 / np.abs(freqs)
        psd[freqs < self.f_low] = 0
        psd[freqs > self.f_high] = 0

        # Generate complex Gaussian with that PSD
        amplitude = np.sqrt(psd * fs / 2)
        y_fft = amplitude * (np.random.randn(len(freqs)) + 1j * np.random.randn(len(freqs)))
        y_fft[0] = 0  # Zero DC

        y = np.fft.irfft(y_fft, n)

        # Time error is the integral of fractional frequency
        phase = np.cumsum(y) * dt

        return phase

    def power_spectral_density(self, f: np.ndarray) -> np.ndarray:
        """One-sided fractional-frequency PSD S_y(f)."""
        psd = self.h_minus1 / np.abs(f)
        psd[f < self.f_low] = 0
        psd[f > self.f_high] = 0
        return psd

    def allan_deviation(self, tau: np.ndarray) -> np.ndarray:
        """Theoretical Allan deviation (approximately constant)."""
        return np.sqrt(2.0 * np.log(2) * self.h_minus1) * np.ones_like(tau)


class RandomWalkClock(ClockModel):
    """
    Random walk frequency noise (frequency drift).

    PSD: S_φ(f) = h_{-2} / f^2
    Allan deviation: σ(τ) = sqrt(h_{-2} * τ / 2)
    """

    def __init__(self, h_minus2: float):
        """
        Args:
            h_minus2: Random walk frequency noise level (s)
        """
        self.h_minus2 = h_minus2

    def generate_phase(self, t: np.ndarray, seed: Optional[int] = None) -> np.ndarray:
        if seed is not None:
            np.random.seed(seed)

        dt = np.diff(t)
        dt_mean = np.mean(dt)

        # Random walk: integrate frequency random walk twice
        freq_walk = np.sqrt(self.h_minus2 / dt_mean) * np.random.randn(len(t))
        freq = np.cumsum(freq_walk) * dt_mean
        phase = np.cumsum(freq) * dt_mean

        return phase

    def power_spectral_density(self, f: np.ndarray) -> np.ndarray:
        # Avoid division by zero
        f_safe = np.where(f == 0, 1e-10, f)
        return self.h_minus2 / f_safe**2

    def allan_deviation(self, tau: np.ndarray) -> np.ndarray:
        """Theoretical Allan deviation."""
        return np.sqrt(self.h_minus2 * tau / 2.0)


class CompositeClock(ClockModel):
    """
    Composite clock model (sum of multiple noise types).
    """

    def __init__(self, models: list[ClockModel], weights: Optional[list[float]] = None):
        """
        Args:
            models: List of clock models
            weights: Optional weights for each model (default: all 1.0)
        """
        self.models = models
        self.weights = weights if weights is not None else [1.0] * len(models)

    def generate_phase(self, t: np.ndarray, seed: Optional[int] = None) -> np.ndarray:
        phase_total = np.zeros(len(t))

        for i, model in enumerate(self.models):
            phase_i = model.generate_phase(t, seed=seed + i if seed is not None else None)
            phase_total += self.weights[i] * phase_i

        return phase_total

    def power_spectral_density(self, f: np.ndarray) -> np.ndarray:
        psd_total = np.zeros_like(f)

        for i, model in enumerate(self.models):
            psd_total += self.weights[i]**2 * model.power_spectral_density(f)

        return psd_total


# ============================================================================
# Stability Metrics
# ============================================================================

def allan_deviation(
    phase: np.ndarray,
    dt: float,
    tau_values: Optional[np.ndarray] = None,
    overlapping: bool = False,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Compute Allan deviation (standard or overlapping).

    The Allan deviation at averaging time τ is:
        σ_y(τ) = sqrt(< (y_{k+1} - y_k)^2 > / 2)

    where y_k is the fractional frequency averaged over interval k.

    Args:
        phase: Phase samples (s), shape (n,)
        dt: Sampling interval (s)
        tau_values: Averaging times to compute (s), shape (m,).
                   If None, uses [dt, 2*dt, 4*dt, ..., n*dt/4]
        overlapping: If True, use overlapping Allan deviation (better statistics)

    Returns:
        (tau, sigma): Averaging times and Allan deviations
    """
    n = len(phase)

    if tau_values is None:
        # Default: logarithmic spacing from dt to n*dt/4
        tau_values = dt * np.unique(np.logspace(0, np.log10(n // 4), 20).astype(int))

    sigma = np.zeros(len(tau_values))

    for i, tau in enumerate(tau_values):
        m = int(tau / dt)  # Number of samples per averaging interval

        if m < 1 or m > n // 2:
            sigma[i] = np.nan
            continue

        # Compute fractional frequencies
        # y_k = (φ[k+m] - φ[k]) / (m * dt)
        if overlapping:
            # Overlapping: average frequencies over every possible
            # interval, then difference frequencies m samples apart
            # (adjacent-sample differences bias the estimate and
            # produce a spurious tau^-1 slope for every noise type).
            y = (phase[m:] - phase[:-m]) / (m * dt)
            if len(y) <= m:
                sigma[i] = np.nan
                continue
            diff_y = y[m:] - y[:-m]
        else:
            # Non-overlapping: disjoint intervals
            num_intervals = n // m - 1
            y = np.zeros(num_intervals + 1)
            for k in range(num_intervals + 1):
                idx_start = k * m
                idx_end = (k + 1) * m
                if idx_end < n:
                    y[k] = (phase[idx_end] - phase[idx_start]) / (m * dt)

            diff_y = y[1:num_intervals+1] - y[:num_intervals]

        # Allan variance
        sigma[i] = np.sqrt(np.mean(diff_y**2) / 2.0)

    return tau_values, sigma


def overlapping_allan_deviation(
    phase: np.ndarray,
    dt: float,
    tau_values: Optional[np.ndarray] = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """Overlapping Allan deviation (better statistical confidence)."""
    return allan_deviation(phase, dt, tau_values, overlapping=True)


def modified_allan_deviation(
    phase: np.ndarray,
    dt: float,
    tau_values: Optional[np.ndarray] = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Modified Allan deviation (better for white phase noise).

    Uses averaging within each interval before differencing.

    Args:
        phase: Phase samples (s), shape (n,)
        dt: Sampling interval (s)
        tau_values: Averaging times (s)

    Returns:
        (tau, mod_sigma)
    """
    n = len(phase)

    if tau_values is None:
        tau_values = dt * np.unique(np.logspace(0, np.log10(n // 4), 20).astype(int))

    sigma = np.zeros(len(tau_values))

    for i, tau in enumerate(tau_values):
        m = int(tau / dt)

        if m < 1 or m > n // 3:
            sigma[i] = np.nan
            continue

        # Average phase over intervals of length τ
        num_avg = n // m
        phase_avg = np.zeros(num_avg)

        for k in range(num_avg):
            phase_avg[k] = np.mean(phase[k*m:(k+1)*m])

        # Fractional frequency from averaged phase
        y = (phase_avg[1:] - phase_avg[:-1]) / tau

        # Second difference
        if len(y) < 2:
            sigma[i] = np.nan
            continue

        diff2_y = y[1:] - y[:-1]

        # Modified Allan variance
        sigma[i] = np.sqrt(np.mean(diff2_y**2) / 2.0)

    return tau_values, sigma


def hadamard_variance(
    phase: np.ndarray,
    dt: float,
    tau_values: Optional[np.ndarray] = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Hadamard variance (three-sample variance, rejects linear frequency drift).

    σ_H^2(τ) = < (x_{k+2} - 2*x_{k+1} + x_k)^2 > / 6

    where x_k is the phase averaged over interval k.

    Args:
        phase: Phase samples (s), shape (n,)
        dt: Sampling interval (s)
        tau_values: Averaging times (s)

    Returns:
        (tau, sigma_H)
    """
    n = len(phase)

    if tau_values is None:
        tau_values = dt * np.unique(np.logspace(0, np.log10(n // 6), 20).astype(int))

    sigma = np.zeros(len(tau_values))

    for i, tau in enumerate(tau_values):
        m = int(tau / dt)

        if m < 1 or m > n // 3:
            sigma[i] = np.nan
            continue

        # Average phase over intervals
        num_intervals = n // m
        if num_intervals < 3:
            sigma[i] = np.nan
            continue

        x = np.zeros(num_intervals)
        for k in range(num_intervals):
            x[k] = np.mean(phase[k*m:(k+1)*m])

        # Three-sample differences
        diff3 = x[2:] - 2.0 * x[1:-1] + x[:-2]

        # Hadamard variance
        sigma[i] = np.sqrt(np.mean(diff3**2) / 6.0)

    return tau_values, sigma


def time_deviation(
    phase: np.ndarray,
    dt: float,
    tau_values: Optional[np.ndarray] = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Time deviation (related to Allan deviation by integration).

    σ_x(τ) = τ * σ_y(τ)

    Represents RMS time error over averaging interval τ.

    Args:
        phase: Phase samples (s), shape (n,)
        dt: Sampling interval (s)
        tau_values: Averaging times (s)

    Returns:
        (tau, sigma_x): Time deviation (s)
    """
    tau, sigma_y = allan_deviation(phase, dt, tau_values)
    sigma_x = tau * sigma_y

    return tau, sigma_x


# ============================================================================
# Utility functions
# ============================================================================

def estimate_noise_coefficients(
    phase: np.ndarray,
    dt: float,
    plot: bool = False,
) -> dict:
    """
    Estimate noise coefficients h0, h_-1, h_-2 from Allan deviation.

    Fits power-law regions:
    - White phase: σ ~ τ^(-1/2)  →  h0
    - Flicker phase: σ ~ τ^0     →  h_{-1}
    - Random walk: σ ~ τ^(1/2)   →  h_{-2}

    Args:
        phase: Phase samples (s)
        dt: Sampling interval (s)
        plot: If True, plot Allan deviation with fitted regions

    Returns:
        Dictionary with 'h0', 'h_minus1', 'h_minus2'
    """
    tau, sigma = allan_deviation(phase, dt)

    # Filter out NaN values
    mask = ~np.isnan(sigma)
    tau = tau[mask]
    sigma = sigma[mask]

    if len(tau) < 3:
        return {'h0': np.nan, 'h_minus1': np.nan, 'h_minus2': np.nan}

    # Log-log slopes
    log_tau = np.log10(tau)
    log_sigma = np.log10(sigma)

    # Find regions with different slopes
    # White phase: slope ≈ -0.5
    # Flicker: slope ≈ 0
    # Random walk: slope ≈ 0.5

    # Simple estimation: fit entire range and pick closest power law
    from scipy.stats import linregress

    slope, intercept, _, _, _ = linregress(log_tau, log_sigma)

    # Determine dominant noise type
    if slope < -0.25:
        # White phase noise dominant
        h0 = 2.0 * np.median(sigma**2 * tau)
        h_minus1 = np.nan
        h_minus2 = np.nan
    elif slope < 0.25:
        # Flicker phase noise dominant
        h0 = np.nan
        h_minus1 = np.median(sigma**2 / (2.0 * np.log(2)))
        h_minus2 = np.nan
    else:
        # Random walk frequency noise dominant
        h0 = np.nan
        h_minus1 = np.nan
        h_minus2 = 2.0 * np.median(sigma**2 / tau)

    result = {'h0': h0, 'h_minus1': h_minus1, 'h_minus2': h_minus2, 'slope': slope}

    if plot:
        try:
            import matplotlib.pyplot as plt
            plt.figure(figsize=(8, 6))
            plt.loglog(tau, sigma, 'o-', label='Measured')
            plt.xlabel('Averaging time τ (s)')
            plt.ylabel('Allan deviation σ(τ)')
            plt.title(f'Allan Deviation (slope={slope:.2f})')
            plt.grid(True, alpha=0.3)
            plt.legend()
            plt.tight_layout()
            plt.show()
        except ImportError:
            pass

    return result


def save_stability_analysis(
    filename: str,
    tau: np.ndarray,
    sigma_allan: np.ndarray,
    sigma_hadamard: Optional[np.ndarray] = None,
    metadata: Optional[dict] = None,
):
    """
    Save stability analysis results to JSON.

    Args:
        filename: Output JSON file
        tau: Averaging times (s)
        sigma_allan: Allan deviation
        sigma_hadamard: Hadamard variance (optional)
        metadata: Additional metadata
    """
    data = {
        'tau': tau.tolist(),
        'sigma_allan': sigma_allan.tolist(),
    }

    if sigma_hadamard is not None:
        data['sigma_hadamard'] = sigma_hadamard.tolist()

    if metadata is not None:
        data['metadata'] = metadata

    with open(filename, 'w') as f:
        json.dump(data, f, indent=2)


def load_stability_analysis(filename: str) -> dict:
    """Load stability analysis results from JSON."""
    with open(filename, 'r') as f:
        data = json.load(f)

    data['tau'] = np.array(data['tau'])
    data['sigma_allan'] = np.array(data['sigma_allan'])

    if 'sigma_hadamard' in data:
        data['sigma_hadamard'] = np.array(data['sigma_hadamard'])

    return data
