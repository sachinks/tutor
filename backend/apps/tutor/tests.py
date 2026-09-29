"""The student AI tutor: access rules, daily limit, what is sent to the AI service, the SSE relay, storage, safety
flags and helplines, retention, the admin safety queue.

A FakeAI plays the AI service through httpx.MockTransport, so the tests see exactly what Django sends and control
exactly what comes back.
"""

import json
import uuid
from datetime import timedelta
from io import StringIO
from unittest import mock

import httpx
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import StudentProfile, User
from apps.aiservice.client import AIServiceClient
from apps.assessment import services as assessment_services
from apps.catalogue.models import Board, ClassLevel, Course, Lesson, Module
from apps.commerce.models import Entitlement
from apps.content import services as content_services

from . import services
from .models import SafetyFlag, TutorConversation, TutorMessage, UsageCounter

TOKEN = "s" * 40
AI_ON = {"TUTOR_AI_URL": "http://ai.test", "TUTOR_AI_SERVICE_TOKEN": TOKEN}
BASE = "/api/v1/tutor"


def sse(*events):
    return "".join(f"event: {name}\ndata: {json.dumps(data)}\n\n" for name, data in events)


def final(text="(Demo tutor) Leaves make glucose [P1].", **overrides):
    value = {
        "text": text,
        "message": "What do leaves make?",
        "blocked": False,
        "replaced": False,
        "off_topic": False,
        "citations": [{"label": "P1", "chunk_id": str(uuid.uuid4()), "heading": "What leaves make"}],
        "safety": {"input": {}, "output": {}, "personal_data": [], "grounding": 0.6},
        "flags": [],
        "context": {"pinned_chunk_ids": ["c1", "c2"]},
        "usage": {"prompt_tokens_estimate": 420, "reply_tokens_estimate": 12},
        "latency_ms": 850,
        "model": "mock-tutor-v1",
        "prompt_version": "tutor/v1",
        "safety_version": "safety/v1",
        "mode": "explain",
    }
    value.update(overrides)
    return value


class FakeAI:
    def __init__(self):
        self.requests = []
        self.events = [
            ("meta", {"mode": "explain", "model": "mock-tutor-v1"}),
            ("delta", {"text": "(Demo tutor) "}),
            ("delta", {"text": "Leaves make glucose [P1]."}),
            ("final", final()),
        ]
        self.raise_exc = None
        self.status = 200

    def handler(self, request):
        self.requests.append(json.loads(request.content))
        if self.raise_exc is not None:
            raise self.raise_exc
        if self.status != 200:
            return httpx.Response(self.status, json={"error": {"code": "validation_error", "message": "bad"}})
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=sse(*self.events).encode())

    def client(self):
        return AIServiceClient("http://ai.test", TOKEN, timeout=5, transport=httpx.MockTransport(self.handler))


def parse(response):
    body = b"".join(response.streaming_content).decode()
    events = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.split("\n"))
        events.append((lines["event"], json.loads(lines["data"])))
    return events


@override_settings(**AI_ON)
class TutorBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo_catalogue", verbosity=0)
        cls.course = Course.objects.get(slug="ai-foundations")
        cls.lesson = Lesson.objects.get(slug="what-is-data")
        cls.version = content_services.published_version(cls.lesson)
        cls.student = cls.make_student("kid@example.com")
        Entitlement.objects.create(student=cls.student, product_type="course", product_id=cls.course.id)

    @classmethod
    def make_student(cls, email, status="active"):
        user = User.objects.create_user(email=email, password="Kid-pass-2026", full_name="Kid Learner")
        StudentProfile.objects.create(
            user=user,
            class_level=ClassLevel.objects.get(number=8),
            board=Board.objects.get(code="CBSE"),
            city="Kolkata",
            status=status,
        )
        return user

    def setUp(self):
        self.fake = FakeAI()
        patcher = mock.patch("apps.tutor.services.get_client", side_effect=lambda: self.fake.client())
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client.force_login(self.student)

    def start(self, **payload):
        return self.client.post(
            f"{BASE}/conversations", {"lesson_id": str(self.lesson.id), **payload}, content_type="application/json"
        )

    def conversation(self):
        return TutorConversation.objects.create(
            student=self.student, lesson=self.lesson, content_version_id=self.version.pk
        )

    def send(self, conversation, message="What do leaves make?", **payload):
        return self.client.post(
            f"{BASE}/conversations/{conversation.pk}/messages",
            {"message": message, **payload},
            content_type="application/json",
        )


