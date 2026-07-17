# GALILEO V2.0 → v3.0 — Master Implementation Prompt (18 Months)

> **How to use this document**: This is a self-contained build directive. Hand any phase (or any single workstream) to an engineering team or an AI coding agent verbatim. Every phase has entry criteria, exit criteria, and verification gates. Findings referenced as "AUDIT §N" point to `PLATFORM_AUDIT_2026.md`.

---

## 0. Mission Statement

Transform GALILEO V2.0 from a partially-integrated scaffold into a **fully functional, scientifically validated, deployable satellite gravimetry platform**: synthetic mission data flows from orbit/sensor simulation through ingestion, precise orbit determination, gravity-field inversion, and ML enhancement to versioned data products rendered live in a mission-operations UI — with every number on every screen traceable to a real computation.

## 0.1 Non-Negotiable Ground Rules (apply to every phase, every PR)

1. **No fabricated data presented as real.** Synthetic data is allowed (it's a simulation platform) but must be *labeled* synthetic end-to-end (API field `data_provenance: synthetic|replay|live`). Client-side `Math.random()` fallbacks that impersonate telemetry are forbidden; a failed fetch must render an error state. (AUDIT §4)
2. **No claim without a gate.** A feature is "done" only when: (a) unit tests assert its actual behavior, (b) it is reachable from a running deployment, (c) CI proves both on every push. Status documents may only report what CI verifies.
3. **One source of truth each** for: architecture (one deployment story), DB schema (alembic only), API contract (OpenAPI + proto files, generated clients), ports (one `PORTS.md` generated from compose), status (one `STATUS.md`, auto-updated from CI).
4. **Physics changes require a validation test** against an independent reference (analytic solution, published test case, or cross-check tool such as Orekit/GMAT outputs committed as fixtures). No numerics PR merges without one.
5. **Delete, don't deprecate.** Dead code, legacy trees, and contradictory docs are removed in the same PR that supersedes them.
6. **Definition of Done for the whole program**: `docker compose up` from a clean clone → all services healthy → demo mission scenario runs end-to-end → UI shows the resulting gravity anomaly map — in under 15 minutes, on CI, nightly.

---

## PHASE 0 — Truth & Stabilization (Month 1)

*Goal: a repo where green means green.*

### Workstreams
- **W0.1 Repo hygiene**: Delete `GALILEO_Session_*` trees, root-level duplicate frontend configs (`package.json`, `next.config.js`, `index.html`, `tsconfig.json`), `api/main_backup.py`, `api/main_integrated.py`, `auth.py`-vs-`auth_v2.py` duplication, tracked `.pkl/.npy/.png` binaries (move needed fixtures to Git LFS or regenerate in CI). Collapse the ~60 root status files into `docs/history/` (archived, immutable) + a single living `STATUS.md`.
- **W0.2 Single architecture decision**: Adopt the **gRPC microservices** stack as canonical (it has the best tests, real TimescaleDB, real Kafka bridge). The FastAPI monolith (`api/`, `ops/`) becomes a compatibility shim scheduled for deletion in Phase 2. Archive `docker-compose.yml` (monolith); make `docker-compose.microservices.yaml` + `docker-compose.infrastructure.yaml` merge into ONE canonical `docker-compose.yaml` with correct Kafka advertised listeners, DB init that actually runs (fix `scripts/init-db.sql` CREATE DATABASE-in-DO-block bug), and creation of `mlflow`/`airflow` databases. (AUDIT §5)
- **W0.3 CI repair**: Python matrix = 3.11/3.12 only; remove the mkdocs job until mkdocs exists (Phase 6) or add a minimal `mkdocs.yml` now; fix artifact paths (`.next/` not `dist/`); make `services-tests.yml` the required gate; keep security scans non-blocking but *reported*. Split the monolithic `requirements.txt` into per-component requirement sets with a constraints file; unpin the unresolvable airflow+feast+torch flat pin. Fix `pytest.ini` (`--cov=bench` covers the wrong package).
- **W0.4 Immediate breakage fixes** (each ≤1 day): rename `time/` → `gtime/` (stdlib shadow, AUDIT §2.6) and fix all imports/tests; fix `pod/dynamics.py` truncation (restore or stub honestly with `NotImplementedError` + remove phantom `__init__` exports); fix `telemetry/__init__.py` phantom exports; fix `ops/tasks.py` phantom `sim.keplerian.propagate_j2` imports; remove or repair the `/phase5` static page; delete the hardcoded `/home/claude/...` path.

### Exit criteria (Gate 0)
- [ ] Clean clone → `docker compose up` → all containers healthy (no crash loops) on CI.
- [ ] `pytest` collects with **zero collection errors** repo-wide; every currently-passing test still passes.
- [ ] CI required checks green on main branch.
- [ ] Exactly one compose file, one `PORTS.md` (matching it), one `STATUS.md`.

---

## PHASE 1 — Scientific Core Correctness (Months 2–4)

*Goal: the physics is right, proven right, and stays right.*

### W1.1 Dynamics & gravity (Month 2)
- Fix the four verified defects: J2 sign (`perturbations.py:104`), element-conversion rotation (`keplerian.py:168`), drag/SRP unit factors (`:229,:310`), JIT crashes (make `atmospheric_density` traceable via `jnp.select`; mark static args on propagators). **Each fix ships with a reference test**: J2 secular RAAN drift for a sun-synchronous orbit vs published value; element round-trip vs Vallado test cases; drag decay vs analytical King-Hele approximation; propagator vs two-body analytic solution at 1e-9 relative tolerance.
- **Implement real spherical-harmonic gravity** (replaces the all-zeros `sim/gravity.py`): stable Legendre recursion (Holmes-Featherstone normalization), Cunningham/Pines acceleration, EGM2008 coefficient loader (degree/order 120 minimum, file fetched/cached via a data script, checksum-pinned), geoid heights. Validate against ICGEM computed values at 10 test points (fixtures committed).
- Add Kepler equation solver (Newton + Danby fallback), true adaptive integrator (Dormand-Prince 8(7) in JAX via `diffrax` or hand-rolled), third-body (Sun/Moon, low-precision ephemerides), solid-Earth tide (IERS 2010 anelastic, degree-2 only to start).

### W1.2 Time & relativity (Month 3, after `gtime` rename)
- Fix leap-second lookup keyed by TAI vs UTC boundary; fix `redshift_doppler` sign errors; replace pseudo-`relativistic_range_correction` with the standard −2r·v/c² periodic correction; correct ADEV noise-slope taxonomy in both implementations; implement true MDEV/Hadamard or delete the mislabeled ones.
- Validation: GPS clock rate offset (+38.6 µs/day composite) reproduced to 1%; leap-second boundary tests; ADEV slopes recovered from synthesized noise of each type.

### W1.3 POD becomes real (Months 3–4)
- Add the missing dynamics layer: two-body + J2 (reuse W1.1) force model inside batch least squares (multi-epoch, state = position/velocity/clock/ambiguities), a correct SRIF (single convention, QR-based time and measurement updates), and RTS smoothing over the *filter* states. Fix covariance double-scaling (`estimators.py:161`) and DOP ENU rotation.
- Complete `doppler_residual` with an observed-Doppler field; add carrier-phase ionosphere sign; empirical accelerations (piecewise-constant RTN) — the module `pod/dynamics.py` promises them; make it true.
- Validation: recover a truth orbit from synthetic GNSS (generated by W1.1 propagator + measurement noise) to <10 cm 3D RMS; overlap statistics; residual whiteness.

### W1.4 Telemetry & sensing (Month 4)
- Fix CCSDS deframer over-read (`ccsds.py:149`) with a two-packet stream regression test; add CRC-16; implement the promised Protobuf/Avro encoders or delete them from `__all__`; adopt a standard CUC time code.
- Emulator: couple the channels (vibration → phase jitter, thermal → OPD drift, laser RIN → intensity) so injected events propagate physically; fix OPD scan rate to a resolvable regime; version the WebSocket handler signature for `websockets>=11`.
- `sim/synthetic.py`: rewrite `density_to_gravity` as a proper Newtonian kernel sum (vectorized, all source cells to each observation point, correct lever arm `h+z`), fix the nanoGal definition, derive telemetry attributes from the phase model instead of RNG, route all randomness through the seeded generator.

### Exit criteria (Gate 1)
- [ ] `pytest tests/unit tests/time tests/pod tests/telemetry` — all green, including ≥25 new reference-validation tests.
- [ ] A `scripts/validate_physics.py` CI job reproduces: J2 RAAN drift, GPS relativistic rate, EGM2008 spot values, POD 10 cm recovery — nightly.
- [ ] `pyproject.toml` packages and installs `gtime`, `pod`, `telemetry`, `emulator`; a wheel installs and imports cleanly in a fresh venv on CI.

---

## PHASE 2 — Platform Backbone (Months 5–7)

*Goal: one coherent, secure, observable system.*

### W2.1 Kill the monolith (Month 5)
- Port the ~15 genuinely-used monolith endpoints (emulator, calibration, tasks, db admin) into the gateway/microservices; delete `api/` and `ops/` FastAPI apps; Celery workers become service-owned consumers or are replaced by the existing Kafka workflow engine. One backend, one port map.

### W2.2 Database single source of truth (Month 5)
- Alembic becomes authoritative: regenerate the initial migration from the *microservices* schema (`timescale_setup.sql` content, including hypertables via `op.execute`), reconcile `ops/models.py` drift (id columns, `metadata` naming) or delete the stale models with the monolith. Migration test in CI: empty DB → `alembic upgrade head` → services boot → smoke queries pass.

### W2.3 Real authentication & authorization (Month 6)
- One JWT issuer service (or Keycloak if operator SSO is desired): register/login/refresh, RBAC roles (viewer/operator/admin), key from secrets manager — delete both hardcoded SECRET_KEYs. Gateway enforces on REST + WebSocket; gRPC interceptors validate service-to-service mTLS or tokens. UI: real signin/signout pages, session-gated routes, remove `demo-token-for-testing`.

### W2.4 API contract & generated clients (Month 6)
- Gateway publishes a complete OpenAPI spec; **UI API client is generated from it** (openapi-typescript) — this permanently eliminates the endpoint-name-drift class of bug (AUDIT §4). Contract tests in CI: every UI-called path must exist in the spec; every spec path must have a handler test.

### W2.5 Observability that observes (Month 7)
- Prometheus scrapes what exists: add postgres/redis/kafka exporters to compose; add `/metrics` to every service (the gateway module already exists — mount and scrape it); fix Alertmanager config (no env interpolation); rewrite alert rules against emitted metric names only; Grafana dashboards checked by a CI job that queries each panel expression against a live stack and fails on "no data".
- OpenTelemetry traces gateway→gRPC→DB wired to Jaeger; correlation IDs end-to-end.

### W2.6 Deployment story (Month 7)
- Helm chart re-targeted at the microservices (matching the Istio config), rendered + `kubeval`-validated in CI, images built and pushed to GHCR by CI with SBOM (syft) + signing (cosign); `helm install` smoke-tested against kind/k3d in CI. Terraform: single root, remote state documented; drop the second conflicting root.

### Exit criteria (Gate 2)
- [ ] One backend; UI client generated from OpenAPI; contract test green.
- [ ] Login required and working end-to-end; zero hardcoded secrets (gitleaks gate turned blocking).
- [ ] `helm install` on kind in CI: all pods Ready, smoke API calls pass.
- [ ] Grafana panel-validation job green; at least 5 meaningful alerts firing correctly in a chaos test (kill a service → alert within 2 min).

---

## PHASE 3 — End-to-End Science Pipeline (Months 8–10)

*Goal: the platform produces its first honest scientific product.*

### W3.1 Mission scenario generator (Month 8)
- A `galileo-mission` CLI: define a 2-satellite low-low SST formation (GRACE-like), propagate 30 days with the Phase-1 dynamics, generate inter-satellite ranging (from `sensing/` phase model + Phase-1 emulator noise), GNSS observables, and attitude/housekeeping telemetry — streamed through the *real* ingestion path (CCSDS frames → Kafka → data-service → TimescaleDB). Every record tagged `data_provenance: synthetic`.

### W3.2 L1 processing (Month 8–9)
- POD service consumes GNSS from the DB (not RNG): orbits + covariances stored as products. Ranging calibration (biases, timing) using `sim/calibration.py` (fixed in Phase 1).

### W3.3 Gravity inversion for real (Month 9–10)
- Inversion service consumes POD orbits + calibrated ranging: variational equations or acceleration approach to monthly spherical-harmonic corrections (degree 60 to start); regularization via existing Tikhonov/TV solvers; multiscale wavelet path retained as a solver option; resolution/error diagnostics stored with each product.
- **Bayesian UQ**: HMC/NUTS (numpyro) on a reduced problem; posterior maps stored as product layers.
- Validation campaign: closed-loop recovery — inject a known mass anomaly (hydrology signal from the synthetic Earth), run the full pipeline, recover it within stated error bars. This becomes the flagship nightly CI job (`bench/` framework repurposed to score it).

### W3.4 Product catalog (Month 10)
- Versioned L1B/L2 products in MinIO with STAC metadata; retrieval API; provenance chain (which orbit version, which inversion config) queryable.

### Exit criteria (Gate 3)
- [ ] `make demo-mission` on a clean stack: scenario → ingestion → POD → inversion → catalogued product, fully automated, <30 min.
- [ ] Closed-loop anomaly recovery test green nightly with tracked error metrics (regression alarms on degradation).
- [ ] Zero `np.random` in any service request path except the scenario generator.

---

## PHASE 4 — ML & Autonomy (Months 11–13)

- **W4.1**: PINN/U-Net retrained on Phase-3 pipeline outputs (real synthetic fields, not toy RNG): denoising L1B ranging, downscaling L2 fields. FNO implemented or the placeholder deleted. Model registry (MLflow) wired to the training orchestrator; hyperparameter tuning (existing Optuna integration) driven by real objectives.
- **W4.2**: Inference service: models served with provenance + input-drift monitoring; A/B evaluation against the closed-loop benchmark — an ML product may only be published if it beats the classical baseline on held-out scenarios.
- **W4.3**: Onboard/edge autonomy (SUPER-PROMPT Session 13): housekeeping anomaly detection (autoencoder), RL or rule-based station-keeping scheduler exercised in the emulator loop with fuel budget accounting; FDIR rules engine with an operator-facing action log.
- **W4.4**: `control-rs` promotion: benchmark Rust LQR/MPC vs Python via pyo3 bindings in CI; hot paths (MPC QP solve) moved to Rust if ≥5× faster, else the crate is archived with a decision record.
- **Gate 4**: ML products beat baselines on benchmark (documented); autonomy demo runs in emulator loop for 24 simulated hours without operator intervention; all models reproducible from `dvc repro` or equivalent lockfile.

---

## PHASE 5 — Mission Operations UI (Months 14–16)

- **W5.1 Foundation repair (Month 14)**: fix all 24 type errors; ESLint config; unit tests (jest configured properly) + Playwright with `@playwright/test` as a real dependency, run headless in CI against the compose stack; delete every `Math.random` data path and mock fallback — replace with explicit error/empty states; single generated API client (from W2.4); one WebSocket layer consuming the real Kafka bridge.
- **W5.2 Mission views (Months 14–15)**: live formation tracking on the Cesium globe fed by real telemetry stream; time-controller replay of any mission window (ephemeris from POD products); gravity-anomaly heatmap draped on the globe with time-lapse across monthly solutions and diff-vs-baseline mode; spherical-harmonic spectrum viewer.
- **W5.3 Ops console (Months 15–16)**: job/workflow dashboard on the real workflow engine (no simulated progress bars); command queue with RBAC approval flow + audit trail; alert/anomaly center wired to Alertmanager webhooks; product catalog browser with download; system health page fed by Prometheus (replacing the decorative "System Online" badge).
- **W5.4**: settings (endpoints, Cesium token), user management (admin), accessibility pass, error-boundary discipline.
- **Gate 5**: `next build` green in CI; Playwright e2e suite (≥30 scenarios) green against the live stack; a user can log in, replay yesterday's synthetic mission, watch the inversion job run, and open the resulting anomaly map — with zero fabricated numbers on screen.

---

## PHASE 6 — Hardening, Validation & Release (Months 17–18)

- **W6.1 Security**: penetration checklist (authn/z bypass, SSRF via gateway, gRPC reflection off in prod); dependency and container scanning become blocking; SBOM published per release; secrets rotated via Vault or cloud secrets manager (pick one; delete the other scaffold); rate limiting + circuit breakers verified under k6 (load scripts fixed to real endpoints, thresholds meaningful).
- **W6.2 Reliability**: chaos suite (kill each service, partition Kafka, fill disk) with documented recovery behavior; SLOs defined and measured (the existing SLO dashboard made real); backup/restore drill for TimescaleDB + MinIO documented and CI-tested.
- **W6.3 Validation campaign & publication**: extended closed-loop campaigns (seasonal hydrology, ice-mass trend, co-seismic step scenarios) with a written validation report per scenario; comparison table vs published GRACE-FO sensitivity curves; MkDocs documentation site (architecture, operator guide, API reference, science validation) deployed; whitepaper draft.
- **W6.4 Release v3.0**: semantic versioning, signed images, helm chart in a chart repo, `CHANGELOG.md`, upgrade guide, and a final honest `STATUS.md` generated from the CI gate matrix.
- **Gate 6 (Program Definition of Done)**: the Ground Rule 6 demo (clean clone → full mission → UI product in <15 min) runs nightly and is green for 30 consecutive days; all six phase gates documented with evidence links.

---

## Timeline Summary

| Months | Phase | Headline deliverable |
|---|---|---|
| 1 | 0 Truth & Stabilization | Green CI, one architecture, boot from clean clone |
| 2–4 | 1 Scientific Core | Correct dynamics/gravity/time/POD, validated vs references |
| 5–7 | 2 Platform Backbone | One backend, real auth, real observability, deployable Helm |
| 8–10 | 3 Science Pipeline | First honest end-to-end gravity product + closed-loop benchmark |
| 11–13 | 4 ML & Autonomy | ML beating baselines; autonomy in the emulator loop |
| 14–16 | 5 Mission Ops UI | Buildable, tested UI with zero fabricated data |
| 17–18 | 6 Hardening & Release | Security/reliability/validation campaign; v3.0 release |

## Staffing model (reference)

- 1 tech lead/architect (full program), 2 backend/platform engineers, 1 astrodynamics/geodesy specialist (Phases 1, 3, 6 critical), 1 ML engineer (Phases 3–4), 1 frontend engineer (Phases 2, 5), 0.5 DevOps/SRE (Phases 0, 2, 6). AI coding agents may execute any workstream, but **the verification gates are executed by CI, never self-attested**.

## Program-level KPIs (tracked monthly in STATUS.md, auto-generated)

1. CI required-gate pass rate on main (target: 100%).
2. Closed-loop anomaly recovery error (target: within 2× formal error by Month 10, within 1.2× by Month 18).
3. Fabricated-data pathways remaining (target: 0 from Month 14; enumerated by grep-based CI check for `Math.random`/`np.random` in serving paths).
4. Clean-clone-to-demo time (target: <15 min).
5. Mean time to detect injected service failure (target: <2 min from Month 7).

## Standing anti-patterns (rejected in code review, enforced where possible by CI)

- New status/summary markdown files at repo root.
- Endpoints added to UI without appearing in the OpenAPI spec (contract test fails).
- Physics constants or formulas without a cited reference in the docstring and a validation test.
- `try/except ImportError` that silently downgrades functionality without logging + a `/status` capability flag.
- Committing generated artifacts (proto stubs, builds, datasets) — regenerate in CI.
