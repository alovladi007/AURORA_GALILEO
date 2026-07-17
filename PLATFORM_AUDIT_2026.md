# GALILEO V2.0 — Deep Platform Analysis (July 2026)

**Method**: Five parallel evidence-based code audits (infrastructure/DevOps, frontend, scientific core with execution-verified numerics, services spot-checks, repo history review). Every claim below carries file:line evidence; numeric/physics claims marked ✅ were verified by executing the code.

**Companion document**: [`MASTER_BUILD_PROMPT_18_MONTHS.md`](MASTER_BUILD_PROMPT_18_MONTHS.md) — the phased implementation prompt that fixes everything catalogued here.

---

## 1. Executive Summary

GALILEO V2.0 presents itself as a "95% production-ready" satellite gravimetry platform. The honest assessment:

| Layer | Claimed | Actual |
|---|---|---|
| Scientific core (sim/pod/time/telemetry) | "High-fidelity dynamics" | **Multiple verified physics errors; 3 of 5 packages unimportable** |
| Gravity modeling | "EGM2008, geoid, spherical harmonics" | **Returns zeros — entire module is placeholder** |
| Microservices | "5 production gRPC services" | Skeletons run, but compute on seeded RNG synthetic data |
| Frontend | "Mission control dashboard" | **Cannot produce a production build** (24 type errors); ~half of panels fabricate data client-side |
| Deployment | "Kubernetes/Istio/Helm ready" | **None of 3 deployment stories is self-consistent**; Helm chart un-renderable |
| CI/CD | "Comprehensive pipelines" | **Main pipeline structurally cannot pass** |
| Tests | "84+ passing" | Per-service tests are real; root `tests/{time,pod,telemetry}` fail at collection; UI tests: 0 runnable |

**Realistic completion estimate: ~35–40% of the SUPER-PROMPT vision**, consistent with the repo's own `HONEST_STATUS.md` (Nov 2025) and far below the "92%"/"95%" claims in `STATUS.md`/`README.md`.

The dominant failure mode is **unintegrated code drops**: large modules generated in isolated sessions, committed without cross-checking imports, units, signs, ports, or endpoint names against the rest of the system — then documented as complete.

---

## 2. Verified Scientific Defects (highest severity)

These were confirmed by *running the code*, not just reading it:

1. **`sim/gravity.py` is entirely placeholder** — `associated_legendre` (line 57-59), `gravitational_potential` (79-84), `load_egm2008_model` (120-122), `compute_geoid_height` (152-154) all return zeros. `gravitational_acceleration` takes `jax.grad` of a zero potential → always 0. *The gravity-field estimation platform cannot compute a gravity field.*
2. **J2 perturbation sign inverted** ✅ — `sim/dynamics/perturbations.py:104-109`. Earth's oblateness bulge *repels* satellites; RAAN regresses the wrong way. Verified numerically: equatorial acceleration points outward.
3. **Orbital element conversion rotates the wrong way** ✅ — `sim/dynamics/keplerian.py:168-199` applies the ECI→perifocal matrix to perifocal coordinates; Ω and ω are effectively negated. Verified: Ω=90° places the satellite at −y instead of +y.
4. **Drag and SRP ~10⁶× too strong** — unit conversion errors at `perturbations.py:229` (1e9 vs 1e3 for kg/m³→kg/km³) and `:308-310` (×1000 where ÷1000 is correct); plus atmosphere co-rotation underweighted 1000× at line 224.
5. **Flagship propagators crash under their own `@jit`** ✅ — `perturbed_dynamics` with drag (the default) raises `TracerBoolConversionError`; `propagate_orbit_jax`/`propagate_relative_orbit` raise `ConcretizationTypeError` on every call (`propagators.py:229-230`).
6. **`time/` package is permanently unimportable** ✅ — it shadows Python's built-in `time` module (`time/__init__.py:15`); no sys.path configuration can fix this. All timescale/relativity/clock code — including a *correct and complete* leap-second table — is unreachable dead code. `tests/time` fails at collection.
7. **`pod/` fails to import** ✅ — `pod/dynamics.py` is a 5-line truncated file (unterminated docstring → SyntaxError); `pod/__init__.py:35-39` imports classes that exist nowhere. Beyond that, "POD" contains **no orbital dynamics at all**: batch LS is single-epoch GPS point positioning (`estimators.py:86-87,170-171`), the SRIF mixes incompatible conventions (`z=Rx` vs `z=RᵀRx`, lines 209 vs 259), and the RTS smoother uses constant-velocity dynamics.
8. **CCSDS deframer reads 8 bytes past user data** ✅ — `telemetry/ccsds.py:149`; any concatenated packet stream is mis-parsed. `telemetry/__init__.py` exports phantom classes (`ProtobufEncoder`, `AvroEncoder` — never written).
9. **Relativity sign errors** — `time/relativity.py:283-292`: gravitational redshift and Doppler terms both inverted (uphill photons blueshift, receding receivers blueshift).
10. **Noise taxonomy swapped in both ADEV implementations** — `sim/calibration.py:185-191` and `time/clock.py:54-145` label white-PM as white-FM and vice versa; `hadamard_variance` is not the Hadamard variance.
11. **`sim/synthetic.py` forward model is physically incoherent** — per-pixel vertical-column-only integration with a wrong lever arm (`density_to_gravity:303-307`); nanoGal defined as 10⁻⁹ instead of 10⁻¹¹ m/s² (`gravity_to_baseline:328`); telemetry attributes (coherence, SNR) are pure RNG (443-448).
12. **Phantom imports in production tasks** — `ops/tasks.py:90,128` import `sim.keplerian.propagate_j2` and `sim.relative.propagate_hcw_formation`; neither exists → both Celery tasks always silently fail.

