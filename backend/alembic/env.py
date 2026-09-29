"""
Alembic migration environment.

This file configures Alembic to:
1. Read the DB URL from our app settings (.env / config.py) — no duplicates.
2. Discover our ORM models so autogenerate works.
"""
from logging.config import fileConfig
import sys
from pathlib import Path

from sqlalchemy import engine_from_config, pool
from alembic import context

# --- Make our app importable when Alembic runs standalone ---
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings          # noqa: E402
from app.db.base import Base                  # noqa: E402
from app.db import models                     # noqa: F401,E402  (imports Farm, Plot)


# Alembic Config object — gives access to alembic.ini values.
config = context.config

# Read the DB URL from our app settings and inject it into Alembic.
config.set_main_option("sqlalchemy.url", settings.database_url)

# Configure Python logging using alembic.ini's logging section.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata for autogenerate — Alembic compares this to the live DB.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — emit SQL without a DB connection."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live DB."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()