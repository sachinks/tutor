"""Keeping the AI service's lesson index in step with published content (docs/architecture/ai-service.md §5).

Entry points:
- lesson_changed(): called inside the transaction that publishes or retires lesson content.
- process(): sends due requests (sync_ai_index, and straight after a publish commits).
- reconcile(): compares the AI service's index with what is published and queues every difference.
"""

import logging
import uuid
from collections import Counter
from datetime import timedelta
from functools import partial
from typing import Any

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import F, Max
from django.utils import timezone

from apps.content.models import ContentVersion

from .client import AIServiceClient, AIServiceError, get_client, is_configured
from .models import IndexRequest

logger = logging.getLogger("tutor.aiservice")

MAX_ATTEMPTS = 8  # 30 s, 1, 2, 4, 8, 16, 32 min, then failed (≈ 1 h of trying); sync_ai_index can queue it again
LEASE = timedelta(minutes=5)  # a claimed request is invisible to other senders for this long
STOP_CODES = frozenset({"unreachable", "timeout"})  # the service is down: stop instead of failing every request


def backoff(attempts: int) -> timedelta:
    return timedelta(seconds=min(30 * 2 ** max(attempts - 1, 0), 3600))


# ---------------------------------------------------------------------------------------------------------------
# Queueing
# ---------------------------------------------------------------------------------------------------------------


def enqueue(lesson_id: uuid.UUID, reason: str) -> IndexRequest:
    """Record that a lesson needs (re)indexing. Joins the caller's transaction; safe under concurrency."""
    for _ in range(3):
        now = timezone.now()
        try:
            with transaction.atomic():  # savepoint: a lost race doesn't break the caller's transaction
                bumped = IndexRequest.objects.filter(lesson_id=lesson_id, status=IndexRequest.Status.PENDING).update(
                    generation=F("generation") + 1, next_attempt_at=now, updated_at=now
                )
                if bumped:
                    return IndexRequest.objects.get(lesson_id=lesson_id, status=IndexRequest.Status.PENDING)
                return IndexRequest.objects.create(lesson_id=lesson_id, reason=reason, next_attempt_at=now)
        except IntegrityError:
            continue  # another transaction created the pending row between our update and insert: bump that one
    raise RuntimeError(f"could not queue lesson {lesson_id} for indexing")  # pragma: no cover - needs 3 lost races


def lesson_changed(lesson_id: uuid.UUID, reason: str = IndexRequest.Reason.PUBLISHED) -> None:
    """Queue the lesson inside the current transaction and, once it commits, try to send it straight away."""
    enqueue(lesson_id, reason)
    if settings.TUTOR_AI_INDEX_ON_PUBLISH and is_configured():
        transaction.on_commit(partial(_send_now, lesson_id), robust=True)


def _send_now(lesson_id: uuid.UUID) -> None:
    """Best effort after commit: whatever fails here stays queued for sync_ai_index."""
    try:
        with get_client() as client:
            process(client, lesson_id=lesson_id, limit=1)
    except Exception:  # never let indexing break the publish that triggered it
        logger.warning("sending an index request after publish failed", exc_info=True)


# ---------------------------------------------------------------------------------------------------------------
# Sending
# ---------------------------------------------------------------------------------------------------------------


def build_payload(version: ContentVersion) -> dict[str, Any]:
    lesson = version.lesson
    course = lesson.module.course
    sections = []
    for section in version.sections:
        if not isinstance(section, dict):
            continue
        blocks = [b for b in section.get("blocks") or [] if isinstance(b, dict)]
        sections.append({"heading": str(section.get("heading") or ""), "blocks": blocks})
    return {
        "content_version_id": str(version.pk),
        "version_no": version.version_no,
        "course_id": str(course.pk),
        "subject": course.subject.name,
        "class_number": course.class_level.number if course.class_level_id else None,
        "title": lesson.title,
        "sections": sections,
    }


def _claim(exclude: set[int], include_waiting: bool, lesson_id: uuid.UUID | None) -> IndexRequest | None:
    now = timezone.now()
    with transaction.atomic():
        due = IndexRequest.objects.select_for_update(skip_locked=True).filter(status=IndexRequest.Status.PENDING)
        if not include_waiting:
            due = due.filter(next_attempt_at__lte=now)
        if lesson_id is not None:
            due = due.filter(lesson_id=lesson_id)
        request = due.exclude(pk__in=exclude).order_by("next_attempt_at", "pk").first()
        if request is None:
            return None
        request.next_attempt_at = now + LEASE
        request.save(update_fields=["next_attempt_at", "updated_at"])
    return request


def _complete(request: IndexRequest, generation: int, **changes: Any) -> bool:
    """Apply `changes` only if the lesson hasn't changed since the request was claimed."""
    changes["updated_at"] = timezone.now()
    return bool(IndexRequest.objects.filter(pk=request.pk, generation=generation).update(**changes))


