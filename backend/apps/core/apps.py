from django.apps import AppConfig


class CoreConfig(AppConfig):
    """Shared plumbing (errors, logging, rate limits, messaging). No models; installed for its management commands."""

    name = "apps.core"
    label = "tutor_core"
    verbose_name = "Core"
