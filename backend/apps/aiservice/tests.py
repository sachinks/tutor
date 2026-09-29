"""Lesson-index outbox, AI service client, reconciliation and sync_ai_index (docs/architecture/ai-service.md §5).

A FakeAI plays the AI service through httpx.MockTransport, so every test runs without a network or a model and
checks exactly what Django sends.
"""

import json
import uuid
from datetime import timedelta
from io import StringIO
from types import SimpleNamespace
from unittest import mock

import httpx
from django.core.management import CommandError, call_command
from django.db import transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.catalogue.models import ClassLevel, Course, Discipline, Lesson, Module, PublishStatus, Subject
from apps.content import services as content_services
from apps.content.models import ContentVersion
from apps.core import request_context

from . import indexing
from .apps import check_ai_settings
from .client import AIServiceClient, AIServiceError, AIServiceNotConfigured, get_client, is_configured
from .models import IndexRequest

TOKEN = "s" * 40
AI_ON = {"TUTOR_AI_URL": "http://ai.test", "TUTOR_AI_SERVICE_TOKEN": TOKEN}
COMMAND = "apps.aiservice.management.commands.sync_ai_index"


def error(status, code, message="refused"):
    return httpx.Response(status, json={"error": {"code": code, "message": message, "fields": {}, "request_id": "r"}})


class FakeAI:
    """A minimal AI service: remembers what is indexed and records every call. `script` holds responses (or
    exceptions, or callables) to use before the normal behaviour."""

    def __init__(self):
        self.calls = []
        self.indexed = {}  # lesson id (str) -> (content version id (str), embedding model)
        self.model = "mock-hashed-bow-v1"
        self.script = []

    def handler(self, request):
        body = json.loads(request.content) if request.content else None
        call = SimpleNamespace(
            method=request.method,
            path=request.url.path,
            headers=request.headers,
            json=body,
            params=dict(request.url.params),
        )
        self.calls.append(call)
        if self.script:
            step = self.script.pop(0)
            if isinstance(step, Exception):
                raise step
            if callable(step):
                step = step(call)
            if step is not None:
                return step
        parts = call.path.strip("/").split("/")  # v1 / lessons / <id> / index
        if call.method == "PUT":
            self.indexed[parts[2]] = (body["content_version_id"], self.model)
            return httpx.Response(200, json={"status": "indexed", "chunks": len(body["sections"])})
        if call.method == "DELETE":
            self.indexed.pop(parts[2], None)
            return httpx.Response(204)
        if call.path == "/v1/index/status":
            lessons = [
                {"lesson_id": lid, "content_version_id": vid, "embedding_model": model, "version_no": 1, "chunks": 1}
                for lid, (vid, model) in self.indexed.items()
            ]
            return httpx.Response(200, json={"embedding_model": self.model, "lessons": lessons})
        return httpx.Response(200, json={"service": "tutor-ai"})

    def client(self):
        return AIServiceClient("http://ai.test", TOKEN, timeout=5, transport=httpx.MockTransport(self.handler))

    def calls_to(self, method):
        return [c for c in self.calls if c.method == method]


class Fixtures(TestCase):
    @classmethod
    def setUpTestData(cls):
        science = Discipline.objects.create(name="Science", slug="science")
        cls.subject = Subject.objects.create(discipline=science, name="Science", slug="science")
        cls.class8 = ClassLevel.objects.create(number=8, label="Class 8")
        cls.course = Course.objects.create(
            subject=cls.subject, class_level=cls.class8, title="Science 8", slug="sci-8", status=PublishStatus.PUBLISHED
        )
        cls.module = Module.objects.create(course=cls.course, title="Plants", position=1)
        cls.lesson = Lesson.objects.create(module=cls.module, title="Photosynthesis", slug="photo", position=1)
        cls.other_lesson = Lesson.objects.create(module=cls.module, title="Roots", slug="roots", position=2)
        cls.author = User.objects.create_user(email="author@example.com", password="x-long-pass-1", full_name="A")
        cls.reviewer = User.objects.create_user(email="reviewer@example.com", password="x-long-pass-1", full_name="R")
        cls.lead = User.objects.create_superuser(email="lead@example.com", password="x-long-pass-1", full_name="L")

    def setUp(self):
        self.fake = FakeAI()

    body = {
        "sections": [
            {"heading": "What plants need", "blocks": [{"type": "text", "text": "Light, water and CO2."}]},
            {"heading": "Look", "blocks": [{"type": "image", "asset": "a1", "alt": "A leaf"}]},
        ]
    }

    def approved(self, lesson=None, body=None):
        lesson = lesson or self.lesson
        return ContentVersion.objects.create(
            lesson=lesson,
            version_no=content_services.next_version_no(lesson),
            body=body or self.body,
            status=ContentVersion.Status.APPROVED,
            author=self.author,
            reviewer=self.reviewer,
        )

    def publish(self, lesson=None, body=None):
        return content_services.publish(self.approved(lesson, body), self.lead)

    def pending(self, lesson=None):
        return IndexRequest.objects.get(lesson_id=(lesson or self.lesson).pk, status=IndexRequest.Status.PENDING)


