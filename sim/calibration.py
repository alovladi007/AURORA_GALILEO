"""
Calibration and Noise Characterization Tools

This module provides tools for analyzing measurement noise and system stability:
- Allan deviation (overlapping and non-overlapping)
- Cross-spectral density estimation
- Power spectral density analysis
- Noise type identification (white, flicker, random walk, etc.)
"""

import numpy as np
from scipy import signal
from scipy.fft import fft, fftfreq
from typing import Tuple, Optional, Dict
import warnings


class AllanDeviation:
    """
    Compute Allan deviation for time series data.
    
    Allan deviation is used to characterize the stability and noise characteristics
    of sensors, oscillators, and measurement systems.
    """
    
    def __init__(self, data: np.ndarray, rate: float, overlapping: bool = True):
        """
        Initialize Allan deviation calculator.
        
        Parameters
        ----------
        data : np.ndarray
            Time series data (1D array)
        rate : float
            Sampling rate (Hz)
        overlapping : bool
            Use overlapping Allan deviation (more data efficient)
        """
        self.data = np.asarray(data).flatten()
        self.rate = rate
        self.dt = 1.0 / rate
        self.overlapping = overlapping
        
        if len(self.data) < 3:
            raise ValueError("Need at least 3 data points")
    
    def compute(self, taus: Optional[np.ndarray] = None) -> Tuple[np.ndarray, np.ndarray]:
        """
        Compute Allan deviation.
        
        Parameters
        ----------
        taus : np.ndarray, optional
            Averaging times to evaluate. If None, uses decade points.
        
        Returns
        -------
        taus : np.ndarray
            Averaging times
        adev : np.ndarray
            Allan deviation at each tau
        """
        if taus is None:
            taus = self._generate_taus()
        else:
            taus = np.asarray(taus)
        
        if self.overlapping:
            adev = self._overlapping_adev(taus)
        else:
            adev = self._nonoverlapping_adev(taus)
        
        return taus, adev
    
    def _generate_taus(self) -> np.ndarray:
        """Generate logarithmically-spaced averaging times."""
        n = len(self.data)
        max_m = n // 3  # Maximum averaging factor
        
        # Generate taus from 1*dt to max_m*dt
        m_values = np.unique(np.logspace(0, np.log10(max_m), 50).astype(int))
        taus = m_values * self.dt
        
        return taus
    
    def _overlapping_adev(self, taus: np.ndarray) -> np.ndarray:
        """Compute overlapping Allan deviation."""
        adev = np.zeros_like(taus)
        n = len(self.data)
        
        for i, tau in enumerate(taus):
            m = max(1, int(np.round(tau / self.dt)))
            
            if m >= n - 1:
                adev[i] = np.nan
                continue
            
            # Overlapping differences
            max_j = n - 2 * m
            if max_j < 1:
                adev[i] = np.nan
                continue
            
            # Compute two-sample differences
            diffs = np.zeros(max_j)
            for j in range(max_j):
                avg1 = np.mean(self.data[j:j+m])
                avg2 = np.mean(self.data[j+m:j+2*m])
                diffs[j] = avg2 - avg1
            
            # Allan variance
            avar = np.mean(diffs**2) / 2.0
            adev[i] = np.sqrt(avar)
        
        return adev
    
    def _nonoverlapping_adev(self, taus: np.ndarray) -> np.ndarray:
        """Compute non-overlapping Allan deviation."""
        adev = np.zeros_like(taus)
        n = len(self.data)
        
        for i, tau in enumerate(taus):
            m = max(1, int(np.round(tau / self.dt)))
            
            # Number of complete non-overlapping pairs
            num_pairs = n // (2 * m)
            
            if num_pairs < 1:
                adev[i] = np.nan
                continue
            
            diffs = np.zeros(num_pairs)
            for j in range(num_pairs):
                idx1 = 2 * j * m
                idx2 = (2 * j + 1) * m
                idx3 = (2 * j + 2) * m
                
                avg1 = np.mean(self.data[idx1:idx2])
                avg2 = np.mean(self.data[idx2:idx3])
                diffs[j] = avg2 - avg1
            
            # Allan variance
            avar = np.mean(diffs**2) / 2.0
            adev[i] = np.sqrt(avar)
        
        return adev
    
    def identify_noise_type(self, taus: np.ndarray, adev: np.ndarray) -> Dict[str, float]:
        """
        Identify dominant noise type from Allan deviation slope.
        
        Parameters
        ----------
        taus : np.ndarray
            Averaging times
        adev : np.ndarray
            Allan deviation values
        
        Returns
        -------
        dict
            Noise type identification with slopes
        """
        # Remove NaN values
        mask = np.isfinite(adev) & (adev > 0)
        taus_clean = taus[mask]
        adev_clean = adev[mask]
        
        if len(taus_clean) < 3:
            return {"type": "insufficient_data", "slope": np.nan}
        
        # Fit in log-log space
        log_tau = np.log10(taus_clean)
        log_adev = np.log10(adev_clean)
        
        coeffs = np.polyfit(log_tau, log_adev, 1)
        slope = coeffs[0]
        
        # Identify noise type based on slope
        # Standard Allan-deviation log-log slopes (IEEE 1139):
        #   -1.0: white/flicker PHASE modulation (tau^-1)
        #   -0.5: white FREQUENCY modulation (tau^-1/2)
        #    0.0: flicker frequency modulation (flicker floor)
        #   +0.5: random-walk frequency modulation
        #   +1.0: frequency drift
        noise_types = {
            -1.0: "white/flicker phase modulation",
            -0.5: "white frequency modulation",
            0.0: "flicker frequency modulation (flicker floor)",
            0.5: "random walk frequency modulation",
            1.0: "frequency drift",
        }
        
        # Find closest match
        closest_slope = min(noise_types.keys(), key=lambda x: abs(x - slope))
        identified_type = noise_types[closest_slope]
        
        return {
            "type": identified_type,
            "slope": slope,
            "expected_slope": closest_slope
        }


