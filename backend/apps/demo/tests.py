"""The demo world: content files are valid, seeding is safe, repeatable and produces every state testers rely on."""

import copy
from io import StringIO

from django.contrib.auth import authenticate
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, SimpleTestCase, TestCase, override_settings

from apps.accounts.models import RoleGrant, StudentProfile, User
from apps.accounts.permissions import can_publish_for_lesson, is_super_admin
from apps.assessment.models import Attempt, QuestionVersion
from apps.catalogue.models import Course, Lesson, Programme, PublishStatus
from apps.content import services as content_services
from apps.content.models import ContentVersion
from apps.learning.models import CourseCompletion, MasteryState
from apps.learning.planner import streak_days

from . import activity, content
from .content import DemoContentError, validate
from .people import BY_KEY, PEOPLE

PASSWORD = "Demo-Pass-2026-local"
DEMO = override_settings(TUTOR_DEMO_DATA=True, TUTOR_DEMO_PASSWORD=PASSWORD)


def user(key):
    return User.objects.get(mobile=BY_KEY[key].mobile)


class ContentFileTests(SimpleTestCase):
    """Every JSON file under apps/demo/content is checked before it can reach a database."""

    def setUp(self):
        self.courses, self.programmes = content.read_all()

    def check(self, courses=None, programmes=None):
        return validate(
            courses or self.courses,
            programmes or self.programmes,
            known_skills=content.AI_FOUNDATIONS_SKILLS,
            known_courses=["ai-foundations"],
        )

    def test_shipped_files_are_valid(self):
        self.assertTrue(self.check())
        self.assertGreaterEqual(len(self.courses), 5)

    def broken(self, mutate):
        courses = copy.deepcopy(self.courses)
        mutate(courses[0][1])
        with self.assertRaises(DemoContentError):
            self.check(courses=courses)

    def first_question(self, data):
        return data["modules"][0]["lessons"][0]["questions"][0]

    def test_answer_out_of_range_is_rejected(self):
        self.broken(lambda d: self.first_question(d).update(answer=9))

    def test_duplicate_options_are_rejected(self):
        self.broken(lambda d: self.first_question(d).update(options=["a", "a"], answer=0))

    def test_question_on_untaught_skill_is_rejected(self):
        self.broken(lambda d: self.first_question(d).update(skill="NOPE-01"))

    def test_misconception_on_the_correct_option_is_rejected(self):
        self.broken(
            lambda d: self.first_question(d).update(misconceptions={str(self.first_question(d)["answer"]): "x"})
        )

    def test_missing_explanation_is_rejected(self):
        self.broken(lambda d: self.first_question(d).update(explanation=""))

    def test_unknown_prerequisite_is_rejected(self):
        self.broken(lambda d: d["skills"][0].update(requires=["NOPE-01"]))

    def test_bad_free_module_is_rejected(self):
        self.broken(lambda d: d["course"].update(free_module_position=99))

    def test_programme_with_unknown_course_is_rejected(self):
        programmes = copy.deepcopy(self.programmes)
        programmes["programmes"][0]["courses"].append("no-such-course")
        with self.assertRaises(DemoContentError):
            self.check(programmes=programmes)


