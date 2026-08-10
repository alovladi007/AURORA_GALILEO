"""Alembic environment for the GALILEO canonical schema.

Schema authority (Phase 2 W2.2 of MASTER_BUILD_PROMPT_18_MONTHS.md):
the initial migration executes ops/db/timescale_setup.sql — the same
idempotent DDL the compose stack applies at first boot — so a database
bootstrapped either way ends up identical. Autogenerate targets the
data-service ORM metadata for future incremental migrations.

Database URL resolution: DATABASE_URL env var wins; falls back to the
canonical compose development default.
"""

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "services" / "data-service"))

from src.database import Base  # noqa: E402  (data-service ORM)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

DEFAULT_URL = "postgresql://galileo:galileo_dev@localhost:27432/galileo"
config.set_main_option(
    "sqlalchemy.url", os.environ.get("DATABASE_URL", DEFAULT_URL)
)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
