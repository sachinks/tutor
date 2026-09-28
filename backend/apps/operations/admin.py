from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor", "action", "object_type", "object_id", "ip")
    list_filter = ("action", "object_type")
    search_fields = ("object_id", "actor__full_name", "action")

    # Read-only everywhere: the audit log is never edited (Q21, A9).
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
