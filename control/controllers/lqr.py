"""
Linear Quadratic Regulator (LQR) controller for formation flying.

This module implements continuous and discrete-time LQR controllers
optimized for satellite formation control using JAX for acceleration.
"""

import jax
import jax.numpy as jnp
import jax.scipy as jsp
from typing import Tuple, Optional, Dict, Any
import numpy as np


@jax.jit
def solve_continuous_riccati(
    A: jnp.ndarray,
    B: jnp.ndarray, 
    Q: jnp.ndarray,
    R: jnp.ndarray,
    max_iter: int = 100,
    tol: float = 1e-10
) -> jnp.ndarray:
    """
    Solve continuous-time algebraic Riccati equation.
    
    Solves: PA + A^T P - PBR^{-1}B^T P + Q = 0
    
    Args:
        A: System dynamics matrix (n x n)
        B: Control input matrix (n x m)
        Q: State cost matrix (n x n), positive semi-definite
        R: Control cost matrix (m x m), positive definite
        max_iter: Maximum iterations for solver
        tol: Convergence tolerance
        
    Returns:
        P: Solution to Riccati equation (n x n)
    """
    n = A.shape[0]
    
    # Use Schur method for robust solution
    # Form Hamiltonian matrix
    R_inv = jnp.linalg.inv(R)
    BR_inv_BT = B @ R_inv @ B.T
    
    H = jnp.block([
        [A, -BR_inv_BT],
        [-Q, -A.T]
    ])
    
    # Compute eigendecomposition
    eigenvals, eigenvecs = jnp.linalg.eig(H)
    
    # Select stable subspace (negative real part eigenvalues)
    stable_mask = jnp.real(eigenvals) < 0
    stable_indices = jnp.argsort(jnp.real(eigenvals))[:n]
    
    # Extract stable eigenvectors
    U = eigenvecs[:, stable_indices]
    U1 = U[:n, :]
    U2 = U[n:, :]
    
    # Compute P
    P = jnp.real(U2 @ jnp.linalg.inv(U1))
    
    # Ensure symmetry
    P = 0.5 * (P + P.T)
    
    return P


@jax.jit
def solve_discrete_riccati(
    A: jnp.ndarray,
    B: jnp.ndarray,
    Q: jnp.ndarray,
    R: jnp.ndarray,
    max_iter: int = 100,
    tol: float = 1e-10
) -> jnp.ndarray:
    """
    Solve discrete-time algebraic Riccati equation.
    
    Solves: P = A^T P A - A^T P B (R + B^T P B)^{-1} B^T P A + Q
    
    Args:
        A: Discrete system matrix (n x n)
        B: Discrete control matrix (n x m)
        Q: State cost matrix (n x n)
        R: Control cost matrix (m x m)
        max_iter: Maximum iterations
        tol: Convergence tolerance
        
    Returns:
        P: Solution to discrete Riccati equation
    """
    P = Q
    
    def iterate(carry, _):
        P_prev = carry
        temp = R + B.T @ P_prev @ B
        P_new = Q + A.T @ P_prev @ (A - B @ jnp.linalg.solve(temp, B.T @ P_prev @ A))
        P_new = 0.5 * (P_new + P_new.T)  # Ensure symmetry
        return P_new, jnp.linalg.norm(P_new - P_prev)
    
    # Use scan for efficient iteration
    P_final, errors = jax.lax.scan(iterate, P, jnp.arange(max_iter))
    
    return P_final


@jax.jit
def lqr_gain_continuous(
    A: jnp.ndarray,
    B: jnp.ndarray,
    Q: jnp.ndarray,
    R: jnp.ndarray
) -> Tuple[jnp.ndarray, jnp.ndarray]:
    """
    Compute continuous-time LQR gain matrix.
    
    Control law: u = -K*x
    
    Args:
        A: System dynamics matrix
        B: Control input matrix
        Q: State cost matrix
        R: Control cost matrix
        
    Returns:
        K: Optimal gain matrix
        P: Solution to Riccati equation
    """
    P = solve_continuous_riccati(A, B, Q, R)
    K = jnp.linalg.inv(R) @ B.T @ P
    return K, P


@jax.jit
def lqr_gain_discrete(
    A: jnp.ndarray,
    B: jnp.ndarray,
    Q: jnp.ndarray,
    R: jnp.ndarray
) -> Tuple[jnp.ndarray, jnp.ndarray]:
    """
    Compute discrete-time LQR gain matrix.
    
    Args:
        A: Discrete system matrix
        B: Discrete control matrix
        Q: State cost matrix
        R: Control cost matrix
        
    Returns:
        K: Optimal gain matrix
        P: Solution to Riccati equation
    """
    P = solve_discrete_riccati(A, B, Q, R)
    K = jnp.linalg.inv(R + B.T @ P @ B) @ B.T @ P @ A
    return K, P


