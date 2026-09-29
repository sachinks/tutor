from django.contrib import admin, messages

from . import indexing
from .models import IndexRequest


@admin.register(IndexRequest)
class IndexRequestAdmin(admin.ModelAdmin):
    """Read-only view of the lesson-index outbox, with one action: queue the selected lessons again."""

    list_display = ("lesson_id", "status", "reason", "action", "attempts", "next_attempt_at", "updated_at")
    list_filter = ("status", "reason", "action", "retryable")
    search_fields = ("lesson_id", "last_error")
    ordering = ("-updated_at",)
    actions = ["queue_again"]

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False  # the history of what was sent is kept

    @admin.action(description="Queue the selected lessons for indexing again")
    def queue_again(self, request, queryset):
        lessons = set(queryset.values_list("lesson_id", flat=True))
        for lesson_id in lessons:
            indexing.enqueue(lesson_id, IndexRequest.Reason.MANUAL)
        self.message_user(
            request, f"Queued {len(lessons)} lesson(s). They are sent by sync_ai_index.", level=messages.SUCCESS
        )
