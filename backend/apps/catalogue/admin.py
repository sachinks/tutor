from django.contrib import admin

from .models import (
    Board,
    BoardMapping,
    ClassLevel,
    Course,
    Discipline,
    Lesson,
    LessonSkill,
    Module,
    Programme,
    ProgrammeCourse,
    Skill,
    SkillPrerequisite,
    Subject,
)


@admin.register(Discipline)
class DisciplineAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "order")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("name", "discipline", "slug", "order")
    list_filter = ("discipline",)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Board)
class BoardAdmin(admin.ModelAdmin):
    list_display = ("code", "name")


@admin.register(ClassLevel)
class ClassLevelAdmin(admin.ModelAdmin):
    list_display = ("number", "label")


class ModuleInline(admin.TabularInline):
    model = Module
    extra = 0


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("title", "subject", "class_level", "track", "path_stage", "price_paise", "status")
    list_filter = ("status", "subject", "class_level", "track", "path_stage")
    search_fields = ("title", "slug")
    prepopulated_fields = {"slug": ("title",)}
    inlines = [ModuleInline]


class LessonInline(admin.TabularInline):
    model = Lesson
    extra = 0
    fields = ("position", "title", "slug", "est_minutes")
    prepopulated_fields = {"slug": ("title",)}


@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    list_display = ("__str__", "course", "position")
    list_filter = ("course",)
    inlines = [LessonInline]


class LessonSkillInline(admin.TabularInline):
    model = LessonSkill
    extra = 0
    autocomplete_fields = ("skill",)


class BoardMappingInline(admin.TabularInline):
    model = BoardMapping
    extra = 0


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ("title", "module", "position", "est_minutes")
    list_filter = ("module__course",)
    search_fields = ("title",)
    prepopulated_fields = {"slug": ("title",)}
    inlines = [LessonSkillInline, BoardMappingInline]


class PrerequisiteInline(admin.TabularInline):
    model = SkillPrerequisite
    fk_name = "skill"
    extra = 0
    verbose_name = "prerequisite"


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "subject", "class_level")
    list_filter = ("subject", "class_level")
    search_fields = ("code", "name")
    inlines = [PrerequisiteInline]


class ProgrammeCourseInline(admin.TabularInline):
    model = ProgrammeCourse
    extra = 0


@admin.register(Programme)
class ProgrammeAdmin(admin.ModelAdmin):
    list_display = ("title", "path_stage", "class_level", "price_paise", "status")
    list_filter = ("status", "path_stage", "class_level")
    prepopulated_fields = {"slug": ("title",)}
    inlines = [ProgrammeCourseInline]