class CrossSpectralDensity:
    """
    Cross-spectral density and coherence analysis.
    
    Used for analyzing relationships between measurement channels,
    identifying common-mode noise, and validating filter performance.
    """
    
    def __init__(self, nperseg: Optional[int] = None, window: str = 'hann',
                 detrend: str = 'constant', scaling: str = 'density'):
        """
        Initialize cross-spectral density estimator.
        
        Parameters
        ----------
        nperseg : int, optional
            Length of each segment for Welch's method
        window : str
            Window function to use
        detrend : str
            Detrending method ('constant', 'linear', or False)
        scaling : str
            'density' for power spectral density or 'spectrum' for power spectrum
        """
        self.nperseg = nperseg
        self.window = window
        self.detrend = detrend
        self.scaling = scaling
    
    def compute_psd(self, x: np.ndarray, fs: float) -> Tuple[np.ndarray, np.ndarray]:
        """
        Compute power spectral density using Welch's method.
        
        Parameters
        ----------
        x : np.ndarray
            Time series data
        fs : float
            Sampling frequency
        
        Returns
        -------
        freqs : np.ndarray
            Frequency array
        psd : np.ndarray
            Power spectral density
        """
        nperseg = self.nperseg or min(256, len(x))
        
        freqs, psd = signal.welch(
            x, fs=fs,
            window=self.window,
            nperseg=nperseg,
            detrend=self.detrend,
            scaling=self.scaling
        )
        
        return freqs, psd
    
    def compute_csd(self, x: np.ndarray, y: np.ndarray, fs: float) -> \
            Tuple[np.ndarray, np.ndarray]:
        """
        Compute cross-spectral density between two signals.
        
        Parameters
        ----------
        x, y : np.ndarray
            Time series data
        fs : float
            Sampling frequency
        
        Returns
        -------
        freqs : np.ndarray
            Frequency array
        csd : np.ndarray
            Cross-spectral density (complex)
        """
        nperseg = self.nperseg or min(256, len(x))
        
        freqs, csd = signal.csd(
            x, y, fs=fs,
            window=self.window,
            nperseg=nperseg,
            detrend=self.detrend,
            scaling=self.scaling
        )
        
        return freqs, csd
    
    def compute_coherence(self, x: np.ndarray, y: np.ndarray, fs: float) -> \
            Tuple[np.ndarray, np.ndarray]:
        """
        Compute magnitude-squared coherence between two signals.
        
        Coherence ranges from 0 (uncorrelated) to 1 (perfectly correlated).
        
        Parameters
        ----------
        x, y : np.ndarray
            Time series data
        fs : float
            Sampling frequency
        
        Returns
        -------
        freqs : np.ndarray
            Frequency array
        coherence : np.ndarray
            Magnitude-squared coherence
        """
        nperseg = self.nperseg or min(256, len(x))
        
        freqs, coherence = signal.coherence(
            x, y, fs=fs,
            window=self.window,
            nperseg=nperseg,
            detrend=self.detrend
        )
        
        return freqs, coherence
    
    def compute_transfer_function(self, x: np.ndarray, y: np.ndarray, fs: float) -> \
            Tuple[np.ndarray, np.ndarray]:
        """
        Compute transfer function H(f) = Pyx(f) / Pxx(f).
        
        Parameters
        ----------
        x : np.ndarray
            Input signal
        y : np.ndarray
            Output signal
        fs : float
            Sampling frequency
        
        Returns
        -------
        freqs : np.ndarray
            Frequency array
        H : np.ndarray
            Transfer function (complex)
        """
        freqs, Pxx = self.compute_psd(x, fs)
        freqs, Pyx = self.compute_csd(y, x, fs)
        
        # Avoid division by zero
        Pxx_safe = np.where(Pxx > 1e-20, Pxx, 1e-20)
        H = Pyx / Pxx_safe
        
        return freqs, H