**What is genuinely solid in the scientific core**: `time/timescales.py` (correct constants, complete leap-second table — tragically unreachable), `sim/dynamics/relative.py` (correct CW equations and Hill transforms with proper Coriolis handling), `rk4_step`, CCSDS header bit-packing, `pod/measurements.py` GNSS geometry (ionosphere-free combination, Saastamoinen, correct Jacobians), `inversion/solvers.py` (real scipy Tikhonov/Gauss-Newton/Bayesian MAP), whiteness-test statistics, and `control-rs` (the Rust crate **compiles cleanly**, 11 warnings).

---

## 3. Services Layer

- The five gRPC services start and their per-service test suites (`services/*/tests/`) are the most genuine part of the repo, with a coherent proto-generation script (`scripts/generate_protos.sh`).
- **However, the computational services run on synthetic data end to end**: `services/ml-service/src/training_orchestrator.py:64,214` and `services/inversion-service/src/inversion_engine.py:71,340` seed `np.random.default_rng` and generate their own observations. Optuna/PyWavelets/JAX integrations are real *libraries*, exercised on fabricated inputs. There is no path from ingested data to a scientific product.
- `services/data-service` is the exception: real asyncpg + TimescaleDB with hypertables, compression, and retention (`database.py:119-122`, `ops/db/timescale_setup.sql`).
- Generated proto stubs (`services/*/src/gen/`) are gitignored and must be regenerated — undocumented in the quickstart.
- **Hardcoded JWT signing key**: `services/api-gateway/src/api/auth_v2.py:11` (`SECRET_KEY = "dev-secret-key-change-in-production"`, no env fallback) — and the auth router is not even mounted in `main.py`.

---

## 4. Frontend (ui/)

Executed checks: `npm ci` ✓, `npm run type-check` ✗ (24 errors, 6 files), `npm run build` ✗, `npm run lint` ✗ (no eslintrc), `npm test` ✗ (jest picks up a Playwright spec; `@playwright/test` not even a dependency).

