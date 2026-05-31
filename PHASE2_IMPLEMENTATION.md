# GALILEO V2.0 — Phase 2 Implementation

Phase 2 implements the scientific-computing core for the **Control Service** and
connects the **Inversion Service** to real data from the Data Service.

## Summary

| Service | Before | After |
|---------|--------|-------|
| **Control Service** | Mock plans, `success=`-style Response crashes, simplified circular orbit, mock simulation; **CreateMissionPlan/GetMissionPlan mismatched the proto** | Real two-body + J2 RK4 orbit propagation, mission planning with delta-v budgeting, async J2 mission simulation — aligned to `control_service.proto` |
| **Inversion Service** | Synthetic-only inversion | Optionally fetches **real gravity data from the Data Service** via gRPC and inverts it; synthetic fallback preserved |

## Critical bugs found & fixed (Control Service)

Like the Data Service in Phase 1, the Control Service code did not match its
proto and would crash:

1. **`CreateMissionPlan` read `request.mission_name` and returned
   `MissionPlanResponse`.** The RPC is `CreateMissionPlan(CreateMissionPlanRequest)
   returns (CreateMissionPlanResponse)`; the request field is `name`. Fixed.
2. **`GetMissionPlan` set `MissionPlan.mission_name/objectives/metadata`** —
   none of which exist on the `MissionPlan` message (`name`, `description`,
   `commands`, `created_by`). Fixed to use the real fields.
3. **`ExecuteManeuver` returned `common_pb2.Response(success=, data=, error=)`**
   — those fields don't exist. Fixed to `status_code`/`message`/`metadata`.

## New modules

### Control Service (`services/control-service/src/`)
- `propagator.py` — self-contained NumPy orbit propagator: two-body gravity +
  J2 oblateness perturbation, classical RK4 integrator, circular-orbit
  initialisation, and osculating orbital-element extraction. (The repo-root
  `sim/dynamics` uses JAX, which is not in the service image, so the physics is
  vendored in NumPy.)
- `mission.py` — `MissionManager`: in-memory mission-plan store with a
  station-keeping delta-v budget estimate, maneuver delta-v costing, and an
  asynchronous mission **simulator** that propagates each satellite over the
  mission window and reports J2-driven altitude variation.

### Inversion Service (`services/inversion-service/src/`)
- `data_fetcher.py` — `GravityDataFetcher`: gRPC client to the Data Service that
  queries gravity measurements (by satellite / bounding box) and bins them onto
  a regular lat/lon grid (mean per cell). Degrades to `None` (synthetic
  fallback) when the Data Service is unreachable.
- `inversion_engine.py` — extended so `start(...)` accepts `observed_data`; when
  present the solvers invert the real gridded gravity field instead of the
  synthetic forward problem, and the job reports `data_source="data_service"`.

## Verified results (local integration tests)

- Control: mission plan created (delta-v budget computed), maneuver delta-v
  costed (0.51 m/s), **orbit propagated with two-body + J2 RK4** (94.6-min LEO
  period, correct nodal drift), async simulation of 2 satellites over 6 h
  completes with a J2 altitude-variation summary.
- Inversion: real-data path inverts an externally supplied gridded gravity
  field end-to-end (`data_source=data_service`); the gRPC fetcher returns a
  clean `None` and the engine falls back to synthetic when the Data Service is
  absent.

## Graceful degradation

The inversion data fetcher and all Phase 1 optional integrations continue to
degrade safely, so every service runs without the full infrastructure and adds
capability when it is present.

## Follow-ups (Phase 3+)

- API Gateway WebSocket bridge over the Kafka topics for live UI telemetry.
- Frontend: replace mock data hooks with real gateway calls; visualise real
  inversion fields.
- Persist ML and Control jobs to the database (parity with inversion).
- Formation-flying controllers (`control/controllers/*`) and EKF navigation.
