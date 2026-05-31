"""
Control Service gRPC implementation

Real orbit propagation (two-body + J2, RK4), mission planning with delta-v
budgeting, and asynchronous mission simulation. Aligned with
proto/control_service.proto (CreateMissionPlanRequest/Response, MissionPlan,
ManeuverRequest -> common.Response, PropagationRequest/Response, etc.).
"""

import grpc
import logging
import math
from datetime import datetime, timedelta

import numpy as np

from src.gen import control_service_pb2, control_service_pb2_grpc, common_pb2
from google.protobuf.timestamp_pb2 import Timestamp

from src.propagator import propagate, circular_state, R_EARTH
from src.mission import MissionManager

logger = logging.getLogger(__name__)


def datetime_to_timestamp(dt: datetime) -> Timestamp:
    ts = Timestamp()
    ts.FromDatetime(dt)
    return ts


def timestamp_to_datetime(ts: Timestamp) -> datetime:
    return ts.ToDatetime()


def _response(status_code: int, message: str, metadata: dict = None) -> common_pb2.Response:
    ts = Timestamp()
    ts.FromDatetime(datetime.utcnow())
    return common_pb2.Response(
        status_code=status_code,
        message=message,
        timestamp=ts,
        metadata={k: str(v) for k, v in (metadata or {}).items()},
    )


