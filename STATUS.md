# GALILEO V2.0 — Project Status

**Last Updated**: 2026-07-17
**Single source of truth.** Historical status documents are archived
(immutable) under `docs/history/`. Do not add new status files at the
repo root — update this one.

---

## Honest Assessment

A five-audit, evidence-based review (2026-07) found the platform at
roughly **35–40% of its intended scope**, not the 92–95% previously
claimed. Full findings with file:line evidence:
[`PLATFORM_AUDIT_2026.md`](PLATFORM_AUDIT_2026.md).

The remediation and build program (Phases 0–6 over 18 months, with
per-phase verification gates):
[`MASTER_BUILD_PROMPT_18_MONTHS.md`](MASTER_BUILD_PROMPT_18_MONTHS.md).

## Current Phase: Gate 0 PASSED; Phase 1 W1.1+W1.2+W1.3(core) complete; Phase 2 W2.3 auth live

**Phase 1 W1.2 (2026-08):** relativity sign errors fixed (GPS +38
us/day check passes), GNSS -2r.v/c range correction, leap-second
boundary round-trips, clock-noise generators consistent with their own
ADEV formulas, overlapping ADEV estimator corrected, CCSDS deframer
stream-safe, POD covariance/DOP corrected.

**Phase 1 W1.3 (core):** dynamic batch least-squares orbit
determination (`pod/orbit_determination.py`) with two-body+J2 force
model and JAX-autodiff measurement partials; closed-loop recovery of
a LEO epoch state to <10 cm from 0.1 m noisy positions with credible
formal covariance — the Gate 1 POD criterion on positions.
gate0-smoke.yml runs the full compose stack + auth round-trip in CI.

**Phase 1 W1.4:** sim/synthetic.py unit chain made physical (correct
nanoGal-free HCW quasi-static baseline response, meters end-to-end,
orbit-corrected residual baselines; telemetry coherence/SNR/incidence
derived from the noise model instead of RNG). Emulator channels now
physically coupled (vibration/thermal/laser reach the fringes;
resolvable piezo scan; visibility-degradation model), verified by 5
new coupling tests; websockets>=11 handler compatibility.

**Phase 2 W2.4 (contract):** the gateway now exposes 28 REST paths (13
new routes backed by real gRPC RPCs: gravity ingest/query, export,
model lifecycle, inversion list/results/cancel, satellite/command
status, orbit prediction). docs/api/openapi.json is the contract of
record (scripts/export_openapi.py) and tests/contract/ enforces that
every UI client call exists in the spec and that the spec is not
stale — the phantom-endpoint drift class is now structurally
impossible. Verified live: authenticated gravity ingest -> gRPC ->
TimescaleDB -> query round-trip. Also fixed en route: gateway log
formatter (every record errored on trace_id), sub/user_id claim
mismatch, data-service ORM/DDL schema drift (proto is the schema of
record; composite PKs satisfy hypertable partitioning), Redis
eviction/persistence for the auth store, stale-pool self-healing.

**Phase 2 W2.1 (monolith retired):** the FastAPI monolith (api/) and
its Celery layer (ops/*.py) are archived under legacy/ — the gRPC
microservices + gateway are the only backend. The monolith's api/
package name was shadowing the gateway's api package in test runs
(root cause of the CI service-suite failures). ops/db and ops/nginx
remain live (mounted by compose). Also fixed from CI: orchestrator/
bridge now use Kafka only when KAFKA_BOOTSTRAP_SERVERS is set (library
presence alone caused infinite retries and starved the in-process
queue), tuner job-id collisions within the same second, and the
conditional-mlflow test patch. All five service suites green.

**Phase 2 W2.2 (schema authority):** Alembic rebuilt around the
canonical schema — env.py targets the data-service ORM; the initial
migration executes ops/db/timescale_setup.sql (now fully idempotent,
including guarded add_job registration). Verified live: upgrade on a
container-bootstrapped DB is a no-op with no duplicate jobs; a fresh
empty database bootstraps completely from the migration alone (3
hypertables). Both checks now run in the Gate 0 CI job.

**Phase 2 W2.5 (observability observes):** postgres/redis exporters
and Alertmanager (valid static config — the env-interpolation config
that failed validation is gone) added to the canonical stack; alert
rules reference only actually-emitted metrics (gateway http_*/
circuit_breaker_state, exporter pg_up/redis_up). Verified live: all 4
Prometheus scrape targets UP, 5 rules loaded and healthy, pg_up=1.
Target/rule sanity now runs in the Gate 0 CI job.

**Phase 3 W3.1 (first end-to-end mission pipeline), verified live:**
`scripts/run_mission_scenario.py` generates a GRACE-like two-satellite
formation with the validated two-body+J2 dynamics, synthesizes
telemetry and gravity observables from the real degree-6 spherical-
harmonic field (values match the analytic J2 anchors to 5%), ingests
everything through the authenticated gateway -> gRPC -> TimescaleDB
path (364 records), queries it back with provenance tags intact, and
runs dynamic orbit determination on the ingested telemetry:
epoch state recovered to 0.30 m / 0.30 mm/s, post-fit RMS 1.6 m
(the injected 1 m noise floor). 7 new acceptance tests in
tests/mission/.

