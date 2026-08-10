"""Canonical TimescaleDB schema (executes ops/db/timescale_setup.sql).

The SQL file is the single schema of record, shared between first-boot
container initialization and this migration; it is idempotent
(IF NOT EXISTS / OR REPLACE / guarded add_job), so upgrading a
database that was bootstrapped by the container init is a no-op.

TimescaleDB continuous aggregates cannot be created inside a
transaction block, so statements run one-by-one in an autocommit
block, split with a dollar-quote-aware splitter.

Revision ID: 20260810_0001
Revises:
Create Date: 2026-08-10
"""

import re
from pathlib import Path

from alembic import op

revision = "20260810_0001"
down_revision = None
branch_labels = None
depends_on = None

SQL_FILE = (
    Path(__file__).resolve().parents[2] / "ops" / "db" / "timescale_setup.sql"
)


def _split_sql(script: str):
    """Split a SQL script into statements, respecting dollar-quoted
    bodies ($tag$ ... $tag$) and line comments."""
    statements = []
    buf = []
    dollar_tag = None
    for raw_line in script.splitlines():
        line = raw_line
        if dollar_tag is None:
            # strip full-line comments outside dollar quotes
            if line.strip().startswith("--"):
                continue
        buf.append(line)
        # Track dollar-quote state
        for m in re.finditer(r"\$[A-Za-z_]*\$", line):
            tag = m.group(0)
            if dollar_tag is None:
                dollar_tag = tag
            elif tag == dollar_tag:
                dollar_tag = None
        if dollar_tag is None and line.rstrip().endswith(";"):
            stmt = "\n".join(buf).strip()
            if stmt and stmt != ";":
                statements.append(stmt)
            buf = []
    tail = "\n".join(buf).strip()
    if tail:
        statements.append(tail)
    return statements


def upgrade() -> None:
    script = SQL_FILE.read_text()
    with op.get_context().autocommit_block():
        for stmt in _split_sql(script):
            op.execute(stmt)


def downgrade() -> None:
    # The canonical schema is foundational; downgrade drops everything.
    with op.get_context().autocommit_block():
        for table in (
            "satellite_telemetry_hourly",
            "gravity_daily_summary",
            "api_metrics_hourly",
        ):
            op.execute(f"DROP MATERIALIZED VIEW IF EXISTS {table} CASCADE")
        for table in (
            "satellite_telemetry",
            "gravity_measurements",
            "api_metrics",
        ):
            op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
