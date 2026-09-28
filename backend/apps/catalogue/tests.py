from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import Client, TestCase

from apps.accounts.models import User
from apps.catalogue.models import (
    Board,
    BoardMapping,
    ClassLevel,
    Course,
    Lesson,
    Module,
    PublishStatus,
    Subject,
)
from apps.content import services as content_services
from apps.content.models import ContentVersion
from apps.core.errors import ApiError


class CatalogueApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo_catalogue", verbosity=0)
        cls.c = Client()
        # A Class 8 CBSE maths course with one lesson mapped to CBSE
        maths = Subject.objects.get(slug="mathematics")
        cls.maths8 = Course.objects.create(
            subject=maths, class_level=ClassLevel.objects.get(number=8), title="Maths Class 8", slug="maths-8",
            price_paise=99900, status=PublishStatus.PUBLISHED,
        )
        m = Module.objects.create(course=cls.maths8, title="Numbers", position=1)
        lesson = Lesson.objects.create(module=m, title="Rational numbers", slug="rational-numbers", position=1)
        BoardMapping.objects.create(lesson=lesson, board=Board.objects.get(code="CBSE"),
                                    class_level=ClassLevel.objects.get(number=8), chapter_ref="Chapter 1")
        Course.objects.create(subject=maths, title="Hidden draft", slug="draft-course")  # draft: never listed

    def get(self, path):
        return self.c.get(f"/api/v1{path}")

    def slugs(self, res):
        return {i["slug"] for i in res.json()["results"]}

    def test_facets(self):
        data = self.get("/catalogue/facets").json()
        self.assertEqual([c["number"] for c in data["classes"]], list(range(6, 13)))
        self.assertEqual(len(data["stages"]), 5)

    def test_items_lists_published_only(self):
        slugs = self.slugs(self.get("/catalogue/items"))
        self.assertIn("ai-foundations", slugs)
        self.assertIn("explore-ai-class-8", slugs)
        self.assertNotIn("draft-course", slugs)

    def test_board_filter_keeps_board_independent_courses(self):
        icse = self.slugs(self.get("/catalogue/items?type=course&board=icse"))
        self.assertEqual(icse, {"ai-foundations"})  # maths-8 is mapped to CBSE only
        cbse = self.slugs(self.get("/catalogue/items?type=course&board=CBSE"))
        self.assertEqual(cbse, {"ai-foundations", "maths-8"})

    def test_class_filter(self):
        self.assertNotIn("maths-8", self.slugs(self.get("/catalogue/items?type=course&class_number=9")))
        self.assertIn("maths-8", self.slugs(self.get("/catalogue/items?type=course&class_number=8")))

    def test_pagination(self):
        data = self.get("/catalogue/items?page_size=1&page=2").json()
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["page"], 2)
        self.assertGreaterEqual(data["total"], 3)

    def test_course_detail(self):
        data = self.get("/courses/ai-foundations").json()
        self.assertEqual(data["path_stage_label"], "Explore")
        self.assertEqual(len(data["modules"][0]["lessons"]), 3)
        self.assertTrue(all(lesson["is_free"] and lesson["has_content"] for lesson in data["modules"][0]["lessons"]))
        self.assertIn("AI-EVAL-01", {s["code"] for s in data["skills"]})

    def test_draft_course_is_404(self):
        self.assertEqual(self.get("/courses/draft-course").status_code, 404)

    def test_programme_detail(self):
        data = self.get("/programmes/explore-ai-class-8").json()
        self.assertEqual(data["class_number"], 8)
        self.assertEqual([c["slug"] for c in data["courses"]], ["ai-foundations"])

    def test_free_lesson_preview(self):
        lesson = Lesson.objects.get(slug="what-is-data")
        data = self.get(f"/lessons/{lesson.id}/preview").json()
        self.assertEqual(data["sections"][1]["heading"], "Features and labels")

    def test_paid_lesson_preview_is_blocked(self):
        lesson = Lesson.objects.get(slug="rational-numbers")  # maths-8 has no free module
        res = self.get(f"/lessons/{lesson.id}/preview")
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["error"]["code"], "not_entitled")

    def test_demo_seed_is_idempotent(self):
        call_command("seed_demo_catalogue", verbosity=0)
        self.assertEqual(Lesson.objects.filter(module__course__slug="ai-foundations").count(), 3)
        self.assertEqual(ContentVersion.objects.filter(status="published", lesson__module__course__slug="ai-foundations").count(), 3)


class ContentVersionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo_catalogue", verbosity=0)
        cls.lesson = Lesson.objects.get(slug="what-is-data")
        cls.author = User.objects.create_user(email="a@example.com", password="x-long-pass-1", full_name="A")
        cls.reviewer = User.objects.create_user(email="r@example.com", password="x-long-pass-1", full_name="R")

    def new_version(self, status="approved"):
        return ContentVersion.objects.create(
            lesson=self.lesson, version_no=content_services.next_version_no(self.lesson),
            body={"sections": [{"heading": "New", "blocks": []}]}, status=status,
            author=self.author, reviewer=self.reviewer,
        )

    def test_publishing_archives_previous(self):
        old = content_services.published_version(self.lesson)
        new = content_services.publish(self.new_version(), self.reviewer)
        old.refresh_from_db()
        self.assertEqual(old.status, "archived")
        self.assertEqual(content_services.published_version(self.lesson), new)

    def test_only_approved_can_be_published(self):
        with self.assertRaises(ApiError):
            content_services.publish(self.new_version(status="draft"), self.reviewer)

    def test_reviewer_cannot_be_author(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ContentVersion.objects.create(
                lesson=self.lesson, version_no=99, body={}, author=self.author, reviewer=self.author
            )

    def test_one_published_version_per_lesson(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.new_version(status="published")