class OutboxTests(Fixtures):
    def test_publishing_queues_the_lesson_in_the_same_transaction(self):
        self.publish()
        request = self.pending()
        self.assertEqual((request.reason, request.generation, request.attempts), ("published", 0, 0))
        self.assertLessEqual(request.next_attempt_at, timezone.now())

    def test_a_rolled_back_publish_queues_nothing(self):
        version = self.approved()
        try:
            with transaction.atomic():
                content_services.publish(version, self.lead)
                raise RuntimeError("something later in the same transaction failed")
        except RuntimeError:
            pass
        self.assertFalse(IndexRequest.objects.exists())

    def test_changes_while_pending_merge_into_one_request(self):
        self.publish()
        self.publish()
        self.assertEqual(IndexRequest.objects.count(), 1)
        self.assertEqual(self.pending().generation, 1)

    def test_other_lessons_get_their_own_request(self):
        self.publish()
        self.publish(self.other_lesson)
        self.assertEqual(IndexRequest.objects.filter(status="pending").count(), 2)

    @override_settings(**AI_ON, TUTOR_AI_INDEX_ON_PUBLISH=True)
    def test_sent_straight_after_commit_when_an_ai_service_is_configured(self):
        with mock.patch("apps.aiservice.indexing.get_client", return_value=self.fake.client()):
            with self.captureOnCommitCallbacks(execute=True):
                version = self.publish()
        [put] = self.fake.calls_to("PUT")
        self.assertEqual(put.json["content_version_id"], str(version.pk))
        request = IndexRequest.objects.get(lesson_id=self.lesson.pk)
        self.assertEqual((request.status, request.action), ("done", "index"))

    @override_settings(**AI_ON, TUTOR_AI_INDEX_ON_PUBLISH=True)
    def test_a_failure_after_commit_never_breaks_publishing(self):
        with mock.patch("apps.aiservice.indexing.get_client", side_effect=RuntimeError("boom")):
            with self.assertLogs("tutor.aiservice", "WARNING"), self.captureOnCommitCallbacks(execute=True):
                version = self.publish()
        version.refresh_from_db()
        self.assertEqual(version.status, ContentVersion.Status.PUBLISHED)
        self.assertEqual(self.pending().attempts, 0)  # still queued for sync_ai_index

    @override_settings(TUTOR_AI_URL="", TUTOR_AI_INDEX_ON_PUBLISH=True)
    def test_nothing_is_sent_without_an_ai_service(self):
        with self.captureOnCommitCallbacks() as callbacks:
            self.publish()
        self.assertEqual([c for c in callbacks if getattr(c, "func", None) is indexing._send_now], [])
        self.assertTrue(self.pending())

    @override_settings(**AI_ON, TUTOR_AI_INDEX_ON_PUBLISH=False)
    def test_sending_on_publish_can_be_switched_off(self):
        with self.captureOnCommitCallbacks() as callbacks:
            self.publish()
        self.assertEqual([c for c in callbacks if getattr(c, "func", None) is indexing._send_now], [])


