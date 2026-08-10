"""
Control Service for GeoSense Platform API

Provides business logic layer for Guidance, Navigation, and Control operations:
- LQR and MPC controllers for formation flying
- Extended Kalman Filter for state estimation
- Trajectory planning and optimization
- Collision avoidance and safety constraints

This service bridges API endpoints with core control modules.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass

# Import core control modules
try:
    import jax.numpy as jnp
    from control.controllers.lqr import (
        FormationLQRController,
        lqr_gain_continuous,
        lqr_gain_discrete,
        hill_clohessy_wiltshire_matrices,
        design_formation_weights
    )
    from control.controllers.mpc import (
        MPCController,
        FormationMPCController,
        FuelOptimalMPC,
        design_mpc_weights
    )
    from control.navigation.ekf import (
        ExtendedKalmanFilter,
        OrbitalEKF,
        RelativeNavigationEKF
    )
    CONTROL_IMPORTS_AVAILABLE = True
except ImportError as e:
    CONTROL_IMPORTS_AVAILABLE = False
    print(f"Control imports not available: {e}")


@dataclass
class ControllerResult:
    """Container for controller computation results."""
    control: np.ndarray
    predicted_states: Optional[np.ndarray] = None
    cost: Optional[float] = None
    converged: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to serializable dictionary."""
        return {
            'control': self.control.tolist(),
            'predicted_states': self.predicted_states.tolist() if self.predicted_states is not None else None,
            'cost': float(self.cost) if self.cost is not None else None,
            'converged': self.converged
        }