class ControlServicer(control_service_pb2_grpc.ControlServiceServicer):
    """Control Service implementation backed by real orbital dynamics."""

    def __init__(self):
        self.manager = MissionManager()

    # ------------------------------------------------------------------
    # Mission planning
    # ------------------------------------------------------------------
    def CreateMissionPlan(self, request, context):
        """Create a mission plan (CreateMissionPlanRequest -> Response)."""
        try:
            logger.info("Creating mission plan: %s", request.name)
            start = (timestamp_to_datetime(request.start_time)
                     if request.start_time.seconds else datetime.utcnow())
            end = (timestamp_to_datetime(request.end_time)
                   if request.end_time.seconds else start + timedelta(days=7))
            plan = self.manager.create_plan(
                name=request.name,
                description=request.description,
                satellite_ids=list(request.satellite_ids),
                start_time=start,
                end_time=end,
            )
            return control_service_pb2.CreateMissionPlanResponse(
                plan_id=plan.plan_id,
                response=_response(200, f"Mission plan '{plan.name}' created", {
                    "delta_v_budget_mps": round(plan.delta_v_budget, 3),
                    "satellites": len(plan.satellite_ids),
                }),
            )
        except Exception as e:
            logger.error("Error creating mission plan: %s", e)
            return control_service_pb2.CreateMissionPlanResponse(
                response=_response(500, f"Error: {e}")
            )

    def GetMissionPlan(self, request, context):
        """Get a mission plan (MissionPlanQuery -> MissionPlan)."""
        try:
            plan = self.manager.get_plan(request.plan_id)
            if not plan:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details(f"Plan {request.plan_id} not found")
                return control_service_pb2.MissionPlan()
            return control_service_pb2.MissionPlan(
                plan_id=plan.plan_id,
                name=plan.name,
                description=plan.description,
                satellite_ids=plan.satellite_ids,
                start_time=datetime_to_timestamp(plan.start_time),
                end_time=datetime_to_timestamp(plan.end_time),
                status=plan.status,
            )
        except Exception as e:
            logger.error("Error getting mission plan: %s", e)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return control_service_pb2.MissionPlan()

    # ------------------------------------------------------------------
    # Maneuvers
    # ------------------------------------------------------------------
    def ExecuteManeuver(self, request, context):
        """Execute a satellite maneuver (ManeuverRequest -> common.Response)."""
        try:
            logger.info("Executing maneuver for satellite %s", request.satellite_id)
            delta_v = self.manager.maneuver_cost(request.delta_v)
            exec_time = (timestamp_to_datetime(request.execution_time)
                         if request.execution_time.seconds else datetime.utcnow())
            return _response(200, f"Maneuver executed for {request.satellite_id}", {
                "maneuver_id": f"mnv_{datetime.utcnow().timestamp()}",
                "maneuver_type": request.maneuver_type,
                "delta_v_mps": round(delta_v, 4),
                "execution_time": exec_time.isoformat(),
            })
        except Exception as e:
            logger.error("Error executing maneuver: %s", e)
            return _response(500, f"Error: {e}")

    # ------------------------------------------------------------------
    # Orbit propagation
    # ------------------------------------------------------------------
    def PropagateOrbit(self, request, context):
        """Propagate an orbit using two-body + J2 RK4 integration."""
        try:
            logger.info("Propagating orbit for satellite %s", request.satellite_id)
            start_time = (timestamp_to_datetime(request.start_time)
                          if request.start_time.seconds else datetime.utcnow())
            duration = request.duration or 5400  # default ~1 orbit
            timestep = request.timestep or 60

            # Build the initial state from the request if provided, else a
            # default near-polar circular LEO at 500 km.
            init = request.initial_state
            if init.position.x or init.position.y or init.position.z:
                state0 = np.array([
                    init.position.x, init.position.y, init.position.z,
                    init.velocity.x, init.velocity.y, init.velocity.z,
                ], dtype=float)
            else:
                state0 = circular_state(500.0, 89.0)

            times, states = propagate(state0, float(duration), float(timestep),
                                      include_j2=True)

            out_states = []
            for t, s in zip(times, states):
                out_states.append(control_service_pb2.OrbitState(
                    timestamp=datetime_to_timestamp(start_time + timedelta(seconds=t)),
                    position=common_pb2.Vector3(x=float(s[0]), y=float(s[1]), z=float(s[2])),
                    velocity=common_pb2.Vector3(x=float(s[3]), y=float(s[4]), z=float(s[5])),
                ))

            logger.info("Propagated %d orbital states", len(out_states))
            return control_service_pb2.PropagationResponse(
                satellite_id=request.satellite_id,
                states=out_states,
                propagator_type="two_body_j2_rk4",
                message=f"Propagated {len(out_states)} states over {duration}s",
            )
        except Exception as e:
            logger.error("Error propagating orbit: %s", e)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return control_service_pb2.PropagationResponse()

    # ------------------------------------------------------------------
    # Simulation
    # ------------------------------------------------------------------
    def SimulateMission(self, request, context):
        """Start an asynchronous mission simulation."""
        try:
            logger.info("Simulating mission: %s", request.mission_name)
            job = self.manager.start_simulation(request.mission_name, dict(request.config))
            return control_service_pb2.SimulationResponse(
                job_id=job.job_id,
                status=job.status,
                message=f"Simulation '{request.mission_name}' started",
                estimated_time=float(dict(request.config).get("duration_hours", 24)) * 2.0,
            )
        except Exception as e:
            logger.error("Error simulating mission: %s", e)
            return control_service_pb2.SimulationResponse(
                job_id="", status="failed", message=f"Error: {e}", estimated_time=0.0
            )

    def GetSimulationStatus(self, request, context):
        """Get the status of a mission simulation."""
        try:
            sim = self.manager.get_simulation(request.job_id)
            if not sim:
                return control_service_pb2.SimulationStatusResponse(
                    job_id=request.job_id,
                    status="not_found",
                    progress=0.0,
                    message="Simulation not found",
                )
            return control_service_pb2.SimulationStatusResponse(
                job_id=sim.job_id,
                status=sim.status,
                progress=sim.progress,
                current_time=datetime_to_timestamp(sim.current_time),
                message=sim.message,
            )
        except Exception as e:
            logger.error("Error getting simulation status: %s", e)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return control_service_pb2.SimulationStatusResponse()

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------
    def HealthCheck(self, request, context):
        try:
            return common_pb2.HealthCheckResponse(
                status=common_pb2.HealthCheckResponse.SERVING
            )
        except Exception as e:
            logger.error("Health check failed: %s", e)
            return common_pb2.HealthCheckResponse(
                status=common_pb2.HealthCheckResponse.NOT_SERVING,
                details={"error": str(e)},
            )
