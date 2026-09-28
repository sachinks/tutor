from datetime import datetime
from typing import Optional
from uuid import UUID

from ninja import Schema


class SkillBrief(Schema):
    code: str
    name: str


class LessonOut(Schema):
    id: UUID
    title: str
    course_slug: str
    course_title: str
    module_title: str
    version_no: int
    sections: list[dict]
    skills: list[SkillBrief]
    has_quiz: bool


class FinishOut(Schema):
    finished: bool
    course_completed: bool
    next_lesson_id: Optional[UUID] = None


class LessonBrief(Schema):
    id: UUID
    title: str
    course_title: str


class ReviewOut(Schema):
    skill_code: str
    skill_name: str
    level: str
    lesson_id: Optional[UUID] = None


class TodayOut(Schema):
    next_lesson: Optional[LessonBrief] = None
    review: Optional[ReviewOut] = None
    next_session: Optional[dict] = None  # arrives with the batches app
    streak_days: int


class MasteryOut(Schema):
    code: str
    name: str
    subject: str
    level: str
    score: float
    evidence: int


class CompletedCourseOut(Schema):
    slug: str
    title: str
    completed_at: datetime


class QuizHistoryOut(Schema):
    lesson_title: str
    score: int
    max_score: int
    submitted_at: datetime


class RecordOut(Schema):
    mastery: list[MasteryOut]
    completed_courses: list[CompletedCourseOut]
    quizzes: list[QuizHistoryOut]
    lessons_finished: int