class AccessTests(TutorBase):
    def test_an_enrolled_student_starts_a_chat(self):
        response = self.start(mode="socratic")
        self.assertEqual(response.status_code, 201, response.content)
        data = response.json()
        self.assertEqual((data["lesson_title"], data["mode"], data["messages"]), ("What is data?", "socratic", []))
        self.assertEqual(data["usage"], {"used": 0, "limit": 50, "left": 50})
        conversation = TutorConversation.objects.get(pk=data["id"])
        self.assertEqual(conversation.content_version_id, self.version.pk)

    def test_the_free_module_does_not_include_the_tutor(self):
        free_only = self.make_student("free@example.com")
        self.client.force_login(free_only)
        response = self.start()
        self.assertEqual((response.status_code, response.json()["error"]["code"]), (403, "not_entitled"))

    def test_consent_and_role_are_required(self):
        waiting = self.make_student("waiting@example.com", status="awaiting_consent")
        Entitlement.objects.create(student=waiting, product_type="course", product_id=self.course.id)
        self.client.force_login(waiting)
        self.assertEqual(self.start().json()["error"]["code"], "consent_required")
        parent = User.objects.create_user(email="parent@example.com", password="Parent-pass-2026", full_name="P")
        self.client.force_login(parent)
        self.assertEqual(self.start().status_code, 403)
        self.client.logout()
        self.assertEqual(self.start().status_code, 401)

    def test_unknown_lesson_unpublished_lesson_and_no_ai_service(self):
        response = self.client.post(
            f"{BASE}/conversations", {"lesson_id": str(uuid.uuid4())}, content_type="application/json"
        )
        self.assertEqual(response.status_code, 404)
        module = Module.objects.create(course=self.course, title="Later", position=9)
        empty = Lesson.objects.create(module=module, title="Coming soon", slug="soon", position=1)
        response = self.client.post(
            f"{BASE}/conversations", {"lesson_id": str(empty.id)}, content_type="application/json"
        )
        self.assertEqual((response.status_code, response.json()["error"]["code"]), (409, "lesson_not_ready"))
        with override_settings(TUTOR_AI_URL=""):
            response = self.start()
        self.assertEqual((response.status_code, response.json()["error"]["code"]), (503, "feature_unavailable"))

    def test_students_only_see_their_own_chats(self):
        mine = self.conversation()
        other = self.make_student("other@example.com")
        theirs = TutorConversation.objects.create(student=other, lesson=self.lesson, content_version_id=self.version.pk)
        listed = self.client.get(f"{BASE}/conversations").json()
        self.assertEqual([c["id"] for c in listed], [str(mine.pk)])
        self.assertEqual(self.client.get(f"{BASE}/conversations?lesson_id={uuid.uuid4()}").json(), [])
        self.assertEqual(self.client.get(f"{BASE}/conversations/{theirs.pk}").status_code, 404)
        self.assertEqual(self.send(theirs).status_code, 404)
        self.assertEqual(self.client.delete(f"{BASE}/conversations/{theirs.pk}").status_code, 404)

    def test_deleting_a_chat_and_keeping_a_flagged_one_for_review(self):
        plain, flagged = self.conversation(), self.conversation()
        flagged.flagged = True
        flagged.save()
        self.assertEqual(self.client.delete(f"{BASE}/conversations/{plain.pk}").status_code, 204)
        self.assertEqual(self.client.delete(f"{BASE}/conversations/{flagged.pk}").status_code, 204)
        self.assertFalse(TutorConversation.objects.filter(pk=plain.pk).exists())
        flagged.refresh_from_db()
        self.assertTrue(flagged.hidden_by_student)
        self.assertEqual(self.client.get(f"{BASE}/conversations/{flagged.pk}").status_code, 404)

    def test_the_learner_ref_is_stable_and_not_the_user_id(self):
        ref = services.learner_ref(self.student)
        self.assertRegex(ref, r"^lr_[0-9a-f]{40}$")
        self.assertEqual(ref, services.learner_ref(self.student))
        self.assertNotIn(str(self.student.pk), ref)
        self.assertNotEqual(ref, services.learner_ref(self.make_student("twin@example.com")))


