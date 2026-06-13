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

try:
    from src.formation_controller import FormationControlManager, FormationState, ThrustCommand
    _HAS_FORMATION = True
except ImportError:
    _HAS_FORMATION = False
    logger.warning("Formation controller not available (JAX not installed or repo structure issue)")

try:
    from src.navigation_ekf import NavigationEKFManager, StateEstimate as NavStateEstimate
    _HAS_NAVIGATION = True
except ImportError:
    _HAS_NAVIGATION = False
    logger.warning("Navigation EKF not available (JAX not installed or repo structure issue)")

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
        if _HAS_FORMATION:
            self.formation_manager = FormationControlManager()
        else:
            self.formation_manager = None

        if _HAS_NAVIGATION:
            self.navigation_manager = NavigationEKFManager()
        else:
            self.navigation_manager = None

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
    # Formation Flying Control
    # ------------------------------------------------------------------
    def CreateFormation(self, request, context):
        """Create a formation flying controller."""
        try:
            if not self.formation_manager:
                context.set_code(grpc.StatusCode.UNIMPLEMENTED)
                context.set_details("Formation control not available (JAX not installed)")
                return control_service_pb2.CreateFormationResponse(
                    response=_response(503, "Formation control not available")
                )

            logger.info(
                f"Creating {request.controller_type} controller for formation {request.formation_id}"
            )

            # Convert config maps to single dict
            config = {k: float(v) for k, v in request.config_float.items()}
            config.update({k: int(v) for k, v in request.config_int.items()})

            result = self.formation_manager.create_controller(
                formation_id=request.formation_id,
                controller_type=request.controller_type,
                mean_motion=request.mean_motion,
                num_satellites=request.num_satellites,
                config=config
            )

            return control_service_pb2.CreateFormationResponse(
                formation_id=result["formation_id"],
                controller_type=result["controller_type"],
                mean_motion=result["mean_motion"],
                num_satellites=result["num_satellites"],
                response=_response(
                    200,
                    f"Formation controller created: {request.controller_type}",
                    {"mean_motion": f"{request.mean_motion:.6f}"}
                )
            )

        except Exception as e:
            logger.error(f"Error creating formation controller: {e}")
            return control_service_pb2.CreateFormationResponse(
                response=_response(500, f"Error: {e}")
            )

    def ComputeFormationControl(self, request, context):
        """Compute formation control thrust commands."""
        try:
            if not self.formation_manager:
                context.set_code(grpc.StatusCode.UNIMPLEMENTED)
                context.set_details("Formation control not available")
                return control_service_pb2.FormationControlResponse()

            # Convert proto states to FormationState objects
            states = []
            for s in request.satellite_states:
                states.append(FormationState(
                    satellite_id=s.satellite_id,
                    position=np.array([
                        s.relative_position.x,
                        s.relative_position.y,
                        s.relative_position.z
                    ]),
                    velocity=np.array([
                        s.relative_velocity.x,
                        s.relative_velocity.y,
                        s.relative_velocity.z
                    ])
                ))

            # Reference state (optional)
            reference = None
            if request.HasField("reference_state"):
                ref = request.reference_state
                reference = FormationState(
                    satellite_id="reference",
                    position=np.array([
                        ref.relative_position.x,
                        ref.relative_position.y,
                        ref.relative_position.z
                    ]),
                    velocity=np.array([
                        ref.relative_velocity.x,
                        ref.relative_velocity.y,
                        ref.relative_velocity.z
                    ])
                )

            # Compute control
            commands = self.formation_manager.compute_control(
                formation_id=request.formation_id,
                states=states,
                reference=reference
            )

            # Convert to proto
            proto_commands = []
            for cmd in commands:
                proto_commands.append(
                    control_service_pb2.ThrustCommand(
                        satellite_id=cmd.satellite_id,
                        thrust=common_pb2.Vector3(
                            x=float(cmd.thrust[0]),
                            y=float(cmd.thrust[1]),
                            z=float(cmd.thrust[2])
                        ),
                        duration=cmd.duration,
                        timestamp=datetime_to_timestamp(cmd.timestamp)
                    )
                )

            return control_service_pb2.FormationControlResponse(
                formation_id=request.formation_id,
                commands=proto_commands,
                response=_response(
                    200,
                    f"Computed {len(commands)} thrust commands",
                    {"num_satellites": len(commands)}
                )
            )

        except Exception as e:
            logger.error(f"Error computing formation control: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return control_service_pb2.FormationControlResponse()

    def GetFormationInfo(self, request, context):
        """Get formation controller information."""
        try:
            if not self.formation_manager:
                context.set_code(grpc.StatusCode.UNIMPLEMENTED)
                return control_service_pb2.FormationInfo()

            info = self.formation_manager.get_controller_info(request.formation_id)
            if not info:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details(f"Formation {request.formation_id} not found")
                return control_service_pb2.FormationInfo()

            return control_service_pb2.FormationInfo(
                formation_id=request.formation_id,
                controller_type=info["controller_type"],
                mean_motion=info["mean_motion"],
                num_satellites=info["num_satellites"],
                created_at=datetime_to_timestamp(info["created_at"])
            )

        except Exception as e:
            logger.error(f"Error getting formation info: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return control_service_pb2.FormationInfo()

    def ListFormations(self, request, context):
        """List all formation controllers."""
        try:
            if not self.formation_manager:
                return control_service_pb2.ListFormationsResponse()

            formations = self.formation_manager.list_formations()

            proto_formations = []
            for f in formations:
                proto_formations.append(
                    control_service_pb2.FormationInfo(
                        formation_id=f["formation_id"],
                        controller_type=f["controller_type"],
                        mean_motion=f["mean_motion"],
                        num_satellites=f["num_satellites"],
                        created_at=datetime_to_timestamp(f["created_at"])
                    )
                )

            return control_service_pb2.ListFormationsResponse(
                formations=proto_formations,
                response=_response(200, f"Found {len(formations)} formations")
            )

        except Exception as e:
            logger.error(f"Error listing formations: {e}")
            return control_service_pb2.ListFormationsResponse()

    def DeleteFormation(self, request, context):
        """Delete a formation controller."""
        try:
            if not self.formation_manager:
                context.set_code(grpc.StatusCode.UNIMPLEMENTED)
                return control_service_pb2.DeleteFormationResponse(success=False)

            success = self.formation_manager.delete_controller(request.formation_id)

            return control_service_pb2.DeleteFormationResponse(
                success=success,
                response=_response(
                    200 if success else 404,
                    f"Formation {'deleted' if success else 'not found'}"
                )
            )

        except Exception as e:
            logger.error(f"Error deleting formation: {e}")
            return control_service_pb2.DeleteFormationResponse(success=False)

    # ------------------------------------------------------------------
    # Navigation and State Estimation (EKF)
    # ------------------------------------------------------------------
    def CreateNavigationFilter(self, request, context):
        """Create an EKF for satellite navigation."""
        try:
            if not self.navigation_manager:
                context.set_code(grpc.StatusCode.UNIMPLEMENTED)
                context.set_details("Navigation EKF not available (JAX not installed)")
                return control_service_pb2.CreateNavigationFilterResponse(
                    response=_response(503, "Navigation EKF not available")
                )

            logger.info(
                f"Creating {request.dynamics_type} EKF for {request.satellite_id}"
            )

            # Convert config
            config = {k: float(v) for k, v in request.config_float.items()}

            # Convert initial state/covariance if provided
            initial_state = np.array(request.initial_state) if request.initial_state else None
            initial_cov = None
            if request.initial_covariance:
                cov_flat = np.array(request.initial_covariance)
                initial_cov = cov_flat.reshape(6, 6)

            result = self.navigation_manager.create_filter(
                satellite_id=request.satellite_id,
                dynamics_type=request.dynamics_type,
                measurement_type=request.measurement_type,
                initial_state=initial_state,
                initial_covariance=initial_cov,
                config=config
            )

            return control_service_pb2.CreateNavigationFilterResponse(
                satellite_id=result["satellite_id"],
                dynamics_type=result["dynamics_type"],
                measurement_type=result["measurement_type"],
                dt=result["dt"],
                response=_response(
                    200,
                    f"Navigation filter created: {request.dynamics_type}",
                    {"measurement_type": request.measurement_type}
                )
            )

        except Exception as e:
            logger.error(f"Error creating navigation filter: {e}")
            return control_service_pb2.CreateNavigationFilterResponse(
                response=_response(500, f"Error: {e}")
            )

    def ProcessMeasurement(self, request, context):
        """Process a navigation measurement and update state estimate."""
        try:
            if not self.navigation_manager:
                context.set_code(grpc.StatusCode.UNIMPLEMENTED)
                return control_service_pb2.ProcessMeasurementResponse()

            meas = request.measurement
            measurement = np.array(meas.measurement)
            control = np.array(meas.control) if meas.control else None
            timestamp = meas.timestamp.ToDatetime() if meas.timestamp.seconds else None

            estimate = self.navigation_manager.process_measurement(
                satellite_id=meas.satellite_id,
                measurement=measurement,
                timestamp=timestamp,
                control=control
            )

            # Convert to proto
            proto_estimate = control_service_pb2.StateEstimate(
                satellite_id=estimate.satellite_id,
                state=estimate.state.tolist(),
                covariance=estimate.covariance.flatten().tolist(),
                timestamp=datetime_to_timestamp(estimate.timestamp)
            )

            if estimate.measurement_residual is not None:
                proto_estimate.measurement_residual.extend(
                    estimate.measurement_residual.tolist()
                )

            # Compute position uncertainty (km)
            pos_uncertainty = np.sqrt(np.trace(estimate.covariance[:3, :3]))

            return control_service_pb2.ProcessMeasurementResponse(
                estimate=proto_estimate,
                response=_response(
                    200,
                    "Measurement processed",
                    {"position_uncertainty_km": f"{pos_uncertainty:.6f}"}
                )
            )

        except Exception as e:
            logger.error(f"Error processing measurement: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return control_service_pb2.ProcessMeasurementResponse()

    def GetStateEstimate(self, request, context):
        """Get current state estimate."""
        try:
            if not self.navigation_manager:
                context.set_code(grpc.StatusCode.UNIMPLEMENTED)
                return control_service_pb2.GetStateEstimateResponse()

            estimate = self.navigation_manager.get_state_estimate(request.satellite_id)
            if not estimate:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details(f"No filter found for {request.satellite_id}")
                return control_service_pb2.GetStateEstimateResponse()

            proto_estimate = control_service_pb2.StateEstimate(
                satellite_id=estimate.satellite_id,
                state=estimate.state.tolist(),
                covariance=estimate.covariance.flatten().tolist(),
                timestamp=datetime_to_timestamp(estimate.timestamp)
            )

            return control_service_pb2.GetStateEstimateResponse(
                estimate=proto_estimate,
                response=_response(200, "State estimate retrieved")
            )

        except Exception as e:
            logger.error(f"Error getting state estimate: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return control_service_pb2.GetStateEstimateResponse()

    def PredictAhead(self, request, context):
        """Predict state evolution over multiple time steps."""
        try:
            if not self.navigation_manager:
                context.set_code(grpc.StatusCode.UNIMPLEMENTED)
                return control_service_pb2.PredictAheadResponse()

            # Extract control sequence if provided
            control_sequence = None
            if request.control_sequence:
                control_sequence = [
                    np.array(ctrl.control) for ctrl in request.control_sequence
                ]

            predictions = self.navigation_manager.predict_ahead(
                satellite_id=request.satellite_id,
                steps=request.steps,
                control_sequence=control_sequence
            )

            # Convert to proto
            proto_predictions = []
            for pred in predictions:
                proto_predictions.append(
                    control_service_pb2.StateEstimate(
                        satellite_id=pred.satellite_id,
                        state=pred.state.tolist(),
                        covariance=pred.covariance.flatten().tolist(),
                        timestamp=datetime_to_timestamp(pred.timestamp)
                    )
                )

            return control_service_pb2.PredictAheadResponse(
                predictions=proto_predictions,
                response=_response(
                    200,
                    f"Predicted {len(predictions)} time steps",
                    {"steps": request.steps}
                )
            )

        except Exception as e:
            logger.error(f"Error predicting ahead: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return control_service_pb2.PredictAheadResponse()

    def ListNavigationFilters(self, request, context):
        """List all navigation filters."""
        try:
            if not self.navigation_manager:
                return control_service_pb2.ListNavigationFiltersResponse()

            filters = self.navigation_manager.list_filters()

            proto_filters = []
            for f in filters:
                proto_filters.append(
                    control_service_pb2.NavigationFilterInfo(
                        satellite_id=f["satellite_id"],
                        dynamics_type=f["dynamics_type"],
                        measurement_type=f["measurement_type"],
                        created_at=datetime_to_timestamp(f["created_at"])
                    )
                )

            return control_service_pb2.ListNavigationFiltersResponse(
                filters=proto_filters,
                response=_response(200, f"Found {len(filters)} filters")
            )

        except Exception as e:
            logger.error(f"Error listing navigation filters: {e}")
            return control_service_pb2.ListNavigationFiltersResponse()

    def DeleteNavigationFilter(self, request, context):
        """Delete a navigation filter."""
        try:
            if not self.navigation_manager:
                context.set_code(grpc.StatusCode.UNIMPLEMENTED)
                return control_service_pb2.DeleteNavigationFilterResponse(success=False)

            success = self.navigation_manager.delete_filter(request.satellite_id)

            return control_service_pb2.DeleteNavigationFilterResponse(
                success=success,
                response=_response(
                    200 if success else 404,
                    f"Filter {'deleted' if success else 'not found'}"
                )
            )

        except Exception as e:
            logger.error(f"Error deleting navigation filter: {e}")
            return control_service_pb2.DeleteNavigationFilterResponse(success=False)

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
