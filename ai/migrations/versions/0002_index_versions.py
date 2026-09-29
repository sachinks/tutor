"""Lesson index bookkeeping: version numbers on chunks (stale-update guard) and result details on index events.

- lesson_chunk.version_no: the lesson's version number in Django. Indexing refuses a version older than the one
  already indexed, so a delayed retry can never replace newer content (design §5).
- index_event.version_no / chunk_count / embedding_model / updated_at: what a successful call produced, so a
  replayed request (same Idempotency-Key) gets the original answer, and failed attempts show when they last ran.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "ai"


def upgrade() -> None:
    # Existing rows (none are expected before step 3) get version 1; the default is removed straight after, so new
    # rows must always say which version they belong to.
    op.add_column(
        "lesson_chunk", sa.Column("version_no", sa.Integer, nullable=False, server_default="1"), schema=SCHEMA
    )
    op.alter_column("lesson_chunk", "version_no", server_default=None, schema=SCHEMA)
    op.create_check_constraint("ck_lesson_chunk_version_no", "lesson_chunk", "version_no >= 1", schema=SCHEMA)

    op.add_column("index_event", sa.Column("version_no", sa.Integer, nullable=True), schema=SCHEMA)
    op.add_column("index_event", sa.Column("chunk_count", sa.Integer, nullable=True), schema=SCHEMA)
    op.add_column("index_event", sa.Column("embedding_model", sa.String(100), nullable=True), schema=SCHEMA)
    op.add_column("index_event", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True), schema=SCHEMA)
    op.create_index("ix_index_event_lesson", "index_event", ["lesson_id"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_index_event_lesson", table_name="index_event", schema=SCHEMA)
    for column in ("updated_at", "embedding_model", "chunk_count", "version_no"):
        op.drop_column("index_event", column, schema=SCHEMA)
    op.drop_constraint("ck_lesson_chunk_version_no", "lesson_chunk", schema=SCHEMA)
    op.drop_column("lesson_chunk", "version_no", schema=SCHEMA)
