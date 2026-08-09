"""
Orbit Estimation Algorithms
============================

Batch least-squares and sequential square-root information filter.
"""

import numpy as np
from dataclasses import dataclass
from typing import List, Tuple, Optional, Callable
from scipy.linalg import cholesky, solve_triangular, qr
import warnings

from pod.measurements import GNSSMeasurement, pseudorange_residual, gnss_measurement_jacobian


@dataclass
class OrbitEstimate:
    """
    Orbit estimation result.

    Attributes:
        time: Estimation time (s)
        position: ECEF position (m), shape (3,)
        velocity: ECEF velocity (m/s), shape (3,)
        covariance: State covariance, shape (6, 6) or (n, n)
        residuals: Measurement residuals (m), shape (m,)
        num_iterations: Number of iterations (batch LS)
        converged: Whether estimation converged
    """
    time: float
    position: np.ndarray
    velocity: np.ndarray
    covariance: np.ndarray
    residuals: Optional[np.ndarray] = None
    num_iterations: int = 0
    converged: bool = True


class BatchLeastSquares:
    """
    Batch least-squares orbit estimator.

    Iteratively solves the normal equations:
        (H^T W H) δx = H^T W r

    where H is the Jacobian, W is the weight matrix, r is the residual vector.
    """

    def __init__(
        self,
        max_iterations: int = 10,
        convergence_tol: float = 1e-4,
        outlier_threshold: float = 3.0,
    ):
        """
        Args:
            max_iterations: Maximum number of iterations
            convergence_tol: Convergence tolerance on state change (m)
            outlier_threshold: Outlier rejection threshold (sigmas)
        """
        self.max_iterations = max_iterations
        self.convergence_tol = convergence_tol
        self.outlier_threshold = outlier_threshold

    def estimate(
        self,
        measurements: List[GNSSMeasurement],
        initial_state: np.ndarray,
        measurement_noise: float = 1.0,
    ) -> OrbitEstimate:
        """
        Estimate orbit from batch of measurements.

        Args:
            measurements: List of GNSS measurements
            initial_state: Initial state [x, y, z, clock_bias], shape (4,)
            measurement_noise: Measurement noise std (m)

        Returns:
            OrbitEstimate with position, clock bias, and covariance
        """
        if len(measurements) < 4:
            raise ValueError("Need at least 4 measurements for position + clock")

        # State: [x, y, z, clock_bias]
        x = np.array(initial_state, dtype=float)
        n_state = len(x)

        # Measurement weight matrix
        W = np.eye(len(measurements)) / measurement_noise**2

        converged = False
        iteration = 0

        for iteration in range(self.max_iterations):
            # Compute residuals and Jacobian
            residuals = []
            H_list = []

            for meas in measurements:
                # Residual
                receiver_pos = x[:3]
                clock_bias = x[3]

                r = pseudorange_residual(
                    receiver_pos,
                    clock_bias,
                    meas,
                    use_dual_freq=True,
                )
                residuals.append(r)

                # Jacobian
                if meas.sat_position is None:
                    raise ValueError("Satellite position required")

                H_pos = gnss_measurement_jacobian(receiver_pos, meas.sat_position)
                H_clock = np.array([[1.0]])  # ∂ρ/∂clock_bias = 1

                H_row = np.hstack([H_pos, H_clock])
                H_list.append(H_row)

            residuals = np.array(residuals)
            H = np.vstack(H_list)  # shape (m, 4)

            # Outlier rejection
            if iteration > 0:
                residual_std = np.std(residuals)
                outlier_mask = np.abs(residuals) > self.outlier_threshold * residual_std

                if np.any(outlier_mask):
                    warnings.warn(f"Rejecting {np.sum(outlier_mask)} outliers")
                    # Zero out outlier weights
                    W_diag = np.diag(W).copy()
                    W_diag[outlier_mask] = 0
                    W = np.diag(W_diag)

            # Weighted normal equations
            # (H^T W H) δx = H^T W r
            N = H.T @ W @ H  # Normal matrix
            b = H.T @ W @ residuals

            try:
                # Solve for state update
                delta_x = np.linalg.solve(N, b)
            except np.linalg.LinAlgError:
                warnings.warn("Normal matrix singular, stopping")
                break

            # Update state
            x = x + delta_x

            # Check convergence
            if np.linalg.norm(delta_x) < self.convergence_tol:
                converged = True
                break

        # Covariance from normal matrix. N = H^T W H with W = I/sigma^2
        # already carries the measurement variance, so inv(N) IS the
        # covariance; multiplying by sigma^2 again double-counted it.
        try:
            P = np.linalg.inv(N)
        except np.linalg.LinAlgError:
            warnings.warn("Cannot invert normal matrix, using large covariance")
            P = np.eye(n_state) * 1e6

        # Extract position and clock bias
        position = x[:3]
        clock_bias = x[3]

        # Velocity not estimated in batch LS (would need dynamics model)
        velocity = np.zeros(3)

        # Extended covariance (include velocity = 0)
        P_extended = np.zeros((6, 6))
        P_extended[:3, :3] = P[:3, :3]
        P_extended[3, 3] = P[3, 3]  # Clock bias variance

        return OrbitEstimate(
            time=measurements[0].time,
            position=position,
            velocity=velocity,
            covariance=P_extended,
            residuals=residuals,
            num_iterations=iteration + 1,
            converged=converged,
        )


