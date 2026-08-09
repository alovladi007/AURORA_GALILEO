"""
Formation Controller
====================

Manages formation flying controllers for satellite constellations.
Wraps the repository-root control/controllers module for gRPC exposure.

Supports:
- LQR (Linear Quadratic Regulator): Optimal control for relative motion
- LQG (Linear Quadratic Gaussian): LQR + Kalman filtering
- MPC (Model Predictive Control): Constrained optimization
- Station-keeping: Fuel-optimal maintenance
- Collision avoidance: Safety monitoring

Example:
    >>> manager = FormationControlManager()
    >>> manager.create_controller(
    ...     formation_id="constellation_1",
    ...     controller_type="lqr",
    ...     mean_motion=0.001,  # rad/s for LEO
    ...     num_satellites=3
    ... )
    >>> control = manager.compute_control(
    ...     formation_id="constellation_1",
    ...     states=satellite_states,
    ...     reference=target_formation
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

# Add repository root to sys.path to import the control package.
# Search upward for a directory containing control/__init__.py: works
# both in the repo checkout (services/control-service/src -> repo root)
# and in the Docker image (where control/ is copied next to src/).
for _cand in Path(__file__).resolve().parents:
    if (_cand / "control" / "__init__.py").exists():
        if str(_cand) not in sys.path:
            sys.path.insert(0, str(_cand))
        break

# Import formation control modules
try:
    import jax.numpy as jnp
    from control.controllers import (
        FormationLQRController,
        hill_clohessy_wiltshire_matrices,
        lqr_gain_continuous,
    )
    _HAS_JAX = True
    _HAS_CONTROLLERS = True
except ImportError as e:
    logger.warning(f"Formation controllers not available: {e}")
    _HAS_JAX = False
    _HAS_CONTROLLERS = False


@dataclass
class FormationState:
    """Relative state of a satellite in a formation."""
    satellite_id: str
    position: np.ndarray  # [x, y, z] relative to reference (km)
    velocity: np.ndarray  # [vx, vy, vz] relative to reference (km/s)
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ThrustCommand:
    """Thrust command for a satellite."""
    satellite_id: str
    thrust: np.ndarray  # [Fx, Fy, Fz] (N)
    duration: float  # seconds
    timestamp: datetime = field(default_factory=datetime.utcnow)


class FormationControlManager:
    """
    Manages formation flying controllers for multiple constellations.

    Each formation has its own controller instance configured with
    specific parameters (mean motion, weights, constraints).
    """

    def __init__(self):
        if not _HAS_CONTROLLERS:
            raise RuntimeError(
                "Formation controllers require JAX and control.controllers module. "
                "Ensure JAX is installed and repo structure is correct."
            )

        self.formations: Dict[str, Dict[str, Any]] = {}
        self.controllers: Dict[str, Any] = {}
        self._lock = None  # Would use threading.Lock() in production

    def create_controller(
        self,
        formation_id: str,
        controller_type: str,
        mean_motion: float,
        num_satellites: int,
        config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a formation controller.

        Args:
            formation_id: Unique identifier for the formation
            controller_type: "lqr", "lqg", "mpc", "station_keeping"
            mean_motion: Orbital mean motion (rad/s), typically ~0.001 for LEO
            num_satellites: Number of satellites in formation
            config: Additional configuration (weights, constraints, etc.)

        Returns:
            Controller metadata
        """
        if formation_id in self.controllers:
            logger.warning(f"Formation {formation_id} already exists, replacing")

        config = config or {}

        # Store formation metadata
        self.formations[formation_id] = {
            "controller_type": controller_type,
            "mean_motion": mean_motion,
            "num_satellites": num_satellites,
            "config": config,
            "created_at": datetime.utcnow()
        }

        # Create controller instance
        if controller_type.lower() == "lqr":
            controller = self._create_lqr_controller(mean_motion, config)
        elif controller_type.lower() == "lqg":
            controller = self._create_lqg_controller(mean_motion, config)
        elif controller_type.lower() == "mpc":
            controller = self._create_mpc_controller(mean_motion, config)
        elif controller_type.lower() == "station_keeping":
            controller = self._create_station_keeping_controller(mean_motion, config)
        else:
            raise ValueError(f"Unknown controller type: {controller_type}")

        self.controllers[formation_id] = controller

        logger.info(
            f"Created {controller_type} controller for formation {formation_id} "
            f"with n={mean_motion:.6f} rad/s, {num_satellites} satellites"
        )

        return {
            "formation_id": formation_id,
            "controller_type": controller_type,
            "mean_motion": mean_motion,
            "num_satellites": num_satellites
        }

    def _create_lqr_controller(
        self,
        mean_motion: float,
        config: Dict[str, Any]
    ) -> FormationLQRController:
        """Create LQR controller with HCW dynamics."""
        # State weights: penalize position more than velocity
        Q_diag = config.get("Q_diag", [100.0, 100.0, 100.0, 1.0, 1.0, 1.0])
        R_diag = config.get("R_diag", [1.0, 1.0, 1.0])

        Q = jnp.diag(jnp.array(Q_diag))
        R = jnp.diag(jnp.array(R_diag))

        # Create HCW system matrices
        A, B = hill_clohessy_wiltshire_matrices(mean_motion)

        # Compute LQR gain
        K, P = lqr_gain_continuous(A, B, Q, R)

        # Create controller
        controller = FormationLQRController(
            n=mean_motion,
            Q=Q,
            R=R
        )

        return controller

    def _create_lqg_controller(
        self,
        mean_motion: float,
        config: Dict[str, Any]
    ) -> Any:
        """Create LQG controller (LQR + Kalman filter)."""
        try:
            from control.controllers import FormationLQGController

            Q = jnp.diag(jnp.array(config.get("Q_diag", [100.0] * 6)))
            R = jnp.diag(jnp.array(config.get("R_diag", [1.0] * 3)))

            # Process and measurement noise covariances
            Q_noise = jnp.diag(jnp.array(config.get("Q_noise_diag", [1e-4] * 6)))
            R_noise = jnp.diag(jnp.array(config.get("R_noise_diag", [1e-2] * 3)))

            controller = FormationLQGController(
                n=mean_motion,
                Q=Q,
                R=R,
                Q_noise=Q_noise,
                R_noise=R_noise
            )

            return controller
        except ImportError:
            logger.error("LQG controller not available")
            raise RuntimeError("LQG controller requires full control.controllers module")

    def _create_mpc_controller(
        self,
        mean_motion: float,
        config: Dict[str, Any]
    ) -> Any:
        """Create MPC controller with constraints."""
        try:
            from control.controllers import FormationMPCController

            horizon = config.get("horizon", 10)

            controller = FormationMPCController(
                n=mean_motion,
                horizon=horizon,
                state_bounds=config.get("state_bounds"),
                control_bounds=config.get("control_bounds")
            )

            return controller
        except ImportError:
            logger.error("MPC controller not available (requires cvxpy)")
            raise RuntimeError("MPC requires cvxpy: pip install cvxpy")

    def _create_station_keeping_controller(
        self,
        mean_motion: float,
        config: Dict[str, Any]
    ) -> Any:
        """Create station-keeping controller."""
        try:
            from control.controllers import DeadBandController

            box_size = config.get("box_size", 1.0)  # km

            controller = DeadBandController(
                n=mean_motion,
                box_half_width=box_size / 2.0
            )

            return controller
        except ImportError:
            logger.error("Station-keeping controller not available")
            raise

    def compute_control(
        self,
        formation_id: str,
        states: List[FormationState],
        reference: Optional[FormationState] = None
    ) -> List[ThrustCommand]:
        """
        Compute control thrust for all satellites in a formation.

        Args:
            formation_id: Formation identifier
            states: Current states of all satellites
            reference: Reference (desired) formation state

        Returns:
            List of thrust commands, one per satellite
        """
        if formation_id not in self.controllers:
            raise ValueError(f"Formation {formation_id} not found")

        controller = self.controllers[formation_id]
        formation_info = self.formations[formation_id]

        # Reference state (origin if not specified)
        if reference is None:
            ref_pos = np.zeros(3)
            ref_vel = np.zeros(3)
        else:
            ref_pos = reference.position
            ref_vel = reference.velocity

        commands = []

        for state in states:
            # Relative state (difference from reference)
            rel_pos = state.position - ref_pos
            rel_vel = state.velocity - ref_vel
            rel_state = np.concatenate([rel_pos, rel_vel])

            # Compute control (u = -K*x for LQR)
            control = controller.compute_control(rel_state)

            # Convert JAX array to NumPy if needed
            if hasattr(control, "to_py"):
                control = np.array(control)

            commands.append(
                ThrustCommand(
                    satellite_id=state.satellite_id,
                    thrust=control,
                    duration=1.0  # 1-second impulse
                )
            )

        logger.debug(
            f"Computed {len(commands)} thrust commands for formation {formation_id}"
        )

        return commands

    def get_controller_info(self, formation_id: str) -> Optional[Dict[str, Any]]:
        """Get controller metadata."""
        return self.formations.get(formation_id)

    def delete_controller(self, formation_id: str) -> bool:
        """Delete a formation controller."""
        if formation_id in self.controllers:
            del self.controllers[formation_id]
            del self.formations[formation_id]
            logger.info(f"Deleted controller for formation {formation_id}")
            return True
        return False

    def list_formations(self) -> List[Dict[str, Any]]:
        """List all active formations."""
        return [
            {
                "formation_id": fid,
                **info
            }
            for fid, info in self.formations.items()
        ]
