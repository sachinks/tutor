"""Who may do what. Every student-learning endpoint goes through these checks (API_CONTRACTS §2.6–2.8)."""
from apps.catalogue.models import ProgrammeCourse, PublishStatus
from apps.commerce.models import Entitlement
from apps.core.errors import ApiError


def require_active_student(user):
    """Student✓: a student account with active parental consent (D10)."""
    profile = getattr(user, "student_profile", None) if hasattr(user, "student_profile") else None
    if profile is None:
        raise ApiError(403, "forbidden", "Only a student account can do this.")
    if profile.status != "active":
        raise ApiError(403, "consent_required", "A parent needs to approve your account first.")
    return profile


def entitled_course_ids(student) -> set:
    ents = Entitlement.active_for(student)
    course_ids = set(ents.filter(product_type="course").values_list("product_id", flat=True))
    programme_ids = ents.filter(product_type="programme").values_list("product_id", flat=True)
    course_ids |= set(
        ProgrammeCourse.objects.filter(programme_id__in=programme_ids).values_list("course_id", flat=True)
    )
    return course_ids


def can_open_lesson(student, lesson) -> bool:
    course = lesson.module.course
    if course.status != PublishStatus.PUBLISHED:
        return False
    return lesson.module_id == course.free_module_id or course.id in entitled_course_ids(student)


def require_lesson_access(student, lesson):
    if not can_open_lesson(student, lesson):
        raise ApiError(403, "not_entitled", "Enrol in the course to open this lesson.")
