"""
Rauch-Tung-Striebel (RTS) Smoother
===================================

Post-processing smoother for orbit determination.
Smooths backward from filtered estimates.
"""

import numpy as np
from typing import List
from dataclasses import dataclass
import warnings

from pod.estimators import OrbitEstimate


@dataclass
class SmoothedOrbitEstimate(OrbitEstimate):
    """
    Smoothed orbit estimate (extends OrbitEstimate).

    Adds smoothed uncertainties which should be lower than filtered.
    """
    smoothed_covariance: np.ndarray = None


class RTSSmoother:
    """
    Rauch-Tung-Striebel smoother for post-processing.

    Given forward-filtered estimates x̂[k|k] and P[k|k],
    compute smoothed estimates x̂[k|N] and P[k|N] where N is final time.

    Smoothing gain: C[k] = P[k|k] F^T P[k+1|k]^{-1}

    Smoothed state: x̂[k|N] = x̂[k|k] + C[k] (x̂[k+1|N] - x̂[k+1|k])

    Smoothed covariance: P[k|N] = P[k|k] + C[k] (P[k+1|N] - P[k+1|k]) C[k]^T
    """

    def __init__(self, dt: float = 1.0, process_noise: float = 0.01):
        """
        Args:
            dt: Time step (s)
            process_noise: Process noise std (m)
        """
        self.dt = dt
        self.process_noise = process_noise

    def smooth(
        self,
        filtered_estimates: List[OrbitEstimate],
    ) -> List[SmoothedOrbitEstimate]:
        """
        Apply RTS smoothing to forward-filtered estimates.

        Args:
            filtered_estimates: List of filtered estimates from forward pass

        Returns:
            List of smoothed estimates
        """
        n = len(filtered_estimates)
        if n < 2:
            warnings.warn("Need at least 2 estimates for smoothing")
            return [SmoothedOrbitEstimate(**est.__dict__) for est in filtered_estimates]

        # State dimension (position + velocity)
        n_state = 6

        # State transition matrix (constant velocity)
        F = self._get_state_transition_matrix(self.dt)

        # Process noise covariance
        Q = self._get_process_noise_covariance(self.dt, self.process_noise)

        # Initialize smoothed estimates with final filtered estimate
        smoothed = [None] * n
        smoothed[-1] = SmoothedOrbitEstimate(
            time=filtered_estimates[-1].time,
            position=filtered_estimates[-1].position,
            velocity=filtered_estimates[-1].velocity,
            covariance=filtered_estimates[-1].covariance,
            smoothed_covariance=filtered_estimates[-1].covariance,
        )

        # Backward pass
        for k in range(n - 2, -1, -1):
            # Current filtered estimate
            x_filt = np.hstack([
                filtered_estimates[k].position,
                filtered_estimates[k].velocity,
            ])
            P_filt = filtered_estimates[k].covariance

            # Predicted state at k+1
            x_pred = F @ x_filt
            P_pred = F @ P_filt @ F.T + Q

            # Previous smoothed estimate (at k+1)
            x_smooth_next = np.hstack([
                smoothed[k + 1].position,
                smoothed[k + 1].velocity,
            ])
            P_smooth_next = smoothed[k + 1].smoothed_covariance

            # Smoothing gain
            try:
                C = P_filt @ F.T @ np.linalg.inv(P_pred)
            except np.linalg.LinAlgError:
                warnings.warn(f"Singular prediction covariance at k={k}, skipping")
                C = np.zeros((n_state, n_state))

            # Smoothed state
            x_smooth = x_filt + C @ (x_smooth_next - x_pred)

            # Smoothed covariance
            P_smooth = P_filt + C @ (P_smooth_next - P_pred) @ C.T

            # Ensure symmetry and positive definiteness
            P_smooth = 0.5 * (P_smooth + P_smooth.T)
            P_smooth += 1e-10 * np.eye(n_state)  # Regularization

            # Store smoothed estimate
            smoothed[k] = SmoothedOrbitEstimate(
                time=filtered_estimates[k].time,
                position=x_smooth[:3],
                velocity=x_smooth[3:6],
                covariance=P_filt,  # Keep original filtered covariance
                smoothed_covariance=P_smooth,
            )

        return smoothed

    def _get_state_transition_matrix(self, dt: float) -> np.ndarray:
        """
        State transition matrix for constant velocity model.

        Args:
            dt: Time step (s)

        Returns:
            F matrix, shape (6, 6)
        """
        F = np.eye(6)
        F[:3, 3:6] = np.eye(3) * dt  # Position += velocity * dt
        return F

    def _get_process_noise_covariance(
        self,
        dt: float,
        sigma: float,
    ) -> np.ndarray:
        """
        Process noise covariance for constant velocity model.

        Uses continuous-time white noise acceleration model:
            Q = σ^2 * [[dt^3/3 * I, dt^2/2 * I],
                       [dt^2/2 * I, dt * I]]

        Args:
            dt: Time step (s)
            sigma: Process noise std (m/s^2)

        Returns:
            Q matrix, shape (6, 6)
        """
        q1 = sigma**2 * dt**3 / 3.0
        q2 = sigma**2 * dt**2 / 2.0
        q3 = sigma**2 * dt

        Q = np.array([
            [q1, 0, 0, q2, 0, 0],
            [0, q1, 0, 0, q2, 0],
            [0, 0, q1, 0, 0, q2],
            [q2, 0, 0, q3, 0, 0],
            [0, q2, 0, 0, q3, 0],
            [0, 0, q2, 0, 0, q3],
        ])

        return Q


# ============================================================================
# Convenience function
# ============================================================================

def smooth_orbit(
    filtered_estimates: List[OrbitEstimate],
    dt: float = 1.0,
    process_noise: float = 0.01,
) -> List[SmoothedOrbitEstimate]:
    """
    Apply RTS smoothing to filtered orbit estimates.

    Args:
        filtered_estimates: List of filtered estimates
        dt: Time step (s)
        process_noise: Process noise std (m/s^2)

    Returns:
        List of smoothed estimates with reduced uncertainty
    """
    smoother = RTSSmoother(dt=dt, process_noise=process_noise)
    return smoother.smooth(filtered_estimates)


def compute_smoothing_improvement(
    smoothed_estimates: List[SmoothedOrbitEstimate],
) -> dict:
    """
    Compute smoothing improvement metrics.

    Args:
        smoothed_estimates: List of smoothed estimates

    Returns:
        Dictionary with improvement statistics
    """
    position_improvement = []
    velocity_improvement = []

    for est in smoothed_estimates:
        # Position uncertainty reduction
        pos_filt = np.sqrt(np.trace(est.covariance[:3, :3]))
        pos_smooth = np.sqrt(np.trace(est.smoothed_covariance[:3, :3]))
        position_improvement.append(pos_filt / pos_smooth)

        # Velocity uncertainty reduction
        vel_filt = np.sqrt(np.trace(est.covariance[3:6, 3:6]))
        vel_smooth = np.sqrt(np.trace(est.smoothed_covariance[3:6, 3:6]))
        velocity_improvement.append(vel_filt / vel_smooth)

    return {
        'mean_position_improvement': np.mean(position_improvement),
        'mean_velocity_improvement': np.mean(velocity_improvement),
        'max_position_improvement': np.max(position_improvement),
        'max_velocity_improvement': np.max(velocity_improvement),
    }