@jax.jit
def hill_clohessy_wiltshire_matrices(
    n: float,
    dt: Optional[float] = None
) -> Tuple[jnp.ndarray, jnp.ndarray]:
    """
    Generate HCW matrices for relative orbital motion.
    
    Args:
        n: Mean motion (rad/s)
        dt: Time step for discrete-time (None for continuous)
        
    Returns:
        A: System matrix (6x6)
        B: Control matrix (6x3)
    """
    if dt is None:
        # Continuous-time HCW
        A = jnp.array([
            [0, 0, 0, 1, 0, 0],
            [0, 0, 0, 0, 1, 0],
            [0, 0, 0, 0, 0, 1],
            [3*n**2, 0, 0, 0, 2*n, 0],
            [0, 0, 0, -2*n, 0, 0],
            [0, 0, -n**2, 0, 0, 0]
        ])
        
        B = jnp.array([
            [0, 0, 0],
            [0, 0, 0],
            [0, 0, 0],
            [1, 0, 0],
            [0, 1, 0],
            [0, 0, 1]
        ])
    else:
        # Discrete-time HCW (closed-form solution)
        c = jnp.cos(n * dt)
        s = jnp.sin(n * dt)
        
        A = jnp.array([
            [4-3*c, 0, 0, s/n, 2*(1-c)/n, 0],
            [6*(s-n*dt), 1, 0, -2*(1-c)/n, (4*s-3*n*dt)/n, 0],
            [0, 0, c, 0, 0, s/n],
            [3*n*s, 0, 0, c, 2*s, 0],
            [6*n*(c-1), 0, 0, -2*s, 4*c-3, 0],
            [0, 0, -n*s, 0, 0, c]
        ])
        
        # Discrete control influence matrix
        B = jnp.zeros((6, 3))
        # Simplified - would need integration for exact
        B = B.at[3:6, :].set(jnp.eye(3) * dt)
        
    return A, B


class FormationLQRController:
    """
    LQR controller specialized for satellite formation flying.
    """
    
    def __init__(
        self,
        n: float,
        Q: Optional[jnp.ndarray] = None,
        R: Optional[jnp.ndarray] = None,
        discrete: bool = False,
        dt: Optional[float] = None
    ):
        """
        Initialize formation LQR controller.
        
        Args:
            n: Chief orbit mean motion (rad/s)
            Q: State cost matrix (6x6). If None, uses default
            R: Control cost matrix (3x3). If None, uses default
            discrete: Use discrete-time formulation
            dt: Time step for discrete-time
        """
        self.n = n
        self.discrete = discrete
        self.dt = dt
        
        # Default cost matrices if not provided
        if Q is None:
            # Penalize position errors more than velocity
            Q = jnp.diag(jnp.array([10., 10., 10., 1., 1., 1.]))
        if R is None:
            # Equal control cost in all directions
            R = jnp.eye(3) * 0.01
            
        self.Q = Q
        self.R = R
        
        # Generate system matrices
        self.A, self.B = hill_clohessy_wiltshire_matrices(n, dt)
        
        # Compute optimal gain
        if discrete:
            self.K, self.P = lqr_gain_discrete(self.A, self.B, Q, R)
        else:
            self.K, self.P = lqr_gain_continuous(self.A, self.B, Q, R)
    
    # NOTE: no @jax.jit here - jitting an instance method traces
    # `self` (not a pytree) and raises on every call.
    def compute_control(
        self,
        state: jnp.ndarray,
        reference: Optional[jnp.ndarray] = None
    ) -> jnp.ndarray:
        """
        Compute LQR control input.
        
        Args:
            state: Current relative state [x, y, z, vx, vy, vz]
            reference: Desired relative state (default: origin)
            
        Returns:
            u: Control acceleration [ax, ay, az] (m/s²)
        """
        if reference is None:
            reference = jnp.zeros(6)
        
        error = state - reference
        u = -self.K @ error
        
        return u
    
    def simulate_trajectory(
        self,
        initial_state: jnp.ndarray,
        duration: float,
        dt: float,
        reference: Optional[jnp.ndarray] = None,
        disturbances: Optional[jnp.ndarray] = None
    ) -> Dict[str, jnp.ndarray]:
        """
        Simulate controlled trajectory.
        
        Args:
            initial_state: Initial relative state
            duration: Simulation duration (s)
            dt: Time step (s)
            reference: Reference trajectory (time x 6)
            disturbances: Disturbance forces (time x 3)
            
        Returns:
            Dictionary with times, states, controls
        """
        steps = int(duration / dt)
        times = jnp.arange(steps) * dt
        
        if reference is None:
            reference = jnp.zeros((steps, 6))
        if disturbances is None:
            disturbances = jnp.zeros((steps, 3))
            
        # Discrete-time system for simulation
        Ad, Bd = hill_clohessy_wiltshire_matrices(self.n, dt)
        
        def step(state, inputs):
            ref, dist = inputs
            # Compute control
            u = self.compute_control(state, ref)
            # Apply dynamics with control and disturbances
            next_state = Ad @ state + Bd @ (u + dist)
            return next_state, (state, u)
        
        # Run simulation
        final_state, (states, controls) = jax.lax.scan(
            step,
            initial_state,
            (reference, disturbances)
        )
        
        return {
            'times': times,
            'states': states,
            'controls': controls,
            'reference': reference
        }
    
    def get_cost(
        self,
        states: jnp.ndarray,
        controls: jnp.ndarray,
        reference: Optional[jnp.ndarray] = None
    ) -> float:
        """
        Compute total LQR cost.
        
        Args:
            states: State trajectory (N x 6)
            controls: Control trajectory (N x 3)
            reference: Reference trajectory
            
        Returns:
            J: Total quadratic cost
        """
        if reference is None:
            reference = jnp.zeros_like(states)
            
        errors = states - reference
        
        # Quadratic costs
        state_cost = jnp.sum(errors @ self.Q * errors)
        control_cost = jnp.sum(controls @ self.R * controls)
        
        return state_cost + control_cost


