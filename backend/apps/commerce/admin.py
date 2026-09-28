from django.contrib import admin

from .models import Entitlement


@admin.register(Entitlement)
class EntitlementAdmin(admin.ModelAdmin):
    list_display = ("student", "product_type", "product_id", "source", "starts_at", "ends_at", "revoked_at")
    list_filter = ("product_type", "source")
    search_fields = ("student__full_name", "student__email", "student__mobile", "product_id")
    raw_id_fields = ("student",)
