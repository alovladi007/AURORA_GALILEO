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

## Current Phase: Gate 0 PASSED; Phase 1 W1.1 complete; Phase 2 W2.3 auth live

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
378 collected: 317 passed, 0 failed, 61 skipped (0 collection errors)
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
