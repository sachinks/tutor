from typing import Optional
from uuid import UUID

from ninja import Schema


class ItemOut(Schema):
    position: int
    stem: str
    options: list[str]
    hints_available: int
    hints_used: int
    answered: bool


class AttemptOut(Schema):
    attempt_id: UUID
    lesson_id: UUID
    items: list[ItemOut]


class PositionIn(Schema):
    position: int


class AnswerIn(Schema):
    position: int
    choice_index: int


class HintOut(Schema):
    hint: str
    hints_left: int


class MasteryBrief(Schema):
    skill: str
    level: str
    score: float


class AnswerResultOut(Schema):
    correct: bool
    correct_index: int
    explanation: str
    misconception: Optional[str] = None
    mastery: MasteryBrief


class SkillChangeOut(Schema):
    skill: str
    name: str
    before: float
    after: float


class SubmitOut(Schema):
    score: int
    max_score: int
    skill_changes: list[SkillChangeOut]
    course_completed: bool
    next_lesson_id: Optional[UUID] = None
