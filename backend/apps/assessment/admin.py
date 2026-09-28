from django.contrib import admin, messages

from apps.core.errors import ApiError

from . import services
from .models import Answer, Attempt, AttemptItem, Question, QuestionVersion


class QuestionVersionInline(admin.StackedInline):
    model = QuestionVersion
    extra = 0
    fields = ("version_no", "status", "body", "is_ai_draft", "author", "reviewer", "published_at")
    readonly_fields = ("published_at",)
    raw_id_fields = ("author", "reviewer")


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("__str__", "lesson", "skill", "type", "difficulty", "purpose", "position")
    list_filter = ("purpose", "type", "difficulty", "lesson__module__course")
    search_fields = ("skill__code",)
    inlines = [QuestionVersionInline]


@admin.register(QuestionVersion)
class QuestionVersionAdmin(admin.ModelAdmin):
    list_display = ("__str__", "question", "status", "is_ai_draft", "author", "reviewer")
    list_filter = ("status", "is_ai_draft")
    raw_id_fields = ("question", "author", "reviewer", "published_by")
    actions = ["publish_selected"]

    @admin.action(description="Publish selected approved versions")
    def publish_selected(self, request, queryset):
        for version in queryset:
            try:
                services.publish_question_version(version, request.user)
            except ApiError as exc:
                self.message_user(request, f"{version}: {exc.message}", level=messages.WARNING)


class AttemptItemInline(admin.TabularInline):
    model = AttemptItem
    extra = 0
    readonly_fields = ("question_version", "position", "hints_used")
    can_delete = False


@admin.register(Attempt)
class AttemptAdmin(admin.ModelAdmin):
    list_display = ("student", "lesson", "kind", "score", "max_score", "started_at", "submitted_at")
    list_filter = ("kind",)
    raw_id_fields = ("student", "lesson")
    inlines = [AttemptItemInline]


@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    list_display = ("item", "is_correct", "marks", "marked_by", "answered_at")
    list_filter = ("is_correct", "marked_by")
