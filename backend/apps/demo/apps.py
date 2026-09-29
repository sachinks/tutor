from django.apps import AppConfig


class DemoConfig(AppConfig):
    """Demo data for local development and the hosted demo (D29). No models; never used by production code paths."""

    name = "apps.demo"
    label = "demo"
    verbose_name = "Demo data"
