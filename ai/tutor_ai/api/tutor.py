"""Tutor endpoints (design §3). Called only by Django, which has already checked login, consent, entitlement and the
student's daily limit; this service never looks anything up about the student."""

import json
import logging
import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from ..prompt_builder import Turn
from ..safety import SafetyPolicy
from ..tutor import LessonRef, TurnRequest, TutorService
from .deps import Engine, Provider

logger = logging.getLogger("tutor_ai.api.tutor")

router = APIRouter(tags=["tutor"])


class LessonIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    version_id: uuid.UUID
    course_id: uuid.UUID
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]


class HistoryTurnIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["student", "tutor"]
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


class GuardIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    open_quiz: bool = False
    protected_answers: list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]] = (
        Field(default_factory=list, max_length=20)
    )


class LimitsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_reply_tokens: int = Field(250, ge=20, le=2000)


class TurnIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    learner_ref: Annotated[str, StringConstraints(pattern=r"^lr_[A-Za-z0-9_-]{8,64}$")]
    chat_id: uuid.UUID
    class_number: int | None = Field(None, ge=1, le=12)
    lesson: LessonIn
    mode: Literal["explain", "socratic", "hint"] = "explain"
    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    history: list[HistoryTurnIn] = Field(default_factory=list, max_length=40)
    pinned_chunk_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)
    guard: GuardIn = Field(default_factory=GuardIn)
    limits: LimitsIn = Field(default_factory=LimitsIn)


class SafetyCheckIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: Annotated[str, StringConstraints(min_length=1, max_length=4000)]


class SafetyCheckOut(BaseModel):
    category: str
    severity: str
    flagged: bool


def _policy(request: Request) -> SafetyPolicy:
    policy: SafetyPolicy = request.app.state.safety
    return policy


Policy = Annotated[SafetyPolicy, Depends(_policy)]


def sse(event: str, data: dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post(
    "/tutor/turns",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}, "description": "meta, delta…, final | error"}},
)
async def tutor_turn(
    body: TurnIn, request: Request, engine: Engine, provider: Provider, policy: Policy
) -> StreamingResponse:
    """One tutor turn as Server-Sent Events: `meta`, many `delta`, then one `final` (or one `error`)."""
    service = TutorService(engine, provider, request.app.state.prompts, policy, request.app.state.settings)
    turn = TurnRequest(
        learner_ref=body.learner_ref,
        chat_id=body.chat_id,
        class_number=body.class_number,
        lesson=LessonRef(body.lesson.id, body.lesson.version_id, body.lesson.course_id, body.lesson.title),
        mode=body.mode,
        message=body.message,
        history=[Turn(t.role, t.text) for t in body.history],
        pinned_chunk_ids=body.pinned_chunk_ids,
        open_quiz=body.guard.open_quiz,
        protected_answers=body.guard.protected_answers,
        max_reply_tokens=body.limits.max_reply_tokens,
    )

    async def events() -> AsyncIterator[str]:
        try:
            async for name, data in service.turn(turn):
                yield sse(name, data)
        except Exception:  # the response has started: report the failure as an event, never a broken stream
            logger.exception("tutor turn crashed", extra={"chat_id": str(body.chat_id)})
            yield sse("error", {"code": "server_error", "message": "Something went wrong on our side."})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},  # proxies must not buffer the stream
    )


@router.post("/safety/check", response_model=SafetyCheckOut)
async def safety_check(body: SafetyCheckIn, policy: Policy) -> SafetyCheckOut:
    """Classify a text with the current safety policy (for parent-visible content later). The text is not stored."""
    verdict = policy.classify(body.text)
    if verdict.severity in ("none", "low") and policy.is_injection(body.text):
        return SafetyCheckOut(category="injection", severity=policy.injection_severity, flagged=True)
    return SafetyCheckOut(**verdict.as_dict())
