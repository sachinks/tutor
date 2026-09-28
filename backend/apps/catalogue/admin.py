from django.contrib import admin

from .models import Board, ClassLevel, Discipline, Subject


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
