"""Quiz API — API_CONTRACTS.md §2.7. Correct answers are never sent before the student answers."""
from uuid import UUID

from ninja import Router
from ninja.security import django_auth

from apps.catalogue.api import lessons_router
from apps.learning import planner
from apps.learning.access import require_active_student
from apps.learning.api import get_lesson_for_student

from . import services
from .schemas import AnswerIn, AnswerResultOut, AttemptOut, HintOut, PositionIn, SubmitOut

attempts_router = Router(tags=["quiz"], auth=django_auth)


def attempt_payload(attempt):
    items = attempt.items.select_related("question_version").prefetch_related("answer")
    return {
        "attempt_id": attempt.id,
        "lesson_id": attempt.lesson_id,
        "items": [
            {
                "position": it.position,
                "stem": it.question_version.body.get("stem", ""),
                "options": it.question_version.body.get("options", []),
                "hints_available": len(it.question_version.body.get("hints", [])) - it.hints_used,
                "hints_used": it.hints_used,
                "answered": hasattr(it, "answer"),
            }
            for it in items
        ],
    }


@lessons_router.post("/{lesson_id}/quiz/start", response=AttemptOut, auth=django_auth, tags=["quiz"])
def start_quiz(request, lesson_id: UUID):
    lesson = get_lesson_for_student(request.user, lesson_id)
    return attempt_payload(services.start_lesson_quiz(request.user, lesson))


@attempts_router.post("/{attempt_id}/hint", response=HintOut)
def hint(request, attempt_id: UUID, payload: PositionIn):
    require_active_student(request.user)
    text, left = services.use_hint(request.user, attempt_id, payload.position)
    return {"hint": text, "hints_left": left}


@attempts_router.post("/{attempt_id}/answers", response=AnswerResultOut)
def answer(request, attempt_id: UUID, payload: AnswerIn):
    require_active_student(request.user)
    return services.answer_item(request.user, attempt_id, payload.position, payload.choice_index)


@attempts_router.post("/{attempt_id}/submit", response=SubmitOut)
def submit(request, attempt_id: UUID):
    require_active_student(request.user)
    attempt, changes, completed = services.submit_attempt(request.user, attempt_id)
    nxt = planner.next_lesson(request.user)
    return {
        "score": attempt.score, "max_score": attempt.max_score, "skill_changes": changes,
        "course_completed": completed, "next_lesson_id": nxt.id if nxt else None,
    }
