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


# ---------------------------------------------------------------------------
# What is taught and sold (DATA_MODEL.md §5)
# ---------------------------------------------------------------------------
import uuid  # noqa: E402

from django.core.validators import MaxValueValidator, MinValueValidator  # noqa: E402


class PublishStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    PUBLISHED = "published", "Published"
    RETIRED = "retired", "Retired"


PATH_STAGE_VALIDATORS = [MinValueValidator(1), MaxValueValidator(5)]
PATH_STAGES = {
    1: "Build your foundation",
    2: "Explore",
    3: "Build depth",
    4: "Integrate (AI + Core)",
    5: "Go further (Frontier AI)",
}


class Course(models.Model):
    class Track(models.TextChoices):
        FOUNDATION = "foundation", "Foundation"
        AI_IN_SUBJECT = "ai_in_subject", "AI in the subject"
        FRONTIER_AI = "frontier_ai", "Frontier AI"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="courses")
    class_level = models.ForeignKey(
        ClassLevel,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        help_text="Empty for board-independent courses such as AI Foundations.",
    )
    title = models.CharField(max_length=150)
    slug = models.SlugField(max_length=150, unique=True)
    summary = models.TextField(blank=True)
    track = models.CharField(max_length=20, choices=Track.choices, default=Track.FOUNDATION)
    path_stage = models.PositiveSmallIntegerField(default=1, validators=PATH_STAGE_VALIDATORS)
    price_paise = models.PositiveIntegerField(default=0, help_text="Whole paise: ₹499 = 49900.")
    free_module = models.ForeignKey(
        "Module",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="Readable without buying (decision Q5).",
    )
    status = models.CharField(max_length=10, choices=PublishStatus.choices, default=PublishStatus.DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["subject__order", "class_level__number", "title"]

    def __str__(self):
        return self.title


class Module(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="modules")
    title = models.CharField(max_length=150)
    position = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ["course", "position"]
        constraints = [models.UniqueConstraint(fields=["course", "position"], name="unique_module_position")]

    def __str__(self):
        return f"{self.course.title} · {self.position}. {self.title}"


class Lesson(models.Model):
    """The lesson's text lives in content.ContentVersion (one published version at a time)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name="lessons")
    title = models.CharField(max_length=150)
    slug = models.SlugField(max_length=150)
    position = models.PositiveSmallIntegerField(default=1)
    est_minutes = models.PositiveSmallIntegerField(default=10)

    class Meta:
        ordering = ["module__course", "module__position", "position"]
        constraints = [models.UniqueConstraint(fields=["module", "position"], name="unique_lesson_position")]

    def __str__(self):
        return self.title

    @property
    def course(self):
        return self.module.course


class Skill(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name="skills")
    code = models.CharField(max_length=40, unique=True, help_text="Stable forever, e.g. MATH-FRAC-ADD.")
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    class_level = models.ForeignKey(ClassLevel, on_delete=models.PROTECT, null=True, blank=True)
    prerequisites = models.ManyToManyField(
        "self", symmetrical=False, blank=True, through="SkillPrerequisite", related_name="unlocks"
    )

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} — {self.name}"


class SkillPrerequisite(models.Model):
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name="+")
    requires = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name="+")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["skill", "requires"], name="unique_prerequisite"),
            models.CheckConstraint(condition=~models.Q(skill=models.F("requires")), name="no_self_prerequisite"),
        ]

    def __str__(self):
        return f"{self.skill.code} needs {self.requires.code}"


class LessonSkill(models.Model):
    class Role(models.TextChoices):
        TEACHES = "teaches", "Teaches"
        REVISES = "revises", "Revises"

    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="skill_links")
    skill = models.ForeignKey(Skill, on_delete=models.PROTECT, related_name="lesson_links")
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.TEACHES)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["lesson", "skill"], name="unique_lesson_skill")]

    def __str__(self):
        return f"{self.lesson} {self.role} {self.skill.code}"


class BoardMapping(models.Model):
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="board_mappings")
    board = models.ForeignKey(Board, on_delete=models.PROTECT)
    class_level = models.ForeignKey(ClassLevel, on_delete=models.PROTECT)
    chapter_ref = models.CharField(max_length=120, help_text="e.g. 'Chapter 3: Linear equations'")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["lesson", "board", "class_level"], name="unique_board_mapping")]

    def __str__(self):
        return f"{self.lesson} → {self.board.code} {self.class_level}: {self.chapter_ref}"


class Programme(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=150)
    slug = models.SlugField(max_length=150, unique=True)
    summary = models.TextField(blank=True)
    path_stage = models.PositiveSmallIntegerField(default=1, validators=PATH_STAGE_VALIDATORS)
    class_level = models.ForeignKey(ClassLevel, on_delete=models.PROTECT, null=True, blank=True)
    price_paise = models.PositiveIntegerField(default=0)
    courses = models.ManyToManyField(Course, through="ProgrammeCourse", related_name="programmes")
    status = models.CharField(max_length=10, choices=PublishStatus.choices, default=PublishStatus.DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["path_stage", "title"]

    def __str__(self):
        return self.title


class ProgrammeCourse(models.Model):
    programme = models.ForeignKey(Programme, on_delete=models.CASCADE, related_name="course_links")
    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name="programme_links")
    position = models.PositiveSmallIntegerField(default=1)
    required = models.BooleanField(default=True)

    class Meta:
        ordering = ["programme", "position"]
        constraints = [models.UniqueConstraint(fields=["programme", "course"], name="unique_programme_course")]

    def __str__(self):
        return f"{self.programme} · {self.position}. {self.course}"
