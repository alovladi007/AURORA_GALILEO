"""
Navigation EKF Manager
======================

Manages Extended Kalman Filters for satellite state estimation.
Wraps control/navigation/ekf.py for gRPC exposure.

Supports:
- GPS position measurements (3D)
- Orbital dynamics (two-body + J2 perturbations)
- Multi-sensor fusion (GPS, IMU, laser ranging)
- Covariance tracking (uncertainty quantification)

Example:
    >>> manager = NavigationEKFManager()
    >>> manager.create_filter(
    ...     satellite_id="SAT-001",
    ...     dynamics_type="two_body_j2",
    ...     measurement_type="gps"
    ... )
    >>> estimate = manager.process_measurement(
    ...     satellite_id="SAT-001",
    ...     measurement=gps_position
    ... )
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# Add repository root to sys.path
repo_root = Path(__file__).parents[3]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

# Import navigation modules
try:
    import jax.numpy as jnp
    from control.navigation import ExtendedKalmanFilter, OrbitalEKF, RelativeNavigationEKF
    _HAS_EKF = True
except ImportError as e:
    logger.warning(f"EKF not available: {e}")
    _HAS_EKF = False


@dataclass
class StateEstimate:
    """State estimate from EKF."""
    satellite_id: str
    state: np.ndarray  # [rx, ry, rz, vx, vy, vz] (km, km/s)
    covariance: np.ndarray  # 6x6 error covariance
    timestamp: datetime = field(default_factory=datetime.utcnow)
    measurement_residual: Optional[np.ndarray] = None


class NavigationEKFManager:
    """
    Manages EKF state estimators for satellite navigation.

    Each satellite has its own filter instance configured with
    specific dynamics and measurement models.
    """

    def __init__(self):
        if not _HAS_EKF:
            raise RuntimeError(
                "Navigation EKF requires JAX and control.navigation module. "
                "Ensure JAX is installed and repo structure is correct."
            )

        self.filters: Dict[str, Any] = {}
        self.filter_configs: Dict[str, Dict[str, Any]] = {}

    def create_filter(
        self,
        satellite_id: str,
        dynamics_type: str = "two_body_j2",
        measurement_type: str = "gps",
        initial_state: Optional[np.ndarray] = None,
        initial_covariance: Optional[np.ndarray] = None,
        config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create an EKF for a satellite.

        Args:
            satellite_id: Unique identifier
            dynamics_type: "two_body", "two_body_j2", "relative_hcw"
            measurement_type: "gps", "laser", "imu"
            initial_state: Initial state estimate [rx,ry,rz,vx,vy,vz] (km, km/s)
            initial_covariance: Initial 6x6 covariance matrix
            config: Additional configuration (noise levels, etc.)

        Returns:
            Filter metadata
        """
        if satellite_id in self.filters:
            logger.warning(f"Filter for {satellite_id} already exists, replacing")

        config = config or {}

        # Store configuration
        self.filter_configs[satellite_id] = {
            "dynamics_type": dynamics_type,
            "measurement_type": measurement_type,
            "config": config,
            "created_at": datetime.utcnow()
        }

        # Process noise covariance (position and velocity uncertainty growth)
        Q_diag = config.get("Q_diag", [1e-6, 1e-6, 1e-6, 1e-9, 1e-9, 1e-9])
        Q = jnp.diag(jnp.array(Q_diag))

        # Measurement noise covariance
        if measurement_type == "gps":
            # GPS: ~1m position accuracy
            R_diag = config.get("R_diag", [1e-6, 1e-6, 1e-6])  # km^2
        elif measurement_type == "laser":
            # Laser ranging: ~1cm accuracy
            R_diag = config.get("R_diag", [1e-10, 1e-10, 1e-10])
        else:
            R_diag = config.get("R_diag", [1.0, 1.0, 1.0])

        R = jnp.diag(jnp.array(R_diag))

        # Time step
        dt = config.get("dt", 1.0)  # seconds

        # Create appropriate filter
        if dynamics_type == "relative_hcw":
            # Relative navigation for formation flying
            mean_motion = config.get("mean_motion", 0.001)  # rad/s
            ekf = RelativeNavigationEKF(n=mean_motion, Q=Q, R=R, dt=dt)
        else:
            # Absolute orbital navigation
            ekf = OrbitalEKF(
                perturbations=["j2"] if "j2" in dynamics_type else [],
                Q=Q,
                R=R,
                dt=dt
            )

        # Set initial state if provided
        if initial_state is not None:
            ekf.x = jnp.array(initial_state)

        if initial_covariance is not None:
            ekf.P = jnp.array(initial_covariance)
        else:
            # Default: 1km position, 0.01 km/s velocity uncertainty
            ekf.P = jnp.diag(jnp.array([1.0, 1.0, 1.0, 0.01, 0.01, 0.01]))

        self.filters[satellite_id] = ekf

        logger.info(
            f"Created {dynamics_type} EKF for {satellite_id} "
            f"with {measurement_type} measurements"
        )

        return {
            "satellite_id": satellite_id,
            "dynamics_type": dynamics_type,
            "measurement_type": measurement_type,
            "dt": dt
        }

    def process_measurement(
        self,
        satellite_id: str,
        measurement: np.ndarray,
        timestamp: Optional[datetime] = None,
        control: Optional[np.ndarray] = None
    ) -> StateEstimate:
        """
        Process a measurement and update state estimate.

        Args:
            satellite_id: Satellite identifier
            measurement: Measurement vector (e.g., GPS position [x,y,z] in km)
            timestamp: Measurement timestamp
            control: Optional control input [Fx, Fy, Fz] (N)

        Returns:
            Updated state estimate
        """
        if satellite_id not in self.filters:
            raise ValueError(f"No filter found for {satellite_id}")

        ekf = self.filters[satellite_id]
        timestamp = timestamp or datetime.utcnow()

        # Convert to JAX arrays
        y = jnp.array(measurement)
        u = jnp.array(control) if control is not None else None

        # EKF predict step
        x_pred, P_pred = ekf.predict(ekf.x, ekf.P, u, 0.0)

        # EKF update step
        x_est, P_est, residual = ekf.update(x_pred, P_pred, y, 0.0)

        # Update filter state
        ekf.x = x_est
        ekf.P = P_est

        # Convert back to numpy
        state = np.array(x_est)
        covariance = np.array(P_est)
        residual_np = np.array(residual)

        logger.debug(
            f"Processed measurement for {satellite_id}: "
            f"position uncertainty = {np.sqrt(np.trace(covariance[:3, :3])):.3f} km"
        )

        return StateEstimate(
            satellite_id=satellite_id,
            state=state,
            covariance=covariance,
            timestamp=timestamp,
            measurement_residual=residual_np
        )

    def get_state_estimate(self, satellite_id: str) -> Optional[StateEstimate]:
        """Get current state estimate without measurement update."""
        if satellite_id not in self.filters:
            return None

        ekf = self.filters[satellite_id]

        return StateEstimate(
            satellite_id=satellite_id,
            state=np.array(ekf.x),
            covariance=np.array(ekf.P),
            timestamp=datetime.utcnow()
        )

    def predict_ahead(
        self,
        satellite_id: str,
        steps: int,
        control_sequence: Optional[List[np.ndarray]] = None
    ) -> List[StateEstimate]:
        """
        Predict state evolution over multiple time steps.

        Args:
            satellite_id: Satellite identifier
            steps: Number of time steps to predict
            control_sequence: Optional control inputs for each step

        Returns:
            List of predicted state estimates
        """
        if satellite_id not in self.filters:
            raise ValueError(f"No filter found for {satellite_id}")

        ekf = self.filters[satellite_id]
        predictions = []

        x_current = ekf.x
        P_current = ekf.P

        for i in range(steps):
            u = None
            if control_sequence and i < len(control_sequence):
                u = jnp.array(control_sequence[i])

            x_pred, P_pred = ekf.predict(x_current, P_current, u, 0.0)

            predictions.append(
                StateEstimate(
                    satellite_id=satellite_id,
                    state=np.array(x_pred),
                    covariance=np.array(P_pred),
                    timestamp=datetime.utcnow()
                )
            )

            x_current = x_pred
            P_current = P_pred

        return predictions

    def get_filter_info(self, satellite_id: str) -> Optional[Dict[str, Any]]:
        """Get filter configuration."""
        return self.filter_configs.get(satellite_id)

    def delete_filter(self, satellite_id: str) -> bool:
        """Delete a filter."""
        if satellite_id in self.filters:
            del self.filters[satellite_id]
            del self.filter_configs[satellite_id]
            logger.info(f"Deleted filter for {satellite_id}")
            return True
        return False

    def list_filters(self) -> List[Dict[str, Any]]:
        """List all active filters."""
        return [
            {
                "satellite_id": sat_id,
                **info
            }
            for sat_id, info in self.filter_configs.items()
        ]
