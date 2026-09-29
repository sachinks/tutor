"""Lesson index endpoints (design §3, §5). Called only by Django, which decides *what* is published; this service
only keeps the index in step with what it is told."""

import uuid
from datetime import datetime
from typing import Annotated, Literal, Self

from fastapi import APIRouter, Header, Query, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .. import indexing
from .deps import Engine, Provider

router = APIRouter(tags=["index"])

MAX_LESSON_CHARACTERS = 500_000

IdempotencyKey = Annotated[
    str,
    Header(
        alias="Idempotency-Key",
        pattern=r"^[A-Za-z0-9._:-]{8,100}$",
        description="Unique per logical request; a retry of the same request sends the same key.",
    ),
]


class Block(BaseModel):
    """One content block as stored by Django. Unknown block types are accepted and ignored if they have no text,
    so new block types in the editor never break indexing."""

    model_config = ConfigDict(extra="ignore")

    type: str = Field(min_length=1, max_length=30)
    text: str | None = Field(None, max_length=20_000)
    alt: str | None = Field(None, max_length=300)


class Section(BaseModel):
    model_config = ConfigDict(extra="ignore")

    heading: str = Field("", max_length=200)
    blocks: list[Block] = Field(default_factory=list, max_length=100)


class IndexLessonIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_version_id: uuid.UUID
    version_no: int = Field(ge=1, le=1_000_000)
    course_id: uuid.UUID
    subject: str = Field(min_length=1, max_length=80)
    class_number: int | None = Field(None, ge=1, le=12)  # None for board-independent courses
    title: str = Field(min_length=1, max_length=150)
    sections: list[Section] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def _total_size(self) -> Self:
        total = sum(len(b.text or "") + len(b.alt or "") for s in self.sections for b in s.blocks)
        if total > MAX_LESSON_CHARACTERS:
            raise ValueError(f"the lesson has {total} characters of text; the limit is {MAX_LESSON_CHARACTERS}")
        return self


class IndexLessonOut(BaseModel):
    lesson_id: uuid.UUID
    content_version_id: uuid.UUID
    version_no: int
    chunks: int
    embedding_model: str
    status: Literal["indexed", "unchanged"]


class IndexedLessonOut(BaseModel):
    lesson_id: uuid.UUID
    content_version_id: uuid.UUID
    version_no: int
    embedding_model: str
    chunks: int
    indexed_at: datetime


class IndexStatusOut(BaseModel):
    embedding_model: str = Field(description="The model new chunks are embedded with; others need a re-index.")
    lessons: list[IndexedLessonOut]


@router.put("/lessons/{lesson_id}/index", response_model=IndexLessonOut)
async def index_lesson(
    lesson_id: uuid.UUID, body: IndexLessonIn, key: IdempotencyKey, engine: Engine, provider: Provider
) -> IndexLessonOut:
    """Index one published lesson version, replacing whatever was indexed for the lesson."""
    doc = indexing.LessonDocument(
        lesson_id=lesson_id,
        content_version_id=body.content_version_id,
        version_no=body.version_no,
        course_id=body.course_id,
        subject=body.subject,
        class_number=body.class_number,
        title=body.title,
        sections=[s.model_dump() for s in body.sections],
    )
    result = await indexing.index_lesson(engine, provider, doc, key)
    return IndexLessonOut(**result.__dict__)


@router.delete("/lessons/{lesson_id}/index", status_code=204)
async def delete_lesson(
    lesson_id: uuid.UUID,
    key: IdempotencyKey,
    engine: Engine,
    up_to_version: Annotated[int | None, Query(ge=1, description="Refuse if a newer version is indexed.")] = None,
) -> Response:
    """Remove a lesson from the index (no longer published). Removing a lesson that isn't indexed is not an
    error."""
    await indexing.delete_lesson(engine, lesson_id, key, up_to_version)
    return Response(status_code=204)


@router.get("/index/status", response_model=IndexStatusOut)
async def index_status(engine: Engine, provider: Provider) -> IndexStatusOut:
    """Every indexed lesson with its version and embedding model, for Django's reconciliation."""
    lessons = await indexing.indexed_lessons(engine)
    return IndexStatusOut(
        embedding_model=provider.embedding_model,
        lessons=[IndexedLessonOut(**lesson.__dict__) for lesson in lessons],
    )
