# Legacy Monolith (archived)

The FastAPI monolith (`monolith-api/`, formerly `api/`) and its Celery
worker layer (`monolith-ops/`, formerly `ops/`) are retired as of
Phase 2 W2.1 of MASTER_BUILD_PROMPT_18_MONTHS.md. The gRPC
microservices + API gateway are the only backend.

Kept for reference only — nothing imports or deploys this code. The
former `api/` package name actively shadowed the gateway's `api`
package in test runs, which is what forced the archive date.

`ops/db/` (TimescaleDB DDL) and `ops/nginx/` remain live at their old
paths because the canonical compose stack mounts them.