class TurnTests(TutorBase):
    def test_a_turn_streams_and_stores_only_the_final_answer(self):
        conversation = self.conversation()
        response = self.send(conversation)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/event-stream")
        self.assertEqual(response["Cache-Control"], "no-cache")
        events = parse(response)
        self.assertEqual([name for name, _ in events], ["meta", "delta", "delta", "final"])
        self.assertEqual(events[0][1], {"mode": "explain", "conversation_id": str(conversation.pk)})
        answer = events[-1][1]
        self.assertEqual(answer["text"], "(Demo tutor) Leaves make glucose [P1].")
        self.assertEqual(answer["citations"], [{"label": "P1", "heading": "What leaves make"}])
        self.assertEqual((answer["helplines"], answer["blocked"], answer["personal_data_hidden"]), ([], False, False))

        student, tutor = conversation.messages.all()
        self.assertEqual((student.role, student.text), ("student", "What do leaves make?"))
        self.assertEqual(
            (tutor.role, tutor.text, tutor.model, tutor.prompt_version),
            ("tutor", answer["text"], "mock-tutor-v1", "tutor/v1"),
        )
        self.assertEqual((tutor.latency_ms, tutor.prompt_tokens, tutor.reply_tokens), (850, 420, 12))
        self.assertEqual(answer["message_id"], tutor.pk)
        conversation.refresh_from_db()
        self.assertEqual(conversation.pinned_chunk_ids, ["c1", "c2"])
        self.assertEqual(UsageCounter.objects.get(student=self.student).messages, 1)

    def test_what_is_sent_to_the_ai_service(self):
        conversation = self.conversation()
        parse(self.send(conversation, mode="hint"))
        [sent] = self.fake.requests
        self.assertEqual(sent["learner_ref"], services.learner_ref(self.student))
        self.assertNotIn("kid@example.com", json.dumps(sent))
        self.assertEqual(sent["chat_id"], str(conversation.pk))
        self.assertEqual(
            sent["lesson"],
            {
                "id": str(self.lesson.id),
                "version_id": str(self.version.pk),
                "course_id": str(self.course.id),
                "title": "What is data?",
            },
        )
        self.assertIsNone(sent["class_number"])  # AI Foundations is board-independent
        self.assertEqual(
            (sent["mode"], sent["message"], sent["history"], sent["pinned_chunk_ids"]),
            ("hint", "What do leaves make?", [], []),
        )
        self.assertEqual(sent["guard"], {"open_quiz": False, "protected_answers": []})
        self.assertEqual(sent["limits"], {"max_reply_tokens": 250})

    def test_later_turns_send_history_and_pinned_passages_but_not_blocked_turns(self):
        conversation = self.conversation()
        parse(self.send(conversation))
        blocked = final(text="I'm really sorry…", message="I want to die", blocked=True)
        self.fake.events = [("meta", {}), ("final", blocked)]
        parse(self.send(conversation, "I want to die"))
        self.fake.events = [("meta", {}), ("final", final())]
        parse(self.send(conversation, "And roots?"))
        third = self.fake.requests[2]
        self.assertEqual(
            third["history"],
            [
                {"role": "student", "text": "What do leaves make?"},
                {"role": "tutor", "text": "(Demo tutor) Leaves make glucose [P1]."},
            ],
        )
        self.assertEqual(third["pinned_chunk_ids"], ["c1", "c2"])

    def test_an_open_quiz_protects_the_unanswered_correct_options(self):
        attempt = assessment_services.start_lesson_quiz(self.student, self.lesson)
        items = list(attempt.items.select_related("question_version"))
        first = items[0].question_version.body
        assessment_services.answer_item(self.student, attempt.id, items[0].position, first["answer_index"])
        conversation = self.conversation()
        parse(self.send(conversation))
        guard = self.fake.requests[0]["guard"]
        expected = [i.question_version.body["options"][i.question_version.body["answer_index"]] for i in items[1:]]
        self.assertEqual(guard, {"open_quiz": True, "protected_answers": expected})
        attempt.submitted_at = timezone.now()
        attempt.save()
        parse(self.send(conversation))
        self.assertFalse(self.fake.requests[1]["guard"]["open_quiz"])

    def test_the_daily_limit(self):
        conversation = self.conversation()
        UsageCounter.objects.create(student=self.student, day=timezone.localdate(), messages=50)
        response = self.send(conversation)
        self.assertEqual((response.status_code, response.json()["error"]["code"]), (429, "daily_limit_reached"))
        self.assertEqual(self.fake.requests, [])
        with override_settings(TUTOR_TUTOR_DAILY_LIMIT=51):
            self.assertEqual(self.send(conversation).status_code, 200)
        self.assertEqual(services.usage_today(self.student), {"used": 51, "limit": 50, "left": 0})
        yesterday = UsageCounter.objects.get(student=self.student)
        yesterday.day -= timedelta(days=1)
        yesterday.save()
        self.assertEqual(self.send(conversation).status_code, 200)  # a new IST day, a new allowance

    def test_invalid_messages_are_refused_before_anything_is_counted(self):
        conversation = self.conversation()
        for payload in ({"message": "x" * 501}, {"message": "   "}, {"message": "hi", "mode": "lecture"}):
            response = self.client.post(
                f"{BASE}/conversations/{conversation.pk}/messages", payload, content_type="application/json"
            )
            self.assertEqual(response.status_code, 400, payload)
        self.assertFalse(UsageCounter.objects.filter(messages__gt=0).exists())

    def test_losing_the_entitlement_or_the_ai_service_stops_sending(self):
        conversation = self.conversation()
        with override_settings(TUTOR_AI_URL=""):
            self.assertEqual(self.send(conversation).json()["error"]["code"], "feature_unavailable")
        Entitlement.objects.filter(student=self.student).update(revoked_at=timezone.now())
        self.assertEqual(self.send(conversation).json()["error"]["code"], "not_entitled")
        self.assertEqual(self.fake.requests, [])


