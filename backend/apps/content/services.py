from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.core.errors import ApiError
from apps.operations import audit

from .models import ContentVersion


def published_version(lesson):
    return lesson.versions.filter(status=ContentVersion.Status.PUBLISHED).first()


def next_version_no(lesson):
    return (lesson.versions.aggregate(m=Max("version_no"))["m"] or 0) + 1


@transaction.atomic
def publish(version: ContentVersion, by_user):
    """Publish an approved version. The previous published version is archived, never edited (M6)."""
    if version.status != ContentVersion.Status.APPROVED:
        raise ApiError(409, "conflict", "Only approved content can be published.")
    now = timezone.now()
    previous = published_version(version.lesson) if version.lesson_id else None
    if previous:
        previous.status = ContentVersion.Status.ARCHIVED
        previous.save(update_fields=["status", "updated_at"])
    version.status = ContentVersion.Status.PUBLISHED
    version.published_at = now
    version.published_by = by_user
    version.save(update_fields=["status", "published_at", "published_by", "updated_at"])
    audit.record(by_user, "content.published", version,
                 before={"previous": str(previous.pk) if previous else None})
    # Next step: tell the background worker to re-index this lesson for the AI tutor.
    return version
