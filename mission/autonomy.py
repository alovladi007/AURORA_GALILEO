"""
Station-keeping autonomy (Phase 4 W4.3).

Closed-loop autonomy for the deputy satellite of the GRACE-like
formation: hold the along-track separation box against differential
drag using the REAL control assets (``control.controllers`` LQR on the
Hill-Clohessy-Wiltshire dynamics), with dead-band burn logic and full
delta-v accounting.

Decision logic (the "autonomy"):
- Coast while the position error is inside the dead-band.
- When the error leaves the dead-band, plan a burn campaign: engage
  the LQR law (thrust-limited) until the error settles back inside
  the inner settle radius, then return to coasting.
- Every commanded acceleration is integrated into the delta-v budget;
  each engage/disengage pair is logged as one burn event with its cost.

All state is in the Hill/LVLH frame of the chief, meters and m/s (the
control package convention).
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

import jax

jax.config.update("jax_enable_x64", True)

import jax.numpy as jnp  # noqa: E402

from control.controllers import (  # noqa: E402
    FormationLQRController,
    hill_clohessy_wiltshire_matrices,
)


@dataclass
class AutonomyConfig:
    mean_motion: float = 1.107e-3       # rad/s (~500 km orbit)
    dt_s: float = 10.0                  # control cycle
    deadband_m: float = 50.0            # engage when |pos error| exceeds
    settle_m: float = 10.0              # disengage when back inside
    max_thrust_accel: float = 5e-4      # m/s^2 (thruster limit)
    # Differential drag on the deputy relative to the chief (m/s^2,
    # along-track). Order 1e-7 is realistic for small A/m differences.
    differential_drag: float = 2e-7
    delta_v_budget: float = 5.0         # m/s for the campaign


@dataclass
class BurnEvent:
    t_start: float
    t_end: float = 0.0
    delta_v: float = 0.0


@dataclass
class AutonomyResult:
    times: np.ndarray
    states: np.ndarray                  # (n, 6) Hill-frame
    controlled: np.ndarray              # (n,) bool: thrusting?
    burns: List[BurnEvent] = field(default_factory=list)
    total_delta_v: float = 0.0
    max_pos_error_m: float = 0.0
    budget_exceeded: bool = False


class StationKeepingAutonomy:
    """Dead-band LQR station keeping with fuel accounting."""

    def __init__(self, config: Optional[AutonomyConfig] = None):
        self.config = config or AutonomyConfig()
        cfg = self.config
        # Q/R tuned to ORBITAL scales: commanded acceleration at the
        # dead-band edge (~2e-4 m/s^2 at 50 m) stays under the thruster
        # limit, closed-loop time constant ~40 min. The controller
        # defaults (Q_pos=10, R=0.01) produce poles at -9.4 rad/s and
        # ~1600 m/s^2 commands - deep saturation chatter that LOSES the
        # formation (162 km drift observed in the acceptance test).
        self.controller = FormationLQRController(
            n=cfg.mean_motion,
            Q=jnp.diag(jnp.array([1e-6, 1e-6, 1e-6, 1e-2, 1e-2, 1e-2])),
            R=jnp.eye(3) * 1e6,
        )
        # Continuous HCW matrices for the plant propagation
        self.A, self.B = hill_clohessy_wiltshire_matrices(cfg.mean_motion)
        self.A = np.asarray(self.A)
        self.B = np.asarray(self.B)

    def _plant_step(self, x: np.ndarray, u: np.ndarray) -> np.ndarray:
        """One RK4 step of the HCW plant with control + disturbance."""
        cfg = self.config
        d = np.array([0.0, cfg.differential_drag, 0.0])

        def f(state):
            return self.A @ state + self.B @ (u + d)

        dt = cfg.dt_s
        k1 = f(x)
        k2 = f(x + 0.5 * dt * k1)
        k3 = f(x + 0.5 * dt * k2)
        k4 = f(x + dt * k3)
        return x + dt / 6.0 * (k1 + 2 * k2 + 2 * k3 + k4)

    def run(self, duration_s: float,
            x0: Optional[np.ndarray] = None) -> AutonomyResult:
        """Run the autonomy loop for ``duration_s`` simulated seconds."""
        cfg = self.config
        n_steps = int(duration_s / cfg.dt_s)
        x = np.zeros(6) if x0 is None else np.asarray(x0, dtype=float)

        times = np.zeros(n_steps + 1)
        states = np.zeros((n_steps + 1, 6))
        controlled = np.zeros(n_steps + 1, dtype=bool)
        states[0] = x

        burns: List[BurnEvent] = []
        engaged = False
        total_dv = 0.0
        max_err = float(np.linalg.norm(x[:3]))
        budget_exceeded = False

        for k in range(n_steps):
            t = k * cfg.dt_s
            pos_err = float(np.linalg.norm(x[:3]))
            max_err = max(max_err, pos_err)

            # ── autonomy decision ────────────────────────────────────
            if not engaged and pos_err > cfg.deadband_m:
                engaged = True
                burns.append(BurnEvent(t_start=t))
            elif engaged and pos_err < cfg.settle_m:
                engaged = False
                burns[-1].t_end = t

            if engaged and not budget_exceeded:
                u = np.asarray(
                    self.controller.compute_control(jnp.asarray(x))
                )
                # Thrust limiting (per-axis saturation)
                u = np.clip(u, -cfg.max_thrust_accel, cfg.max_thrust_accel)
                dv = float(np.linalg.norm(u)) * cfg.dt_s
                if total_dv + dv > cfg.delta_v_budget:
                    # FDIR: out of fuel budget — stop thrusting, flag it
                    budget_exceeded = True
                    u = np.zeros(3)
                else:
                    total_dv += dv
                    burns[-1].delta_v += dv
            else:
                u = np.zeros(3)

            x = self._plant_step(x, u)
            times[k + 1] = (k + 1) * cfg.dt_s
            states[k + 1] = x
            controlled[k + 1] = engaged and not budget_exceeded

        if engaged and burns and burns[-1].t_end == 0.0:
            burns[-1].t_end = times[-1]

        return AutonomyResult(
            times=times,
            states=states,
            controlled=controlled,
            burns=burns,
            total_delta_v=total_dv,
            max_pos_error_m=max_err,
            budget_exceeded=budget_exceeded,
        )