**Phase 3 W3.3 (inversion consumes real data), verified live:** the
inversion engine's observed-data path now uses an honest observation
operator (selection of populated grid cells + Laplacian completion)
instead of the RNG point-mass kernel, with 3 acceptance tests proving
>0.95 recovery correlation on track-sampled fields and honest failure
on empty data. StartInversion implemented in the servicer (the gateway
called an RPC that did not exist); GetInversionStatus now returns the
proto-declared GetInversionStatusResponse (the legacy message failed
wire deserialization on every call). RBAC is now enforced (the old
checker returned True unconditionally) and three phantom Permission
members fixed. Verified live end-to-end: 172 ingested mission
measurements fetched via gRPC, binned to a 16x16 grid (29 ground-track
cells), inverted, and polled to completion through the gateway.
Mission script now runs all 7 stages.

**Phase 3 W3.4 + Phase 5 W5.2 (first product view), verified live:**
GetDensityModel implemented (georeferenced model grid with bounds and
statistics) and exposed as GET /api/v1/inversions/{id}/model (spec now
29 paths, contract tests green). The served model visibly carries the
J2 physics (row means 907 -> 104 -> 762 mGal from south pole to
equator to north). New UI page /gravity: real JWT sign-in, trigger
inversions on the ingested mission data, poll to completion, and
render the anomaly map from the served grid on a canvas — with error
states, no client-side fallbacks. UI builds clean (0 type errors).

**Phase 3 flagship KPI — closed-loop anomaly recovery (LIVE in the
test suite):** tests/mission/test_closed_loop_recovery.py injects an
80 mGal ground-fixed Gaussian anomaly under an actual overflight of
the two-satellite formation, generates observables from the real
field, bins them exactly as the platform's fetcher does, removes the
reference field via a twin background scenario (identical tracks and
noise draws — standard gravimetry practice), and inverts through the
platform's masked Tikhonov path. Acceptance: signal survives binning
(>50% of injected amplitude), peak recovered within 2 grid cells of
the injection point, recovered amplitude >=60% of the observed signal
without amplification, and far-field spurious structure <15% of the
peak. All four gates pass. (The benchmark's first version exposed a
real lesson now encoded in it: inverting against the raw +/-2300 mGal
J2 background crushes local signals — reference-field removal is
mandatory, as in every real processor.)

**Gate 0 (2026-08-09, verified on a live Docker stack):** 14/14
containers healthy from the canonical `docker-compose.yaml`; gateway
/health reports all four gRPC services connected; register -> JWT
login -> /auth/me -> refresh verified end-to-end against the live
stack (Redis-backed users, bcrypt, 401 on bad credentials); workflow
engine serving registered workflows; UI `next build` green with zero
type errors and no fabricated-telemetry fallbacks.

Completed (W0.4 — package-level breakage):
- [x] `time/` renamed to `gtime/` (was shadowing the stdlib and
      permanently unimportable; all timing/relativity code was dead)
- [x] `pod/` importable again (`dynamics.py` was a truncated file);
      real piecewise-constant RTN empirical accelerations implemented
- [x] `telemetry/` exports real CCSDS classes; phantom exports removed
- [x] `ops/tasks.py` phantom imports fixed; tasks that reported fake
      success now fail honestly with `NotImplementedError`
- [x] `pytest.ini` repaired (markers were silently unregistered;
      `--cov=bench` forced on every run); tests/ package shadowing fixed
- [x] `scripts/init-db.sql` no longer aborts container first boot
- [x] `pod/gtime/telemetry/emulator/...` added to packaging
- [x] Dishonest `/phase5` UI page removed

Completed (W0.1 — repo hygiene):
- [x] Legacy `GALILEO_Session_*` snapshot trees deleted
- [x] Duplicate root frontend configs deleted; `api/main_backup.py`,
      `api/main_integrated.py` deleted
- [x] ~60 contradictory status/session docs archived to `docs/history/`

In progress / next (see master prompt for full list):
- [x] W0.3 CI repair (python matrix, mkdocs job, artifact paths)
- [x] W0.2 single canonical docker-compose stack (deploy/legacy-compose/ archived)
- [x] Gate 0: compose up -> 14/14 containers healthy, verified live
- [ ] Gate 0 in CI: nightly compose-up smoke job (next)

## Test Baseline (repo-root suite, 2026-07-17)

```
Root suite: 309 passed, 0 failed. Service suites: data 10, ml 16,
control 14, inversion 25, gateway 35 — all passing.
```

All 17 previously-failing tests are fixed by real implementations (see
Phase 1 commits): corrected J2/element/drag/SRP physics with 19 new
reference-validation tests, a real spherical-harmonic gravity model
cross-validated against the independent closed-form J2, a Newtonian
FFT forward model in sim/synthetic.py, corrected TV smoothing floor,
corrected heterodyne phase-noise scaling and a deterministic timing
card mock, STAC timezone handling, and the previously-phantom
BenchmarkResult class.

Per-service suites under `services/*/tests/` run separately in CI
(`services-tests.yml`) and remain the most reliable part of the stack.
