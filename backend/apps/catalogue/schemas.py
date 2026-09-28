from typing import Optional
from uuid import UUID

from ninja import Schema


class NamedOut(Schema):
    slug: str
    name: str


class DisciplineOut(NamedOut):
    subjects: list[NamedOut]


class BoardOut(Schema):
    code: str
    name: str


class ClassOut(Schema):
    number: int
    label: str


class StageOut(Schema):
    stage: int
    label: str


class FacetsOut(Schema):
    disciplines: list[DisciplineOut]
    boards: list[BoardOut]
    classes: list[ClassOut]
    stages: list[StageOut]


class ItemOut(Schema):
    type: str  # course | programme  (batch added with the batches app)
    id: UUID
    slug: str
    title: str
    summary: str
    subject: Optional[str] = None
    class_number: Optional[int] = None
    path_stage: int
    track: Optional[str] = None
    price_paise: int


class ItemPageOut(Schema):
    results: list[ItemOut]
    page: int
    page_size: int
    total: int


class LessonCardOut(Schema):
    id: UUID
    title: str
    position: int
    est_minutes: int
    is_free: bool
    has_content: bool


class ModuleOut(Schema):
    title: str
    position: int
    lessons: list[LessonCardOut]


class SkillOut(Schema):
    code: str
    name: str


class CourseOut(Schema):
    id: UUID
    slug: str
    title: str
    summary: str
    subject: str
    class_number: Optional[int] = None
    track: str
    path_stage: int
    path_stage_label: str
    price_paise: int
    boards: list[str]
    skills: list[SkillOut]
    modules: list[ModuleOut]
    includes_ai_tutor: bool = True


class ProgrammeCourseOut(Schema):
    slug: str
    title: str
    required: bool
    price_paise: int


class ProgrammeOut(Schema):
    id: UUID
    slug: str
    title: str
    summary: str
    path_stage: int
    path_stage_label: str
    class_number: Optional[int] = None
    price_paise: int
    courses: list[ProgrammeCourseOut]


class LessonPreviewOut(Schema):
    id: UUID
    title: str
    course_slug: str
    version_no: int
    sections: list[dict]