class FailureTests(TutorBase):
    def assertFailedCleanly(self, events, code):
        self.assertEqual(events[-1][0], "error")
        self.assertEqual(events[-1][1]["code"], code)
        self.assertFalse(TutorMessage.objects.exists())
        self.assertEqual(UsageCounter.objects.get(student=self.student).messages, 0)  # given back

    def test_an_ai_error_event(self):
        self.fake.events = [("meta", {}), ("delta", {"text": "Part"}), ("error", {"code": "provider_unavailable"})]
        self.assertFailedCleanly(parse(self.send(self.conversation())), "tutor_unavailable")

    def test_lesson_not_indexed_and_timeouts_have_their_own_messages(self):
        self.fake.events = [("error", {"code": "lesson_not_indexed"})]
        self.assertFailedCleanly(parse(self.send(self.conversation())), "lesson_not_ready")
        self.fake.raise_exc = httpx.ReadTimeout("slow")
        self.assertFailedCleanly(parse(self.send(self.conversation())), "tutor_timeout")

    def test_an_unreachable_ai_service(self):
        self.fake.raise_exc = httpx.ConnectError("refused")
        self.assertFailedCleanly(parse(self.send(self.conversation())), "tutor_unavailable")

    def test_a_refused_request(self):
        self.fake.status = 400
        self.assertFailedCleanly(parse(self.send(self.conversation())), "tutor_unavailable")

    def test_a_stream_that_ends_without_an_answer(self):
        self.fake.events = [("meta", {}), ("delta", {"text": "Half an ans"})]
        self.assertFailedCleanly(parse(self.send(self.conversation())), "tutor_unavailable")

    def test_a_crash_while_storing_is_an_error_event(self):
        with (
            mock.patch("apps.tutor.services.record_final", side_effect=RuntimeError("boom")),
            self.assertLogs("tutor.tutor", "ERROR"),
        ):
            events = parse(self.send(self.conversation()))
        self.assertEqual(
            events[-1], ("error", {"code": "server_error", "message": "Something went wrong on our side."})
        )
        self.assertEqual(UsageCounter.objects.get(student=self.student).messages, 0)

    def test_invalid_event_data(self):
        self.fake.events = []
        self.fake.handler = lambda request: httpx.Response(200, content=b"event: meta\ndata: {not json\n\n")
        self.assertFailedCleanly(parse(self.send(self.conversation())), "tutor_unavailable")


