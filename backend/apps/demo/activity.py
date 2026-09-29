"""Learning history for demo students, created through the real services so mastery, progress and course
completion follow the production rules exactly. Each quiz is then moved back in time, so streaks and
"recent activity" look real. Runs once per student (skipped if the student already has quiz attempts);
``reset`` removes demo students' history so it can be rebuilt.
"""

from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.assessment import services as quiz
from apps.assessment.models import Answer, Attempt
from apps.catalogue.models import Lesson
from apps.learning import progress
from apps.learning.models import CourseCompletion, LessonProgress, MasteryEvent, MasteryState

from .people import BY_KEY


@dataclass(frozen=True)
class QuizRun:
    lesson: str  # lesson slug
    pattern: str  # one letter per question: C = correct, W = wrong, H = correct after one hint
    days_ago: int


# Chronological per student (oldest first), because mastery depends on order.
HISTORY = {
    "student_enrolled": [QuizRun("what-is-data", "CCW", 2)],
    "kabir": [
        QuizRun("what-is-data", "CCC", 12),
        QuizRun("learning-from-examples", "CHC", 11),
        QuizRun("is-the-model-any-good", "CCC", 10),
        QuizRun("what-are-rational-numbers", "CCCW", 6),
        QuizRun("inverses-of-rational-numbers", "WCWW", 5),
        QuizRun("solving-linear-equations", "CWCC", 2),
        QuizRun("force-push-and-pull", "CCCC", 1),
    ],
    "meera": [
        QuizRun("si-units", "CCCC", 2),
        QuizRun("significant-figures", "CWWH", 1),
        QuizRun("speed-and-velocity", "CCWC", 0),
    ],
    "zoya": [
        QuizRun("place-value-large-numbers", "CCWC", 4),
        QuizRun("comparing-and-estimating", "CHCC", 3),
        QuizRun("what-is-a-fraction", "CCCW", 2),
        QuizRun("equivalent-fractions", "WCWC", 1),
        QuizRun("equivalent-fractions", "CCCC", 0),  # retake the next day
    ],
    "rohan": [QuizRun("what-are-rational-numbers", "WWCW", 20)],
}
# Opened a free lesson but never took the quiz.
OPENED_ONLY = {"student_active": ["what-is-data"], "ishaan": ["si-units"]}


def _run_quiz(student, lesson, pattern, when):
    attempt = quiz.start_lesson_quiz(student, lesson)
    items = list(attempt.items.select_related("question_version").order_by("position"))
    for i, item in enumerate(items):
        mark = pattern[min(i, len(pattern) - 1)]
        body = item.question_version.body
        correct = body["answer_index"]
        if mark == "H" and body.get("hints"):
            quiz.use_hint(student, attempt.id, item.position)
        choice = correct if mark in "CH" else (correct + 1) % len(body["options"])
        quiz.answer_item(student, attempt.id, item.position, choice)
    quiz.submit_attempt(student, attempt.id)
    # Move this quiz back in time. auto_now_add fields can only be changed with update().
    Attempt.objects.filter(pk=attempt.pk).update(started_at=when - timedelta(minutes=12), submitted_at=when)
    Answer.objects.filter(item__attempt=attempt).update(answered_at=when)
    MasteryEvent.objects.filter(answer__item__attempt=attempt).update(created_at=when)
    LessonProgress.objects.filter(student=student, lesson=lesson).update(finished_at=when)
    CourseCompletion.objects.filter(student=student, course=lesson.module.course, completed_at__gt=when).update(
        completed_at=when
    )


def study_time(now, days_ago):
    """10:00 IST on the day `days_ago` days before `now`, never in the future (streaks are counted in IST, C14)."""
    local = timezone.localtime(now)
    when = (local - timedelta(days=days_ago)).replace(hour=10, minute=0, second=0, microsecond=0)
    return min(when, now)


def _user(key):
    return User.objects.get(mobile=BY_KEY[key].mobile)


@transaction.atomic
def build(now=None) -> int:
    """Create missing history. Returns the number of quizzes created."""
    now = now or timezone.now()
    created = 0
    for key, runs in HISTORY.items():
        student = _user(key)
        if Attempt.objects.filter(student=student).exists():
            continue
        paused = student.student_profile.status != "active"
        if paused:  # history from before consent was withdrawn: build it as if active
            student.student_profile.status = "active"
            student.student_profile.save(update_fields=["status"])
        for run in runs:
            lesson = Lesson.objects.select_related("module__course").get(slug=run.lesson)
            progress.mark_opened(student, lesson)
            _run_quiz(student, lesson, run.pattern, study_time(now, run.days_ago))
            created += 1
        if paused:
            student.student_profile.status = "paused"
            student.student_profile.save(update_fields=["status"])
    for key, slugs in OPENED_ONLY.items():
        student = _user(key)
        for slug in slugs:
            progress.mark_opened(student, Lesson.objects.get(slug=slug))
    return created


@transaction.atomic
def reset():
    """Delete demo students' learning history (quizzes, mastery, progress, completions)."""
    students = [_user(key) for key in {*HISTORY, *OPENED_ONLY}]
    Attempt.objects.filter(student__in=students).delete()
    MasteryEvent.objects.filter(student__in=students).delete()
    MasteryState.objects.filter(student__in=students).delete()
    LessonProgress.objects.filter(student__in=students).delete()
    CourseCompletion.objects.filter(student__in=students).delete()
