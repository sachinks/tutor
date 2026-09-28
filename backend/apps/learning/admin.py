from django.contrib import admin

from .models import CourseCompletion, LessonProgress, MasteryEvent, MasteryState


@admin.register(MasteryState)
class MasteryStateAdmin(admin.ModelAdmin):
    list_display = ("student", "skill", "level", "score", "evidence_count", "updated_at")
    list_filter = ("level",)
    search_fields = ("student__full_name", "skill__code")
    raw_id_fields = ("student",)


@admin.register(MasteryEvent)
class MasteryEventAdmin(admin.ModelAdmin):
    list_display = ("student", "skill", "source", "old_score", "new_score", "created_at")
    raw_id_fields = ("student", "answer")

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(LessonProgress)
class LessonProgressAdmin(admin.ModelAdmin):
    list_display = ("student", "lesson", "status", "first_opened_at", "finished_at")
    list_filter = ("status",)
    raw_id_fields = ("student",)


@admin.register(CourseCompletion)
class CourseCompletionAdmin(admin.ModelAdmin):
    list_display = ("student", "course", "via", "completed_at")
    raw_id_fields = ("student",)