class SafetyTests(TutorBase):
    def flagged_turn(self, *flags, **overrides):
        self.fake.events = [("meta", {}), ("final", final(flags=list(flags), **overrides))]
        conversation = self.conversation()
        return conversation, parse(self.send(conversation))[-1][1]

    def test_a_critical_message_shows_helplines_alerts_operations_and_is_parent_visible(self):
        flag = {"stage": "input", "category": "self_harm", "severity": "critical", "flagged": True}
        with self.assertLogs("tutor.tutor", "ERROR") as logs:
            conversation, answer = self.flagged_turn(
                flag, blocked=True, text="I'm really sorry…", message="I want to die"
            )
        self.assertIn("tutor safety alert", logs.output[0])
        self.assertTrue(answer["blocked"])
        self.assertEqual([h["phone"] for h in answer["helplines"]], ["14416", "112", "1098"])
        saved = SafetyFlag.objects.get()
        self.assertEqual(
            (saved.severity, saved.category, saved.status, saved.parent_visible),
            ("critical", "self_harm", "open", True),
        )
        self.assertEqual(saved.message.role, "student")
        conversation.refresh_from_db()
        self.assertTrue(conversation.flagged)
        self.assertTrue(all(m.blocked for m in conversation.messages.all()))

    def test_high_severity_output_shows_the_child_helpline(self):
        flag = {"stage": "output", "category": "violence", "severity": "high", "flagged": True}
        _, answer = self.flagged_turn(flag, replaced=True)
        self.assertEqual([h["phone"] for h in answer["helplines"]], ["1098"])
        self.assertEqual(SafetyFlag.objects.get().message.role, "tutor")

    def test_personal_data_is_flagged_but_not_shown_to_parents_and_never_stored(self):
        flag = {"stage": "input", "category": "personal_data", "severity": "medium", "flagged": True}
        _, answer = self.flagged_turn(flag, message="my phone is [phone hidden]", safety={"personal_data": ["phone"]})
        self.assertTrue(answer["personal_data_hidden"] and answer["helplines"] == [])
        self.assertFalse(SafetyFlag.objects.get().parent_visible)
        self.assertEqual(TutorMessage.objects.get(role="student").text, "my phone is [phone hidden]")

    def test_low_notes_and_unknown_severities_are_not_flags(self):
        self.flagged_turn(
            {"stage": "output", "category": "ungrounded", "severity": "low", "flagged": False},
            {"stage": "output", "category": "odd", "severity": "extreme", "flagged": True},
        )
        self.assertFalse(SafetyFlag.objects.exists())

    def test_the_helplines_file_is_marked_draft_and_well_formed(self):
        data = json.loads(services.HELPLINES_FILE.read_text(encoding="utf-8"))
        self.assertIn("DRAFT", data["_about"])
        for entry in services.helplines()["critical"] + services.helplines()["high"]:
            self.assertTrue(entry["name"] and entry["phone"].isdigit())


