"""
Operations console routes (Phase 5 W5.3).

Aggregates the observability plane for the ops UI:
- /api/v1/ops/targets: Prometheus scrape-target health
- /api/v1/ops/alerts:  active Alertmanager alerts

Both proxy the in-cluster observability services (env-configured), so
the browser needs no cross-origin access to Prometheus/Alertmanager
and the ops view carries real monitoring state — never a decorative
"System Online" badge.
"""

import asyncio
import json
import os
import urllib.request
from typing import Any, Callable, Dict

from fastapi import APIRouter, Depends, HTTPException

from gen.python.proto import common_pb2

PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://prometheus:9090")
ALERTMANAGER_URL = os.getenv("ALERTMANAGER_URL", "http://alertmanager:9093")


def _fetch_json(url: str, timeout: float = 5.0) -> Any:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read())


def build_ops_router(get_user_context: Callable) -> APIRouter:
    router = APIRouter(prefix="/api/v1/ops", tags=["ops"])

    @router.get("/targets")
    async def scrape_targets(
        user_context: common_pb2.UserContext = Depends(get_user_context),
    ) -> Dict[str, Any]:
        """Prometheus scrape-target health (job, state, last scrape)."""
        try:
            data = await asyncio.to_thread(
                _fetch_json, f"{PROMETHEUS_URL}/api/v1/targets"
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=503, detail=f"prometheus unreachable: {exc}"
            )
        targets = [
            {
                "job": t["labels"].get("job", "?"),
                "instance": t["labels"].get("instance", "?"),
                "health": t["health"],
                "last_scrape": t.get("lastScrape"),
                "last_error": t.get("lastError", ""),
            }
            for t in data["data"]["activeTargets"]
        ]
        return {
            "targets": targets,
            "up": sum(1 for t in targets if t["health"] == "up"),
            "total": len(targets),
        }

    @router.get("/alerts")
    async def active_alerts(
        user_context: common_pb2.UserContext = Depends(get_user_context),
    ) -> Dict[str, Any]:
        """Active alerts from Alertmanager (v2 API)."""
        try:
            data = await asyncio.to_thread(
                _fetch_json, f"{ALERTMANAGER_URL}/api/v2/alerts?active=true"
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=503, detail=f"alertmanager unreachable: {exc}"
            )
        alerts = [
            {
                "name": a.get("labels", {}).get("alertname", "?"),
                "severity": a.get("labels", {}).get("severity", ""),
                "summary": a.get("annotations", {}).get("summary", ""),
                "starts_at": a.get("startsAt"),
                "state": a.get("status", {}).get("state", ""),
            }
            for a in data
        ]
        return {"alerts": alerts, "count": len(alerts)}

    @router.get("/rules")
    async def alert_rules(
        user_context: common_pb2.UserContext = Depends(get_user_context),
    ) -> Dict[str, Any]:
        """Configured alert rules and their evaluation state."""
        try:
            data = await asyncio.to_thread(
                _fetch_json, f"{PROMETHEUS_URL}/api/v1/rules"
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=503, detail=f"prometheus unreachable: {exc}"
            )
        rules = [
            {"name": r["name"], "state": r.get("state", "n/a"),
             "group": g["name"]}
            for g in data["data"]["groups"]
            for r in g["rules"]
        ]
        return {"rules": rules}

    return router
