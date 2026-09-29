"""Demo courses from the JSON files in ./content (one file per course, plus programmes.json).

The files are data, not code, so content authors can add lessons without touching Python. ``validate`` checks every
file before anything is written; ``load`` is idempotent and publishes through the normal services, so the same rules
(approved before published, reviewer ≠ author, curriculum lead publishes) apply to demo content as to real content.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

from django.db import transaction

from apps.accounts.models import RoleGrant, User
from apps.assessment import services as assessment_services
from apps.assessment.models import Question, QuestionVersion
from apps.catalogue.management.commands.seed_demo_catalogue import SKILLS as AI_FOUNDATIONS_SKILL_ROWS
from apps.catalogue.models import (
    Board,
    BoardMapping,
    ClassLevel,
    Course,
    Lesson,
    LessonSkill,
    Module,
    Programme,
    ProgrammeCourse,
    PublishStatus,
    Skill,
    SkillPrerequisite,
    Subject,
)
from apps.content import services as content_services
from apps.content.models import ContentVersion

CONTENT_DIR = Path(__file__).resolve().parent / "content"
PROGRAMMES_FILE = "programmes.json"
AI_FOUNDATIONS_SKILLS = [code for code, _, _ in AI_FOUNDATIONS_SKILL_ROWS]  # defined by seed_demo_catalogue
TRACKS = {c.value for c in Course.Track}


class DemoContentError(ValueError):
    """A demo content file is malformed. The message names the file and the problem."""


@dataclass
class LoadReport:
    courses: int = 0
    lessons: int = 0
    questions: int = 0
    programmes: int = 0
    notes: list = field(default_factory=list)


def course_files():
    return sorted(p for p in CONTENT_DIR.glob("*.json") if p.name != PROGRAMMES_FILE)


def read_all():
    courses = [(p.name, json.loads(p.read_text(encoding="utf-8"))) for p in course_files()]
    programmes = json.loads((CONTENT_DIR / PROGRAMMES_FILE).read_text(encoding="utf-8"))
    return courses, programmes


def validate(courses, programmes, known_skills=(), known_courses=()):
    """Raise DemoContentError on the first problem. Pure: no database access."""
    skill_codes = set(known_skills)
    slugs = set(known_courses)
    lesson_keys = set()
    for name, data in courses:
        for s in data.get("skills", []):
            if s["code"] in skill_codes:
                raise DemoContentError(f"{name}: skill {s['code']} is defined twice")
            skill_codes.add(s["code"])
    for name, data in courses:
        c = data["course"]
        if c["slug"] in slugs:
            raise DemoContentError(f"{name}: course slug {c['slug']} is used twice")
        slugs.add(c["slug"])
        if c["track"] not in TRACKS:
            raise DemoContentError(f"{name}: unknown track {c['track']}")
        if not 1 <= c["path_stage"] <= 5:
            raise DemoContentError(f"{name}: path_stage must be 1–5")
        positions = [m["position"] for m in data["modules"]]
        if len(positions) != len(set(positions)):
            raise DemoContentError(f"{name}: duplicate module positions")
        if c.get("free_module_position") not in (None, *positions):
            raise DemoContentError(f"{name}: free_module_position doesn't match a module")
        for s in data["skills"]:
            for req in s["requires"]:
                if req not in skill_codes:
                    raise DemoContentError(f"{name}: skill {s['code']} requires unknown skill {req}")
        for m in data["modules"]:
            for lesson in m["lessons"]:
                key = (c["slug"], lesson["slug"])
                if key in lesson_keys:
                    raise DemoContentError(f"{name}: lesson {lesson['slug']} appears twice")
                lesson_keys.add(key)
                if not lesson["sections"]:
                    raise DemoContentError(f"{name}: lesson {lesson['slug']} has no sections")
                for code in lesson["skills"]:
                    if code not in skill_codes:
                        raise DemoContentError(f"{name}: lesson {lesson['slug']} uses unknown skill {code}")
                for q in lesson["questions"]:
                    where = f"{name}: {lesson['slug']}: '{q['stem'][:40]}'"
                    if q["skill"] not in lesson["skills"]:
                        raise DemoContentError(f"{where} tests a skill the lesson doesn't teach")
                    if len(q["options"]) < 2 or len(set(q["options"])) != len(q["options"]):
                        raise DemoContentError(f"{where} needs at least two distinct options")
                    if not 0 <= q["answer"] < len(q["options"]):
                        raise DemoContentError(f"{where} has an answer index out of range")
                    for idx in q.get("misconceptions", {}):
                        if not idx.isdigit() or int(idx) == q["answer"] or int(idx) >= len(q["options"]):
                            raise DemoContentError(f"{where} has a misconception on option {idx}")
                    if not q.get("explanation"):
                        raise DemoContentError(f"{where} has no explanation")
    for p in programmes["programmes"]:
        for slug in p["courses"]:
            if slug not in slugs:
                raise DemoContentError(f"{PROGRAMMES_FILE}: programme {p['slug']} lists unknown course {slug}")
    return True


def _system_user(email, name):
    user, created = User.objects.get_or_create(
        email=email, defaults={"full_name": name, "account_type": "staff", "is_staff": False}
    )
    if created:
        user.set_unusable_password()
        user.save()
    return user


def _publish_lesson_content(lesson, sections, author, reviewer, lead):
    if content_services.published_version(lesson):
        return
    version = ContentVersion.objects.create(
        lesson=lesson,
        version_no=content_services.next_version_no(lesson),
        body={
            "sections": [{"heading": s["heading"], "blocks": [{"type": "text", "text": s["text"]}]} for s in sections]
        },
        status=ContentVersion.Status.APPROVED,
        author=author,
        reviewer=reviewer,
    )
    content_services.publish(version, lead)


def _publish_question(lesson, position, q, skill, author, reviewer, lead):
    question, _ = Question.objects.get_or_create(
        lesson=lesson,
        position=position,
        purpose=Question.Purpose.QUIZ,
        defaults={"skill": skill, "type": Question.Type.MCQ},
    )
    if assessment_services.published_question_version(question):
        return 0
    qv = QuestionVersion.objects.create(
        question=question,
        version_no=assessment_services.next_question_version_no(question),
        body={
            "stem": q["stem"],
            "options": q["options"],
            "answer_index": q["answer"],
            "explanation": q["explanation"],
            "hints": q.get("hints", []),
            "misconceptions": q.get("misconceptions", {}),
        },
        status=QuestionVersion.Status.APPROVED,
        author=author,
        reviewer=reviewer,
    )
    assessment_services.publish_question_version(qv, lead)
    return 1


@transaction.atomic
def load():
    """Create or update every demo course, lesson, skill, question and programme. Safe to run repeatedly."""
    courses, programmes = read_all()
    validate(courses, programmes, known_skills=AI_FOUNDATIONS_SKILLS, known_courses=["ai-foundations"])
    report = LoadReport()
    author = _system_user("demo-author@tutor.local", "Demo Author")
    reviewer = _system_user("demo-reviewer@tutor.local", "Demo Reviewer")
    lead = _system_user("demo-lead@tutor.local", "Demo Curriculum Lead")
    boards = {b.code: b for b in Board.objects.all()}
    classes = {c.number: c for c in ClassLevel.objects.all()}

    skills = {}
    for _, data in courses:
        subject = Subject.objects.get(slug=data["course"]["subject"])
        RoleGrant.objects.get_or_create(
            user=lead, role=RoleGrant.Role.CURRICULUM_LEAD, subject=subject, class_level=None, revoked_at=None
        )
        for s in data["skills"]:
            skills[s["code"]], _ = Skill.objects.update_or_create(
                code=s["code"], defaults={"name": s["name"], "subject": subject}
            )
    for _, data in courses:
        for s in data["skills"]:
            for req in s["requires"]:
                SkillPrerequisite.objects.get_or_create(skill=skills[s["code"]], requires=Skill.objects.get(code=req))

    for _, data in courses:
        c = data["course"]
        course, _ = Course.objects.update_or_create(
            slug=c["slug"],
            defaults={
                "title": c["title"],
                "subject": Subject.objects.get(slug=c["subject"]),
                "class_level": classes.get(c["class_number"]),
                "summary": c["summary"],
                "track": c["track"],
                "path_stage": c["path_stage"],
                "price_paise": c["price_paise"],
                "status": PublishStatus.PUBLISHED,
            },
        )
        report.courses += 1
        for m in data["modules"]:
            module, _ = Module.objects.update_or_create(
                course=course, position=m["position"], defaults={"title": m["title"]}
            )
            if m["position"] == c.get("free_module_position") and course.free_module_id != module.id:
                course.free_module = module
                course.save(update_fields=["free_module"])
            for position, ld in enumerate(m["lessons"], start=1):
                lesson, _ = Lesson.objects.update_or_create(
                    module=module,
                    position=position,
                    defaults={"slug": ld["slug"], "title": ld["title"], "est_minutes": ld["est_minutes"]},
                )
                report.lessons += 1
                for code in ld["skills"]:
                    LessonSkill.objects.get_or_create(lesson=lesson, skill=skills[code])
                for mapping in ld.get("boards", []):
                    if course.class_level_id:
                        BoardMapping.objects.update_or_create(
                            lesson=lesson,
                            board=boards[mapping["board"]],
                            class_level=course.class_level,
                            defaults={"chapter_ref": mapping["chapter"]},
                        )
                _publish_lesson_content(lesson, ld["sections"], author, reviewer, lead)
                for qpos, q in enumerate(ld["questions"], start=1):
                    report.questions += _publish_question(lesson, qpos, q, skills[q["skill"]], author, reviewer, lead)

    for p in programmes["programmes"]:
        programme, _ = Programme.objects.update_or_create(
            slug=p["slug"],
            defaults={
                "title": p["title"],
                "summary": p["summary"],
                "class_level": classes.get(p["class_number"]),
                "path_stage": p["path_stage"],
                "price_paise": p["price_paise"],
                "status": PublishStatus.PUBLISHED,
            },
        )
        report.programmes += 1
        for position, slug in enumerate(p["courses"], start=1):
            ProgrammeCourse.objects.update_or_create(
                programme=programme, course=Course.objects.get(slug=slug), defaults={"position": position}
            )

    for u in programmes.get("unpublished_courses", []):
        course, _ = Course.objects.update_or_create(
            slug=u["slug"],
            defaults={
                "title": u["title"],
                "subject": Subject.objects.get(slug=u["subject"]),
                "class_level": classes.get(u["class_number"]),
                "summary": u["summary"],
                "status": PublishStatus.DRAFT,
            },
        )
        module, _ = Module.objects.update_or_create(course=course, position=1, defaults={"title": u["module"]})
        Lesson.objects.update_or_create(
            module=module, position=1, defaults={"slug": u["lesson"]["slug"], "title": u["lesson"]["title"]}
        )
    return report
