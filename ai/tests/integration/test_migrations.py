"""The `ai` schema as Alembic builds it: tables, pgvector column and index, constraints, and a clean round trip."""

import uuid

import psycopg
import pytest
from alembic import command

pytestmark = pytest.mark.db


def connect(database_url):
    return psycopg.connect(database_url.replace("postgresql+psycopg://", "postgresql://", 1), autocommit=True)


def test_tables_exist_only_in_the_ai_schema(database_url):
    with connect(database_url) as conn:
        rows = conn.execute(
            "SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema = 'ai'"
        ).fetchall()
        public = conn.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'").fetchone()
    assert {name for _, name in rows} == {
        "lesson_chunk",
        "prompt_version",
        "eval_run",
        "index_event",
        "alembic_version",
    }
    assert public == (0,)  # nothing leaks into Django's schema


def test_embedding_column_and_hnsw_index(database_url):
    with connect(database_url) as conn:
        column_type = conn.execute(
            "SELECT format_type(atttypid, atttypmod) FROM pg_attribute "
            "WHERE attrelid = 'ai.lesson_chunk'::regclass AND attname = 'embedding'"
        ).fetchone()
        index = conn.execute(
            "SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_lesson_chunk_embedding_hnsw'"
        ).fetchone()
    assert column_type == ("vector(768)",)
    assert "hnsw" in index[0] and "vector_cosine_ops" in index[0]


def insert_chunk(conn, **overrides):
    values = {
        "lesson_id": uuid.uuid4(),
        "content_version_id": uuid.uuid4(),
        "course_id": uuid.uuid4(),
        "subject": "ai-foundations",
        "class_number": None,
        "position": 0,
        "heading": "Features and labels",
        "text": "Features are what we observe.",
        "token_count": 6,
        "embedding": "[" + ",".join(["0.1"] * 768) + "]",
        "embedding_model": "mock-hashed-bow-v1",
    }
    values.update(overrides)
    columns = ", ".join(values)
    placeholders = ", ".join(f"%({k})s" for k in values)
    conn.execute(f"INSERT INTO ai.lesson_chunk ({columns}) VALUES ({placeholders})", values)
    return values


def test_constraints_protect_the_data(database_url):
    with connect(database_url) as conn:
        first = insert_chunk(conn)
        for bad in ({"position": -1}, {"token_count": 0}, {"embedding": "[0.1,0.2]"}):
            with pytest.raises(psycopg.Error):
                insert_chunk(conn, **bad)
        with pytest.raises(psycopg.errors.UniqueViolation):
            insert_chunk(conn, lesson_id=first["lesson_id"], content_version_id=first["content_version_id"])
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute(
                "INSERT INTO ai.index_event (lesson_id, action, idempotency_key, status) VALUES (%s, 'rename', 'k1', 'done')",
                (uuid.uuid4(),),
            )
        conn.execute("DELETE FROM ai.lesson_chunk")


def test_nearest_neighbour_query_uses_cosine_distance(database_url):
    with connect(database_url) as conn:
        near = "[" + ",".join(["1"] + ["0"] * 767) + "]"
        far = "[" + ",".join(["0", "1"] + ["0"] * 766) + "]"
        insert_chunk(conn, heading="near", embedding=near)
        insert_chunk(conn, heading="far", embedding=far)
        best = conn.execute(
            "SELECT heading FROM ai.lesson_chunk ORDER BY embedding <=> %s::vector LIMIT 1", (near,)
        ).fetchone()
        conn.execute("DELETE FROM ai.lesson_chunk")
    assert best == ("near",)


def test_downgrade_and_upgrade_round_trip(alembic_config, database_url):
    command.downgrade(alembic_config, "base")
    with connect(database_url) as conn:
        remaining = conn.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'ai' AND table_name <> 'alembic_version'"
        ).fetchone()
    assert remaining == (0,)
    command.upgrade(alembic_config, "head")
    with connect(database_url) as conn:
        assert conn.execute("SELECT to_regclass('ai.lesson_chunk')").fetchone() == ("ai.lesson_chunk",)
