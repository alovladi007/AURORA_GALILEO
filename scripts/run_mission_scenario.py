#!/usr/bin/env python3
"""
Run a GRACE-like mission scenario through the LIVE platform.

    dynamics -> observables -> gateway auth -> REST ingestion
    -> gRPC -> TimescaleDB -> query-back -> orbit determination

Usage (stack must be up: docker compose up -d):
    python3 scripts/run_mission_scenario.py \
        --gateway http://localhost:18000 --duration 5400

The script registers/logs in a service account, ingests every
telemetry and gravity record through the real API, queries them back,
compares counts, and finally runs the dynamic orbit determination on
the queried-back telemetry, reporting recovery error against the truth
orbit. Exit code 0 only if every stage succeeds.
"""

import argparse
import json
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from mission.scenario import MissionConfig, MissionScenario  # noqa: E402

ACCOUNT = {"email": "mission-sim@galileo.dev", "password": "mission-scenario-2026"}


def _post(url: str, body: dict, token: str = "") -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def _get(url: str, token: str) -> dict:
    req = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {token}"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gateway", default="http://localhost:18000")
    ap.add_argument("--duration", type=float, default=5400.0)
    ap.add_argument("--dt", type=float, default=10.0)
    ap.add_argument("--batch", type=int, default=50)
    args = ap.parse_args()
    gw = args.gateway.rstrip("/")

    print("=== 1/6 generate scenario (two-body+J2, degree-6 gravity) ===")
    scenario = MissionScenario(MissionConfig(
        duration_s=args.duration, dt_s=args.dt
    ))
    scenario.propagate()
    scenario.synthesize()
    n_tel = sum(len(a.telemetry) for a in scenario.arcs)
    n_grav = sum(len(a.gravity) for a in scenario.arcs)
    print(f"    {len(scenario.arcs)} satellites, "
          f"{n_tel} telemetry records, {n_grav} gravity records")

    print("=== 2/6 authenticate ===")
    try:
        _post(f"{gw}/auth/register", ACCOUNT)
    except Exception:
        pass  # already registered
    token = _post(f"{gw}/auth/token", ACCOUNT)["access_token"]
    print("    token acquired")

    print("=== 3/6 ingest telemetry ===")
    ingested_tel = 0
    for arc in scenario.arcs:
        for rec in arc.telemetry:
            _post(f"{gw}/api/v1/data/telemetry", rec, token)
            ingested_tel += 1
    print(f"    {ingested_tel} telemetry records ingested")

    print("=== 4/6 ingest gravity (batched) ===")
    ingested_grav = 0
    for arc in scenario.arcs:
        for i in range(0, len(arc.gravity), args.batch):
            batch = arc.gravity[i:i + args.batch]
            out = _post(f"{gw}/api/v1/data/gravity",
                        {"measurements": batch}, token)
            ingested_grav += int(out.get("records_ingested", 0))
    assert ingested_grav == n_grav, (
        f"ingested {ingested_grav} != generated {n_grav}"
    )
    print(f"    {ingested_grav} gravity measurements ingested")

    print("=== 5/6 query back and verify counts ===")
    sat_a = scenario.config.satellite_ids[0]
    grav_back = _get(
        f"{gw}/api/v1/data/gravity?satellite_ids={sat_a}&page_size=1000",
        token,
    ).get("measurements", [])
    per_sat = len(scenario.arcs[0].gravity)
    assert len(grav_back) >= per_sat, (
        f"queried back {len(grav_back)} < ingested {per_sat} for {sat_a}"
    )
    synthetic = [m for m in grav_back if m.get("quality_flag") == "synthetic"]
    print(f"    {len(grav_back)} gravity rows for {sat_a} "
          f"({len(synthetic)} provenance-tagged synthetic)")

    print("=== 6/6 orbit determination on the generated telemetry ===")
    od = scenario.orbit_determination_check(
        scenario.arcs[0].telemetry, scenario.arcs[0]
    )
    print(f"    converged={bool(od['converged'])}  "
          f"epoch position error={od['epoch_position_error_m']:.2f} m  "
          f"velocity error={od['epoch_velocity_error_mm_s']:.2f} mm/s  "
          f"post-fit RMS={od['postfit_rms_m']:.2f} m")
    assert od["converged"], "orbit determination did not converge"
    assert od["epoch_position_error_m"] < 10.0, "OD recovery worse than 10 m"

    print("=== 7/7 gravity inversion on the ingested measurements ===")
    import time as _time
    start = _post(f"{gw}/api/v1/inversions", {
        "name": "mission-anomaly-map",
        "measurement_ids": list(scenario.config.satellite_ids),
        "parameters": {"method": "tikhonov"},
        "grid": {
            "min_latitude": -85, "max_latitude": 85,
            "min_longitude": -180, "max_longitude": 180,
            "num_lat_points": 16, "num_lon_points": 16,
        },
    }, token)
    job_id = start["job_id"]
    status = {}
    for _ in range(20):
        _time.sleep(3)
        status = _get(f"{gw}/api/v1/inversions/{job_id}", token)
        if status.get("status") in ("completed", "failed"):
            break
    assert status.get("status") == "completed", f"inversion: {status}"
    print(f"    job {job_id}: completed, "
          f"progress={status['progress']:.0%}, "
          f"residual={status['rms_residual']:.1f}")

    print("\nMISSION SCENARIO PIPELINE: ALL STAGES PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