class DispatchTests(Fixtures):
    def test_payload_and_headers(self):
        version = self.publish()
        request = self.pending()
        token = request_context._request_id.set("django-req-12345")
        try:
            outcomes = indexing.process(self.fake.client())
        finally:
            request_context._request_id.reset(token)
        self.assertEqual(outcomes["done"], 1)
        [put] = self.fake.calls
        self.assertEqual(put.path, f"/v1/lessons/{self.lesson.pk}/index")
        self.assertEqual(put.headers["authorization"], f"Bearer {TOKEN}")
        self.assertEqual(put.headers["idempotency-key"], f"django-ir{request.pk}-g0-index-{version.pk}")
        self.assertEqual(put.headers["x-request-id"], "django-req-12345")
        self.assertEqual(
            put.json,
            {
                "content_version_id": str(version.pk),
                "version_no": 1,
                "course_id": str(self.course.pk),
                "subject": "Science",
                "class_number": 8,
                "title": "Photosynthesis",
                "sections": self.body["sections"],
            },
        )
        request.refresh_from_db()
        self.assertEqual((request.status, request.action, request.target_version_id), ("done", "index", version.pk))
        self.assertIsNotNone(request.done_at)

    def test_a_request_id_is_generated_outside_a_web_request(self):
        self.publish()
        indexing.process(self.fake.client())
        self.assertRegex(self.fake.calls[0].headers["x-request-id"], r"^[0-9a-f]{32}$")

    def test_board_independent_course_has_no_class_and_odd_sections_are_cleaned(self):
        self.course.class_level = None
        self.course.save()
        body = {"sections": ["junk", {"heading": None, "blocks": ["junk", {"type": "text", "text": "Hi."}]}]}
        self.publish(body=body)
        indexing.process(self.fake.client())
        sent = self.fake.calls[0].json
        self.assertIsNone(sent["class_number"])
        self.assertEqual(sent["sections"], [{"heading": "", "blocks": [{"type": "text", "text": "Hi."}]}])

    def test_a_lesson_with_nothing_published_is_removed_from_the_index(self):
        self.approved()  # version 1, never published
        indexing.enqueue(self.lesson.pk, IndexRequest.Reason.MANUAL)
        indexing.process(self.fake.client())
        [delete] = self.fake.calls
        self.assertEqual((delete.method, delete.params), ("DELETE", {"up_to_version": "1"}))
        self.assertEqual(IndexRequest.objects.get().action, "delete")

    def test_a_deleted_lesson_is_removed_without_a_version_guard(self):
        gone = uuid.uuid4()
        indexing.enqueue(gone, IndexRequest.Reason.RECONCILE)
        indexing.process(self.fake.client())
        [delete] = self.fake.calls
        self.assertEqual((delete.path, delete.params), (f"/v1/lessons/{gone}/index", {}))

    def test_temporary_failures_are_retried_with_backoff_and_the_same_key(self):
        self.publish()
        self.fake.script = [error(503, "provider_unavailable")]
        self.assertEqual(indexing.process(self.fake.client())["retry"], 1)
        request = self.pending()
        self.assertEqual(request.attempts, 1)
        self.assertIn("provider_unavailable", request.last_error)
        self.assertAlmostEqual((request.next_attempt_at - timezone.now()).total_seconds(), 30, delta=5)
        self.assertEqual(sum(indexing.process(self.fake.client()).values()), 0)  # not due yet
        self.assertEqual(indexing.process(self.fake.client(), include_waiting=True)["done"], 1)
        first, second = self.fake.calls
        self.assertEqual(first.headers["idempotency-key"], second.headers["idempotency-key"])

    def test_giving_up_after_the_last_attempt(self):
        self.publish()
        IndexRequest.objects.update(attempts=indexing.MAX_ATTEMPTS - 1)
        self.fake.script = [error(500, "server_error")]
        self.assertEqual(indexing.process(self.fake.client())["failed"], 1)
        request = IndexRequest.objects.get()
        self.assertEqual((request.status, request.retryable, request.attempts), ("failed", True, indexing.MAX_ATTEMPTS))

    def test_a_request_the_ai_service_refuses_fails_at_once(self):
        self.publish()
        self.fake.script = [error(400, "empty_lesson", "The lesson has no text to index.")]
        self.assertEqual(indexing.process(self.fake.client())["failed"], 1)
        request = IndexRequest.objects.get()
        self.assertEqual((request.status, request.retryable), ("failed", False))
        self.assertIn("empty_lesson", request.last_error)
        indexing.enqueue(self.lesson.pk, IndexRequest.Reason.MANUAL)  # a new change can be queued again
        self.assertEqual(IndexRequest.objects.filter(status="pending").count(), 1)

    def test_a_newer_version_already_indexed_counts_as_done(self):
        self.publish()
        self.fake.script = [error(409, "stale_version")]
        self.assertEqual(indexing.process(self.fake.client())["done"], 1)
        self.assertIn("stale_version", IndexRequest.objects.get().last_error)

    def test_an_unreachable_service_stops_the_run_without_using_up_attempts(self):
        self.publish()
        self.publish(self.other_lesson)
        self.fake.script = [httpx.ConnectError("connection refused")]
        outcomes = indexing.process(self.fake.client())
        self.assertEqual((outcomes["retry"], outcomes["stopped"]), (1, 1))
        self.assertEqual(sorted(IndexRequest.objects.values_list("attempts", flat=True)), [0, 1])

    def test_timeouts_are_retryable(self):
        self.publish()
        self.fake.script = [httpx.ReadTimeout("slow")]
        self.assertEqual(indexing.process(self.fake.client())["retry"], 1)
        self.assertIn("timeout", self.pending().last_error)

    def test_a_change_while_sending_keeps_the_request_pending(self):
        self.publish()

        def publish_again_meanwhile(call):
            indexing.enqueue(self.lesson.pk, IndexRequest.Reason.PUBLISHED)
            return None  # then answer normally

        self.fake.script = [publish_again_meanwhile]
        self.assertEqual(indexing.process(self.fake.client(), limit=1)["requeued"], 1)
        request = self.pending()
        self.assertEqual(request.generation, 1)
        self.assertLessEqual(request.next_attempt_at, timezone.now())  # due again straight away

    def test_a_failure_while_the_lesson_changes_is_also_requeued(self):
        self.publish()

        def change_then_fail(call):
            indexing.enqueue(self.lesson.pk, IndexRequest.Reason.PUBLISHED)
            return error(503, "provider_unavailable")

        self.fake.script = [change_then_fail]
        self.assertEqual(indexing.process(self.fake.client(), limit=1)["requeued"], 1)
        self.assertEqual(self.pending().attempts, 0)

    def test_a_claimed_request_is_leased(self):
        self.publish()
        claimed = indexing._claim(set(), include_waiting=False, lesson_id=None)
        self.assertGreater(claimed.next_attempt_at, timezone.now() + timedelta(minutes=4))
        self.assertIsNone(indexing._claim(set(), include_waiting=False, lesson_id=None))

    def test_limit_and_lesson_filter(self):
        self.publish()
        self.publish(self.other_lesson)
        self.assertEqual(indexing.process(self.fake.client(), lesson_id=self.other_lesson.pk)["done"], 1)
        self.assertEqual(self.fake.calls[0].path, f"/v1/lessons/{self.other_lesson.pk}/index")
        self.assertEqual(indexing.process(self.fake.client(), limit=1)["done"], 1)

    def test_backoff_doubles_up_to_an_hour(self):
        self.assertEqual(
            [indexing.backoff(n).total_seconds() for n in (1, 2, 3, 7, 8, 20)], [30, 60, 120, 1920, 3600, 3600]
        )


