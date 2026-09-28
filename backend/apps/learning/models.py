"""The learner record (DATA_MODEL.md §8): what a student has really achieved."""

from django.conf import settings
from django.db import models


class MasteryState(models.Model):
    class Level(models.TextChoices):
        NOT_STARTED = "not_started", "Not started"
        WEAK = "weak", "Needs help"
        DEVELOPING = "developing", "In progress"
        MASTERED = "mastered", "Mastered"

    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="mastery")
    skill = models.ForeignKey("catalogue.Skill", on_delete=models.CASCADE, related_name="+")
    score = models.FloatField(default=0.0)
    evidence_count = models.PositiveIntegerField(default=0)
    level = models.CharField(max_length=12, choices=Level.choices, default=Level.NOT_STARTED)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["student", "skill"], name="unique_mastery_per_skill")]

    def __str__(self):
        return f"{self.student} · {self.skill.code}: {self.level} ({self.score:.2f})"


class MasteryEvent(models.Model):
    """Every change to mastery and its cause, so mastery is always explainable."""

    class Source(models.TextChoices):
        QUIZ = "quiz", "Quiz"
        WARMUP = "warmup", "Warm-up"
        TEACHER = "teacher", "Teacher"

    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    skill = models.ForeignKey("catalogue.Skill", on_delete=models.CASCADE, related_name="+")
    answer = models.ForeignKey("assessment.Answer", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.QUIZ)
    old_score = models.FloatField()
    new_score = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.skill.code}: {self.old_score:.2f} → {self.new_score:.2f}"


class LessonProgress(models.Model):
    class Status(models.TextChoices):
        OPENED = "opened", "Opened"
        FINISHED = "finished", "Finished"

    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="lesson_progress")
    lesson = models.ForeignKey("catalogue.Lesson", on_delete=models.CASCADE, related_name="+")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPENED)
    first_opened_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["student", "lesson"], name="unique_lesson_progress")]

    def __str__(self):
        return f"{self.student} · {self.lesson}: {self.status}"


class CourseCompletion(models.Model):
    """'Completed course X' — counts in every programme containing it (the learner record rule)."""

    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="course_completions")
    course = models.ForeignKey("catalogue.Course", on_delete=models.CASCADE, related_name="+")
    completed_at = models.DateTimeField(auto_now_add=True)
    via = models.CharField(max_length=12, default="self_paced")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["student", "course"], name="unique_course_completion")]

    def __str__(self):
        return f"{self.student} completed {self.course}"
