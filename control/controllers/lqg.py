"""
Linear Quadratic Gaussian (LQG) controller for formation flying.

Combines LQR control with Kalman filtering for optimal control
under process and measurement noise.
"""

import jax
import jax.numpy as jnp
from typing import Tuple, Optional, Dict, Any
from .lqr import (
    lqr_gain_continuous,
    lqr_gain_discrete,
    hill_clohessy_wiltshire_matrices
)


@jax.jit
def kalman_filter_continuous(
    A: jnp.ndarray,
    C: jnp.ndarray,
    Q_process: jnp.ndarray,
    R_measurement: jnp.ndarray,
    max_iter: int = 100,
    tol: float = 1e-10
) -> jnp.ndarray:
    """
    Compute steady-state Kalman filter gain for continuous system.
    
    Solves the dual Riccati equation for estimation.
    
    Args:
        A: System dynamics matrix (n x n)
        C: Measurement matrix (m x n)
        Q_process: Process noise covariance (n x n)
        R_measurement: Measurement noise covariance (m x m)
        max_iter: Maximum iterations
        tol: Convergence tolerance
        
    Returns:
        L: Steady-state Kalman gain (n x m)
    """
    # Solve dual Riccati equation: P*A^T + A*P - P*C^T*R^{-1}*C*P + Q = 0
    n = A.shape[0]
    P = Q_process
    
    for _ in range(max_iter):
        P_prev = P
        
        # Kalman gain
        L = P @ C.T @ jnp.linalg.inv(R_measurement)
        
        # Riccati equation update
        P = Q_process + A @ P @ A.T - A @ P @ C.T @ jnp.linalg.inv(
            R_measurement + C @ P @ C.T
        ) @ C @ P @ A.T
        
        # Ensure symmetry
        P = 0.5 * (P + P.T)
        
        if jnp.linalg.norm(P - P_prev) < tol:
            break
    
    # Final Kalman gain
    L = P @ C.T @ jnp.linalg.inv(R_measurement)
    
    return L, P


@jax.jit
def kalman_filter_discrete(
    A: jnp.ndarray,
    C: jnp.ndarray,
    Q_process: jnp.ndarray,
    R_measurement: jnp.ndarray,
    max_iter: int = 100
) -> Tuple[jnp.ndarray, jnp.ndarray]:
    """
    Compute steady-state Kalman filter for discrete system.
    
    Args:
        A: Discrete system matrix
        C: Measurement matrix
        Q_process: Process noise covariance
        R_measurement: Measurement noise covariance
        max_iter: Maximum iterations
        
    Returns:
        L: Steady-state Kalman gain
        P: Steady-state error covariance
    """
    P = Q_process
    
    def riccati_step(P_prev, _):
        # Prediction covariance
        P_pred = A @ P_prev @ A.T + Q_process
        
        # Kalman gain
        S = C @ P_pred @ C.T + R_measurement
        L = P_pred @ C.T @ jnp.linalg.inv(S)
        
        # Update covariance
        P = (jnp.eye(P_pred.shape[0]) - L @ C) @ P_pred
        P = 0.5 * (P + P.T)  # Ensure symmetry
        
        return P, L
    
    P_final, L_history = jax.lax.scan(
        riccati_step,
        P,
        jnp.arange(max_iter)
    )
    
    # Get final Kalman gain
    S = C @ P_final @ C.T + R_measurement
    L_final = P_final @ C.T @ jnp.linalg.inv(S)
    
    return L_final, P_final


