"""AI tutor records (DATA_MODEL: tutor app; decisions D13, D40).

- A conversation belongs to one student and one lesson. Messages store the student's text with personal data already
  hidden by the AI service's input check, and the tutor's final text (never the streamed pieces).
- Safety flags point at the message that raised them. High and critical flags are visible to the parent in full
  (D13); Operations reviews them in the admin safety queue.
- Usage counters (no text) enforce the daily message limit per IST day.
- Retention (D40): purge_tutor_chats deletes conversations 90 days after their last message unless a flag is open or
  was closed less than 90 days ago. Deleting the student deletes everything (consent withdrawal, M5).
"""

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class Mode(models.TextChoices):
    EXPLAIN = "explain", "Explain"
    SOCRATIC = "socratic", "Guide me"
    HINT = "hint", "Hint"


class TutorConversation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tutor_conversations")
    lesson = models.ForeignKey("catalogue.Lesson", on_delete=models.CASCADE, related_name="+")
    content_version_id = models.UUIDField(help_text="The published lesson version when the chat started.")
    mode = models.CharField(max_length=10, choices=Mode.choices, default=Mode.EXPLAIN)
    pinned_chunk_ids = models.JSONField(default=list, blank=True, help_text="Lesson passages chosen by the AI service.")
    flagged = models.BooleanField(default=False, help_text="At least one safety flag was raised in this chat.")
    hidden_by_student = models.BooleanField(default=False, help_text="Deleted by the student but kept for a flag.")
    created_at = models.DateTimeField(auto_now_add=True)
    last_message_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-last_message_at"]
        indexes = [
            models.Index(fields=["student", "lesson", "-last_message_at"], name="tutor_conv_student_idx"),
            models.Index(fields=["last_message_at"], name="tutor_conv_retention_idx"),
        ]

    def __str__(self):
        return f"Tutor chat {self.id} ({self.lesson_id})"


class TutorMessage(models.Model):
    class Role(models.TextChoices):
        STUDENT = "student", "Student"
        TUTOR = "tutor", "Tutor"

    conversation = models.ForeignKey(TutorConversation, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=10, choices=Role.choices)
    text = models.TextField()
    mode = models.CharField(max_length=10, choices=Mode.choices, default=Mode.EXPLAIN)
    blocked = models.BooleanField(default=False, help_text="Answered with a fixed safety reply.")
    replaced = models.BooleanField(default=False, help_text="The model's reply was stopped and replaced.")
    off_topic = models.BooleanField(default=False)
    citations = models.JSONField(default=list, blank=True)
    model = models.CharField(max_length=100, blank=True)
    prompt_version = models.CharField(max_length=40, blank=True)
    safety_version = models.CharField(max_length=40, blank=True)
    latency_ms = models.PositiveIntegerField(null=True, blank=True)
    prompt_tokens = models.PositiveIntegerField(default=0)
    reply_tokens = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"{self.role}: {self.text[:40]}"


class SafetyFlag(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        REVIEWED = "reviewed", "Reviewed"
        CLOSED = "closed", "Closed"

    class Severity(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    conversation = models.ForeignKey(TutorConversation, on_delete=models.CASCADE, related_name="flags")
    message = models.ForeignKey(TutorMessage, on_delete=models.CASCADE, null=True, blank=True, related_name="flags")
    stage = models.CharField(max_length=10, help_text="input (student) or output (tutor)")
    category = models.CharField(max_length=40)
    severity = models.CharField(max_length=10, choices=Severity.choices)
    parent_visible = models.BooleanField(default=False, help_text="High and critical: the parent sees the chat (D13).")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    note = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "severity"], name="tutor_flag_queue_idx")]

    def __str__(self):
        return f"{self.severity} {self.category} ({self.status})"


class UsageCounter(models.Model):
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    day = models.DateField(help_text="IST day (C14).")
    messages = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["student", "day"], name="unique_tutor_usage_per_day")]

    def __str__(self):
        return f"{self.student_id} {self.day}: {self.messages}"
