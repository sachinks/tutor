"""Operations' view of the tutor: the safety queue (D15) and read-only chats. Chats are children's data: the admin
shows them only to staff with the model's view permission, and nothing here can edit what was said."""

from django.contrib import admin, messages
from django.utils import timezone

from .models import SafetyFlag, TutorConversation, TutorMessage


class ReadOnlyMixin:
    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class TutorMessageInline(ReadOnlyMixin, admin.TabularInline):
    model = TutorMessage
    extra = 0
    can_delete = False
    fields = ("created_at", "role", "mode", "text", "blocked", "replaced", "off_topic", "model", "prompt_version")
    readonly_fields = fields


@admin.register(TutorConversation)
class TutorConversationAdmin(ReadOnlyMixin, admin.ModelAdmin):
    list_display = ("id", "lesson", "flagged", "hidden_by_student", "last_message_at")
    list_filter = ("flagged", "hidden_by_student")
    raw_id_fields = ("student", "lesson")
    readonly_fields = (
        "student",
        "lesson",
        "content_version_id",
        "mode",
        "pinned_chunk_ids",
        "flagged",
        "hidden_by_student",
        "created_at",
        "last_message_at",
    )
    inlines = [TutorMessageInline]

    def has_delete_permission(self, request, obj=None):
        return False  # retention (purge_tutor_chats) and account deletion remove chats, nobody by hand


@admin.register(SafetyFlag)
class SafetyFlagAdmin(admin.ModelAdmin):
    """The safety queue: newest first, open critical and high flags at the top of the filters."""

    list_display = ("created_at", "severity", "category", "stage", "status", "parent_visible", "conversation")
    list_filter = ("status", "severity", "category", "parent_visible")
    ordering = ("status", "-created_at")
    readonly_fields = (
        "conversation",
        "message",
        "stage",
        "category",
        "severity",
        "parent_visible",
        "reviewed_by",
        "reviewed_at",
        "closed_at",
        "created_at",
        "message_text",
    )
    fields = (
        "conversation",
        "message_text",
        "stage",
        "category",
        "severity",
        "parent_visible",
        "status",
        "note",
        "reviewed_by",
        "reviewed_at",
        "closed_at",
        "created_at",
    )
    actions = ["mark_reviewed", "close"]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Message")
    def message_text(self, obj):
        return obj.message.text if obj.message_id else ""

    def save_model(self, request, obj, form, change):
        if "status" in form.changed_data:
            self._stamp(obj, request.user)
        super().save_model(request, obj, form, change)

    @staticmethod
    def _stamp(flag, user):
        now = timezone.now()
        if flag.status in (SafetyFlag.Status.REVIEWED, SafetyFlag.Status.CLOSED) and not flag.reviewed_at:
            flag.reviewed_by, flag.reviewed_at = user, now
        flag.closed_at = now if flag.status == SafetyFlag.Status.CLOSED else None

    @admin.action(description="Mark selected flags as reviewed")
    def mark_reviewed(self, request, queryset):
        updated = 0
        for flag in queryset.filter(status=SafetyFlag.Status.OPEN):
            flag.status = SafetyFlag.Status.REVIEWED
            self._stamp(flag, request.user)
            flag.save()
            updated += 1
        self.message_user(request, f"{updated} flag(s) marked reviewed.", level=messages.SUCCESS)

    @admin.action(description="Close selected flags")
    def close(self, request, queryset):
        updated = 0
        for flag in queryset.exclude(status=SafetyFlag.Status.CLOSED):
            flag.status = SafetyFlag.Status.CLOSED
            self._stamp(flag, request.user)
            flag.save()
            updated += 1
        self.message_user(request, f"{updated} flag(s) closed.", level=messages.SUCCESS)
