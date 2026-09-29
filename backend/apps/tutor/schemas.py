from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from ninja import Schema
from pydantic import Field, StringConstraints

ModeName = Literal["explain", "socratic", "hint"]
Message = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class StartIn(Schema):
    lesson_id: UUID
    mode: ModeName = "explain"


class MessageIn(Schema):
    message: Message
    mode: ModeName = "explain"


class Citation(Schema):
    label: str
    heading: str


class MessageOut(Schema):
    id: int
    role: str
    text: str
    mode: str
    blocked: bool
    off_topic: bool
    citations: list[Citation]
    created_at: datetime

    @staticmethod
    def resolve_citations(obj):
        return [{"label": c.get("label", ""), "heading": c.get("heading", "")} for c in obj.citations or []]


class UsageOut(Schema):
    used: int
    limit: int
    left: int


class ConversationOut(Schema):
    id: UUID
    lesson_id: UUID
    lesson_title: str
    mode: str
    created_at: datetime
    last_message_at: datetime

    @staticmethod
    def resolve_lesson_title(obj):
        return obj["lesson_title"] if isinstance(obj, dict) else obj.lesson.title


class ConversationDetailOut(ConversationOut):
    messages: list[MessageOut] = Field(default_factory=list)
    usage: UsageOut
