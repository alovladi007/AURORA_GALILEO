# GALILEO V2.0 — Phase 1 Implementation

This document records the Phase 1 work that transitions the core microservices
from **mock** implementations to **real** ones, as identified in the platform
deep-analysis roadmap.

## Summary

| Service | Before | After |
|---------|--------|-------|
| **Data Service** | Mock streaming, no validation, stub export; **code mismatched its own proto** | Batch ingest + validation/QC, Kafka (+ in-process) streaming, CSV/JSON/Parquet export, TimescaleDB hypertables — fully aligned to `data_service.proto` |
| **ML Service** | Mock job IDs, hardcoded 75% progress, fake predictions | Real async training (NumPy MLP) with epoch progress, model registry, real inference, MLflow hooks |
| **Inversion Service** | Mock job IDs, hardcoded 65% progress, fake S3 URLs | Real Tikhonov / Gauss-Newton / Bayesian solvers with forward gravity operator, progress tracking, NetCDF/npz result serialization, optional DB persistence |

All three services were integration-tested end-to-end against their **real
generated protobuf stubs**.

## Critical bugs found & fixed

The deep analysis assumed services worked with mocks; in fact several RPCs
would have **crashed at runtime** because the code did not match the proto:

1. **Data Service was written against a non-existent schema.** The code assumed
   singular-record ingest, `gravity_x/y/z` + `magnitude`, a `region` message,
   `pagination.offset/limit`, and `common_pb2.Response(success=, data=)`. The
   actual `data_service.proto` uses **batch** ingest, a scalar `gravity_value`
   (mGal) + `uncertainty` + string `quality_flag`, flat lat/lon bounds,
   `pagination.page/page_size`, and `Response.status_code/message/metadata`.
   The entire service was rewritten to match.
2. **`ListModelsResponse.models` is `repeated Model`**, not `ModelInfo`. The
   mock used `ModelInfo` and would have raised `TypeError`. Fixed to emit
   `Model` messages (`GetModel` still returns the simplified `ModelInfo`).
3. **`ListInversionsResponse.jobs` is `repeated InversionJob`**, not an
   `inversions` field of `InversionJobInfo`. Fixed to emit `InversionJob`.
4. **`common.Response` has no `success`/`data`/`error` fields.** All such
   usages were replaced with `status_code` + `message` + `metadata`.
5. **`session.execute("SELECT 1")`** would fail on SQLAlchemy 2.0; wrapped in
   `text()`.

## New modules

### Data Service (`services/data-service/src/`)
- `validation.py` — range / plausibility checks, running z-score outlier
  detector, quality-flag bitmask.
- `streaming.py` — `StreamBroker`: Kafka producer with an in-process pub/sub
  fan-out fallback used by the gRPC `Stream*` RPCs. Degrades gracefully when
  Kafka is unavailable.
- `exporters.py` — `DataExporter`: CSV / JSON / Parquet writers with optional
  MinIO/S3 upload.
- `database.py` — gravity model realigned to proto; **TimescaleDB hypertable +
  compression** setup (no-op on vanilla PostgreSQL).

### ML Service (`services/ml-service/src/`)
- `training_orchestrator.py` — `TrainingOrchestrator` runs real async training
  (NumPy 2-layer MLP, full-batch gradient descent) on a synthetic
  gravity-anomaly regression task, with epoch-level progress, validation
  metrics (MSE/MAE/R²), an in-memory model registry, and best-effort MLflow
  tracking.

### Inversion Service (`services/inversion-service/src/`)
- `inversion_engine.py` — point-mass forward gravity operator, Laplacian
  smoothing regularizer, vendored `TikhonovSolver` (with L-curve λ selection),
  `GaussNewtonSolver`, `BayesianMAPSolver`; async `InversionEngine` with
  progress callbacks and cancellation.
- `result_writer.py` — `ResultWriter`: NetCDF (or compressed `.npz`) field
  output + JSON coefficients, optional MinIO/S3 upload.
- `persistence.py` — `JobStore`: optional SQLAlchemy persistence of inversion
  jobs (`inversion_jobs` table); graceful no-op without `DATABASE_URL`.

## Verified results (local integration tests)

- Data: 2-record batch ingest → 1 accepted, 1 rejected (bad latitude);
  query/pagination, CSV export, health check all pass.
- ML: `pinn` model trains 200 epochs → **val R² ≈ 0.72**; registry + inference
  return sensible gravity-anomaly predictions.
- Inversion: `tikhonov` recovers a synthetic anomaly with **residual ≈ 1e-3**,
  `convergence_achieved=True`; Gauss-Newton and Bayesian solvers also run to
  completion; result artifacts serialized; list/cancel work.

## Graceful degradation

All optional dependencies (Kafka, MinIO, netCDF4, pyarrow, MLflow,
TimescaleDB, a database for persistence) degrade to safe fallbacks, so the
services run in a minimal environment and light up extra capabilities when the
infrastructure is present.

## Notable follow-ups (later phases)

- Wire the inversion engine to **fetch real gravity data from the Data Service**
  (currently uses a synthetic forward model + ground truth).
- Persist ML/Control jobs to the database (ML registry is currently in-memory).
- WebSocket bridge in the API Gateway over the Kafka topics
  (`galileo.telemetry`, `galileo.gravity`).
- Replace duplicate "full vs simplified" proto messages with a single set.
