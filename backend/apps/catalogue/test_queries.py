"""Catalogue endpoints: pagination in the database and a fixed number of queries per request (Q1, Q2)."""

from django.core.management import call_command
from django.test import Client, SimpleTestCase, TestCase

from apps.accounts.models import User
from apps.catalogue.api import paginate_concatenated
from apps.catalogue.models import (
    Board,
    ClassLevel,
    Course,
    Lesson,
    Module,
    Programme,
    ProgrammeCourse,
    PublishStatus,
    Subject,
)
from apps.content.models import ContentVersion
from apps.core.testing import QueryBudgetMixin


class FakeQuerySet:
    """Just enough of a queryset for paginate_concatenated: count() and slicing, with a record of the slices."""

    def __init__(self, rows):
        self.rows = rows
        self.slices = []

    def count(self):
        return len(self.rows)

    def __getitem__(self, s):
        self.slices.append((s.start, s.stop))
        return self.rows[s]


class PaginateConcatenatedTests(SimpleTestCase):
    def run_page(self, offset, limit):
        self.a = FakeQuerySet(["a1", "a2", "a3"])
        self.b = FakeQuerySet(["b1", "b2"])
        return paginate_concatenated([(self.a, str.upper), (self.b, str.upper)], offset, limit)

    def test_page_inside_first_source(self):
        self.assertEqual(self.run_page(0, 2), (["A1", "A2"], 5))
        self.assertEqual(self.b.slices, [])  # second source is only counted

    def test_page_spanning_both_sources(self):
        self.assertEqual(self.run_page(2, 2), (["A3", "B1"], 5))
        self.assertEqual(self.a.slices, [(2, 3)])
        self.assertEqual(self.b.slices, [(0, 1)])

    def test_page_inside_second_source(self):
        self.assertEqual(self.run_page(3, 10), (["B1", "B2"], 5))
        self.assertEqual(self.a.slices, [])

    def test_page_past_the_end(self):
        self.assertEqual(self.run_page(10, 5), ([], 5))

    def test_no_sources(self):
        self.assertEqual(paginate_concatenated([], 0, 20), ([], 0))


class CatalogueQueryTests(QueryBudgetMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo_catalogue", verbosity=0)
        cls.maths = Subject.objects.get(slug="mathematics")
        cls.class8 = ClassLevel.objects.get(number=8)
        cls.author = User.objects.create_user(email="qa-author@example.com", password="x-long-pass-1", full_name="A")
        cls.reviewer = User.objects.create_user(email="qa-rev@example.com", password="x-long-pass-1", full_name="R")
        cls.course = Course.objects.get(slug="ai-foundations")
        cls.programme = Programme.objects.get(slug="explore-ai-class-8")

    def setUp(self):
        self.c = Client()
        self.counter = 0

    def get(self, path):
        return lambda: self.c.get(f"/api/v1{path}")

    def add_courses(self, n):
        for _ in range(n):
            self.counter += 1
            Course.objects.create(
                subject=self.maths,
                class_level=self.class8,
                title=f"Extra course {self.counter}",
                slug=f"extra-course-{self.counter}",
                status=PublishStatus.PUBLISHED,
            )

    def add_published_lessons(self, course, n):
        module, _ = Module.objects.get_or_create(course=course, position=9, defaults={"title": "Extra"})
        start = module.lessons.count() + 1
        for position in range(start, start + n):
            lesson = Lesson.objects.create(
                module=module, title=f"Extra {position}", slug=f"x-{position}", position=position
            )
            ContentVersion.objects.create(
                lesson=lesson,
                version_no=1,
                body={"sections": []},
                status=ContentVersion.Status.PUBLISHED,
                author=self.author,
                reviewer=self.reviewer,
            )

    def test_items_are_paginated_in_the_database(self):
        self.add_courses(25)
        res = self.c.get("/api/v1/catalogue/items?type=course&page=2&page_size=10")
        body = res.json()
        self.assertEqual(body["total"], 26)  # 25 extra + AI Foundations
        self.assertEqual(len(body["results"]), 10)
        _, _, queries = self.count_queries(lambda: self.c.get("/api/v1/catalogue/items?page=3&page_size=10"))
        sql = " ".join(q["sql"] for q in queries)
        self.assertIn("LIMIT", sql.upper())

    def test_items_spill_from_courses_into_programmes(self):
        self.add_courses(4)  # 5 courses + 1 programme = 6 items
        body = self.c.get("/api/v1/catalogue/items?page=2&page_size=4").json()
        self.assertEqual(body["total"], 6)
        self.assertEqual([i["type"] for i in body["results"]], ["course", "programme"])

    def test_items_query_count_is_constant(self):
        self.assertQueriesDoNotGrow(self.get("/catalogue/items?page_size=50"), lambda: self.add_courses(20), budget=6)

    def test_items_with_board_filter_query_count_is_constant(self):
        self.assertQueriesDoNotGrow(
            self.get("/catalogue/items?board=cbse&class_number=8"), lambda: self.add_courses(10), budget=6
        )

    def test_facets_query_count_is_constant(self):
        def grow():
            Board.objects.create(code="XB", name="Extra board")
            Subject.objects.create(discipline=self.maths.discipline, slug="extra-subject", name="Extra subject")

        self.assertQueriesDoNotGrow(self.get("/catalogue/facets"), grow, budget=5)

    def test_course_detail_query_count_is_constant(self):
        self.assertQueriesDoNotGrow(
            self.get("/courses/ai-foundations"), lambda: self.add_published_lessons(self.course, 5), budget=8
        )

    def test_course_detail_marks_lessons_without_content(self):
        module = Module.objects.create(course=self.course, title="Empty", position=8)
        Lesson.objects.create(module=module, title="Coming soon", slug="soon", position=1)
        lessons = [
            lesson for m in self.c.get("/api/v1/courses/ai-foundations").json()["modules"] for lesson in m["lessons"]
        ]
        flags = {lesson["title"]: lesson["has_content"] for lesson in lessons}
        self.assertTrue(flags["What is data?"])
        self.assertFalse(flags["Coming soon"])

    def test_programme_detail_query_count_is_constant(self):
        def grow():
            self.add_courses(5)
            for position, course in enumerate(Course.objects.filter(slug__startswith="extra-course"), start=2):
                ProgrammeCourse.objects.get_or_create(
                    programme=self.programme, course=course, defaults={"position": position}
                )

        self.assertQueriesDoNotGrow(self.get("/programmes/explore-ai-class-8"), grow, budget=4)
