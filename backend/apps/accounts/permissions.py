"""Who may do privileged back-office actions (quality backlog Q4, decisions D14/D15/D19).

Being Django "staff" only opens the admin; what a person may *do* is decided here from their active
RoleGrants. Services call these checks, so the rules hold whether the action comes from the admin,
the API or a script.

    Publish lesson content / questions   curriculum lead for the course's subject and class, or super admin
    Grant or revoke roles                super admin
    Edit admin access (staff, superuser, permissions)   super admin
"""

from django.db.models import Q

from apps.core.errors import ApiError

from .models import RoleGrant

Role = RoleGrant.Role


def _active(user) -> bool:
    return bool(user is not None and user.is_authenticated and user.is_active and user.deleted_at is None)


def is_super_admin(user) -> bool:
    if not _active(user):
        return False
    return (
        user.is_superuser
        or RoleGrant.objects.filter(user=user, role=Role.SUPER_ADMIN, revoked_at__isnull=True).exists()
    )


def holds_role_for(user, role, subject_id, class_level_id) -> bool:
    """True if an active grant of ``role`` covers this subject and class.

    A grant with no subject covers every subject; a grant with no class covers every class. A board-independent
    course (no class) is covered only by grants without a class: a Class 8 lead doesn't own AI Foundations.
    """
    if not _active(user):
        return False
    grants = RoleGrant.objects.filter(user=user, role=role, revoked_at__isnull=True).filter(
        Q(subject__isnull=True) | Q(subject_id=subject_id)
    )
    if class_level_id is None:
        grants = grants.filter(class_level__isnull=True)
    else:
        grants = grants.filter(Q(class_level__isnull=True) | Q(class_level_id=class_level_id))
    return grants.exists()


def can_publish_for_lesson(user, lesson) -> bool:
    """Lesson content and its questions. Content without a lesson (e.g. a shared question bank) needs a super admin."""
    if is_super_admin(user):
        return True
    if lesson is None:
        return False
    course = lesson.module.course
    return holds_role_for(user, Role.CURRICULUM_LEAD, course.subject_id, course.class_level_id)


def require_can_publish(user, lesson):
    if not can_publish_for_lesson(user, lesson):
        raise ApiError(403, "forbidden", "Only the curriculum lead for this subject and class can publish this.")


def can_manage_roles(user) -> bool:
    return is_super_admin(user)
