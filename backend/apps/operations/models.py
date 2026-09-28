from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """Who changed what, when (DATA_MODEL.md §12). Append-only: never edited or deleted in the app."""

    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=60)  # e.g. "consent.given"
    object_type = models.CharField(max_length=60)
    object_id = models.CharField(max_length=64)
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["object_type", "object_id"])]

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.action} {self.object_type}:{self.object_id}"