class ReconcileTests(Fixtures):
    def setUp(self):
        super().setUp()
        self.v_lesson = self.publish()
        self.v_other = self.publish(self.other_lesson)
        IndexRequest.objects.all().delete()  # start from "everything was sent"

    def test_in_step_lessons_are_left_alone(self):
        self.fake.indexed = {
            str(self.lesson.pk): (str(self.v_lesson.pk), self.fake.model),
            str(self.other_lesson.pk): (str(self.v_other.pk), self.fake.model),
        }
        summary = indexing.reconcile(self.fake.client())
        self.assertEqual(summary, {"published": 2, "indexed": 2, "queued": 0, "already_queued": 0, "skipped": 0})
        self.assertFalse(IndexRequest.objects.exists())

    def test_missing_outdated_other_model_and_orphaned_lessons_are_queued(self):
        orphan = uuid.uuid4()
        self.fake.indexed = {
            str(self.lesson.pk): (str(uuid.uuid4()), self.fake.model),  # an older version
            str(self.other_lesson.pk): (str(self.v_other.pk), "old-embedding-model"),
            str(orphan): (str(uuid.uuid4()), self.fake.model),  # no longer published
        }
        summary = indexing.reconcile(self.fake.client())
        self.assertEqual(summary["queued"], 3)
        self.assertEqual(
            set(IndexRequest.objects.values_list("lesson_id", "reason")),
            {(self.lesson.pk, "reconcile"), (self.other_lesson.pk, "reconcile"), (orphan, "reconcile")},
        )
        indexing.process(self.fake.client())
        self.assertEqual(
            {(c.method, c.path.split("/")[3]) for c in self.fake.calls if c.method != "GET"},
            {("PUT", str(self.lesson.pk)), ("PUT", str(self.other_lesson.pk)), ("DELETE", str(orphan))},
        )
        self.assertNotIn(str(orphan), self.fake.indexed)

    def test_a_version_the_ai_service_refused_is_not_queued_again(self):
        IndexRequest.objects.create(
            lesson_id=self.lesson.pk,
            reason="published",
            status="failed",
            retryable=False,
            action="index",
            target_version_id=self.v_lesson.pk,
        )
        summary = indexing.reconcile(self.fake.client())
        self.assertEqual((summary["queued"], summary["skipped"]), (1, 1))  # only the other lesson

    def test_lessons_already_queued_keep_their_backoff(self):
        waiting = indexing.enqueue(self.lesson.pk, IndexRequest.Reason.PUBLISHED)
        IndexRequest.objects.filter(pk=waiting.pk).update(next_attempt_at=timezone.now() + timedelta(minutes=10))
        summary = indexing.reconcile(self.fake.client())
        self.assertEqual((summary["queued"], summary["already_queued"]), (1, 1))
        waiting.refresh_from_db()
        self.assertEqual(waiting.generation, 0)
        self.assertGreater(waiting.next_attempt_at, timezone.now())

    def test_a_malformed_status_is_an_error(self):
        for body in ({"lessons": []}, {"embedding_model": "m", "lessons": [{"lesson_id": "not-a-uuid"}]}):
            self.fake.script = [httpx.Response(200, json=body)]
            with self.assertRaises(AIServiceError) as ctx:
                indexing.reconcile(self.fake.client())
            self.assertEqual(ctx.exception.code, "bad_response")


