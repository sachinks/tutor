from django.contrib import admin, messages

from apps.core.admin_guards import VersionStatusForm
from apps.core.errors import ApiError

from . import services
from .models import ContentVersion, ReviewComment


class ReviewCommentInline(admin.TabularInline):
    model = ReviewComment
    extra = 0
    raw_id_fields = ("author",)


@admin.register(ContentVersion)
class ContentVersionAdmin(admin.ModelAdmin):
    form = VersionStatusForm
    list_display = ("__str__", "kind", "status", "is_ai_draft", "author", "reviewer", "published_at")
    list_filter = ("status", "kind", "is_ai_draft")
    search_fields = ("lesson__title",)
    raw_id_fields = ("lesson", "author", "reviewer", "published_by")
    readonly_fields = ("published_at", "published_by", "created_at", "updated_at")
    inlines = [ReviewCommentInline]
    actions = ["publish_selected"]

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        if obj and obj.status in (ContentVersion.Status.PUBLISHED, ContentVersion.Status.ARCHIVED):
            fields += ["body", "lesson", "version_no", "kind", "is_ai_draft"]  # never edit published content
        return fields

    @admin.action(description="Publish selected approved versions")
    def publish_selected(self, request, queryset):
        done = 0
        for version in queryset:
            try:
                services.publish(version, request.user)
                done += 1
            except ApiError as exc:
                self.message_user(request, f"{version}: {exc.message}", level=messages.WARNING)
        if done:
            self.message_user(request, f"Published {done} version(s).")