class RetentionTests(TutorBase):
    def aged(self, days, *flag_states):
        conversation = self.conversation()
        TutorConversation.objects.filter(pk=conversation.pk).update(
            last_message_at=timezone.now() - timedelta(days=days)
        )
        for status, closed_days_ago in flag_states:
            SafetyFlag.objects.create(
                conversation=conversation,
                stage="input",
                category="self_harm",
                severity="critical",
                status=status,
                closed_at=timezone.now() - timedelta(days=closed_days_ago) if closed_days_ago is not None else None,
            )
        return conversation

    def test_old_chats_are_deleted_unless_a_flag_still_needs_them(self):
        recent = self.aged(10)
        old = self.aged(91)
        open_flag = self.aged(200, ("open", None))
        reviewed = self.aged(200, ("reviewed", None))
        closed_recently = self.aged(200, ("closed", 30))
        closed_long_ago = self.aged(200, ("closed", 120))
        out = StringIO()
        call_command("purge_tutor_chats", "--dry-run", stdout=out)
        self.assertIn("2 tutor chat(s) would be deleted", out.getvalue())
        self.assertEqual(TutorConversation.objects.count(), 6)
        call_command("purge_tutor_chats", stdout=StringIO())
        self.assertEqual(
            set(TutorConversation.objects.values_list("pk", flat=True)),
            {recent.pk, open_flag.pk, reviewed.pk, closed_recently.pk},
        )
        self.assertFalse(TutorConversation.objects.filter(pk__in=[old.pk, closed_long_ago.pk]).exists())

    def test_deleting_the_student_deletes_their_chats(self):
        conversation = self.conversation()
        TutorMessage.objects.create(conversation=conversation, role="student", text="hi")
        self.student.delete()
        self.assertFalse(TutorConversation.objects.exists() or TutorMessage.objects.exists())


class AdminTests(TutorBase):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_superuser(email="ops@example.com", password="Ops-pass-2026", full_name="Ops")
        self.client.force_login(self.admin)
        self.chat = self.conversation()
        message = TutorMessage.objects.create(conversation=self.chat, role="student", text="they beat me")
        self.flag = SafetyFlag.objects.create(
            conversation=self.chat,
            message=message,
            stage="input",
            category="bullying",
            severity="high",
            parent_visible=True,
        )

    def test_the_safety_queue_actions_record_who_and_when(self):
        changelist = reverse("admin:tutor_safetyflag_changelist")
        self.assertEqual(self.client.get(changelist).status_code, 200)
        self.client.post(changelist, {"action": "mark_reviewed", "_selected_action": [self.flag.pk]})
        self.flag.refresh_from_db()
        self.assertEqual((self.flag.status, self.flag.reviewed_by), ("reviewed", self.admin))
        self.client.post(changelist, {"action": "close", "_selected_action": [self.flag.pk]})
        self.flag.refresh_from_db()
        self.assertEqual(self.flag.status, "closed")
        self.assertIsNotNone(self.flag.closed_at)

    def test_changing_the_status_in_the_form_stamps_it_too(self):
        url = reverse("admin:tutor_safetyflag_change", args=[self.flag.pk])
        page = self.client.get(url)
        self.assertContains(page, "they beat me")
        self.client.post(url, {"status": "closed", "note": "Spoke to the parent."})
        self.flag.refresh_from_db()
        self.assertEqual(
            (self.flag.status, self.flag.reviewed_by, self.flag.note), ("closed", self.admin, "Spoke to the parent.")
        )
        self.assertIsNotNone(self.flag.closed_at)
        self.client.post(url, {"status": "open", "note": "Reopened."})
        self.flag.refresh_from_db()
        self.assertIsNone(self.flag.closed_at)

    def test_chats_are_read_only_and_cannot_be_deleted_by_hand(self):
        self.assertEqual(
            self.client.get(reverse("admin:tutor_tutorconversation_change", args=[self.chat.pk])).status_code, 200
        )
        self.assertEqual(self.client.get(reverse("admin:tutor_tutorconversation_add")).status_code, 403)
        self.assertEqual(
            self.client.get(reverse("admin:tutor_tutorconversation_delete", args=[self.chat.pk])).status_code, 403
        )
        self.assertEqual(self.client.get(reverse("admin:tutor_safetyflag_add")).status_code, 403)