class SquareRootInformationFilter:
    """
    Square-Root Information Filter (SRIF) for sequential orbit estimation.

    More numerically stable than standard Kalman filter.
    Propagates information matrix R where R^T R = P^{-1}.
    """

    def __init__(self, process_noise: float = 0.01):
        """
        Args:
            process_noise: Process noise std (m)
        """
        self.process_noise = process_noise

        # State: [x, y, z, vx, vy, vz, clock_bias, clock_drift]
        self.n_state = 8

        # Information matrix square root: R^T R = P^{-1}
        self.R = np.eye(self.n_state) * 1e-3  # Large uncertainty initially
        self.z = np.zeros(self.n_state)  # Information state: z = R^T R x

        # State estimate
        self.x = np.zeros(self.n_state)

    def predict(self, dt: float):
        """
        Prediction step using simple dynamics.

        State dynamics:
            x[k+1] = F x[k] + w[k]

        where F is the state transition matrix.

        Args:
            dt: Time step (s)
        """
        # State transition matrix (constant velocity model)
        F = np.eye(self.n_state)
        F[:3, 3:6] = np.eye(3) * dt  # Position += velocity * dt

        # Process noise covariance
        Q = np.diag([
            self.process_noise**2,  # x
            self.process_noise**2,  # y
            self.process_noise**2,  # z
            (self.process_noise / 10)**2,  # vx
            (self.process_noise / 10)**2,  # vy
            (self.process_noise / 10)**2,  # vz
            1e-10,  # clock_bias (very small, assume stable)
            1e-12,  # clock_drift
        ])

        # SRIF prediction (more complex, using QR factorization)
        # Simplified: P_pred = F P F^T + Q
        P = np.linalg.inv(self.R.T @ self.R + 1e-10 * np.eye(self.n_state))
        P_pred = F @ P @ F.T + Q

        # Update information matrix
        try:
            P_pred_inv = np.linalg.inv(P_pred)
            self.R = cholesky(P_pred_inv, lower=False)  # Upper triangular
        except np.linalg.LinAlgError:
            warnings.warn("SRIF prediction failed, using identity")
            self.R = np.eye(self.n_state) * 1e-3

        # Predict state
        self.x = F @ self.x

        # Update information state
        self.z = self.R.T @ self.R @ self.x

    def update(self, measurement: GNSSMeasurement, measurement_noise: float = 1.0):
        """
        Update step with new measurement.

        Args:
            measurement: GNSS measurement
            measurement_noise: Measurement noise std (m)
        """
        if measurement.sat_position is None:
            warnings.warn("Skipping measurement without satellite position")
            return

        # Measurement Jacobian
        receiver_pos = self.x[:3]
        H_pos = gnss_measurement_jacobian(receiver_pos, measurement.sat_position)
        H = np.zeros((1, self.n_state))
        H[0, :3] = H_pos
        H[0, 6] = 1.0  # Clock bias

        # Measurement residual
        clock_bias = self.x[6]
        r = pseudorange_residual(receiver_pos, clock_bias, measurement)

        # Measurement information
        R_meas = 1.0 / measurement_noise  # Scalar for single measurement

        # SRIF update using QR factorization
        # Stack [R; R_meas * H] and [z; R_meas * (y - h(x) + H*x)]
        # where y is the measurement, h(x) is the predicted measurement

        # Predicted measurement
        h_x = np.linalg.norm(measurement.sat_position - receiver_pos) + clock_bias

        # Innovation
        innovation = measurement.pseudorange_L1 - h_x

        # Augmented system
        A_aug = np.vstack([
            np.hstack([self.R, self.z.reshape(-1, 1)]),
            np.hstack([R_meas * H, (R_meas * innovation).reshape(-1, 1)]),
        ])

        # QR factorization
        Q_qr, R_aug = qr(A_aug, mode='economic')

        # Extract updated information matrix and state
        self.R = R_aug[:-1, :-1]
        z_new = R_aug[:-1, -1]

        # Solve for updated state: R^T R x = z
        try:
            self.x = solve_triangular(
                self.R,
                solve_triangular(self.R.T, z_new, lower=True),
                lower=False,
            )
        except np.linalg.LinAlgError:
            warnings.warn("SRIF update failed")

        self.z = z_new

    def get_estimate(self, time: float) -> OrbitEstimate:
        """
        Get current state estimate.

        Args:
            time: Current time (s)

        Returns:
            OrbitEstimate
        """
        # Covariance: P = (R^T R)^{-1}
        try:
            P = np.linalg.inv(self.R.T @ self.R + 1e-10 * np.eye(self.n_state))
        except np.linalg.LinAlgError:
            P = np.eye(self.n_state) * 1e6

        return OrbitEstimate(
            time=time,
            position=self.x[:3],
            velocity=self.x[3:6],
            covariance=P[:6, :6],  # Position + velocity covariance
        )


