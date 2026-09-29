"""Shared fixtures.

Unit tests need nothing. Integration tests (marked `db`) get a brand-new PostgreSQL database per test session,
migrated with Alembic, and dropped afterwards, so they never touch development data. The server comes from
AI_DATABASE_URL (environment, or the repository .env locally); the role needs CREATEDB, and pgvector must be
available (locally it is in template1; CI uses the pgvector image).
"""

import os
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tutor_ai.settings import REPO_ENV, Settings

TOKEN = "t" * 40
PREVIOUS_TOKEN = "p" * 40


def _env_value(name: str) -> str | None:
    if os.environ.get(name):
        return os.environ[name]
    if REPO_ENV.exists():
        for line in REPO_ENV.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() == name:
                return value.strip().strip("'\"")
    return None


def make_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "TUTOR_ENV": "test",
        "AI_DATABASE_URL": "postgresql://user:pass@localhost:5432/unused",
        "TUTOR_AI_SERVICE_TOKEN": TOKEN,
        "TUTOR_AI_PROVIDER": "mock",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    """Create a throwaway database, migrate it to head, yield its URL, drop it."""
    import psycopg
    from alembic import command
    from alembic.config import Config
    from sqlalchemy.engine import make_url

    base = _env_value("AI_DATABASE_URL")
    if not base:
        pytest.skip("AI_DATABASE_URL is not set; database tests need PostgreSQL with pgvector")
    url = make_url(base.replace("postgres://", "postgresql://", 1).replace("postgresql+psycopg://", "postgresql://", 1))
    name = f"tutor_ai_test_{uuid.uuid4().hex[:10]}"
    admin_dsn = url.set(drivername="postgresql", database="postgres").render_as_string(hide_password=False)
    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        conn.execute(f'CREATE DATABASE "{name}"')
    test_url = url.set(drivername="postgresql+psycopg", database=name).render_as_string(hide_password=False)
    try:
        config = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
        config.attributes["database_url"] = test_url
        command.upgrade(config, "head")
        yield test_url
    finally:
        with psycopg.connect(admin_dsn, autocommit=True) as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


@pytest.fixture(scope="session")
def alembic_config(database_url: str) -> Any:
    from alembic.config import Config

    config = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    config.attributes["database_url"] = database_url
    return config
