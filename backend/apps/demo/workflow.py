"""Content in every review state, so reviewers, curriculum leads and admins have real work to test with.

    what-is-data (AI Foundations)          draft v2 by Tara
    equations-from-word-problems (Maths 8) in review, author Vikram, reviewer Neha
    solving-linear-equations (Maths 8)     approved, ready for Maya (Maths lead) to publish
    what-are-rational-numbers Q1 (Maths 8) approved question version, ready to publish

Created once: a lesson that already has an unpublished version is left alone (testers may have moved it on).
"""

from django.db import transaction

from apps.accounts.models import User
from apps.assessment import services as assessment_services
from apps.assessment.models import Question, QuestionVersion
from apps.catalogue.models import Lesson
from apps.content import services as content_services
from apps.content.models import ContentVersion

from .people import BY_KEY

PENDING = [
    # lesson slug, status, author key, reviewer key, note added to the lesson
    ("what-is-data", ContentVersion.Status.DRAFT, "teacher", None, "Draft: adds a section on data privacy."),
    (
        "equations-from-word-problems",
        ContentVersion.Status.IN_REVIEW,
        "vikram",
        "neha",
        "In review: adds a worked example on speed.",
    ),
    (
        "solving-linear-equations",
        ContentVersion.Status.APPROVED,
        "vikram",
        "neha",
        "Approved: clearer balance explanation.",
    ),
]
UNPUBLISHED = (ContentVersion.Status.DRAFT, ContentVersion.Status.IN_REVIEW, ContentVersion.Status.APPROVED)


def _user(key):
    return User.objects.get(mobile=BY_KEY[key].mobile) if key else None


@transaction.atomic
def build() -> int:
    created = 0
    for slug, status, author_key, reviewer_key, note in PENDING:
        lesson = Lesson.objects.get(slug=slug)
        if lesson.versions.filter(status__in=UNPUBLISHED).exists():
            continue
        current = content_services.published_version(lesson)
        sections = list(current.body.get("sections", [])) if current else []
        sections.append({"heading": "What's new in this version", "blocks": [{"type": "text", "text": note}]})
        ContentVersion.objects.create(
            lesson=lesson,
            version_no=content_services.next_version_no(lesson),
            body={"sections": sections},
            status=status,
            author=_user(author_key),
            reviewer=_user(reviewer_key),
        )
        created += 1

    question = Question.objects.filter(lesson__slug="what-are-rational-numbers", position=1).first()
    if question and not question.versions.filter(status__in=UNPUBLISHED).exists():
        body = dict(assessment_services.published_question_version(question).body)
        body["explanation"] = body["explanation"] + " (Division by zero is never allowed.)"
        QuestionVersion.objects.create(
            question=question,
            version_no=assessment_services.next_question_version_no(question),
            body=body,
            status=QuestionVersion.Status.APPROVED,
            author=_user("vikram"),
            reviewer=_user("neha"),
        )
        created += 1
    return created
