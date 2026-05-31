"""
Mission Planning & Simulation
=============================

In-memory mission plan store and an asynchronous mission simulator that
propagates each satellite over the mission window using the J2 orbit
propagator. Provides delta-v budgeting for maneuvers.
"""

from __future__ import annotations

import logging
import math
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import numpy as np

from src.propagator import (GM_EARTH, R_EARTH, circular_state, orbital_elements,
                            propagate)

logger = logging.getLogger(__name__)


@dataclass
class MissionPlan:
    plan_id: str
    name: str
    description: str
    satellite_ids: List[str]
    start_time: datetime
    end_time: datetime
    status: str = "created"
    objectives: List[str] = field(default_factory=list)
    delta_v_budget: float = 0.0  # m/s


@dataclass
class SimulationJob:
    job_id: str
    mission_name: str
    status: str = "queued"
    progress: float = 0.0
    current_time: datetime = field(default_factory=datetime.utcnow)
    message: str = "queued"
    created_at: datetime = field(default_factory=datetime.utcnow)
    summary: Dict = field(default_factory=dict)
    error: Optional[str] = None


class MissionManager:
    """Manages mission plans and asynchronous mission simulations."""

    def __init__(self):
        self.plans: Dict[str, MissionPlan] = {}
        self.simulations: Dict[str, SimulationJob] = {}
        self._lock = threading.Lock()

    # -- mission plans -----------------------------------------------------
    def create_plan(self, name: str, description: str, satellite_ids: List[str],
                    start_time: datetime, end_time: datetime,
                    objectives: Optional[List[str]] = None) -> MissionPlan:
        plan_id = f"plan_{uuid.uuid4().hex[:12]}"
        duration_days = max((end_time - start_time).total_seconds() / 86400.0, 0.0)
        # Rough station-keeping delta-v budget: ~3 m/s per satellite per 30 days
        # of LEO drag compensation (order-of-magnitude planning figure).
        budget = len(satellite_ids) * 3.0 * (duration_days / 30.0)
        plan = MissionPlan(
            plan_id=plan_id,
            name=name,
            description=description,
            satellite_ids=list(satellite_ids),
            start_time=start_time,
            end_time=end_time,
            status="created",
            objectives=list(objectives or []),
            delta_v_budget=budget,
        )
        with self._lock:
            self.plans[plan_id] = plan
        logger.info("Created mission plan %s (%s)", plan_id, name)
        return plan

    def get_plan(self, plan_id: str) -> Optional[MissionPlan]:
        with self._lock:
            return self.plans.get(plan_id)

    # -- maneuvers ---------------------------------------------------------
    @staticmethod
    def maneuver_cost(delta_v_vec) -> float:
        """Delta-v magnitude (m/s) for a maneuver request's Vector3."""
        return float(math.sqrt(delta_v_vec.x ** 2 + delta_v_vec.y ** 2
                               + delta_v_vec.z ** 2))

    # -- simulation --------------------------------------------------------
    def start_simulation(self, mission_name: str, config: Dict[str, str]) -> SimulationJob:
        job_id = f"sim_{uuid.uuid4().hex[:12]}"
        job = SimulationJob(job_id=job_id, mission_name=mission_name)
        with self._lock:
            self.simulations[job_id] = job
        thread = threading.Thread(target=self._run_simulation,
                                  args=(job, config or {}), daemon=True)
        thread.start()
        return job

    def get_simulation(self, job_id: str) -> Optional[SimulationJob]:
        with self._lock:
            return self.simulations.get(job_id)

    def _run_simulation(self, job: SimulationJob, config: Dict[str, str]) -> None:
        try:
            job.status = "running"
            n_sats = int(config.get("n_satellites", 2))
            altitude = float(config.get("altitude_km", 500.0))
            inclination = float(config.get("inclination_deg", 89.0))
            duration_h = float(config.get("duration_hours", 24.0))
            timestep = float(config.get("timestep_s", 30.0))

            duration_s = duration_h * 3600.0
            decay_total = 0.0
            sat_summaries = []

            for sat in range(n_sats):
                job.message = f"Propagating satellite {sat + 1}/{n_sats}"
                # Slightly stagger altitudes to emulate a formation.
                state0 = circular_state(altitude + sat * 1.0, inclination)
                elems0 = orbital_elements(state0)
                times, states = propagate(state0, duration_s, timestep,
                                          include_j2=True)
                elems1 = orbital_elements(states[-1])
                decay = elems0["altitude_km"] - elems1["altitude_km"]
                decay_total += decay
                sat_summaries.append({
                    "satellite": sat,
                    "initial_altitude_km": round(elems0["altitude_km"], 3),
                    "final_altitude_km": round(elems1["altitude_km"], 3),
                    "period_min": round(elems0["period_s"] / 60.0, 2),
                    "inclination_deg": round(elems0["inclination_deg"], 2),
                    "n_states": len(times),
                })
                job.progress = (sat + 1) / n_sats
                job.current_time = job.created_at + timedelta(seconds=duration_s)

            job.summary = {
                "n_satellites": n_sats,
                "duration_hours": duration_h,
                "mean_altitude_decay_km": round(decay_total / max(n_sats, 1), 4),
                "satellites": sat_summaries,
            }
            job.status = "completed"
            job.message = (
                f"Simulated {n_sats} satellites over {duration_h:.1f} h; "
                f"mean J2 altitude drift {job.summary['mean_altitude_decay_km']:.4f} km"
            )
            logger.info("Simulation %s complete: %s", job.job_id, job.message)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Simulation %s failed", job.job_id)
            job.status = "failed"
            job.error = str(exc)
            job.message = f"Simulation failed: {exc}"