class ClientTests(TestCase):
    def client_with(self, response):
        return AIServiceClient("http://ai.test/", TOKEN, timeout=5, transport=httpx.MockTransport(lambda r: response))

    def test_error_shapes_and_retryability(self):
        cases = [
            (error(400, "validation_error"), "validation_error", False),
            (error(401, "not_authenticated"), "not_authenticated", True),  # token rotation in progress
            (error(404, "not_found"), "not_found", False),
            (error(429, "rate_limited"), "rate_limited", True),
            (httpx.Response(502, text="<html>Bad gateway</html>"), "http_502", True),
            (httpx.Response(418, json=["not", "our", "shape"]), "http_418", False),
        ]
        for response, code, retryable in cases:
            with self.subTest(code=code), self.assertRaises(AIServiceError) as ctx:
                self.client_with(response).whoami()
            self.assertEqual((ctx.exception.code, ctx.exception.retryable), (code, retryable))
            self.assertEqual(ctx.exception.status, response.status_code)
            self.assertIn(str(response.status_code), str(ctx.exception))

    def test_unusable_success_bodies(self):
        for response in (httpx.Response(200, text="not json"), httpx.Response(200, json=[1, 2])):
            with self.subTest(body=response.text), self.assertRaises(AIServiceError) as ctx:
                self.client_with(response).index_status()
            self.assertEqual(ctx.exception.code, "bad_response")

    def test_network_errors(self):
        for exc, code in ((httpx.ConnectError("refused"), "unreachable"), (httpx.ConnectTimeout("slow"), "timeout")):

            def raise_it(request, exc=exc):
                raise exc

            client = AIServiceClient("http://ai.test", TOKEN, timeout=5, transport=httpx.MockTransport(raise_it))
            with self.subTest(code=code), self.assertRaises(AIServiceError) as ctx:
                client.whoami()
            self.assertEqual((ctx.exception.code, ctx.exception.retryable, ctx.exception.status), (code, True, None))

    def test_whoami_and_the_token_never_appears_in_errors(self):
        self.assertEqual(
            self.client_with(httpx.Response(200, json={"service": "tutor-ai"})).whoami()["service"], "tutor-ai"
        )
        with self.assertRaises(AIServiceError) as ctx:
            self.client_with(error(503, "provider_unavailable")).whoami()
        self.assertNotIn(TOKEN, str(ctx.exception))

    @override_settings(TUTOR_AI_URL="", TUTOR_AI_SERVICE_TOKEN=TOKEN)
    def test_not_configured_without_a_url(self):
        self.assertFalse(is_configured())
        with self.assertRaises(AIServiceNotConfigured):
            get_client()

    @override_settings(TUTOR_AI_URL="http://ai.test", TUTOR_AI_SERVICE_TOKEN="short")
    def test_not_configured_with_a_weak_token(self):
        self.assertFalse(is_configured())

    @override_settings(**AI_ON)
    def test_configured(self):
        self.assertTrue(is_configured())
        with get_client() as client:
            self.assertIsInstance(client, AIServiceClient)

    def test_system_check(self):
        with override_settings(TUTOR_AI_URL="", TUTOR_AI_SERVICE_TOKEN=""):
            self.assertEqual(check_ai_settings(), [])
        with override_settings(TUTOR_AI_URL="http://ai.test", TUTOR_AI_SERVICE_TOKEN="short"):
            self.assertEqual([e.id for e in check_ai_settings()], ["aiservice.E001"])
        with override_settings(TUTOR_AI_URL="ai.test", TUTOR_AI_SERVICE_TOKEN=TOKEN):
            self.assertEqual([e.id for e in check_ai_settings()], ["aiservice.E002"])
        with override_settings(**AI_ON):
            self.assertEqual(check_ai_settings(), [])


