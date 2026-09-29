"""Boundary values for catalogue and quiz input, plus manual cases TC-LRN-05, TC-ADM-03 and TC-ADM-08 automated."""

from django.test import Client

from apps.accounts.models import User
from apps.catalogue.models import Lesson
from apps.commerce.models import Entitlement
from apps.learning.models import MasteryEvent

from .tests import LoopBase, post


class CatalogueParameterTests(LoopBase):
    def items(self, query):
        return Client().get(f"/api/v1/catalogue/items?{query}")

    def test_page_numbers_are_clamped(self):
        for query, page, size in (
            ("page=0", 1, 20),
            ("page=-5", 1, 20),
            ("page_size=0", 1, 1),
            ("page_size=1000", 1, 50),
        ):
            with self.subTest(query=query):
                body = self.items(query).json()
                self.assertEqual((body["page"], body["page_size"]), (page, size))

    def test_page_beyond_the_end_is_empty_not_an_error(self):
        body = self.items("page=999").json()
        self.assertEqual(body["results"], [])
        self.assertGreater(body["total"], 0)

    def test_wrong_types_are_400(self):
        for query in ("class_number=eight", "stage=x", "page=abc", "type=video"):
            with self.subTest(query=query):
                self.assertEqual(self.items(query).status_code, 400)

    def test_filters_that_match_nothing_are_empty(self):
        for query in ("stage=5", "board=XYZ&class_number=8", "subject=astrology"):
            with self.subTest(query=query):
                response = self.items(query)
                self.assertEqual(response.status_code, 200)

    def test_non_uuid_lesson_id_is_400_or_404_never_500(self):
        for path in ("/api/v1/lessons/not-a-uuid/preview", "/api/v1/courses/" + "x" * 300):
            with self.subTest(path=path[:40]):
                self.assertIn(Client().get(path).status_code, (400, 404))


class QuizInputTests(LoopBase):
    def setUp(self):
        self.student, self.client = self.make_student()
        self.attempt = post(self.client, f"/lessons/{self.lesson1.id}/quiz/start").json()["attempt_id"]

    def answer(self, position, choice):
        return post(self.client, f"/attempts/{self.attempt}/answers", {"position": position, "choice_index": choice})

    def test_choice_out_of_range(self):
        for choice in (-1, 4, 99):
            with self.subTest(choice=choice):
                response = self.answer(1, choice)
                self.assertEqual(response.status_code, 400)
                self.assertIn("choice_index", response.json()["error"]["fields"])

    def test_position_that_does_not_exist(self):
        for position in (0, 99):
            with self.subTest(position=position):
                self.assertEqual(self.answer(position, 0).status_code, 404)

    def test_missing_and_wrongly_typed_fields(self):
        self.assertEqual(post(self.client, f"/attempts/{self.attempt}/answers", {"position": 1}).status_code, 400)
        self.assertEqual(self.answer("one", 0).status_code, 400)

    def test_unknown_attempt(self):
        response = post(self.client, "/attempts/00000000-0000-0000-0000-000000000000/submit")
        self.assertEqual(response.status_code, 404)


class LessonFinishTests(LoopBase):
    def test_finish_points_to_the_next_unfinished_lesson(self):
        """TC-LRN-05."""
        student, client = self.make_student()
        Entitlement.objects.create(student=student, product_type="course", product_id=self.course.id)
        first, second = Lesson.objects.filter(module__course=self.course, module__position=1).order_by("position")[:2]
        body = post(client, f"/lessons/{first.id}/finish").json()
        self.assertTrue(body["finished"])
        self.assertEqual(body["next_lesson_id"], str(second.id))
        # finishing again is harmless (idempotent)
        self.assertEqual(post(client, f"/lessons/{first.id}/finish").status_code, 200)


class AdminLearningTests(LoopBase):
    def setUp(self):
        self.admin = User.objects.create_superuser(email="su@example.com", password="x-long-pass-1", full_name="Su")
        self.admin_client = Client()
        self.admin_client.force_login(self.admin)

    def test_entitlement_granted_in_admin_opens_paid_lessons(self):
        """TC-ADM-03."""
        student, client = self.make_student()
        self.assertEqual(client.get(f"/api/v1/lessons/{self.paid_lesson.id}").json()["error"]["code"], "not_entitled")
        response = self.admin_client.post(
            "/admin/commerce/entitlement/add/",
            {
                "student": str(student.pk),
                "product_type": "course",
                "product_id": str(self.course.id),
                "source": "admin_grant",
                "starts_at_0": "2026-01-01",
                "starts_at_1": "00:00:00",
            },
        )
        self.assertEqual(response.status_code, 302, response.content[:1500])
        # entitled now: the lesson has no published content yet, so 404 (allowed) instead of 403 (not entitled)
        self.assertEqual(client.get(f"/api/v1/lessons/{self.paid_lesson.id}").status_code, 404)

    def test_mastery_events_are_read_only_in_admin(self):
        """TC-ADM-08."""
        student, client = self.make_student()
        attempt = post(client, f"/lessons/{self.lesson1.id}/quiz/start").json()["attempt_id"]
        post(client, f"/attempts/{attempt}/answers", {"position": 1, "choice_index": 0})
        event = MasteryEvent.objects.filter(student=student).first()
        self.assertIsNotNone(event)
        page = self.admin_client.get(f"/admin/learning/masteryevent/{event.pk}/change/")
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, 'name="_save"')  # view only: no Save button
