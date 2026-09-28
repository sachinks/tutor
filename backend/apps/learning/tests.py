"""The core learning loop, end to end: lesson → quiz (hints, answers) → mastery → record/today (journeys S8–S11)."""
import json

from django.core.management import call_command
from django.test import Client, TestCase

from apps.accounts.models import StudentProfile, User
from apps.catalogue.models import Board, ClassLevel, Course, Lesson, Module, PublishStatus, Subject
from apps.commerce.models import Entitlement
from apps.learning import mastery
from apps.learning.models import CourseCompletion, MasteryState


def post(client, path, data=None):
    return client.post(f"/api/v1{path}", data=json.dumps(data or {}), content_type="application/json")


class LoopBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo_catalogue", verbosity=0)
        cls.course = Course.objects.get(slug="ai-foundations")
        cls.lesson1 = Lesson.objects.get(slug="what-is-data")
        # A paid module (not free) to test entitlements
        paid_module = Module.objects.create(course=cls.course, title="Going further", position=2)
        cls.paid_lesson = Lesson.objects.create(module=paid_module, title="Paid lesson", slug="paid", position=1)

    def make_student(self, status="active", email="kid@example.com"):
        user = User.objects.create_user(email=email, password="Kid-pass-2026", full_name="Kid Learner")
        StudentProfile.objects.create(
            user=user, class_level=ClassLevel.objects.get(number=8), board=Board.objects.get(code="CBSE"),
            city="Kolkata", status=status,
        )
        client = Client()
        client.force_login(user, backend="apps.accounts.backends.EmailOrMobileBackend")
        return user, client


class AccessTests(LoopBase):
    def test_consent_required(self):
        _, c = self.make_student(status="awaiting_consent")
        res = c.get(f"/api/v1/lessons/{self.lesson1.id}")
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["error"]["code"], "consent_required")

    def test_free_lesson_open_without_purchase(self):
        _, c = self.make_student()
        res = c.get(f"/api/v1/lessons/{self.lesson1.id}")
        self.assertEqual(res.status_code, 200, res.content)
        self.assertTrue(res.json()["has_quiz"])

    def test_paid_lesson_needs_entitlement(self):
        student, c = self.make_student()
        self.assertEqual(c.get(f"/api/v1/lessons/{self.paid_lesson.id}").json()["error"]["code"], "not_entitled")
        Entitlement.objects.create(student=student, product_type="course", product_id=self.course.id)
        # entitled but no published content yet → 404, not 403
        self.assertEqual(c.get(f"/api/v1/lessons/{self.paid_lesson.id}").status_code, 404)

    def test_programme_entitlement_covers_its_courses(self):
        from apps.catalogue.models import Programme
        student, c = self.make_student()
        Entitlement.objects.create(student=student, product_type="programme",
                                   product_id=Programme.objects.get(slug="explore-ai-class-8").id)
        self.assertEqual(c.get(f"/api/v1/lessons/{self.paid_lesson.id}").status_code, 404)  # allowed, just empty

    def test_revoked_entitlement(self):
        from django.utils import timezone
        student, c = self.make_student()
        Entitlement.objects.create(student=student, product_type="course", product_id=self.course.id,
                                   revoked_at=timezone.now())
        self.assertEqual(c.get(f"/api/v1/lessons/{self.paid_lesson.id}").status_code, 403)


class QuizFlowTests(LoopBase):
    def test_quiz_does_not_leak_answers(self):
        _, c = self.make_student()
        data = post(c, f"/lessons/{self.lesson1.id}/quiz/start").json()
        self.assertEqual(len(data["items"]), 3)
        self.assertNotIn("answer_index", json.dumps(data))

    def test_full_quiz(self):
        student, c = self.make_student()
        attempt = post(c, f"/lessons/{self.lesson1.id}/quiz/start").json()
        aid = attempt["attempt_id"]

        hint = post(c, f"/attempts/{aid}/hint", {"position": 1}).json()
        self.assertEqual(hint["hints_left"], 1)

        right = post(c, f"/attempts/{aid}/answers", {"position": 1, "choice_index": 2}).json()
        self.assertTrue(right["correct"])
        wrong = post(c, f"/attempts/{aid}/answers", {"position": 2, "choice_index": 1}).json()
        self.assertFalse(wrong["correct"])
        self.assertEqual(wrong["misconception"], "Who won is the label here.")
        post(c, f"/attempts/{aid}/answers", {"position": 3, "choice_index": 1})

        # answering twice is refused
        self.assertEqual(post(c, f"/attempts/{aid}/answers", {"position": 1, "choice_index": 0}).status_code, 409)

        result = post(c, f"/attempts/{aid}/submit").json()
        self.assertEqual((result["score"], result["max_score"]), (2, 3))
        self.assertEqual(result["skill_changes"][0]["skill"], "AI-DATA-01")
        self.assertEqual(post(c, f"/attempts/{aid}/submit").status_code, 409)

        state = MasteryState.objects.get(student=student, skill__code="AI-DATA-01")
        self.assertEqual(state.evidence_count, 3)

        record = c.get("/api/v1/student/record").json()
        self.assertEqual(record["quizzes"][0]["score"], 2)
        self.assertEqual(record["lessons_finished"], 1)

    def test_other_students_attempt_is_invisible(self):
        _, c1 = self.make_student(email="a@example.com")
        _, c2 = self.make_student(email="b@example.com")
        aid = post(c1, f"/lessons/{self.lesson1.id}/quiz/start").json()["attempt_id"]
        self.assertEqual(post(c2, f"/attempts/{aid}/answers", {"position": 1, "choice_index": 0}).status_code, 404)

    def test_course_completion_and_today(self):
        student, c = self.make_student()
        Entitlement.objects.create(student=student, product_type="course", product_id=self.course.id)
        self.paid_lesson.delete()  # keep the course to its 3 demo lessons
        today = c.get("/api/v1/student/today").json()
        self.assertEqual(today["next_lesson"]["title"], "What is data?")

        answers = {"what-is-data": [2, 0, 1], "learning-from-examples": [1, 1, 1], "is-the-model-any-good": [2, 1, 1]}
        for slug, choices in answers.items():
            lesson = Lesson.objects.get(slug=slug)
            aid = post(c, f"/lessons/{lesson.id}/quiz/start").json()["attempt_id"]
            for pos, choice in enumerate(choices, start=1):
                post(c, f"/attempts/{aid}/answers", {"position": pos, "choice_index": choice})
            result = post(c, f"/attempts/{aid}/submit").json()
        self.assertTrue(result["course_completed"])
        self.assertTrue(CourseCompletion.objects.filter(student=student, course=self.course).exists())
        self.assertIsNone(c.get("/api/v1/student/today").json()["next_lesson"])
        self.assertGreaterEqual(c.get("/api/v1/student/today").json()["streak_days"], 1)


class MasteryRuleTests(TestCase):
    def test_levels(self):
        self.assertEqual(mastery.level_for(0.0, 0), "not_started")
        self.assertEqual(mastery.level_for(0.2, 1), "weak")
        self.assertEqual(mastery.level_for(0.9, 2), "developing")  # needs 3 pieces of evidence
        self.assertEqual(mastery.level_for(0.8, 3), "mastered")

    def test_hint_penalty(self):
        self.assertEqual(mastery.credit_for(True, 0), 1.0)
        self.assertEqual(mastery.credit_for(True, 2), 0.5)
        self.assertEqual(mastery.credit_for(False, 0), 0.0)
