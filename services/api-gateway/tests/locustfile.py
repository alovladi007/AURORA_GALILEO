"""
Load Test Harness (Locust)
==========================

Load tests for the API Gateway HTTP endpoints. Run against a deployed gateway:

    locust -f locustfile.py --host http://localhost:8000

Then open http://localhost:8089 to configure users and spawn rate, or run
headless:

    locust -f locustfile.py --host http://localhost:8000 \
        --users 100 --spawn-rate 10 --run-time 2m --headless

Targets (suggested SLOs):
  - p95 latency < 500 ms for read endpoints
  - error rate < 1%
"""

import json
import random
from datetime import datetime, timedelta

try:
    from locust import HttpUser, task, between
except ImportError:  # pragma: no cover
    # Allow importing this module without locust installed (e.g. for linting).
    HttpUser = object

    def task(*a, **k):
        def deco(f):
            return f
        return deco

    def between(*a, **k):
        return None


SATELLITES = [f"SAT{i:03d}" for i in range(1, 11)]


class GatewayUser(HttpUser):
    """Simulates a dashboard client polling read endpoints and ingesting data."""

    wait_time = between(0.5, 2.0)

    def on_start(self):
        # In a real deployment, acquire a JWT here. The gateway accepts
        # unauthenticated reads in dev mode.
        self.headers = {"Content-Type": "application/json"}

    @task(5)
    def health(self):
        self.client.get("/health", name="GET /health")

    @task(3)
    def metrics(self):
        self.client.get("/metrics", name="GET /metrics")

    @task(4)
    def query_telemetry(self):
        sats = random.sample(SATELLITES, k=2)
        params = {
            "satellite_ids": sats,
            "start_time": (datetime.utcnow() - timedelta(hours=1)).isoformat(),
            "end_time": datetime.utcnow().isoformat(),
            "page": 1,
            "page_size": 50,
        }
        self.client.get("/api/v1/data/telemetry", params=params,
                        headers=self.headers, name="GET /data/telemetry")

    @task(2)
    def ingest_telemetry(self):
        sat = random.choice(SATELLITES)
        payload = {
            "satellite_id": sat,
            "location": {
                "latitude": random.uniform(-90, 90),
                "longitude": random.uniform(-180, 180),
                "altitude": random.uniform(400000, 500000),
            },
            "temperature": random.uniform(15, 35),
            "battery_level": random.uniform(60, 100),
        }
        self.client.post("/api/v1/data/telemetry", data=json.dumps(payload),
                         headers=self.headers, name="POST /data/telemetry")

    @task(1)
    def list_workflows(self):
        self.client.get("/api/v1/workflows/workflows",
                        name="GET /workflows/workflows")

    @task(1)
    def workflow_statistics(self):
        self.client.get("/api/v1/workflows/statistics",
                        name="GET /workflows/statistics")