class StudyTimeTests(SimpleTestCase):
    def test_study_time_is_10am_ist_and_never_in_the_future(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo

        ist = ZoneInfo("Asia/Kolkata")
        early = datetime(2026, 9, 29, 0, 30, tzinfo=ist)  # 00:30 IST: 10:00 today is still ahead
        self.assertEqual(activity.study_time(early, 0), early)
        self.assertEqual(activity.study_time(early, 1), datetime(2026, 9, 28, 10, 0, tzinfo=ist))
        late = datetime(2026, 9, 29, 22, 0, tzinfo=ist)
        self.assertEqual(activity.study_time(late, 0), datetime(2026, 9, 29, 10, 0, tzinfo=ist))


class SeedGuardTests(TestCase):
    @override_settings(TUTOR_DEMO_DATA=False)
    def test_refuses_without_the_demo_flag(self):
        with self.assertRaises(CommandError):
            call_command("seed_demo", stdout=StringIO())
        self.assertFalse(Course.objects.filter(slug="mathematics-class-8").exists())

    @override_settings(TUTOR_DEMO_DATA=True, TUTOR_DEMO_PASSWORD="short")
    def test_refuses_a_weak_password(self):
        with self.assertRaises(CommandError):
            call_command("seed_demo", stdout=StringIO())

    @override_settings(TUTOR_DEMO_DATA=True, TUTOR_DEMO_PASSWORD="")
    def test_without_password_loads_content_but_no_people(self):
        out = StringIO()
        call_command("seed_demo", stdout=out)
        self.assertIn("demo people skipped", out.getvalue())
        self.assertTrue(Course.objects.filter(slug="physics-class-11", status="published").exists())
        self.assertFalse(User.objects.filter(email__endswith="@test.tutor").exists())


@DEMO
class DemoWorldTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", stdout=StringIO())

    def test_catalogue(self):
        published = set(Course.objects.filter(status=PublishStatus.PUBLISHED).values_list("slug", flat=True))
        self.assertTrue(
            {
                "ai-foundations",
                "mathematics-class-6",
                "mathematics-class-8",
                "science-class-8",
                "physics-class-11",
                "chemistry-class-11",
            }
            <= published
        )
        self.assertEqual(Course.objects.get(slug="biology-class-12").status, PublishStatus.DRAFT)
        self.assertEqual(Programme.objects.filter(status=PublishStatus.PUBLISHED).count(), 4)
        self.assertGreaterEqual(QuestionVersion.objects.filter(status="published").count(), 81)
        for lesson in Lesson.objects.filter(module__course__status=PublishStatus.PUBLISHED):
            self.assertIsNotNone(content_services.published_version(lesson), lesson.slug)

    def test_draft_course_is_hidden_from_the_public_catalogue(self):
        body = Client().get("/api/v1/catalogue/items?page_size=50").json()
        slugs = {i["slug"] for i in body["results"]}
        self.assertNotIn("biology-class-12", slugs)
        self.assertIn("physics-class-11", slugs)

    def test_everyone_logs_in_with_the_demo_password(self):
        for p in PEOPLE:
            with self.subTest(p.key):
                self.assertIsNotNone(authenticate(None, username=p.email, password=PASSWORD))

    def test_student_states(self):
        states = {p.key: StudentProfile.objects.get(user=user(p.key)).status for p in PEOPLE if p.kind == "student"}
        self.assertEqual(states["student_waiting"], "awaiting_consent")
        self.assertEqual(states["rohan"], "paused")
        self.assertEqual(
            {k for k, v in states.items() if v == "active"},
            {"student_active", "student_enrolled", "kabir", "meera", "zoya", "ishaan"},
        )
        self.assertTrue(
            user("student_waiting")
            .approval_requests.filter(status="sent", parent_contact=BY_KEY["rahul"].mobile)
            .exists()
        )

    def test_four_product_admins(self):
        roles = {
            key: set(user(key).role_grants.filter(revoked_at__isnull=True).values_list("role", flat=True))
            for key in ("ananya", "lead", "maya", "omar")
        }
        self.assertEqual(
            roles,
            {
                "ananya": {"super_admin"},
                "lead": {"curriculum_lead"},
                "maya": {"curriculum_lead"},
                "omar": {"operations"},
            },
        )
        self.assertTrue(is_super_admin(user("ananya")))
        for key in ("ananya", "lead", "maya", "omar"):
            self.assertFalse(user(key).is_superuser, key)  # product admins, never Django superusers

    def test_publishing_rights_match_the_roles(self):
        maths_lesson = Lesson.objects.get(slug="solving-linear-equations")
        ai_lesson = Lesson.objects.get(slug="what-is-data")
        self.assertTrue(can_publish_for_lesson(user("maya"), maths_lesson))
        self.assertFalse(can_publish_for_lesson(user("maya"), ai_lesson))
        self.assertTrue(can_publish_for_lesson(user("lead"), ai_lesson))
        self.assertFalse(can_publish_for_lesson(user("omar"), maths_lesson))
        self.assertFalse(can_publish_for_lesson(user("vikram"), maths_lesson))
        self.assertTrue(can_publish_for_lesson(user("ananya"), maths_lesson))

    def test_content_waiting_in_every_review_state(self):
        states = set(
            ContentVersion.objects.exclude(status__in=["published", "archived"]).values_list("lesson__slug", "status")
        )
        self.assertEqual(
            states,
            {
                ("what-is-data", "draft"),
                ("equations-from-word-problems", "in_review"),
                ("solving-linear-equations", "approved"),
            },
        )
        approved = ContentVersion.objects.get(lesson__slug="solving-linear-equations", status="approved")
        self.assertEqual(content_services.publish(approved, user("maya")).status, "published")
        self.assertTrue(
            QuestionVersion.objects.filter(
                status="approved", question__lesson__slug="what-are-rational-numbers"
            ).exists()
        )

    def test_learning_history(self):
        kabir = user("kabir")
        self.assertTrue(CourseCompletion.objects.filter(student=kabir, course__slug="ai-foundations").exists())
        weak = MasteryState.objects.get(student=kabir, skill__code="M8-RAT-02")
        self.assertLess(weak.score, 0.40)
        self.assertEqual(streak_days(user("zoya")), 5)
        self.assertEqual(streak_days(user("meera")), 3)
        self.assertFalse(Attempt.objects.filter(student=user("student_active")).exists())

    def test_paused_student_keeps_history_but_is_blocked(self):
        rohan = user("rohan")
        self.assertTrue(Attempt.objects.filter(student=rohan).exists())
        client = Client()
        client.force_login(rohan, backend="apps.accounts.backends.EmailOrMobileBackend")
        lesson = Lesson.objects.get(slug="what-are-rational-numbers")
        self.assertEqual(client.get(f"/api/v1/lessons/{lesson.id}").json()["error"]["code"], "consent_required")

    def test_kabir_sees_his_record_and_a_review_item(self):
        client = Client()
        client.force_login(user("kabir"), backend="apps.accounts.backends.EmailOrMobileBackend")
        today = client.get("/api/v1/student/today").json()
        self.assertIsNotNone(today["review"])
        record = client.get("/api/v1/student/record").json()
        self.assertGreaterEqual(len(record["quizzes"]), 7)
        self.assertIn("ai-foundations", {c["slug"] for c in record["completed_courses"]})

    def test_running_again_changes_nothing(self):
        counts = (
            User.objects.count(),
            Attempt.objects.count(),
            ContentVersion.objects.count(),
            RoleGrant.objects.count(),
        )
        call_command("seed_demo", stdout=StringIO())
        self.assertEqual(
            counts,
            (User.objects.count(), Attempt.objects.count(), ContentVersion.objects.count(), RoleGrant.objects.count()),
        )

    def test_reset_activity_rebuilds_history(self):
        activity.reset()
        self.assertFalse(Attempt.objects.filter(student=user("kabir")).exists())
        call_command("seed_demo", "--reset-activity", stdout=StringIO())
        self.assertEqual(streak_days(user("zoya")), 5)
