"""Commerce (DATA_MODEL.md §10). This step adds only Entitlement: the single source of truth for access (C6).
Orders, payments and refunds arrive with the Razorpay step; until then admins can grant entitlements by hand."""

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Entitlement(models.Model):
    class ProductType(models.TextChoices):
        COURSE = "course", "Course"
        PROGRAMME = "programme", "Programme"
        BATCH = "batch", "Batch"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="entitlements")
    product_type = models.CharField(max_length=10, choices=ProductType.choices)
    product_id = models.UUIDField()
    source = models.CharField(max_length=20, default="admin_grant", help_text="admin_grant | payment")
    starts_at = models.DateTimeField(default=timezone.now)
    ends_at = models.DateTimeField(null=True, blank=True, help_text="Empty = no end (recorded courses, C7).")
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoke_reason = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["student", "product_type", "product_id"])]

    def __str__(self):
        return f"{self.student} → {self.product_type}:{self.product_id}"

    @classmethod
    def active_for(cls, student):
        now = timezone.now()
        return cls.objects.filter(student=student, revoked_at__isnull=True, starts_at__lte=now).filter(
            Q(ends_at__isnull=True) | Q(ends_at__gt=now)
        )
