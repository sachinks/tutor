from django.utils import timezone

from apps.catalogue.models import Lesson, Skill

from .models import CourseCompletion, LessonProgress, MasteryState

DONE_LEVELS = {MasteryState.Level.DEVELOPING, MasteryState.Level.MASTERED}


def mark_opened(student, lesson):
    LessonProgress.objects.get_or_create(student=student, lesson=lesson)


def mark_finished(student, lesson):
    progress, _ = LessonProgress.objects.get_or_create(student=student, lesson=lesson)
    if progress.status != LessonProgress.Status.FINISHED:
        progress.status = LessonProgress.Status.FINISHED
        progress.finished_at = timezone.now()
        progress.save(update_fields=["status", "finished_at"])


def check_course_completion(student, course) -> bool:
    """C4: every lesson finished AND every skill the course teaches at least 'developing'."""
    if CourseCompletion.objects.filter(student=student, course=course).exists():
        return True
    lesson_ids = set(Lesson.objects.filter(module__course=course).values_list("id", flat=True))
    finished = set(
        LessonProgress.objects.filter(student=student, lesson_id__in=lesson_ids, status="finished")
        .values_list("lesson_id", flat=True)
    )
    if not lesson_ids or finished != lesson_ids:
        return False
    skill_ids = set(
        Skill.objects.filter(lesson_links__lesson__module__course=course, lesson_links__role="teaches")
        .values_list("id", flat=True)
    )
    good = set(
        MasteryState.objects.filter(student=student, skill_id__in=skill_ids, level__in=DONE_LEVELS)
        .values_list("skill_id", flat=True)
    )
    if good != skill_ids:
        return False
    CourseCompletion.objects.get_or_create(student=student, course=course)
    return True