# ============================================================================
# Convenience functions
# ============================================================================

def estimate_orbit_batch(
    measurements: List[GNSSMeasurement],
    initial_guess: Optional[np.ndarray] = None,
    measurement_noise: float = 1.0,
) -> OrbitEstimate:
    """
    Estimate orbit using batch least squares.

    Args:
        measurements: List of GNSS measurements
        initial_guess: Initial state [x, y, z, clock_bias] (m), optional
        measurement_noise: Measurement noise std (m)

    Returns:
        OrbitEstimate
    """
    if initial_guess is None:
        # Use first measurement satellite position as initial guess
        if measurements[0].sat_position is None:
            raise ValueError("Need satellite position for initial guess")

        # Receiver roughly on Earth surface below satellite
        sat_pos = measurements[0].sat_position
        r_earth = 6371000.0
        r_sat = np.linalg.norm(sat_pos)

        initial_guess = sat_pos * (r_earth / r_sat)
        initial_guess = np.append(initial_guess, 0.0)  # Zero clock bias

    estimator = BatchLeastSquares()
    return estimator.estimate(measurements, initial_guess, measurement_noise)


def estimate_orbit_sequential(
    measurements: List[GNSSMeasurement],
    dt: float = 1.0,
    measurement_noise: float = 1.0,
    process_noise: float = 0.01,
) -> List[OrbitEstimate]:
    """
    Estimate orbit using square-root information filter.

    Args:
        measurements: List of GNSS measurements (sorted by time)
        dt: Time step between measurements (s)
        measurement_noise: Measurement noise std (m)
        process_noise: Process noise std (m)

    Returns:
        List of OrbitEstimate for each measurement
    """
    srif = SquareRootInformationFilter(process_noise=process_noise)

    estimates = []

    for i, meas in enumerate(measurements):
        # Predict
        if i > 0:
            srif.predict(dt)

        # Update
        srif.update(meas, measurement_noise)

        # Store estimate
        estimate = srif.get_estimate(meas.time)
        estimates.append(estimate)

    return estimates


def compute_dilution_of_precision(
    receiver_pos: np.ndarray,
    satellite_positions: List[np.ndarray],
) -> Tuple[float, float, float, float]:
    """
    Compute Dilution of Precision (DOP) metrics.

    DOP quantifies the geometric quality of the satellite constellation.

    Args:
        receiver_pos: Receiver ECEF position (m), shape (3,)
        satellite_positions: List of satellite ECEF positions, each shape (3,)

    Returns:
        (GDOP, PDOP, HDOP, VDOP)
        GDOP: Geometric DOP (position + time)
        PDOP: Position DOP
        HDOP: Horizontal DOP
        VDOP: Vertical DOP
    """
    if len(satellite_positions) < 4:
        return np.inf, np.inf, np.inf, np.inf

    # Build measurement Jacobian
    H_list = []
    for sat_pos in satellite_positions:
        H_pos = gnss_measurement_jacobian(receiver_pos, sat_pos)
        H_clock = np.array([[1.0]])
        H_row = np.hstack([H_pos, H_clock])
        H_list.append(H_row)

    H = np.vstack(H_list)  # shape (n, 4)

    # DOP = sqrt(trace((H^T H)^{-1}))
    try:
        G = np.linalg.inv(H.T @ H)
    except np.linalg.LinAlgError:
        return np.inf, np.inf, np.inf, np.inf

    GDOP = np.sqrt(np.trace(G))
    PDOP = np.sqrt(np.trace(G[:3, :3]))

    # HDOP/VDOP are defined in the local ENU frame: rotate the ECEF
    # position covariance block before splitting horizontal/vertical
    # (the raw ECEF components are only correct at the poles).
    lat = np.arcsin(receiver_pos[2] / np.linalg.norm(receiver_pos))
    lon = np.arctan2(receiver_pos[1], receiver_pos[0])
    sl, cl = np.sin(lat), np.cos(lat)
    so, co = np.sin(lon), np.cos(lon)
    R_enu = np.array([
        [-so, co, 0.0],
        [-sl * co, -sl * so, cl],
        [cl * co, cl * so, sl],
    ])
    G_enu = R_enu @ G[:3, :3] @ R_enu.T
    HDOP = np.sqrt(G_enu[0, 0] + G_enu[1, 1])
    VDOP = np.sqrt(G_enu[2, 2])

    return GDOP, PDOP, HDOP, VDOP
