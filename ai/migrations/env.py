"""Alembic environment: async psycopg 3, everything inside the `ai` schema (including Alembic's own version table),
so the AI service never touches Django's tables and the two migration histories can't collide."""

import asyncio
import os

from alembic import context
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from tutor_ai.schema import SCHEMA, metadata

config = context.config


def database_url() -> str:
    url = config.attributes.get("database_url") or os.environ.get("AI_DATABASE_URL")
    if not url:
        from tutor_ai.settings import get_settings  # reads the repo .env locally

        url = get_settings().database_url.get_secret_value()
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            url = "postgresql+psycopg://" + url[len(prefix) :]
    return url


def include_object(obj, name, type_, reflected, compare_to):  # type: ignore[no-untyped-def]
    """Only compare objects in our schema (Django's tables in `public` are none of our business)."""
    schema = getattr(obj, "schema", None) or getattr(getattr(obj, "table", None), "schema", None)
    return schema == SCHEMA if type_ in ("table", "index", "unique_constraint", "foreign_key_constraint") else True


def run_migrations(connection: Connection) -> None:
    connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}"))
    context.configure(
        connection=connection,
        target_metadata=metadata,
        version_table_schema=SCHEMA,
        include_schemas=True,
        include_object=include_object,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async() -> None:
    engine = create_async_engine(database_url())
    async with engine.connect() as connection:
        await connection.run_sync(run_migrations)
        await connection.commit()
    await engine.dispose()


if context.is_offline_mode():
    raise SystemExit("Offline (SQL-only) migrations aren't supported; run against a database.")
asyncio.run(run_async())