class LQGController:
    """
    Linear Quadratic Gaussian controller combining LQR control with Kalman filtering.
    """
    
    def __init__(
        self,
        A: jnp.ndarray,
        B: jnp.ndarray,
        C: jnp.ndarray,
        Q_lqr: jnp.ndarray,
        R_lqr: jnp.ndarray,
        Q_process: jnp.ndarray,
        R_measurement: jnp.ndarray,
        discrete: bool = False,
        dt: Optional[float] = None
    ):
        """
        Initialize LQG controller.
        
        Args:
            A: System dynamics matrix
            B: Control input matrix
            C: Measurement matrix
            Q_lqr: LQR state cost
            R_lqr: LQR control cost
            Q_process: Process noise covariance
            R_measurement: Measurement noise covariance
            discrete: Use discrete-time formulation
            dt: Time step for discrete-time
        """
        self.A = A
        self.B = B
        self.C = C
        self.discrete = discrete
        self.dt = dt
        
        # LQR design
        if discrete:
            self.K_lqr, self.P_lqr = lqr_gain_discrete(A, B, Q_lqr, R_lqr)
        else:
            self.K_lqr, self.P_lqr = lqr_gain_continuous(A, B, Q_lqr, R_lqr)
        
        # Kalman filter design
        if discrete:
            self.L_kf, self.P_kf = kalman_filter_discrete(
                A, C, Q_process, R_measurement
            )
        else:
            self.L_kf, self.P_kf = kalman_filter_continuous(
                A, C, Q_process, R_measurement
            )
        
        # Store noise parameters
        self.Q_process = Q_process
        self.R_measurement = R_measurement
        
        # Initialize state estimate
        self.n_states = A.shape[0]
        self.x_hat = jnp.zeros(self.n_states)
        self.P_est = jnp.eye(self.n_states)
    
    # NOTE: no @jax.jit here - jitting an instance method traces
    # `self` (not a pytree) and raises on every call.
    def predict(
        self,
        x_hat: jnp.ndarray,
        P: jnp.ndarray,
        u: jnp.ndarray
    ) -> Tuple[jnp.ndarray, jnp.ndarray]:
        """
        Kalman filter prediction step.
        
        Args:
            x_hat: Current state estimate
            P: Current error covariance
            u: Control input
            
        Returns:
            x_hat_pred: Predicted state
            P_pred: Predicted covariance
        """
        x_hat_pred = self.A @ x_hat + self.B @ u
        P_pred = self.A @ P @ self.A.T + self.Q_process
        
        return x_hat_pred, P_pred
    
    # NOTE: no @jax.jit here - jitting an instance method traces
    # `self` (not a pytree) and raises on every call.
    def update(
        self,
        x_hat_pred: jnp.ndarray,
        P_pred: jnp.ndarray,
        y: jnp.ndarray
    ) -> Tuple[jnp.ndarray, jnp.ndarray]:
        """
        Kalman filter update step.
        
        Args:
            x_hat_pred: Predicted state
            P_pred: Predicted covariance
            y: Measurement
            
        Returns:
            x_hat: Updated state estimate
            P: Updated error covariance
        """
        # Innovation
        y_pred = self.C @ x_hat_pred
        innovation = y - y_pred
        
        # Innovation covariance
        S = self.C @ P_pred @ self.C.T + self.R_measurement
        
        # Kalman gain
        K = P_pred @ self.C.T @ jnp.linalg.inv(S)
        
        # Update
        x_hat = x_hat_pred + K @ innovation
        P = (jnp.eye(self.n_states) - K @ self.C) @ P_pred
        
        return x_hat, P
    
    # NOTE: no @jax.jit here - jitting an instance method traces
    # `self` (not a pytree) and raises on every call.
    def compute_control(
        self,
        x_hat: jnp.ndarray,
        reference: Optional[jnp.ndarray] = None
    ) -> jnp.ndarray:
        """
        Compute LQG control based on state estimate.
        
        Args:
            x_hat: State estimate
            reference: Reference state
            
        Returns:
            u: Control input
        """
        if reference is None:
            reference = jnp.zeros_like(x_hat)
        
        # LQR control law on estimated state
        error = x_hat - reference
        u = -self.K_lqr @ error
        
        return u
    
    def step(
        self,
        y: jnp.ndarray,
        reference: Optional[jnp.ndarray] = None,
        u_prev: Optional[jnp.ndarray] = None
    ) -> Tuple[jnp.ndarray, jnp.ndarray, jnp.ndarray]:
        """
        Single LQG control step.
        
        Args:
            y: Current measurement
            reference: Reference state
            u_prev: Previous control (for prediction)
            
        Returns:
            u: Control input
            x_hat: State estimate
            P: Error covariance
        """
        # Prediction step (if previous control available)
        if u_prev is not None:
            self.x_hat, self.P_est = self.predict(
                self.x_hat, self.P_est, u_prev
            )
        
        # Update step
        self.x_hat, self.P_est = self.update(
            self.x_hat, self.P_est, y
        )
        
        # Compute control
        u = self.compute_control(self.x_hat, reference)
        
        return u, self.x_hat, self.P_est
    
    def simulate(
        self,
        initial_state: jnp.ndarray,
        duration: float,
        dt: float,
        process_noise_std: float = 0.0,
        measurement_noise_std: float = 0.0,
        reference: Optional[jnp.ndarray] = None
    ) -> Dict[str, jnp.ndarray]:
        """
        Simulate LQG controlled system with noise.
        
        Args:
            initial_state: True initial state
            duration: Simulation duration
            dt: Time step
            process_noise_std: Process noise standard deviation
            measurement_noise_std: Measurement noise standard deviation
            reference: Reference trajectory
            
        Returns:
            Dictionary with simulation results
        """
        steps = int(duration / dt)
        
        # Initialize arrays
        times = jnp.arange(steps) * dt
        states = jnp.zeros((steps, self.n_states))
        estimates = jnp.zeros((steps, self.n_states))
        controls = jnp.zeros((steps, self.B.shape[1]))
        measurements = jnp.zeros((steps, self.C.shape[0]))
        
        # Generate noise
        key = jax.random.PRNGKey(0)
        key_process, key_measure = jax.random.split(key)
        
        process_noise = jax.random.normal(
            key_process, (steps, self.n_states)
        ) * process_noise_std
        
        measurement_noise = jax.random.normal(
            key_measure, (steps, self.C.shape[0])
        ) * measurement_noise_std
        
        # Initial conditions
        x_true = initial_state
        self.x_hat = initial_state + jax.random.normal(
            jax.random.PRNGKey(1), initial_state.shape
        ) * 0.01
        
        # Simulation loop
        def simulate_step(carry, i):
            x_true, x_hat, P_est = carry
            
            # Get reference for this step
            ref = reference[i] if reference is not None else jnp.zeros_like(x_true)
            
            # Measurement with noise
            y = self.C @ x_true + measurement_noise[i]
            
            # LQG control step
            # Update estimate with measurement
            x_hat_new, P_est_new = self.update(x_hat, P_est, y)
            
            # Compute control
            u = self.compute_control(x_hat_new, ref)
            
            # True system dynamics with process noise
            if self.discrete:
                x_true_new = self.A @ x_true + self.B @ u + process_noise[i]
            else:
                # Euler integration for continuous system
                x_dot = self.A @ x_true + self.B @ u
                x_true_new = x_true + x_dot * dt + process_noise[i]
            
            # Predict for next step
            x_hat_pred, P_pred = self.predict(x_hat_new, P_est_new, u)
            
            return (x_true_new, x_hat_pred, P_pred), (x_true, x_hat_new, u, y)
        
        # Run simulation
        _, (states, estimates, controls, measurements) = jax.lax.scan(
            simulate_step,
            (x_true, self.x_hat, self.P_est),
            jnp.arange(steps)
        )
        
        return {
            'times': times,
            'states': states,
            'estimates': estimates,
            'controls': controls,
            'measurements': measurements,
            'estimation_error': states - estimates
        }


