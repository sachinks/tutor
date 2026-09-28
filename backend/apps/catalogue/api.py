"""Public catalogue API — API_CONTRACTS.md §2.3. No login needed."""
from typing import Literal, Optional
from uuid import UUID

from django.db.models import Exists, OuterRef, Q
from ninja import Router

from apps.content.services import published_version
from apps.core.errors import ApiError

from .models import (
    PATH_STAGES,
    Board,
    BoardMapping,
    ClassLevel,
    Course,
    Discipline,
    Lesson,
    Programme,
    PublishStatus,
    Skill,
)
from .schemas import CourseOut, FacetsOut, ItemPageOut, LessonPreviewOut, ProgrammeOut

catalogue_router = Router(tags=["catalogue"])
courses_router = Router(tags=["catalogue"])
programmes_router = Router(tags=["catalogue"])
lessons_router = Router(tags=["catalogue"])

MAX_PAGE_SIZE = 50


@catalogue_router.get("/facets", response=FacetsOut)
def facets(request):
    return {
        "disciplines": [
            {"slug": d.slug, "name": d.name, "subjects": [{"slug": s.slug, "name": s.name} for s in d.subjects.all()]}
            for d in Discipline.objects.prefetch_related("subjects")
        ],
        "boards": [{"code": b.code, "name": b.name} for b in Board.objects.all()],
        "classes": [{"number": c.number, "label": c.label} for c in ClassLevel.objects.all()],
        "stages": [{"stage": k, "label": v} for k, v in PATH_STAGES.items()],
    }


def _course_item(c):
    return {
        "type": "course", "id": c.id, "slug": c.slug, "title": c.title, "summary": c.summary,
        "subject": c.subject.slug, "class_number": c.class_level.number if c.class_level else None,
        "path_stage": c.path_stage, "track": c.track, "price_paise": c.price_paise,
    }


def _programme_item(p):
    return {
        "type": "programme", "id": p.id, "slug": p.slug, "title": p.title, "summary": p.summary,
        "subject": None, "class_number": p.class_level.number if p.class_level else None,
        "path_stage": p.path_stage, "track": None, "price_paise": p.price_paise,
    }


@catalogue_router.get("/items", response=ItemPageOut)
def items(
    request,
    type: Optional[Literal["course", "programme"]] = None,
    class_number: Optional[int] = None,
    board: Optional[str] = None,
    subject: Optional[str] = None,
    stage: Optional[int] = None,
    page: int = 1,
    page_size: int = 20,
):
    """Courses and programmes in one list. Board-independent items (no class) always match class/board filters."""
    page = max(page, 1)
    page_size = min(max(page_size, 1), MAX_PAGE_SIZE)
    results = []

    if type in (None, "course"):
        courses = Course.objects.filter(status=PublishStatus.PUBLISHED).select_related("subject", "class_level")
        if class_number:
            courses = courses.filter(Q(class_level__number=class_number) | Q(class_level__isnull=True))
        if board:
            mapped = BoardMapping.objects.filter(lesson__module__course=OuterRef("pk"), board__code=board.upper())
            courses = courses.annotate(on_board=Exists(mapped)).filter(Q(on_board=True) | Q(class_level__isnull=True))
        if subject:
            courses = courses.filter(subject__slug=subject)
        if stage:
            courses = courses.filter(path_stage=stage)
        results += [_course_item(c) for c in courses]

    if type in (None, "programme") and not subject:
        programmes = Programme.objects.filter(status=PublishStatus.PUBLISHED).select_related("class_level")
        if class_number:
            programmes = programmes.filter(Q(class_level__number=class_number) | Q(class_level__isnull=True))
        if stage:
            programmes = programmes.filter(path_stage=stage)
        results += [_programme_item(p) for p in programmes]

    total = len(results)
    start = (page - 1) * page_size
    return {"results": results[start:start + page_size], "page": page, "page_size": page_size, "total": total}


@courses_router.get("/{slug}", response=CourseOut)
def course_detail(request, slug: str):
    course = (
        Course.objects.select_related("subject", "class_level")
        .prefetch_related("modules__lessons__versions")
        .filter(slug=slug, status=PublishStatus.PUBLISHED).first()
    )
    if not course:
        raise ApiError(404, "not_found", "Course not found.")
    modules = []
    for m in course.modules.all():
        modules.append({
            "title": m.title, "position": m.position,
            "lessons": [
                {
                    "id": lesson.id, "title": lesson.title, "position": lesson.position,
                    "est_minutes": lesson.est_minutes, "is_free": m.id == course.free_module_id,
                    "has_content": any(v.status == "published" for v in lesson.versions.all()),
                }
                for lesson in m.lessons.all()
            ],
        })
    skills = Skill.objects.filter(
        lesson_links__lesson__module__course=course, lesson_links__role="teaches"
    ).distinct().order_by("code")
    boards = sorted(set(
        BoardMapping.objects.filter(lesson__module__course=course).values_list("board__code", flat=True)
    ))
    return {
        "id": course.id, "slug": course.slug, "title": course.title, "summary": course.summary,
        "subject": course.subject.slug, "class_number": course.class_level.number if course.class_level else None,
        "track": course.track, "path_stage": course.path_stage, "path_stage_label": PATH_STAGES[course.path_stage],
        "price_paise": course.price_paise, "boards": boards,
        "skills": [{"code": s.code, "name": s.name} for s in skills], "modules": modules,
    }


@programmes_router.get("/{slug}", response=ProgrammeOut)
def programme_detail(request, slug: str):
    """Pro-rata price for courses a student already completed arrives with the learner record (C1)."""
    programme = Programme.objects.select_related("class_level").filter(
        slug=slug, status=PublishStatus.PUBLISHED
    ).first()
    if not programme:
        raise ApiError(404, "not_found", "Programme not found.")
    links = programme.course_links.select_related("course").filter(course__status=PublishStatus.PUBLISHED)
    return {
        "id": programme.id, "slug": programme.slug, "title": programme.title, "summary": programme.summary,
        "path_stage": programme.path_stage, "path_stage_label": PATH_STAGES[programme.path_stage],
        "class_number": programme.class_level.number if programme.class_level else None,
        "price_paise": programme.price_paise,
        "courses": [
            {"slug": pc.course.slug, "title": pc.course.title, "required": pc.required,
             "price_paise": pc.course.price_paise}
            for pc in links
        ],
    }


@lessons_router.get("/{lesson_id}/preview", response=LessonPreviewOut)
def lesson_preview(request, lesson_id: UUID):
    """Free-module lessons only, without the AI tutor (decision Q5)."""
    lesson = Lesson.objects.select_related("module__course").filter(
        pk=lesson_id, module__course__status=PublishStatus.PUBLISHED
    ).first()
    if not lesson:
        raise ApiError(404, "not_found", "Lesson not found.")
    if lesson.module_id != lesson.module.course.free_module_id:
        raise ApiError(403, "not_entitled", "Enrol in the course to read this lesson.")
    version = published_version(lesson)
    if not version:
        raise ApiError(404, "not_found", "This lesson has no published content yet.")
    return {
        "id": lesson.id, "title": lesson.title, "course_slug": lesson.module.course.slug,
        "version_no": version.version_no, "sections": version.sections,
    }