class CommandTests(Fixtures):
    def run_command(self, *args):
        out, err = StringIO(), StringIO()
        call_command("sync_ai_index", *args, stdout=out, stderr=err)
        return out.getvalue(), err.getvalue()

    def test_without_an_ai_service_it_reports_the_queue(self):
        self.publish()
        out, _ = self.run_command()
        self.assertIn("No AI service configured", out)
        self.assertIn("1 request(s) queued", out)
        with self.assertRaises(CommandError):
            self.run_command("--strict")

    def test_limit_must_be_positive(self):
        with self.assertRaises(CommandError):
            self.run_command("--limit", "0")

    @override_settings(**AI_ON)
    def test_reconciles_then_sends(self):
        self.publish()
        with mock.patch(f"{COMMAND}.get_client", return_value=self.fake.client()):
            out, err = self.run_command()
        self.assertIn("Reconciled: 1 published, 0 indexed, 0 queued, 1 already queued, 0 skipped", out)
        self.assertIn("Sent: 1 done.", out)
        self.assertEqual(err, "")
        self.assertEqual([c.method for c in self.fake.calls], ["GET", "PUT"])

    @override_settings(**AI_ON)
    def test_nothing_due(self):
        with mock.patch(f"{COMMAND}.get_client", return_value=self.fake.client()):
            out, _ = self.run_command("--no-reconcile")
        self.assertIn("Sent: nothing due.", out)
        self.assertEqual(self.fake.calls, [])

    @override_settings(**AI_ON)
    def test_an_unreachable_service_is_a_warning_unless_strict(self):
        self.fake.script = [httpx.ConnectError("refused")]
        with mock.patch(f"{COMMAND}.get_client", return_value=self.fake.client()):
            _, err = self.run_command()
        self.assertIn("AI service unavailable", err)
        self.fake.script = [httpx.ConnectError("refused")]
        with mock.patch(f"{COMMAND}.get_client", return_value=self.fake.client()), self.assertRaises(CommandError):
            self.run_command("--strict")

    @override_settings(**AI_ON)
    def test_stopping_early_and_permanent_failures_are_reported(self):
        self.publish()
        self.publish(self.other_lesson)
        self.fake.script = [error(400, "empty_lesson"), httpx.ConnectError("refused")]
        with mock.patch(f"{COMMAND}.get_client", return_value=self.fake.client()):
            out, err = self.run_command("--no-reconcile")
        self.assertIn("1 retry, 1 failed", out)
        self.assertIn("Stopped early", err)
        self.assertIn("failed for good", err)
        self.fake.script = [httpx.ConnectError("refused")]
        with mock.patch(f"{COMMAND}.get_client", return_value=self.fake.client()), self.assertRaises(CommandError):
            self.run_command("--no-reconcile", "--all", "--strict")


class AdminTests(Fixtures):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.lead)

    def test_list_is_read_only_with_a_queue_again_action(self):
        self.publish()
        request = self.pending()
        IndexRequest.objects.filter(pk=request.pk).update(status="failed", retryable=False)
        changelist = reverse("admin:aiservice_indexrequest_changelist")
        self.assertEqual(self.client.get(changelist).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin:aiservice_indexrequest_add")).status_code, 403)
        self.assertEqual(
            self.client.get(reverse("admin:aiservice_indexrequest_change", args=[request.pk])).status_code, 200
        )
        response = self.client.post(
            changelist, {"action": "queue_again", "_selected_action": [request.pk]}, follow=True
        )
        self.assertContains(response, "Queued 1 lesson(s)")
        self.assertEqual(self.pending().reason, "manual")