class FormationLQGController:
    """
    LQG controller specialized for satellite formation flying.
    """
    
    def __init__(
        self,
        n: float,
        Q_lqr: Optional[jnp.ndarray] = None,
        R_lqr: Optional[jnp.ndarray] = None,
        Q_process: Optional[jnp.ndarray] = None,
        R_measurement: Optional[jnp.ndarray] = None,
        measurement_type: str = 'position',
        discrete: bool = False,
        dt: Optional[float] = None
    ):
        """
        Initialize formation LQG controller.
        
        Args:
            n: Chief orbit mean motion (rad/s)
            Q_lqr: LQR state cost (6x6)
            R_lqr: LQR control cost (3x3)
            Q_process: Process noise covariance (6x6)
            R_measurement: Measurement noise covariance
            measurement_type: 'position', 'velocity', or 'full'
            discrete: Use discrete-time formulation
            dt: Time step for discrete-time
        """
        self.n = n
        
        # Get HCW matrices
        A, B = hill_clohessy_wiltshire_matrices(n, dt if discrete else None)
        
        # Measurement matrix based on type
        if measurement_type == 'position':
            C = jnp.eye(6)[:3, :]  # Measure only position
            n_meas = 3
        elif measurement_type == 'velocity':
            C = jnp.eye(6)[3:, :]  # Measure only velocity
            n_meas = 3
        else:  # 'full'
            C = jnp.eye(6)  # Measure full state
            n_meas = 6
        
        # Default cost matrices if not provided
        if Q_lqr is None:
            Q_lqr = jnp.diag(jnp.array([10., 10., 10., 1., 1., 1.]))
        if R_lqr is None:
            R_lqr = jnp.eye(3) * 0.01
        
        # Default noise covariances if not provided
        if Q_process is None:
            # Process noise: small accelerations
            Q_process = jnp.zeros((6, 6))
            Q_process = Q_process.at[3:, 3:].set(jnp.eye(3) * 1e-8)
            
        if R_measurement is None:
            # Measurement noise based on type
            if measurement_type == 'position':
                # GPS-like: ~10m position accuracy
                R_measurement = jnp.eye(3) * (10e-3)**2  # km
            elif measurement_type == 'velocity':
                # Doppler: ~1mm/s velocity accuracy
                R_measurement = jnp.eye(3) * (1e-6)**2  # km/s
            else:
                R_measurement = jnp.eye(6)
                R_measurement = R_measurement.at[:3, :3].set(jnp.eye(3) * (10e-3)**2)
                R_measurement = R_measurement.at[3:, 3:].set(jnp.eye(3) * (1e-6)**2)
        
        # Create LQG controller
        self.controller = LQGController(
            A, B, C,
            Q_lqr, R_lqr,
            Q_process, R_measurement,
            discrete, dt
        )
        
        self.measurement_type = measurement_type
    
    def get_separation_principle_error(self) -> float:
        """
        Verify separation principle (LQR and KF can be designed independently).
        
        Returns:
            Error metric showing coupling (should be near zero)
        """
        # The closed-loop poles should be union of LQR and KF poles
        A_cl_lqr = self.controller.A - self.controller.B @ self.controller.K_lqr
        A_cl_kf = self.controller.A - self.controller.L_kf @ self.controller.C
        
        # Compute eigenvalues
        eig_lqr = jnp.linalg.eigvals(A_cl_lqr)
        eig_kf = jnp.linalg.eigvals(A_cl_kf)
        
        # Combined system matrix
        n = self.controller.n_states
        A_combined = jnp.block([
            [self.controller.A, -self.controller.B @ self.controller.K_lqr],
            [self.controller.L_kf @ self.controller.C,
             self.controller.A - self.controller.B @ self.controller.K_lqr - 
             self.controller.L_kf @ self.controller.C]
        ])
        
        eig_combined = jnp.linalg.eigvals(A_combined)
        
        # Check if combined eigenvalues match union of individual
        # This is approximate due to numerical precision
        expected_eigs = jnp.concatenate([eig_lqr, eig_kf])
        
        # Sort for comparison
        eig_combined_sorted = jnp.sort(jnp.abs(eig_combined))
        expected_sorted = jnp.sort(jnp.abs(expected_eigs))
        
        error = jnp.linalg.norm(eig_combined_sorted - expected_sorted)
        
        return error


