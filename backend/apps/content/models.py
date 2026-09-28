"""Versioned lesson content with review (DATA_MODEL.md §6, M6).

Lesson body format (JSON):
{"sections": [{"heading": "What is data?", "blocks": [{"type": "text", "text": "Markdown…"},
                                                      {"type": "image", "asset": "<id>", "alt": "…"},
                                                      {"type": "example", "text": "Worked example…"}]}]}
Each section becomes one chunk for the AI tutor.
"""

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class ContentVersion(models.Model):
    class Kind(models.TextChoices):
        LESSON = "lesson", "Lesson"
        QUESTION = "question", "Question"  # linked to assessment.Question in the next step

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        IN_REVIEW = "in_review", "In review"
        CHANGES_REQUESTED = "changes_requested", "Changes requested"
        APPROVED = "approved", "Approved"
        PUBLISHED = "published", "Published"
        ARCHIVED = "archived", "Archived"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.LESSON)
    lesson = models.ForeignKey(
        "catalogue.Lesson", on_delete=models.CASCADE, null=True, blank=True, related_name="versions"
    )
    version_no = models.PositiveIntegerField()
    body = models.JSONField(default=dict)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    is_ai_draft = models.BooleanField(default=False)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="authored_versions")
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="reviewed_versions"
    )
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="published_versions"
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-version_no"]
        constraints = [
            models.UniqueConstraint(fields=["lesson", "version_no"], name="unique_lesson_version_no"),
            # A lesson has at most one published version at a time.
            models.UniqueConstraint(
                fields=["lesson"], condition=Q(status="published"), name="one_published_version_per_lesson"
            ),
            models.CheckConstraint(
                condition=Q(reviewer__isnull=True) | ~Q(reviewer=models.F("author")),
                name="reviewer_is_not_author",
            ),
        ]

    def __str__(self):
        target = self.lesson.title if self.lesson_id else self.kind
        return f"{target} v{self.version_no} ({self.status})"

    @property
    def sections(self):
        return self.body.get("sections", []) if isinstance(self.body, dict) else []


class ReviewComment(models.Model):
    version = models.ForeignKey(ContentVersion, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    section_ref = models.CharField(max_length=150, blank=True)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Comment on {self.version}"
