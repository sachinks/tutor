"""The lesson-index outbox (docs/architecture/ai-service.md §5).

Publishing content writes an IndexRequest in the same database transaction, so "published" and "needs indexing"
can never disagree, even if the AI service is down or the process dies right after the commit. A request says
only *which lesson changed*; whoever sends it reads the lesson's current state at that moment (index its published
version, or remove it if nothing is published). That makes requests safe to merge and to retry in any order.

- At most one pending request per lesson (a database constraint). A second change while one is pending bumps its
  `generation` instead of adding a row.
- A sender claims a request by pushing `next_attempt_at` forward (a lease), then calls the AI service outside any
  transaction. It completes the request only if `generation` is unchanged; if the lesson changed meanwhile, the
  request stays pending and is sent again with the new content.
- Failures are retried with exponential backoff; after MAX_ATTEMPTS, or at once when the AI service says the
  request is invalid, the request is marked failed and shown in the admin.
"""

from django.db import models
from django.db.models import Q
from django.utils import timezone


class IndexRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        DONE = "done", "Done"
        FAILED = "failed", "Failed"

    class Reason(models.TextChoices):
        PUBLISHED = "published", "Content published"
        RECONCILE = "reconcile", "Found out of step by sync_ai_index"
        MANUAL = "manual", "Requested in the admin"

    class Action(models.TextChoices):
        INDEX = "index", "Index"
        DELETE = "delete", "Delete"

    lesson_id = models.UUIDField(help_text="Not a foreign key: a deleted lesson must still leave the index.")
    reason = models.CharField(max_length=20, choices=Reason.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    generation = models.PositiveIntegerField(default=0, help_text="Bumped when the lesson changes again while pending.")
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(default=timezone.now)
    action = models.CharField(max_length=10, choices=Action.choices, blank=True, help_text="What was last sent.")
    target_version_id = models.UUIDField(null=True, blank=True, help_text="The content version last sent.")
    retryable = models.BooleanField(default=True, help_text="False when the AI service refused the request itself.")
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    done_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["lesson_id"], condition=Q(status="pending"), name="one_pending_index_request_per_lesson"
            ),
        ]
        indexes = [
            models.Index(fields=["status", "next_attempt_at"], name="aiservice_ir_due_idx"),
            models.Index(fields=["lesson_id"], name="aiservice_ir_lesson_idx"),
        ]

    def __str__(self):
        return f"Index lesson {self.lesson_id} ({self.status})"
