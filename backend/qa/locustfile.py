"""Load test for the main read paths and the quiz loop (quality backlog Q17, NFR-PERF-1: p95 < 300 ms).

Not part of CI. Run it against a local production-like server, never against the hosted demo (the free tier is
shared and rate-limited):

    pip install locust                                   # not a project dependency
    python manage.py seed_demo                           # demo accounts and courses
    gunicorn config.wsgi --workers 2 --bind 127.0.0.1:8000 &
    TUTOR_DEMO_PASSWORD=Test-Pass-2026 locust -f qa/locustfile.py --host http://127.0.0.1:8000 \\
        --users 20 --spawn-rate 5 --run-time 2m --headless --csv logs/load

Read the p95 column per endpoint. Rate limits still apply (all users share one IP), so keep --users modest; the
point is latency per request, not maximum throughput. Students log in once each at start.
"""

import os
import random

from locust import HttpUser, between, task

API = "/api/v1"
STUDENTS = ["kabir@test.tutor", "meera@test.tutor", "zoya@test.tutor", "esha@test.tutor"]


class Visitor(HttpUser):
    """Someone browsing the public catalogue."""

    weight = 3
    wait_time = between(1, 3)

    def on_start(self):
        items = self.client.get(f"{API}/catalogue/items?page_size=50", name="catalogue items").json()["results"]
        self.courses = [i["slug"] for i in items if i["type"] == "course"]

    @task(3)
    def browse(self):
        self.client.get(f"{API}/catalogue/items", name="catalogue items")

    @task(2)
    def filter_by_class(self):
        self.client.get(
            f"{API}/catalogue/items?class_number={random.choice([6, 8, 11])}", name="catalogue items (class)"
        )

    @task(2)
    def course_page(self):
        if self.courses:
            self.client.get(f"{API}/courses/{random.choice(self.courses)}", name="course detail")

    @task(1)
    def facets(self):
        self.client.get(f"{API}/catalogue/facets", name="facets")


class Student(HttpUser):
    """A logged-in demo student: Today, record, lessons and quizzes."""

    weight = 1
    wait_time = between(2, 5)

    def on_start(self):
        self.client.post(
            f"{API}/auth/login",
            json={"identifier": random.choice(STUDENTS), "password": os.environ["TUTOR_DEMO_PASSWORD"]},
            name="login",
        )
        self.csrf = self.client.get(f"{API}/auth/csrf", name="csrf").json()["csrf_token"]
        course = self.client.get(f"{API}/courses/ai-foundations", name="course detail").json()
        self.lessons = [lesson["id"] for m in course["modules"] for lesson in m["lessons"] if lesson["has_content"]]

    @task(3)
    def today(self):
        self.client.get(f"{API}/student/today", name="today")

    @task(2)
    def record(self):
        self.client.get(f"{API}/student/record", name="record")

    @task(3)
    def open_lesson(self):
        self.client.get(f"{API}/lessons/{random.choice(self.lessons)}", name="open lesson")

    @task(1)
    def start_quiz(self):
        self.client.post(
            f"{API}/lessons/{random.choice(self.lessons)}/quiz/start",
            headers={"X-CSRFToken": self.csrf},
            name="quiz start",
        )
