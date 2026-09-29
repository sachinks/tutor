"""Create the ai schema: lesson_chunk (with pgvector HNSW index), prompt_version, eval_run, index_event.

Revision ID: 0001
Revises:
Create Date: 2026-09-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "ai"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "lesson_chunk",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column("lesson_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subject", sa.String(80), nullable=False),
        sa.Column("class_number", sa.Integer, nullable=True),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("heading", sa.String(200), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("token_count", sa.Integer, nullable=False),
        sa.Column("embedding", Vector(768), nullable=False),
        sa.Column("embedding_model", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("lesson_id", "content_version_id", "position", name="uq_lesson_chunk_position"),
        sa.CheckConstraint("position >= 0", name="ck_lesson_chunk_position"),
        sa.CheckConstraint("token_count > 0", name="ck_lesson_chunk_tokens"),
        schema=SCHEMA,
    )
    op.create_index("ix_lesson_chunk_lesson", "lesson_chunk", ["lesson_id"], schema=SCHEMA)
    op.create_index("ix_lesson_chunk_course", "lesson_chunk", ["course_id"], schema=SCHEMA)
    op.create_index(
        "ix_lesson_chunk_embedding_hnsw",
        "lesson_chunk",
        ["embedding"],
        schema=SCHEMA,
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_table(
        "prompt_version",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("version", sa.String(40), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("active", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("name", "version", name="uq_prompt_version"),
        schema=SCHEMA,
    )
    op.create_table(
        "eval_run",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column("suite", sa.String(100), nullable=False),
        sa.Column("prompt_version", sa.String(40), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pass_rate", sa.Float, nullable=True),
        sa.Column("results", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.CheckConstraint("pass_rate IS NULL OR (pass_rate >= 0 AND pass_rate <= 1)", name="ck_eval_run_pass_rate"),
        schema=SCHEMA,
    )
    op.create_table(
        "index_event",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("lesson_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("idempotency_key", name="uq_index_event_idempotency_key"),
        sa.CheckConstraint("action IN ('index', 'delete')", name="ck_index_event_action"),
        sa.CheckConstraint("status IN ('done', 'failed')", name="ck_index_event_status"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    for table in ("index_event", "eval_run", "prompt_version", "lesson_chunk"):
        op.drop_table(table, schema=SCHEMA)
    # The vector extension and the schema are left in place: other objects may use them.