class WhitenessTest:
    """
    Statistical tests for whiteness of residuals.
    
    Tests whether residuals are consistent with white noise,
    which is a key assumption in optimal filtering.
    """
    
    @staticmethod
    def ljung_box_test(residuals: np.ndarray, lags: int = 20, 
                       dof: int = 0) -> Dict[str, float]:
        """
        Ljung-Box test for autocorrelation in residuals.
        
        Tests the null hypothesis that residuals are white noise.
        
        Parameters
        ----------
        residuals : np.ndarray
            Residual time series
        lags : int
            Number of lags to test
        dof : int
            Degrees of freedom (number of fitted parameters)
        
        Returns
        -------
        dict
            Test statistics and p-value
        """
        from scipy import stats
        
        n = len(residuals)
        residuals = residuals - np.mean(residuals)
        
        # Compute autocorrelations
        acf = np.correlate(residuals, residuals, mode='full')
        acf = acf[len(acf)//2:] / acf[len(acf)//2]
        
        # Ljung-Box statistic
        Q = 0
        for k in range(1, min(lags + 1, len(acf))):
            Q += acf[k]**2 / (n - k)
        
        Q *= n * (n + 2)
        
        # Chi-squared test
        df = max(1, lags - dof)
        p_value = 1 - stats.chi2.cdf(Q, df)
        
        return {
            'statistic': Q,
            'p_value': p_value,
            'lags': lags,
            'white': p_value > 0.05  # 95% confidence
        }
    
    @staticmethod
    def runs_test(residuals: np.ndarray) -> Dict[str, float]:
        """
        Runs test for randomness.
        
        Tests whether positive/negative runs are consistent with randomness.
        
        Parameters
        ----------
        residuals : np.ndarray
            Residual time series
        
        Returns
        -------
        dict
            Test statistics and p-value
        """
        from scipy import stats
        
        # Demean
        residuals = residuals - np.median(residuals)
        
        # Count runs
        signs = np.sign(residuals)
        runs = np.sum(signs[1:] != signs[:-1]) + 1
        
        # Expected runs for random sequence
        n_pos = np.sum(signs > 0)
        n_neg = np.sum(signs < 0)
        n = len(residuals)
        
        if n_pos == 0 or n_neg == 0:
            return {'statistic': np.nan, 'p_value': 0.0, 'white': False}
        
        expected_runs = 2 * n_pos * n_neg / n + 1
        var_runs = 2 * n_pos * n_neg * (2 * n_pos * n_neg - n) / (n**2 * (n - 1))
        
        # Z-statistic
        z = (runs - expected_runs) / np.sqrt(var_runs)
        p_value = 2 * (1 - stats.norm.cdf(abs(z)))
        
        return {
            'statistic': z,
            'p_value': p_value,
            'runs': runs,
            'expected': expected_runs,
            'white': p_value > 0.05
        }
    
    @staticmethod
    def durbin_watson(residuals: np.ndarray) -> float:
        """
        Durbin-Watson statistic for first-order autocorrelation.
        
        DW ≈ 2(1 - ρ), where ρ is first-order autocorrelation.
        Values near 2 indicate no autocorrelation.
        
        Parameters
        ----------
        residuals : np.ndarray
            Residual time series
        
        Returns
        -------
        float
            Durbin-Watson statistic (0 to 4)
        """
        diff_residuals = np.diff(residuals)
        dw = np.sum(diff_residuals**2) / np.sum(residuals**2)
        
        return dw
    
    @classmethod
    def comprehensive_test(cls, residuals: np.ndarray) -> Dict[str, any]:
        """
        Run comprehensive whiteness tests.
        
        Parameters
        ----------
        residuals : np.ndarray
            Residual time series
        
        Returns
        -------
        dict
            All test results
        """
        results = {
            'ljung_box': cls.ljung_box_test(residuals),
            'runs': cls.runs_test(residuals),
            'durbin_watson': cls.durbin_watson(residuals)
        }
        
        # Overall assessment
        all_white = (
            results['ljung_box']['white'] and
            results['runs']['white'] and
            1.5 < results['durbin_watson'] < 2.5
        )
        
        results['overall_white'] = all_white
        
        return results


def plot_allan_deviation(taus: np.ndarray, adev: np.ndarray, 
                         title: str = "Allan Deviation",
                         ax = None):
    """
    Plot Allan deviation with noise type references.
    
    Parameters
    ----------
    taus : np.ndarray
        Averaging times
    adev : np.ndarray
        Allan deviation values
    title : str
        Plot title
    ax : matplotlib axis, optional
        Axis to plot on
    """
    import matplotlib.pyplot as plt
    
    if ax is None:
        fig, ax = plt.subplots(figsize=(10, 6))
    
    # Plot data
    mask = np.isfinite(adev) & (adev > 0)
    ax.loglog(taus[mask], adev[mask], 'bo-', linewidth=2, label='Measured')
    
    # Reference slopes
    tau_ref = np.array([taus[mask].min(), taus[mask].max()])
    adev_ref = adev[mask][len(adev[mask])//2]
    
    # White noise: τ^(-1/2)
    ax.loglog(tau_ref, adev_ref * (tau_ref / taus[mask][len(taus[mask])//2])**(-0.5),
              'k--', alpha=0.5, label='White noise (slope -1/2)')
    
    # Random walk: τ^(+1/2)
    ax.loglog(tau_ref, adev_ref * (tau_ref / taus[mask][len(taus[mask])//2])**(0.5),
              'r--', alpha=0.5, label='Random walk (slope +1/2)')
    
    ax.set_xlabel('Averaging Time τ (s)', fontsize=12)
    ax.set_ylabel('Allan Deviation', fontsize=12)
    ax.set_title(title, fontsize=14)
    ax.grid(True, alpha=0.3)
    ax.legend()
    
    return ax


if __name__ == "__main__":
    # Example usage
    np.random.seed(42)
    
    # Simulate white noise + random walk
    n = 10000
    rate = 100.0  # Hz
    t = np.arange(n) / rate
    
    white_noise = np.random.randn(n) * 0.1
    random_walk = np.cumsum(np.random.randn(n) * 0.01)
    data = white_noise + random_walk
    
    print("=" * 60)
    print("ALLAN DEVIATION EXAMPLE")
    print("=" * 60)
    
    # Allan deviation
    adev_calc = AllanDeviation(data, rate, overlapping=True)
    taus, adev = adev_calc.compute()
    
    noise_id = adev_calc.identify_noise_type(taus, adev)
    print(f"\nNoise type: {noise_id['type']}")
    print(f"Slope: {noise_id['slope']:.3f} (expected: {noise_id['expected_slope']:.1f})")
    
    # Whiteness test on white noise component
    print("\n" + "=" * 60)
    print("WHITENESS TESTS")
    print("=" * 60)
    
    white_results = WhitenessTest.comprehensive_test(white_noise)
    print(f"\nLjung-Box p-value: {white_results['ljung_box']['p_value']:.4f}")
    print(f"Runs test p-value: {white_results['runs']['p_value']:.4f}")
    print(f"Durbin-Watson: {white_results['durbin_watson']:.4f}")
    print(f"Overall white: {white_results['overall_white']}")
    
    # Cross-spectral density
    print("\n" + "=" * 60)
    print("CROSS-SPECTRAL DENSITY")
    print("=" * 60)
    
    csd_calc = CrossSpectralDensity(nperseg=256)
    freqs, psd = csd_calc.compute_psd(data, rate)
    print(f"\nFrequency range: {freqs[1]:.2e} to {freqs[-1]:.2e} Hz")
    print(f"PSD computed with {len(freqs)} frequency bins")
    
    # Coherence between two channels (simulate)
    data2 = data + np.random.randn(n) * 0.05  # Correlated signal
    freqs, coherence = csd_calc.compute_coherence(data, data2, rate)
    print(f"Mean coherence: {np.mean(coherence):.3f}")
    
    print("\n✓ Calibration tools tested successfully")