- **Production build is impossible** — `GlobeViewer.tsx:148` (invalid Cesium option) breaks `next build`; the `ui/Dockerfile` image cannot have been built from this tree.
- **Silent fake-data fallbacks**: `useSatelliteData.ts:47-63` fabricates satellite positions/battery with `Math.random()` on any API error and presents them as real — operationally dangerous. `useGravityData.ts:12-55` is 100% synthetic by design. `MLPanel.tsx:65-77` fakes training curves with `setInterval` + `Math.exp` decay; `WorkflowPanel.tsx:139-180` "simulates" workflow execution entirely client-side.
- **~30 endpoints called by the UI do not exist in any backend**: all of `simulationApi`, `inversionApi`, `controlApi`, `tradeStudyApi` in `api-client-full.ts` use wrong paths (`/api/simulation/*` vs actual `/api/propagate`; `/api/trade-study/*` vs `/api/trades/*`), plus 15+ phantom `/api/v1/*` gateway paths in `api-client.ts`. Two contradictory API clients target two different backends (ports 18000 vs 5050); hooks import the wrong one (`useInversion.ts:9`, `useML.ts:9`) → runtime crashes.
- **Auth cannot succeed**: NextAuth posts to `/auth/token` which exists nowhere; fallback secret hardcoded; unauthenticated requests silently send `Bearer demo-token-for-testing` (`api-client-full.ts:32`); 401s redirect to a nonexistent `/auth/signin`.
- **The real-time layer is dead code**: the Kafka→WebSocket bridge on the gateway is real, but its only consumer (`LiveSatelliteTracker.tsx`) is unmounted *and* broken. No shipped page has any live data path.
- Only 4 routes exist; `/phase5` (added this session) is a static verification banner depending on a script outside the repo — it should be removed or made honest.
- The one honest end-to-end real-time pipeline: `emulator/dashboard.html` + `emulator/server.py` (ws://8765, 50 Hz) — though the emulator physics itself is decoupled sinusoid+noise channels ("signal theater": vibration events never affect the interference fringes, `optical_bench.py:79-166`).

---

## 5. Infrastructure, CI/CD, Deployment

- **Three conflicting compose stacks** (`docker-compose.yml` monolith, `docker-compose.microservices.yaml`, `docker-compose.infrastructure.yaml`) plus a fourth in `mlops/` — different port universes, different schemas, different architectures. `PORTS.md`, `QUICKSTART.md`, and `DEPLOYMENT.md` each document a *different* port set, none matching any compose file.
- **Fresh boot fails**: `scripts/init-db.sql:5-15` runs `CREATE DATABASE` inside a plpgsql `DO` block (forbidden) and grants to a nonexistent role → Postgres init aborts → every dependent service waits forever. `beat` and `flower` crash-loop (missing deps in the image). nginx mounts a nonexistent `nginx.conf`. Kafka advertises `localhost:19092` while publishing 29092.
- **CI is structurally red**: matrix includes Python 3.9/3.10 against `requires-python >=3.11`; `mkdocs build --strict` with no `mkdocs.yml`; build job uploads `ui/dist/` (Next.js emits `.next/`); security scanners all `|| true`'d. The credible workflow is `services-tests.yml`.
- **Helm chart cannot render** (`templates/secret.yaml:1` reads a values key that doesn't exist); it deploys images (`galileo/*:2.0.0`) that no pipeline builds; **Istio routes to microservice names that the Helm chart never deploys** (chart deploys the monolith).
- **Database schema has four divergent sources**: `ops/db/init.sql` vs alembic migration (drops hypertables, renames `metadata`→`meta_info`) vs `ops/models.py` (declares `id` PKs that no DDL creates → live queries fail at `api/services/database_service.py:326-401`) vs `ops/db/timescale_setup.sql` (the microservices schema — the only good one).
- **Monitoring half-wired**: Prometheus scrapes exporters that aren't deployed, a metrics port that doesn't exist, and an ops-api `/metrics` endpoint that was never written; Alertmanager config is invalid (env-var interpolation Alertmanager doesn't support); alert rules reference metrics emitted by nothing.
- **Load tests hit nonexistent endpoints** (`tests/load/k6-load-test.js:139,175,200`) — thresholds "pass" because 404s are fast.
- **Security**: no real secrets committed (good), but weak defaults everywhere, auth off by default with a committed bcrypt hash of "dev", Jaeger/Flower/DBs exposed unauthenticated, hardcoded JWT constants in two places.

---

## 6. Repo Hygiene

- **~60 contradictory status markdown files** at root (`PRODUCTION_READY.md` next to `HONEST_STATUS.md`; five PHASE*_IMPLEMENTATION.md; a dozen SESSION_* files).
- **Three legacy snapshot trees** (`GALILEO_Session_4_Synthetic_Data/`, `GALILEO_Session_5_6.../` incl. a literal `mnt/` dump, `GALILEO_Session_7_8.../` with its own docker-compose) duplicating `inversion/`, `ml/`, `sim/`.
- ~15 MB of tracked binary artifacts (`.pkl`/`.npy`/`.png`) despite `.gitignore` rules.
- Duplicate frontend config at root (`package.json` named "geosense-ui", `next.config.js`, `index.html`) alongside the real `ui/`.
- Three API mains (`api/main.py`, `main_backup.py`, `main_integrated.py`); two auth modules; `pyproject.toml` packages exclude `pod/time/telemetry/emulator` entirely.
- A hardcoded `/home/claude/...` output path in `sim/validate_calibration.py:30` — direct evidence of unintegrated AI session drops.

---

## 7. Root-Cause Diagnosis

1. **No integration gate.** Code was merged without ever being imported by, or run against, the rest of the system (unimportable packages, phantom imports, endpoint name drift).
2. **No numerical validation gate.** Physics code was merged without a single cross-check against known references (J2 sign, unit errors would be caught by one textbook test case each).
3. **Documentation-driven development in reverse.** Status docs assert completion first; code follows partially or never. 60+ status files exist because each session wrote a new one rather than updating a single source of truth.
4. **Three architectures kept alive simultaneously** (monolith, microservices, helm-monolith+istio-microservices) — every fix must land three times, so none lands anywhere.
5. **Demo pressure produced fake-data pathways** (UI Math.random fallbacks, synthetic-only service pipelines, static "verified real" pages) that now mask genuine failures.

---

## 8. What to Keep (the salvage list)

- `services/data-service` TimescaleDB layer; `scripts/generate_protos.sh` + per-service test suites; the api-gateway Kafka→WS bridge and metrics module.
- `inversion/` scipy solvers; `control/` LQR/LQG/MPC and EKF wrappers; `control-rs` (compiles).
- `time/timescales.py` content (after package rename); `pod/measurements.py` GNSS geometry; CCSDS header packing (after the deframer fix); `sim/dynamics/relative.py`; RK4.
- k6/locust script *structure*; terraform modules; helm template *structure*; Grafana SLO dashboard skeleton.
- The Cesium/Next.js UI shell and the emulator WebSocket architecture.

Everything else is fixable in place or replaceable per the 18-month plan.

---

*Full remediation plan with phases, acceptance criteria, and verification gates:* **`MASTER_BUILD_PROMPT_18_MONTHS.md`**.