# Example usage
if __name__ == "__main__":
    import numpy as np
    import matplotlib.pyplot as plt
    
    # Orbital parameters (500 km LEO)
    mu = 398600.4418  # km³/s²
    a = 6378.137 + 500  # km
    n = np.sqrt(mu / a**3)  # rad/s
    
    # Create formation LQG controller
    controller = FormationLQGController(
        n=n,
        measurement_type='position',  # GPS measurements
        discrete=False
    )
    
    # Initial state with uncertainty
    x0_true = jnp.array([0.1, 0.05, 0.0, 0.0001, 0.0, 0.0])  # km, km/s
    
    # Simulate with noise
    T_orbit = 2 * np.pi / n
    result = controller.controller.simulate(
        initial_state=x0_true,
        duration=T_orbit / 2,  # Half orbit
        dt=10.0,
        process_noise_std=1e-6,
        measurement_noise_std=1e-3
    )
    
    print("Formation LQG Controller Test")
    print(f"Mean motion: {n:.6f} rad/s")
    print(f"Initial true state: {x0_true}")
    print(f"Final estimated state: {result['estimates'][-1]}")
    print(f"Final estimation error: {result['estimation_error'][-1]*1000} m, mm/s")
    print(f"RMS estimation error: {jnp.sqrt(jnp.mean(result['estimation_error']**2, axis=0))*1000}")
    print(f"Max control: {jnp.max(jnp.abs(result['controls']))*1000:.3f} mm/s²")
    print(f"Separation principle error: {controller.get_separation_principle_error():.2e}")
