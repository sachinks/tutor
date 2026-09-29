from django.apps import AppConfig


class TutorConfig(AppConfig):
    """The student-facing AI tutor (docs/architecture/ai-service.md): who may ask, what is stored, limits, safety
    flags and retention. The AI service does the thinking; this app owns everything about the student."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.tutor"
    label = "tutor"
    verbose_name = "AI tutor"
