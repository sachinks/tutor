"""Tables in the `ai` schema (design §5). The AI service owns this schema and nothing else (M7).

Alembic migrations in ai/migrations are the source of truth for the database; these Table objects must match them.
`alembic check` in CI fails if they drift apart.
"""

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

SCHEMA = "ai"
EMBEDDING_DIMENSIONS = 768  # nomic-embed-text; a different model means a new column/migration and a re-index

metadata = MetaData(schema=SCHEMA)

lesson_chunk = Table(
    "lesson_chunk",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()),
    Column("lesson_id", UUID(as_uuid=True), nullable=False),
    Column("content_version_id", UUID(as_uuid=True), nullable=False),
    Column("version_no", Integer, nullable=False),  # Django's version number: older versions never replace newer
    Column("course_id", UUID(as_uuid=True), nullable=False),
    Column("subject", String(80), nullable=False),
    Column("class_number", Integer, nullable=True),  # None = board-independent course
    Column("position", Integer, nullable=False),
    Column("heading", String(200), nullable=False),
    Column("text", Text, nullable=False),
    Column("token_count", Integer, nullable=False),
    Column("embedding", Vector(EMBEDDING_DIMENSIONS), nullable=False),
    Column("embedding_model", String(100), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("lesson_id", "content_version_id", "position", name="uq_lesson_chunk_position"),
    CheckConstraint("position >= 0", name="ck_lesson_chunk_position"),
    CheckConstraint("token_count > 0", name="ck_lesson_chunk_tokens"),
    CheckConstraint("version_no >= 1", name="ck_lesson_chunk_version_no"),
    Index("ix_lesson_chunk_lesson", "lesson_id"),
    Index("ix_lesson_chunk_course", "course_id"),
    Index(
        "ix_lesson_chunk_embedding_hnsw",
        "embedding",
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    ),
)

prompt_version = Table(
    "prompt_version",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(100), nullable=False),
    Column("version", String(40), nullable=False),
    Column("body", Text, nullable=False),
    Column("checksum", String(64), nullable=False),
    Column("active", Boolean, nullable=False, server_default="false"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("name", "version", name="uq_prompt_version"),
)

eval_run = Table(
    "eval_run",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()),
    Column("suite", String(100), nullable=False),
    Column("prompt_version", String(40), nullable=False),
    Column("provider", String(40), nullable=False),
    Column("model", String(100), nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    Column("pass_rate", Float, nullable=True),
    Column("results", JSONB, nullable=False, server_default="{}"),
    CheckConstraint("pass_rate IS NULL OR (pass_rate >= 0 AND pass_rate <= 1)", name="ck_eval_run_pass_rate"),
)

index_event = Table(
    "index_event",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("lesson_id", UUID(as_uuid=True), nullable=False),
    Column("content_version_id", UUID(as_uuid=True), nullable=True),
    Column("action", String(20), nullable=False),
    Column("idempotency_key", String(100), nullable=False),
    Column("status", String(20), nullable=False),
    Column("error", Text, nullable=True),
    Column("version_no", Integer, nullable=True),
    Column("chunk_count", Integer, nullable=True),
    Column("embedding_model", String(100), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=True),
    UniqueConstraint("idempotency_key", name="uq_index_event_idempotency_key"),
    CheckConstraint("action IN ('index', 'delete')", name="ck_index_event_action"),
    CheckConstraint("status IN ('done', 'failed')", name="ck_index_event_status"),
    Index("ix_index_event_lesson", "lesson_id"),
)