@jax.jit
def compute_controllability_gramian(
    A: jnp.ndarray,
    B: jnp.ndarray,
    T: float,
    steps: int = 100
) -> jnp.ndarray:
    """
    Compute controllability Gramian.
    
    W_c = ∫_0^T e^{At} B B^T e^{A^T t} dt
    
    Args:
        A: System matrix
        B: Control matrix
        T: Time horizon
        steps: Integration steps
        
    Returns:
        W_c: Controllability Gramian
    """
    dt = T / steps
    
    def integrate_step(W, t):
        eAt = jsp.linalg.expm(A * t)
        integrand = eAt @ B @ B.T @ eAt.T
        return W + integrand * dt, None
    
    W_c, _ = jax.lax.scan(
        integrate_step,
        jnp.zeros((A.shape[0], A.shape[0])),
        jnp.arange(steps) * dt
    )
    
    return W_c


@jax.jit
def minimum_energy_control(
    A: jnp.ndarray,
    B: jnp.ndarray,
    x0: jnp.ndarray,
    xf: jnp.ndarray,
    T: float
) -> Tuple[jnp.ndarray, float]:
    """
    Compute minimum energy control to reach target state.
    
    Args:
        A: System matrix
        B: Control matrix
        x0: Initial state
        xf: Final state
        T: Transfer time
        
    Returns:
        u_func: Control function u(t)
        energy: Total control energy
    """
    # Compute controllability Gramian
    W_c = compute_controllability_gramian(A, B, T)
    
    # State transition matrix
    Phi_T = jsp.linalg.expm(A * T)
    
    # Required state change
    delta_x = xf - Phi_T @ x0
    
    # Minimum energy control coefficient
    alpha = jnp.linalg.solve(W_c, delta_x)
    
    # Control energy
    energy = alpha.T @ W_c @ alpha
    
    # Control function (would need to return as parameters)
    def u_func(t):
        eATt = jsp.linalg.expm(A.T * (T - t))
        return B.T @ eATt @ alpha
    
    return alpha, energy  # Return coefficient instead of function


# Utility functions for formation control
@jax.jit
def design_formation_weights(
    position_weight: float = 10.0,
    velocity_weight: float = 1.0,
    control_weight: float = 0.01,
    n_satellites: int = 1
) -> Tuple[jnp.ndarray, jnp.ndarray]:
    """
    Design LQR weights for formation control.
    
    Args:
        position_weight: Weight on position errors
        velocity_weight: Weight on velocity errors
        control_weight: Weight on control effort
        n_satellites: Number of satellites
        
    Returns:
        Q: State cost matrix
        R: Control cost matrix
    """
    # Single satellite weights
    q_single = jnp.array([
        position_weight, position_weight, position_weight,
        velocity_weight, velocity_weight, velocity_weight
    ])
    
    if n_satellites == 1:
        Q = jnp.diag(q_single)
        R = jnp.eye(3) * control_weight
    else:
        # Block diagonal for multiple satellites
        Q = jnp.kron(jnp.eye(n_satellites), jnp.diag(q_single))
        R = jnp.eye(3 * n_satellites) * control_weight
    
    return Q, R


# Example usage and testing
if __name__ == "__main__":
    # Example: LEO formation at 500 km altitude
    import numpy as np
    
    # Orbital parameters
    mu = 398600.4418  # km³/s²
    a = 6378.137 + 500  # km
    n = np.sqrt(mu / a**3)  # rad/s
    
    # Create controller
    controller = FormationLQRController(
        n=n,
        discrete=False
    )
    
    # Initial state: 100m offset in x, small velocity
    x0 = jnp.array([0.1, 0.0, 0.0, 0.0001, 0.0, 0.0])  # km, km/s
    
    # Simulate for one orbit
    T_orbit = 2 * np.pi / n
    result = controller.simulate_trajectory(
        initial_state=x0,
        duration=T_orbit,
        dt=10.0  # 10 second steps
    )
    
    print(f"Formation LQR Controller Test")
    print(f"Orbit period: {T_orbit/60:.1f} minutes")
    print(f"Initial state: {x0}")
    print(f"Final state: {result['states'][-1]}")
    print(f"Max control: {jnp.max(jnp.abs(result['controls']))*1000:.3f} mm/s²")
    print(f"Total cost: {controller.get_cost(result['states'], result['controls']):.6f}")
