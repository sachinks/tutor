"""Catalogue reference data (DATA_MODEL.md §5). Courses, lessons and skills are added in the next step."""
from django.db import models


class Discipline(models.Model):
    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=80, unique=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self):
        return self.name


class Subject(models.Model):
    discipline = models.ForeignKey(Discipline, on_delete=models.PROTECT, related_name="subjects")
    name = models.CharField(max_length=80)
    slug = models.SlugField(max_length=80, unique=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["discipline__order", "order", "name"]

    def __str__(self):
        return self.name


class Board(models.Model):
    code = models.CharField(max_length=10, unique=True)  # CBSE, ICSE, WBBSE…
    name = models.CharField(max_length=120)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return self.code


class ClassLevel(models.Model):
    number = models.PositiveSmallIntegerField(unique=True)  # 6–12
    label = models.CharField(max_length=20)  # "Class 8"

    class Meta:
        ordering = ["number"]

    def __str__(self):
        return self.label
