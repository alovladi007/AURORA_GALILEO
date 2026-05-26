"""
Control Service gRPC implementation
"""

import grpc
import logging
import math
from datetime import datetime, timedelta
from typing import List

from src.gen import control_service_pb2, control_service_pb2_grpc, common_pb2
from google.protobuf.timestamp_pb2 import Timestamp

logger = logging.getLogger(__name__)


def datetime_to_timestamp(dt: datetime) -> Timestamp:
    """Convert datetime to protobuf Timestamp"""
    ts = Timestamp()
    ts.FromDatetime(dt)
    return ts


def timestamp_to_datetime(ts: Timestamp) -> datetime:
    """Convert protobuf Timestamp to datetime"""
    return ts.ToDatetime()


class ControlServicer(control_service_pb2_grpc.ControlServiceServicer):
    """Control Service implementation"""

    def __init__(self):
        self.missions = {}  # Track mission plans
        self.simulations = {}  # Track simulation jobs

    def CreateMissionPlan(self, request, context):
        """Create mission plan"""
        try:
            logger.info(f"Creating mission plan: {request.mission_name}")

            # Create plan
            plan_id = f"plan_{datetime.utcnow().timestamp()}"
            self.missions[plan_id] = {
                "mission_name": request.mission_name,
                "satellite_ids": list(request.satellite_ids),
                "status": "created",
                "created_at": datetime.utcnow()
            }

            # In production, this would:
            # 1. Validate satellite availability
            # 2. Optimize mission timeline
            # 3. Generate maneuver sequences
            # 4. Store plan in database

            return control_service_pb2.MissionPlanResponse(
                plan_id=plan_id,
                status="created",
                message=f"Mission plan '{request.mission_name}' created"
            )

        except Exception as e:
            logger.error(f"Error creating mission plan: {e}")
            return control_service_pb2.MissionPlanResponse(
                plan_id="",
                status="failed",
                message=f"Error: {str(e)}"
            )

    def GetMissionPlan(self, request, context):
        """Get mission plan details"""
        try:
            plan = self.missions.get(request.plan_id)
            if not plan:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details(f"Plan {request.plan_id} not found")
                return control_service_pb2.MissionPlan()

            # Mock plan details
            return control_service_pb2.MissionPlan(
                plan_id=request.plan_id,
                mission_name=plan["mission_name"],
                satellite_ids=plan["satellite_ids"],
                start_time=datetime_to_timestamp(datetime.utcnow()),
                end_time=datetime_to_timestamp(datetime.utcnow() + timedelta(days=7)),
                status="active",
                objectives=["gravity_mapping", "orbit_maintenance"],
                metadata={"priority": "high", "coverage": "global"}
            )

        except Exception as e:
            logger.error(f"Error getting mission plan: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return control_service_pb2.MissionPlan()

    def ExecuteManeuver(self, request, context):
        """Execute satellite maneuver"""
        try:
            logger.info(f"Executing maneuver for satellite {request.satellite_id}")

            # In production, this would:
            # 1. Validate maneuver parameters
            # 2. Check satellite constraints
            # 3. Send commands to satellite
            # 4. Monitor execution

            return common_pb2.Response(
                success=True,
                message=f"Maneuver executed for {request.satellite_id}",
                data={
                    "maneuver_id": f"mnv_{datetime.utcnow().timestamp()}",
                    "delta_v_applied": str(request.delta_v),
                    "execution_time": datetime.utcnow().isoformat()
                }
            )

        except Exception as e:
            logger.error(f"Error executing maneuver: {e}")
            return common_pb2.Response(
                success=False,
                message=f"Error: {str(e)}",
                error=common_pb2.Error(
                    code="MANEUVER_ERROR",
                    message=str(e)
                )
            )

    def PropagateOrbit(self, request, context):
        """Propagate satellite orbit"""
        try:
            logger.info(f"Propagating orbit for satellite {request.satellite_id}")

            # Simple circular orbit propagation (mock)
            states = []
            start_time = timestamp_to_datetime(request.start_time)
            duration = request.duration
            timestep = 60.0  # 1 minute steps

            # Mock orbital parameters
            altitude = 550000.0  # 550 km
            radius = 6371000.0 + altitude  # Earth radius + altitude
            velocity = math.sqrt(398600.4418e9 / radius)  # Orbital velocity
            period = 2 * math.pi * radius / velocity  # Orbital period

            num_steps = min(int(duration / timestep), 1000)  # Limit to 1000 points

            for i in range(num_steps):
                t = i * timestep
                current_time = start_time + timedelta(seconds=t)

                # Circular orbit position (simplified)
                angle = (t / period) * 2 * math.pi
                x = radius * math.cos(angle)
                y = radius * math.sin(angle)
                z = 0.0

                vx = -velocity * math.sin(angle)
                vy = velocity * math.cos(angle)
                vz = 0.0

                states.append(
                    control_service_pb2.OrbitState(
                        timestamp=datetime_to_timestamp(current_time),
                        position=common_pb2.Vector3(x=x, y=y, z=z),
                        velocity=common_pb2.Vector3(x=vx, y=vy, z=vz)
                    )
                )

            logger.info(f"Propagated {len(states)} orbital states")

            return control_service_pb2.PropagationResponse(
                satellite_id=request.satellite_id,
                states=states,
                propagator_type="keplerian",
                message=f"Propagated {len(states)} states"
            )

        except Exception as e:
            logger.error(f"Error propagating orbit: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return control_service_pb2.PropagationResponse()

    def SimulateMission(self, request, context):
        """Simulate entire mission"""
        try:
            logger.info(f"Simulating mission: {request.mission_name}")

            # Create simulation job
            job_id = f"sim_{datetime.utcnow().timestamp()}"
            self.simulations[job_id] = {
                "mission_name": request.mission_name,
                "status": "running",
                "started_at": datetime.utcnow()
            }

            return control_service_pb2.SimulationResponse(
                job_id=job_id,
                status="running",
                message=f"Simulation '{request.mission_name}' started",
                estimated_time=1800.0  # Mock: 30 minutes
            )

        except Exception as e:
            logger.error(f"Error simulating mission: {e}")
            return control_service_pb2.SimulationResponse(
                job_id="",
                status="failed",
                message=f"Error: {str(e)}",
                estimated_time=0.0
            )

    def GetSimulationStatus(self, request, context):
        """Get simulation status"""
        try:
            sim = self.simulations.get(request.job_id)
            if not sim:
                return control_service_pb2.SimulationStatusResponse(
                    job_id=request.job_id,
                    status="not_found",
                    progress=0.0,
                    message="Simulation not found"
                )

            # Mock progress
            return control_service_pb2.SimulationStatusResponse(
                job_id=request.job_id,
                status=sim["status"],
                progress=0.55,
                current_time=datetime_to_timestamp(datetime.utcnow()),
                message="Simulation in progress"
            )

        except Exception as e:
            logger.error(f"Error getting simulation status: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return control_service_pb2.SimulationStatusResponse()

    def HealthCheck(self, request, context):
        """Health check endpoint"""
        try:
            return common_pb2.HealthCheckResponse(
                status=common_pb2.HealthCheckResponse.SERVING
            )
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return common_pb2.HealthCheckResponse(
                status=common_pb2.HealthCheckResponse.NOT_SERVING,
                details={"error": str(e)}
            )
