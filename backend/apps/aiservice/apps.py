from django.apps import AppConfig
from django.core import checks


class AIServiceConfig(AppConfig):
    """Everything Django needs to talk to the AI service (docs/architecture/ai-service.md): the HTTP client, the
    lesson-index outbox and the sync command. The tutor app (milestone 5 step 5) reuses the client."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.aiservice"
    label = "aiservice"
    verbose_name = "AI service"

    def ready(self):
        checks.register(check_ai_settings, checks.Tags.security)


def check_ai_settings(app_configs=None, **kwargs):
    """A configured AI service needs a strong token; an empty URL simply means 'no AI service here'."""
    from django.conf import settings

    from .client import MIN_TOKEN_LENGTH

    if settings.TUTOR_AI_URL and len(settings.TUTOR_AI_SERVICE_TOKEN) < MIN_TOKEN_LENGTH:
        return [
            checks.Error(
                f"TUTOR_AI_SERVICE_TOKEN must be at least {MIN_TOKEN_LENGTH} characters when TUTOR_AI_URL is set.",
                hint='Generate one with: python -c "import secrets; print(secrets.token_urlsafe(48))"',
                id="aiservice.E001",
            )
        ]
    if settings.TUTOR_AI_URL and not settings.TUTOR_AI_URL.startswith(("http://", "https://")):
        return [checks.Error("TUTOR_AI_URL must start with http:// or https://.", id="aiservice.E002")]
    return []