@dataclass
class NavigationResult:
    """Container for navigation/estimation results."""
    state_estimate: np.ndarray
    covariance: np.ndarray
    innovation: Optional[np.ndarray] = None
    nis: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to serializable dictionary."""
        return {
            'state_estimate': self.state_estimate.tolist(),
            'covariance': self.covariance.tolist(),
            'covariance_diagonal': np.diag(self.covariance).tolist(),
            'position_uncertainty': float(np.sqrt(np.trace(self.covariance[:3, :3]))),
            'velocity_uncertainty': float(np.sqrt(np.trace(self.covariance[3:6, 3:6]))),
            'innovation': self.innovation.tolist() if self.innovation is not None else None,
            'nis': float(self.nis) if self.nis is not None else None
        }


class ControlService:
    """
    Service for Guidance, Navigation, and Control operations.

    Provides high-level functions that wrap core control modules,
    handling data validation, type conversion, and error handling.
    """

    def __init__(self):
        """Initialize control service."""
        if not CONTROL_IMPORTS_AVAILABLE:
            print("Warning: Control modules not available. Service will have limited functionality.")

        self._lqr_controllers = {}  # Cache LQR controllers
        self._mpc_controllers = {}  # Cache MPC controllers
        self._ekf_filters = {}  # Cache EKF filters

    # =========================================================================
    # LQR Controller Methods
    # =========================================================================

    def create_lqr_controller(
        self,
        mean_motion: float,
        position_weight: float = 10.0,
        velocity_weight: float = 1.0,
        control_weight: float = 0.01,
        discrete: bool = False,
        dt: Optional[float] = None,
        controller_id: str = 'default'
    ) -> Dict[str, Any]:
        """
        Create LQR controller for formation flying.

        Args:
            mean_motion: Orbital mean motion in rad/s
            position_weight: Weight on position errors
            velocity_weight: Weight on velocity errors
            control_weight: Weight on control effort
            discrete: Use discrete-time formulation
            dt: Time step for discrete-time (required if discrete=True)
            controller_id: Unique identifier for this controller

        Returns:
            Dictionary with controller metadata and gain matrix
        """
        if not CONTROL_IMPORTS_AVAILABLE:
            raise RuntimeError("Control modules not available")

        if discrete and dt is None:
            raise ValueError("dt required for discrete-time LQR")

        # Design cost matrices
        Q, R = design_formation_weights(
            position_weight=position_weight,
            velocity_weight=velocity_weight,
            control_weight=control_weight,
            n_satellites=1
        )

        # Create controller
        controller = FormationLQRController(
            n=mean_motion,
            Q=Q,
            R=R,
            discrete=discrete,
            dt=dt
        )

        # Cache controller
        self._lqr_controllers[controller_id] = controller

        # Convert gain to numpy for serialization
        K_np = np.array(controller.K)

        return {
            'controller_id': controller_id,
            'type': 'discrete' if discrete else 'continuous',
            'gain_matrix': K_np.tolist(),
            'mean_motion': mean_motion,
            'dt': dt,
            'cost_matrices': {
                'Q': np.array(Q).tolist(),
                'R': np.array(R).tolist()
            }
        }

    def compute_lqr_control(
        self,
        controller_id: str,
        current_state: np.ndarray,
        reference_state: Optional[np.ndarray] = None
    ) -> ControllerResult:
        """
        Compute LQR control for current state.

        Args:
            controller_id: Controller identifier
            current_state: Current relative state [x, y, z, vx, vy, vz] in km and km/s
            reference_state: Desired reference state (default: origin)

        Returns:
            ControllerResult with control acceleration
        """
        if not CONTROL_IMPORTS_AVAILABLE:
            raise RuntimeError("Control modules not available")

        if controller_id not in self._lqr_controllers:
            raise ValueError(f"Controller {controller_id} not found")

        controller = self._lqr_controllers[controller_id]

        # Convert to JAX arrays
        state_jax = jnp.array(current_state)
        ref_jax = jnp.array(reference_state) if reference_state is not None else None

        # Compute control
        u = controller.compute_control(state_jax, ref_jax)

        # Convert back to numpy
        u_np = np.array(u)

        return ControllerResult(
            control=u_np,
            converged=True
        )

    def simulate_lqr_trajectory(
        self,
        controller_id: str,
        initial_state: np.ndarray,
        duration: float,
        dt: float,
        reference: Optional[np.ndarray] = None
    ) -> Dict[str, Any]:
        """
        Simulate closed-loop trajectory with LQR controller.

        Args:
            controller_id: Controller identifier
            initial_state: Initial relative state
            duration: Simulation duration in seconds
            dt: Time step in seconds
            reference: Reference trajectory (optional)

        Returns:
            Dictionary with times, states, and controls
        """
        if not CONTROL_IMPORTS_AVAILABLE:
            raise RuntimeError("Control modules not available")

        if controller_id not in self._lqr_controllers:
            raise ValueError(f"Controller {controller_id} not found")

        controller = self._lqr_controllers[controller_id]

        # Convert to JAX arrays
        initial_state_jax = jnp.array(initial_state)
        ref_jax = jnp.array(reference) if reference is not None else None

        # Simulate
        result = controller.simulate_trajectory(
            initial_state=initial_state_jax,
            duration=duration,
            dt=dt,
            reference=ref_jax
        )

        # Compute total cost
        total_cost = controller.get_cost(result['states'], result['controls'], result['reference'])

        # Convert to serializable format
        return {
            'times': np.array(result['times']).tolist(),
            'states': np.array(result['states']).tolist(),
            'controls': np.array(result['controls']).tolist(),
            'reference': np.array(result['reference']).tolist(),
            'total_cost': float(total_cost),
            'final_position_error': np.linalg.norm(result['states'][-1, :3]) * 1000,  # meters
            'max_control': float(np.max(np.abs(result['controls']))) * 1000  # mm/s²
        }

    # =========================================================================
    # MPC Controller Methods
    # =========================================================================

    def create_mpc_controller(
        self,
        mean_motion: float,
        horizon: int = 10,
        dt: float = 10.0,
        max_thrust: float = 0.001,
        max_position_error: float = 0.1,
        max_velocity_error: float = 0.001,
        fuel_weight: float = 0.01,
        controller_id: str = 'default_mpc'
    ) -> Dict[str, Any]:
        """
        Create MPC controller for constrained formation control.

        Args:
            mean_motion: Orbital mean motion in rad/s
            horizon: Prediction horizon (steps)
            dt: Time step in seconds
            max_thrust: Maximum thrust magnitude in km/s²
            max_position_error: Maximum position deviation in km
            max_velocity_error: Maximum velocity deviation in km/s
            fuel_weight: Weight on fuel consumption
            controller_id: Unique identifier

        Returns:
            Dictionary with controller metadata
        """
        if not CONTROL_IMPORTS_AVAILABLE:
            raise RuntimeError("Control modules not available")

        # Create MPC controller
        controller = FormationMPCController(
            n=mean_motion,
            N=horizon,
            dt=dt,
            max_thrust=max_thrust,
            max_position_error=max_position_error,
            max_velocity_error=max_velocity_error,
            fuel_weight=fuel_weight
        )

        # Cache controller
        self._mpc_controllers[controller_id] = controller

        return {
            'controller_id': controller_id,
            'type': 'mpc',
            'horizon': horizon,
            'dt': dt,
            'constraints': {
                'max_thrust': max_thrust,
                'max_position_error': max_position_error,
                'max_velocity_error': max_velocity_error
            },
            'mean_motion': mean_motion
        }

    def compute_mpc_control(
        self,
        controller_id: str,
        current_state: np.ndarray,
        reference_state: Optional[np.ndarray] = None
    ) -> Dict[str, Any]:
        """
        Compute MPC control action.

        Args:
            controller_id: Controller identifier
            current_state: Current state vector
            reference_state: Reference state (default: origin)

        Returns:
            Dictionary with control and predicted trajectory
        """
        if not CONTROL_IMPORTS_AVAILABLE:
            raise RuntimeError("Control modules not available")

        if controller_id not in self._mpc_controllers:
            raise ValueError(f"Controller {controller_id} not found")

        controller = self._mpc_controllers[controller_id]

        # Solve MPC
        u_seq, x_pred, info = controller.mpc.solve(
            np.array(current_state),
            np.array([reference_state]) if reference_state is not None else None
        )

        return {
            'control': u_seq[0].tolist(),  # First control action
            'control_sequence': u_seq.tolist(),
            'predicted_trajectory': x_pred.tolist(),
            'cost': float(info['cost']),
            'status': info['status'],
            'solve_time': info.get('solve_time', None)
        }

    # =========================================================================
    # Navigation / State Estimation Methods
    # =========================================================================

    def create_orbital_ekf(
        self,
        mu: float = 398600.4418,
        process_noise_std: float = 1e-6,
        gps_noise_std: float = 0.01,
        dt: float = 1.0,
        ekf_id: str = 'default_ekf'
    ) -> Dict[str, Any]:
        """
        Create Extended Kalman Filter for orbital state estimation.

        Args:
            mu: Gravitational parameter in km³/s²
            process_noise_std: Process noise standard deviation in km/s²
            gps_noise_std: GPS measurement noise standard deviation in km
            dt: Time step in seconds
            ekf_id: Unique identifier

        Returns:
            Dictionary with filter metadata
        """
        if not CONTROL_IMPORTS_AVAILABLE:
            raise RuntimeError("Control modules not available")

        # Create EKF
        ekf = OrbitalEKF(
            mu=mu,
            process_noise_std=process_noise_std,
            gps_noise_std=gps_noise_std,
            dt=dt
        )

        # Cache filter
        self._ekf_filters[ekf_id] = ekf

        return {
            'ekf_id': ekf_id,
            'type': 'orbital',
            'mu': mu,
            'dt': dt,
            'noise_parameters': {
                'process_noise_std': process_noise_std,
                'gps_noise_std': gps_noise_std
            }
        }

    def ekf_prediction_step(
        self,
        ekf_id: str,
        state: np.ndarray,
        covariance: np.ndarray,
        control: Optional[np.ndarray] = None,
        time: float = 0.0
    ) -> NavigationResult:
        """
        Perform EKF prediction step.

        Args:
            ekf_id: Filter identifier
            state: Current state estimate [x, y, z, vx, vy, vz] in km and km/s
            covariance: Current error covariance (6x6)
            control: Control input (optional)
            time: Current time

        Returns:
            NavigationResult with predicted state and covariance
        """
        if not CONTROL_IMPORTS_AVAILABLE:
            raise RuntimeError("Control modules not available")

        if ekf_id not in self._ekf_filters:
            raise ValueError(f"EKF {ekf_id} not found")

        ekf = self._ekf_filters[ekf_id]

        # Convert to JAX arrays
        x_jax = jnp.array(state)
        P_jax = jnp.array(covariance)
        u_jax = jnp.array(control) if control is not None else None

        # Prediction step
        x_pred, P_pred = ekf.predict(x_jax, P_jax, u_jax, time)

        return NavigationResult(
            state_estimate=np.array(x_pred),
            covariance=np.array(P_pred)
        )

    def ekf_update_step(
        self,
        ekf_id: str,
        predicted_state: np.ndarray,
        predicted_covariance: np.ndarray,
        measurement: np.ndarray,
        time: float = 0.0
    ) -> NavigationResult:
        """
        Perform EKF measurement update.

        Args:
            ekf_id: Filter identifier
            predicted_state: Predicted state from prediction step
            predicted_covariance: Predicted covariance
            measurement: GPS position measurement in km
            time: Current time

        Returns:
            NavigationResult with updated state and diagnostics
        """
        if not CONTROL_IMPORTS_AVAILABLE:
            raise RuntimeError("Control modules not available")

        if ekf_id not in self._ekf_filters:
            raise ValueError(f"EKF {ekf_id} not found")

        ekf = self._ekf_filters[ekf_id]

        # Convert to JAX arrays
        x_pred_jax = jnp.array(predicted_state)
        P_pred_jax = jnp.array(predicted_covariance)
        y_jax = jnp.array(measurement)

        # Update step
        x_upd, P_upd, innovation = ekf.update(x_pred_jax, P_pred_jax, y_jax, time)

        # Compute NIS for consistency check
        H = ekf.H_func(x_pred_jax, time)
        S = H @ P_pred_jax @ H.T + ekf.R
        nis = float(innovation.T @ jnp.linalg.inv(S) @ innovation)

        return NavigationResult(
            state_estimate=np.array(x_upd),
            covariance=np.array(P_upd),
            innovation=np.array(innovation),
            nis=nis
        )

    def ekf_full_step(
        self,
        ekf_id: str,
        state: np.ndarray,
        covariance: np.ndarray,
        measurement: np.ndarray,
        control: Optional[np.ndarray] = None,
        time: float = 0.0
    ) -> NavigationResult:
        """
        Perform full EKF step (predict + update).

        Args:
            ekf_id: Filter identifier
            state: Current state estimate
            covariance: Current error covariance
            measurement: Measurement vector
            control: Control input (optional)
            time: Current time

        Returns:
            NavigationResult with updated state and diagnostics
        """
        if not CONTROL_IMPORTS_AVAILABLE:
            raise RuntimeError("Control modules not available")

        if ekf_id not in self._ekf_filters:
            raise ValueError(f"EKF {ekf_id} not found")

        ekf = self._ekf_filters[ekf_id]

        # Convert to JAX arrays
        x_jax = jnp.array(state)
        P_jax = jnp.array(covariance)
        y_jax = jnp.array(measurement)
        u_jax = jnp.array(control) if control is not None else None

        # Full step
        x_new, P_new, info = ekf.step(x_jax, P_jax, y_jax, u_jax, time)

        return NavigationResult(
            state_estimate=np.array(x_new),
            covariance=np.array(P_new),
            innovation=np.array(info['innovation']),
            nis=float(info['nis'])
        )

    # =========================================================================
    # Trajectory Planning Methods
    # =========================================================================

    def plan_formation_reconfiguration(
        self,
        mean_motion: float,
        initial_formation: np.ndarray,
        target_formation: np.ndarray,
        n_satellites: int,
        time_horizon: float,
        dt: float = 10.0,
        horizon: int = 10
    ) -> Dict[str, Any]:
        """
        Plan optimal reconfiguration maneuver for satellite formation.

        Args:
            mean_motion: Orbital mean motion in rad/s
            initial_formation: Initial states (n_satellites x 6)
            target_formation: Target states (n_satellites x 6)
            n_satellites: Number of satellites
            time_horizon: Time to complete maneuver in seconds
            dt: Time step
            horizon: MPC horizon

        Returns:
            Dictionary with plans for each satellite
        """
        if not CONTROL_IMPORTS_AVAILABLE:
            raise RuntimeError("Control modules not available")

        # Create temporary MPC controller
        mpc = FormationMPCController(
            n=mean_motion,
            N=horizon,
            dt=dt,
            max_thrust=0.001,
            fuel_weight=0.01
        )

        # Plan reconfiguration
        plans = mpc.plan_reconfiguration(
            np.array(initial_formation),
            np.array(target_formation),
            n_satellites,
            time_horizon
        )

        # Convert to serializable format
        serialized_plans = {}
        for sat_id, plan in plans.items():
            serialized_plans[sat_id] = {
                'control_sequence': plan['control_sequence'].tolist(),
                'state_trajectory': plan['state_trajectory'].tolist(),
                'total_dv': float(plan['total_dv']),
                'total_dv_ms': float(plan['total_dv'] * 1000),  # m/s
                'status': plan['info']['status'],
                'cost': float(plan['info']['cost'])
            }

        return {
            'plans': serialized_plans,
            'n_satellites': n_satellites,
            'time_horizon': time_horizon,
            'total_formation_dv_ms': sum(p['total_dv_ms'] for p in serialized_plans.values())
        }

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def compute_hcw_matrices(
        self,
        mean_motion: float,
        dt: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Compute Hill-Clohessy-Wiltshire system matrices.

        Args:
            mean_motion: Orbital mean motion in rad/s
            dt: Time step for discrete-time (None for continuous)

        Returns:
            Dictionary with A and B matrices
        """
        if not CONTROL_IMPORTS_AVAILABLE:
            raise RuntimeError("Control modules not available")

        A, B = hill_clohessy_wiltshire_matrices(mean_motion, dt)

        return {
            'A': np.array(A).tolist(),
            'B': np.array(B).tolist(),
            'type': 'discrete' if dt is not None else 'continuous',
            'mean_motion': mean_motion,
            'dt': dt
        }

    def get_controller_info(self, controller_id: str) -> Dict[str, Any]:
        """Get information about a cached controller."""
        if controller_id in self._lqr_controllers:
            controller = self._lqr_controllers[controller_id]
            return {
                'type': 'lqr',
                'id': controller_id,
                'mean_motion': controller.n,
                'discrete': controller.discrete,
                'dt': controller.dt
            }
        elif controller_id in self._mpc_controllers:
            controller = self._mpc_controllers[controller_id]
            return {
                'type': 'mpc',
                'id': controller_id,
                'mean_motion': controller.n,
                'horizon': controller.N,
                'dt': controller.dt
            }
        else:
            raise ValueError(f"Controller {controller_id} not found")

    def list_controllers(self) -> Dict[str, List[str]]:
        """List all cached controllers."""
        return {
            'lqr_controllers': list(self._lqr_controllers.keys()),
            'mpc_controllers': list(self._mpc_controllers.keys()),
            'ekf_filters': list(self._ekf_filters.keys())
        }


# Singleton instance
_control_service = None


def get_control_service() -> ControlService:
    """Get or create control service singleton."""
    global _control_service
    if _control_service is None:
        _control_service = ControlService()
    return _control_service
