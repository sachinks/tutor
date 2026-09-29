"""Prompt versions are recorded in ai.prompt_version, the active one is marked, and edited versions are refused."""

import asyncio

import psycopg
import pytest
from fastapi.testclient import TestClient

from tests.conftest import make_settings
from tutor_ai.db import create_engine
from tutor_ai.main import create_app
from tutor_ai.prompts import PromptError, PromptRegistry, sync_prompts
from tutor_ai.settings import AI_DIR

pytestmark = pytest.mark.db

REAL_V1 = (AI_DIR / "prompts" / "tutor" / "v1.md").read_text(encoding="utf-8")
V2 = REAL_V1.replace("You are TUTOR, a patient study helper", "You are TUTOR, a friendly study helper")


def sync(database_url, directory):
    async def main():
        engine = create_engine(database_url)
        try:
            await sync_prompts(engine, PromptRegistry.load(directory))
        finally:
            await engine.dispose()

    asyncio.run(main())


def stored(database_url):
    with psycopg.connect(database_url.replace("postgresql+psycopg://", "postgresql://", 1)) as conn:
        return {
            (name, version): (checksum, active)
            for name, version, checksum, active in conn.execute(
                "SELECT name, version, checksum, active FROM ai.prompt_version"
            ).fetchall()
        }


def prompt_dir(tmp_path, **versions):
    for version, body in versions.items():
        path = tmp_path / "tutor" / f"{version}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return tmp_path


def test_versions_are_recorded_and_the_newest_is_active(database_url, tmp_path):
    directory = prompt_dir(tmp_path, v1=REAL_V1, v2=V2)
    sync(database_url, directory)
    sync(database_url, directory)  # idempotent
    rows = stored(database_url)
    registry = PromptRegistry.load(directory)
    assert rows[("tutor", "v1")] == (registry.get("tutor", "v1").checksum, False)
    assert rows[("tutor", "v2")] == (registry.get("tutor", "v2").checksum, True)


def test_going_back_to_the_shipped_prompts_reactivates_v1(database_url):
    sync(database_url, AI_DIR / "prompts")  # v2 above stays recorded but inactive
    rows = stored(database_url)
    assert rows[("tutor", "v1")][1] is True
    assert rows.get(("tutor", "v2"), (None, False))[1] is False


def test_an_edited_version_is_refused(database_url, tmp_path):
    sync(database_url, AI_DIR / "prompts")
    edited = prompt_dir(tmp_path, v1=REAL_V1.replace("patient", "strict"))
    with pytest.raises(PromptError, match="tutor/v1 was edited"):
        sync(database_url, edited)


def test_the_app_refuses_to_start_with_an_edited_prompt(database_url, tmp_path):
    sync(database_url, AI_DIR / "prompts")
    edited = prompt_dir(tmp_path, v1=REAL_V1.replace("patient", "strict"))
    app = create_app(make_settings(AI_DATABASE_URL=database_url, TUTOR_AI_PROMPTS_DIR=str(edited)))
    with pytest.raises(PromptError), TestClient(app):
        pass


def test_the_app_starts_when_the_database_is_down_and_reports_it(caplog):
    app = create_app(make_settings(AI_DATABASE_URL="postgresql://nobody:nothing@127.0.0.1:1/none"))
    with TestClient(app) as client:
        assert client.get("/health").status_code == 503
    assert any("could not record prompt versions" in r.getMessage() for r in caplog.records)


def test_a_malformed_prompt_file_stops_the_app_at_creation(tmp_path):
    broken = prompt_dir(tmp_path, v1=REAL_V1.replace("## @hint", "## @hints"))
    with pytest.raises(PromptError):
        create_app(make_settings(TUTOR_AI_PROMPTS_DIR=str(broken)))
