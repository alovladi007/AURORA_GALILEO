"""
Clock Discipline and Fusion
============================

Clock discipline using GPS Disciplined Oscillator (GPSDO) and
dual-clock fusion via Extended Kalman Filter (EKF).
"""

import numpy as np
from dataclasses import dataclass
from typing import Optional, Tuple
from gtime.clock import ClockModel


@dataclass
class GPSDOModel:
    """
    GPS Disciplined Oscillator (GPSDO) model.

    Disciplines a local oscillator using GPS time references.
    """

    # Local oscillator parameters
    local_clock: ClockModel
    tau_discipline: float = 100.0  # Discipline time constant (s)
    gps_noise: float = 1e-9  # GPS measurement noise (s)

    def __post_init__(self):
        """Initialize internal state."""
        self.phase_error = 0.0
        self.freq_correction = 0.0

    def discipline_step(
        self,
        local_phase: float,
        gps_phase: float,
        dt: float,
    ) -> Tuple[float, float]:
        """
        Single discipline step (PI controller).

        Args:
            local_phase: Local clock phase (s)
            gps_phase: GPS reference phase (s)
            dt: Time step (s)

        Returns:
            (corrected_phase, frequency_correction)
        """
        # Phase error
        error = gps_phase - local_phase

        # PI controller gains
        Kp = 1.0 / self.tau_discipline
        Ki = Kp / (10.0 * self.tau_discipline)

        # Proportional term (immediate correction)
        phase_correction = Kp * error

        # Integral term (frequency steering)
        self.freq_correction += Ki * error * dt

        # Apply correction
        corrected_phase = local_phase + phase_correction + self.freq_correction * dt

        return corrected_phase, self.freq_correction

    def simulate_disciplined_clock(
        self,
        t: np.ndarray,
        gps_availability: Optional[np.ndarray] = None,
        seed: Optional[int] = None,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Simulate disciplined clock over time.

        Args:
            t: Time vector (s), shape (n,)
            gps_availability: GPS availability mask (1=available, 0=not), shape (n,)
                            If None, assumes always available
            seed: Random seed

        Returns:
            (local_phase, disciplined_phase, gps_phase): All in seconds, shape (n,)
        """
        if seed is not None:
            np.random.seed(seed)

        n = len(t)
        dt = np.mean(np.diff(t))

        # Generate local clock and GPS reference
        local_phase = self.local_clock.generate_phase(t, seed=seed)
        gps_noise_samples = self.gps_noise * np.random.randn(n)
        gps_phase = t + gps_noise_samples  # Idealized GPS time + noise

        if gps_availability is None:
            gps_availability = np.ones(n)

        # Discipline
        disciplined_phase = np.zeros(n)
        disciplined_phase[0] = local_phase[0]

        for i in range(1, n):
            if gps_availability[i] > 0.5:
                # GPS available: discipline
                disciplined_phase[i], _ = self.discipline_step(
                    local_phase[i],
                    gps_phase[i],
                    dt,
                )
            else:
                # GPS not available: free-run
                disciplined_phase[i] = local_phase[i]

        return local_phase, disciplined_phase, gps_phase


@dataclass
class DualClockFusion:
    """
    Dual-clock fusion using Extended Kalman Filter.

    Fuses two clocks with different stability characteristics
    (e.g., hydrogen maser + rubidium oscillator).
    """

    # Process noise (clock drift)
    Q: np.ndarray = None  # Process noise covariance

    # Measurement noise
    R: np.ndarray = None  # Measurement noise covariance

    def __post_init__(self):
        """Initialize default noise if not provided."""
        if self.Q is None:
            # Default: [phase, freq, freq_drift] process noise
            self.Q = np.diag([1e-18, 1e-20, 1e-24])

        if self.R is None:
            # Default: dual clock measurement noise
            self.R = np.diag([1e-16, 1e-16])

        # State: [Δφ, Δf, Δḟ] (phase, frequency, frequency drift difference)
        self.x = np.zeros(3)

        # Covariance
        self.P = np.eye(3) * 1e-12

    def predict(self, dt: float):
        """
        EKF prediction step.

        State dynamics:
            Δφ[k+1] = Δφ[k] + Δf[k]*dt + 0.5*Δḟ[k]*dt^2
            Δf[k+1] = Δf[k] + Δḟ[k]*dt
            Δḟ[k+1] = Δḟ[k]

        Args:
            dt: Time step (s)
        """
        # State transition matrix
        F = np.array([
            [1.0, dt, 0.5 * dt**2],
            [0.0, 1.0, dt],
            [0.0, 0.0, 1.0],
        ])

        # Predict state
        self.x = F @ self.x

        # Predict covariance
        self.P = F @ self.P @ F.T + self.Q

    def update(self, z: np.ndarray):
        """
        EKF update step.

        Measurements: [φ1 - φ2, f1 - f2] from two clocks

        Args:
            z: Measurement vector [Δφ_meas, Δf_meas], shape (2,)
        """
        # Measurement matrix (observe phase and frequency difference)
        H = np.array([
            [1.0, 0.0, 0.0],  # Phase difference
            [0.0, 1.0, 0.0],  # Frequency difference
        ])

        # Innovation
        y = z - H @ self.x

        # Innovation covariance
        S = H @ self.P @ H.T + self.R

        # Kalman gain
        K = self.P @ H.T @ np.linalg.inv(S)

        # Update state
        self.x = self.x + K @ y

        # Update covariance
        I = np.eye(3)
        self.P = (I - K @ H) @ self.P

    def get_fused_correction(self, weights: np.ndarray = np.array([0.5, 0.5])) -> float:
        """
        Get fused clock correction.

        Args:
            weights: Weights for clock 1 and clock 2

        Returns:
            Fused phase correction (s)
        """
        # Weighted combination of clock difference
        return -weights[0] * self.x[0]

    def get_state(self) -> Tuple[float, float, float]:
        """
        Get current state estimate.

        Returns:
            (phase_diff, freq_diff, freq_drift_diff)
        """
        return self.x[0], self.x[1], self.x[2]

    def get_uncertainty(self) -> Tuple[float, float, float]:
        """
        Get state uncertainties (standard deviations).

        Returns:
            (σ_phase, σ_freq, σ_drift)
        """
        return np.sqrt(np.diag(self.P))


def clock_discipline_ekf(
    t: np.ndarray,
    phase1: np.ndarray,
    phase2: np.ndarray,
    Q: Optional[np.ndarray] = None,
    R: Optional[np.ndarray] = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Dual-clock fusion using EKF.

    Args:
        t: Time vector (s), shape (n,)
        phase1: Clock 1 phase samples (s), shape (n,)
        phase2: Clock 2 phase samples (s), shape (n,)
        Q: Process noise covariance (3x3), optional
        R: Measurement noise covariance (2x2), optional

    Returns:
        (fused_phase, uncertainties): Fused clock phase and 1σ uncertainties
    """
    n = len(t)
    dt = np.mean(np.diff(t))

    # Initialize EKF
    ekf = DualClockFusion(Q=Q, R=R)

    # Storage
    fused_phase = np.zeros(n)
    uncertainties = np.zeros(n)

    for i in range(n):
        # Predict
        if i > 0:
            ekf.predict(dt)

        # Measurement: phase and frequency difference
        phase_diff = phase1[i] - phase2[i]

        if i > 0:
            freq_diff = (phase_diff - (phase1[i-1] - phase2[i-1])) / dt
        else:
            freq_diff = 0.0

        z = np.array([phase_diff, freq_diff])

        # Update
        ekf.update(z)

        # Fused estimate (weighted average)
        weights = np.array([0.5, 0.5])  # Equal weighting
        correction = ekf.get_fused_correction(weights)
        fused_phase[i] = weights[0] * phase1[i] + weights[1] * phase2[i] + correction

        # Uncertainty
        sigma_phase, _, _ = ekf.get_uncertainty()
        uncertainties[i] = sigma_phase

    return fused_phase, uncertainties


# ============================================================================
# Utility functions
# ============================================================================

def optimal_clock_weights(
    sigma1: np.ndarray,
    sigma2: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Compute optimal weights for dual-clock fusion (minimum variance).

    For two clocks with Allan deviations σ1(τ) and σ2(τ), the optimal
    weights that minimize the fused Allan deviation are:

        w1 = σ2^2 / (σ1^2 + σ2^2)
        w2 = σ1^2 / (σ1^2 + σ2^2)

    Args:
        sigma1: Allan deviation of clock 1, shape (n,)
        sigma2: Allan deviation of clock 2, shape (n,)

    Returns:
        (w1, w2): Optimal weights, shape (n,)
    """
    sigma1_sq = sigma1**2
    sigma2_sq = sigma2**2

    w1 = sigma2_sq / (sigma1_sq + sigma2_sq + 1e-30)
    w2 = sigma1_sq / (sigma1_sq + sigma2_sq + 1e-30)

    return w1, w2


def fused_allan_deviation(
    sigma1: np.ndarray,
    sigma2: np.ndarray,
    w1: Optional[np.ndarray] = None,
    w2: Optional[np.ndarray] = None,
) -> np.ndarray:
    """
    Compute Allan deviation of fused clock.

    If weights are optimal, the fused Allan deviation is:
        σ_fused^2 = σ1^2 * σ2^2 / (σ1^2 + σ2^2)

    Args:
        sigma1: Allan deviation of clock 1
        sigma2: Allan deviation of clock 2
        w1, w2: Weights (if None, assumes optimal)

    Returns:
        Fused Allan deviation
    """
    if w1 is None or w2 is None:
        w1, w2 = optimal_clock_weights(sigma1, sigma2)

    sigma1_sq = sigma1**2
    sigma2_sq = sigma2**2

    sigma_fused_sq = w1**2 * sigma1_sq + w2**2 * sigma2_sq

    return np.sqrt(sigma_fused_sq)


def analyze_disciplined_performance(
    t: np.ndarray,
    undisciplined_phase: np.ndarray,
    disciplined_phase: np.ndarray,
    dt: float,
) -> dict:
    """
    Analyze performance improvement from clock discipline.

    Args:
        t: Time vector (s)
        undisciplined_phase: Free-running clock phase (s)
        disciplined_phase: Disciplined clock phase (s)
        dt: Sampling interval (s)

    Returns:
        Dictionary with performance metrics
    """
    from gtime.clock import allan_deviation

    # Allan deviations
    tau_undis, sigma_undis = allan_deviation(undisciplined_phase, dt)
    tau_dis, sigma_dis = allan_deviation(disciplined_phase, dt)

    # RMS phase error
    rms_undis = np.sqrt(np.mean(undisciplined_phase**2))
    rms_dis = np.sqrt(np.mean(disciplined_phase**2))

    # Improvement factor
    improvement = sigma_undis / (sigma_dis + 1e-20)

    return {
        'tau': tau_dis,
        'sigma_undisciplined': sigma_undis,
        'sigma_disciplined': sigma_dis,
        'improvement_factor': improvement,
        'rms_undisciplined': rms_undis,
        'rms_disciplined': rms_dis,
        'rms_improvement': rms_undis / (rms_dis + 1e-20),
    }
