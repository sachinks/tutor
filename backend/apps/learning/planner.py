"""The 'Today' screen (journey S8): chosen from the learner record, never at random."""
from datetime import timedelta

from django.utils import timezone

from apps.assessment.models import Answer
from apps.catalogue.models import Lesson, PublishStatus

from .access import entitled_course_ids
from .models import LessonProgress, MasteryState


def accessible_lessons(student):
    """Lessons in entitled courses, in course order (school chapter order within a course)."""
    return (
        Lesson.objects.filter(module__course_id__in=entitled_course_ids(student),
                              module__course__status=PublishStatus.PUBLISHED)
        .select_related("module__course")
        .order_by("module__course__title", "module__position", "position")
    )


def next_lesson(student):
    finished = set(
        LessonProgress.objects.filter(student=student, status="finished").values_list("lesson_id", flat=True)
    )
    for lesson in accessible_lessons(student):
        if lesson.id not in finished:
            return lesson
    return None


def review_item(student):
    """The weakest practised skill, and a lesson that teaches it."""
    weakest = (
        MasteryState.objects.filter(student=student, evidence_count__gt=0)
        .exclude(level=MasteryState.Level.MASTERED)
        .select_related("skill").order_by("score").first()
    )
    if not weakest:
        return None
    lesson = accessible_lessons(student).filter(skill_links__skill=weakest.skill).first()
    return {"skill": weakest.skill, "state": weakest, "lesson": lesson}


def streak_days(student) -> int:
    # Days are counted in IST (TIME_ZONE), not UTC: 1 a.m. in Kolkata is still "today" for the student.
    local = timezone.localtime
    days = set(
        local(a).date() for a in Answer.objects.filter(item__attempt__student=student).values_list("answered_at", flat=True)
    ) | set(
        local(f).date() for f in LessonProgress.objects.filter(student=student, finished_at__isnull=False)
        .values_list("finished_at", flat=True)
    )
    today = timezone.localdate()
    streak = 0
    day = today
    while day in days:
        streak += 1
        day -= timedelta(days=1)
    return streak