def dispatch(request: IndexRequest, client: AIServiceClient) -> tuple[str, AIServiceError | None]:
    """Send one claimed request. Returns (outcome, error): outcome is done, retry, failed or requeued."""
    generation = request.generation
    published = (
        ContentVersion.objects.select_related("lesson__module__course__subject", "lesson__module__course__class_level")
        .filter(lesson_id=request.lesson_id, kind=ContentVersion.Kind.LESSON, status=ContentVersion.Status.PUBLISHED)
        .first()
    )
    key = f"django-ir{request.pk}-g{generation}"
    error: AIServiceError | None = None
    try:
        if published is not None:
            action, target = IndexRequest.Action.INDEX, published.pk
            client.index_lesson(request.lesson_id, build_payload(published), key=f"{key}-index-{published.pk}")
        else:
            action, target = IndexRequest.Action.DELETE, None
            newest = ContentVersion.objects.filter(lesson_id=request.lesson_id).aggregate(m=Max("version_no"))["m"]
            client.delete_lesson(request.lesson_id, key=f"{key}-delete-{newest or 0}", up_to_version=newest)
    except AIServiceError as exc:
        error = exc

    now = timezone.now()
    sent = {"action": action, "target_version_id": target}
    if error is None or error.code == "stale_version":  # stale: a newer version is already indexed, nothing to do
        note = "" if error is None else str(error)
        done = {"status": IndexRequest.Status.DONE, "done_at": now, "last_error": note, "retryable": True}
        if _complete(request, generation, **sent, **done):
            logger.info("lesson index updated", extra={"lesson_id": str(request.lesson_id), "action": action})
            return "done", error
        return "requeued", error

    attempts = request.attempts + 1
    if error.retryable and attempts < MAX_ATTEMPTS:
        changes = {"attempts": attempts, "next_attempt_at": now + backoff(attempts), "last_error": str(error)}
        outcome = "retry"
    else:
        changes = {
            "attempts": attempts,
            "status": IndexRequest.Status.FAILED,
            "retryable": error.retryable,
            "last_error": str(error),
        }
        outcome = "failed"
    logger.warning(
        "lesson index request failed",
        extra={"lesson_id": str(request.lesson_id), "code": error.code, "attempts": attempts, "outcome": outcome},
    )
    if _complete(request, generation, **sent, **changes):
        return outcome, error
    return "requeued", error  # the lesson changed while we were sending: try again with the new content


def process(
    client: AIServiceClient, *, limit: int = 500, include_waiting: bool = False, lesson_id: uuid.UUID | None = None
) -> Counter[str]:
    """Send up to `limit` due requests. Stops early if the AI service is unreachable, so an outage doesn't use up
    every request's attempts."""
    outcomes: Counter[str] = Counter()
    seen: set[int] = set()
    while len(seen) < limit:
        request = _claim(seen, include_waiting, lesson_id)
        if request is None:
            break
        seen.add(request.pk)
        outcome, error = dispatch(request, client)
        outcomes[outcome] += 1
        if error is not None and error.code in STOP_CODES:
            outcomes["stopped"] += 1
            break
    return outcomes


# ---------------------------------------------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------------------------------------------


def _uuid(value: Any) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except ValueError as exc:
        raise AIServiceError(f"invalid id in index status: {value!r}", code="bad_response") from exc


def reconcile(client: AIServiceClient) -> dict[str, int]:
    """Queue every lesson whose index entry differs from what is published (missing, older version, other embedding
    model, or indexed but no longer published). Lessons the AI service refused for their current version are left
    alone until the content changes."""
    status = client.index_status()
    try:
        model = str(status["embedding_model"])
        indexed = {
            _uuid(row["lesson_id"]): (_uuid(row["content_version_id"]), str(row["embedding_model"]))
            for row in status["lessons"]
        }
    except (KeyError, TypeError) as exc:
        raise AIServiceError("the index status has an unexpected shape", code="bad_response") from exc

    published = dict(
        ContentVersion.objects.filter(
            kind=ContentVersion.Kind.LESSON, status=ContentVersion.Status.PUBLISHED, lesson__isnull=False
        ).values_list("lesson_id", "pk")
    )
    refused = set(
        IndexRequest.objects.filter(
            status=IndexRequest.Status.FAILED, retryable=False, target_version_id__in=list(published.values())
        ).values_list("target_version_id", flat=True)
    )
    out_of_step: list[uuid.UUID] = []
    skipped = 0
    for lesson_id, version_id in published.items():
        if indexed.get(lesson_id) == (version_id, model):
            continue
        if version_id in refused:
            skipped += 1
            continue
        out_of_step.append(lesson_id)
    out_of_step.extend(sorted(indexed.keys() - published.keys()))

    already = set(
        IndexRequest.objects.filter(status=IndexRequest.Status.PENDING, lesson_id__in=out_of_step).values_list(
            "lesson_id", flat=True
        )
    )
    to_queue = [lesson_id for lesson_id in out_of_step if lesson_id not in already]  # keep their backoff as it is
    for lesson_id in to_queue:
        enqueue(lesson_id, IndexRequest.Reason.RECONCILE)
    summary = {
        "published": len(published),
        "indexed": len(indexed),
        "queued": len(to_queue),
        "already_queued": len(already),
        "skipped": skipped,
    }
    logger.info("lesson index reconciled", extra=summary)
    return summary
