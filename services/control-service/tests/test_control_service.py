"""
Control Service gRPC Tests
=========================

Tests the ControlServicer against real generated protobuf stubs: mission
planning, maneuver execution, orbit propagation, and simulation.
"""

import time

import pytest

from src.gen import control_service_pb2, common_pb2
from google.protobuf.timestamp_pb2 import Timestamp


class TestMissionPlanning:

    def test_create_mission_plan(self, servicer, context):
        req = control_service_pb2.CreateMissionPlanRequest(
            name="Gravity Survey",
            description="LEO gravity mapping",
            satellite_ids=["SAT001", "SAT002"],
        )
        resp = servicer.CreateMissionPlan(req, context)
        assert resp.plan_id
        assert resp.response.status_code == 200
        # Delta-v budget should be reported in metadata.
        assert "delta_v_budget_mps" in resp.response.metadata

    def test_get_mission_plan(self, servicer, context):
        create = servicer.CreateMissionPlan(
            control_service_pb2.CreateMissionPlanRequest(
                name="Test Plan", satellite_ids=["SAT001"]),
            context,
        )
        plan = servicer.GetMissionPlan(
            control_service_pb2.MissionPlanQuery(plan_id=create.plan_id),
            context,
        )
        assert plan.plan_id == create.plan_id
        assert plan.name == "Test Plan"
        assert "SAT001" in plan.satellite_ids

    def test_get_missing_plan_sets_not_found(self, servicer, context):
        servicer.GetMissionPlan(
            control_service_pb2.MissionPlanQuery(plan_id="missing"), context)
        import grpc
        assert context.code == grpc.StatusCode.NOT_FOUND


class TestManeuver:

    def test_execute_maneuver(self, servicer, context):
        req = control_service_pb2.ManeuverRequest(
            satellite_id="SAT001",
            maneuver_type="station_keeping",
            delta_v=common_pb2.Vector3(x=0.3, y=0.4, z=0.0),
        )
        resp = servicer.ExecuteManeuver(req, context)
        assert resp.status_code == 200
        # |delta_v| = 0.5 m/s
        assert float(resp.metadata["delta_v_mps"]) == pytest.approx(0.5, abs=0.01)


class TestPropagation:

    def test_propagate_default_leo(self, servicer, context):
        req = control_service_pb2.PropagationRequest(
            satellite_id="SAT001",
            duration=5400,
            timestep=60,
        )
        resp = servicer.PropagateOrbit(req, context)
        assert resp.satellite_id == "SAT001"
        assert resp.propagator_type == "two_body_j2_rk4"
        assert len(resp.states) > 1
        # Each state must carry a position and velocity.
        s0 = resp.states[0]
        assert s0.position.x != 0.0 or s0.position.y != 0.0 or s0.position.z != 0.0

    def test_propagate_with_initial_state(self, servicer, context):
        init = control_service_pb2.OrbitState(
            position=common_pb2.Vector3(x=6878.137, y=0.0, z=0.0),
            velocity=common_pb2.Vector3(x=0.0, y=7.6126, z=0.0),
        )
        req = control_service_pb2.PropagationRequest(
            satellite_id="SAT002",
            duration=600,
            timestep=60,
            initial_state=init,
        )
        resp = servicer.PropagateOrbit(req, context)
        assert len(resp.states) > 1


class TestSimulation:

    def test_simulate_and_status(self, servicer, context):
        sim = servicer.SimulateMission(
            control_service_pb2.SimulationRequest(
                mission_name="Sim1",
                config={"duration_hours": "1", "satellite_ids": "SAT001"}),
            context,
        )
        assert sim.job_id
        assert sim.status in ("queued", "running")

        # Poll a few times for status.
        for _ in range(50):
            status = servicer.GetSimulationStatus(
                control_service_pb2.SimulationStatusRequest(job_id=sim.job_id),
                context,
            )
            if status.status in ("completed", "failed"):
                break
            time.sleep(0.1)
        assert status.job_id == sim.job_id


class TestHealth:

    def test_health_check(self, servicer, context):
        resp = servicer.HealthCheck(common_pb2.HealthCheckRequest(), context)
        assert resp.status == common_pb2.HealthCheckResponse.SERVING
