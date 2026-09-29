"""Exception handling, request IDs, rotating logs and secret-safe messaging."""

import logging
import logging.config
import tempfile
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.http import Http404
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings

from apps.core import messaging
from apps.core.errors import json_404, json_500
from apps.core.logging import BACKUPS, MAX_BYTES, RequestIDFilter, build_logging
from apps.core.request_context import new_request_id


class RequestIdTests(SimpleTestCase):
    def test_generated_and_returned(self):
        response = self.client.get("/")
        self.assertRegex(response["X-Request-ID"], r"^[0-9a-f]{32}$")

    def test_well_formed_incoming_id_is_kept(self):
        response = self.client.get("/", HTTP_X_REQUEST_ID="render-abc-12345")
        self.assertEqual(response["X-Request-ID"], "render-abc-12345")

    def test_malformed_incoming_id_is_replaced(self):
        for bad in ("short", "has spaces in it!!", "x" * 65, "line\nbreak-injection"):
            with self.subTest(bad=bad):
                self.assertNotEqual(new_request_id(bad), bad)


class ApiErrorShapeTests(TestCase):
    def facets_raising(self, exc):
        stages = mock.Mock()
        stages.items.side_effect = exc
        return mock.patch("apps.catalogue.api.PATH_STAGES", stages)

    def test_error_body_carries_the_request_id(self):
        response = self.client.get("/api/v1/courses/does-not-exist")
        body = response.json()["error"]
        self.assertEqual(body["code"], "not_found")
        self.assertEqual(body["request_id"], response["X-Request-ID"])

    def test_unexpected_exception_is_a_clean_500_and_logged_once_with_traceback(self):
        with (
            self.facets_raising(RuntimeError("secret internal detail")),
            self.assertLogs("tutor.api", "ERROR") as logs,
            self.assertLogs("django.request", "ERROR"),  # Django's own 5xx line; captured so test output stays clean
        ):
            response = self.client.get("/api/v1/catalogue/facets")
        self.assertEqual(response.status_code, 500)
        body = response.json()["error"]
        self.assertEqual(body["code"], "server_error")
        self.assertNotIn("secret internal detail", response.content.decode())
        self.assertEqual(len(logs.records), 1)
        record = logs.records[0]
        self.assertIsNotNone(record.exc_info)  # traceback kept for developers
        self.assertIn("GET /api/v1/catalogue/facets", record.getMessage())

    def test_request_id_filter_stamps_records(self):
        record = logging.LogRecord("x", logging.INFO, __file__, 1, "msg", None, None)
        self.assertTrue(RequestIDFilter().filter(record))
        self.assertEqual(record.request_id, "-")  # no request in progress

    def test_django_request_records_get_the_id_from_the_request(self):
        request = RequestFactory().get("/")
        request.request_id = "req-1234567890"
        record = logging.LogRecord("django.request", logging.ERROR, __file__, 1, "msg", None, None)
        record.request = request
        RequestIDFilter().filter(record)
        self.assertEqual(record.request_id, "req-1234567890")

    def test_http404_raised_in_code_uses_the_api_shape(self):
        with self.facets_raising(Http404("gone")):
            response = self.client.get("/api/v1/catalogue/facets")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "not_found")

    def test_unknown_api_url_is_json_404(self):
        response = self.client.get("/api/v1/no-such-endpoint")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "not_found")

    def test_django_level_handlers(self):
        rf = RequestFactory()
        self.assertEqual(json_500(rf.get("/api/v1/x")).status_code, 500)
        self.assertIn(b"server_error", json_500(rf.get("/api/v1/x")).content)
        self.assertEqual(json_404(rf.get("/api/v1/x")).status_code, 404)
        self.assertNotIn(b"not_found", json_404(rf.get("/elsewhere")).content)  # HTML page outside the API


class RotatingLogTests(SimpleTestCase):
    def tearDown(self):
        logging.config.dictConfig(settings.LOGGING)  # restore the test configuration

    def test_console_only_without_a_log_dir(self):
        config = build_logging("INFO", "")
        self.assertEqual(set(config["handlers"]), {"console"})

    def test_rotating_files_when_a_log_dir_is_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = build_logging("INFO", tmp)
            config["handlers"]["console"]["level"] = "CRITICAL"  # keep the test run's output clean
            for name in ("file", "errors"):
                handler = config["handlers"][name]
                self.assertEqual(handler["class"], "logging.handlers.RotatingFileHandler")
                self.assertEqual((handler["maxBytes"], handler["backupCount"]), (MAX_BYTES, BACKUPS))
            logging.config.dictConfig(config)
            logging.getLogger("tutor.test").info("an info line")
            logging.getLogger("tutor.test").error("an error line")
            for handler in logging.getLogger().handlers:
                handler.flush()
            info = (Path(tmp) / "tutor.log").read_text()
            errors = (Path(tmp) / "errors.log").read_text()
            self.assertIn("an info line", info)
            self.assertIn("an error line", errors)
            self.assertNotIn("an info line", errors)
            self.assertIn("[-]", info)  # request ID column present
            logging.config.dictConfig(build_logging("INFO", ""))  # close the files before the directory goes


class MessagingSecretsTests(SimpleTestCase):
    def setUp(self):
        messaging.OUTBOX.clear()
        self.addCleanup(messaging.OUTBOX.clear)

    def test_mask(self):
        self.assertEqual(messaging.mask("+919812345678"), "+91******5678")
        self.assertEqual(messaging.mask("asha@test.tutor"), "a***@test.tutor")

    @override_settings(TUTOR_KEEP_MESSAGES=False)
    def test_hosted_mode_never_logs_or_keeps_the_text(self):
        with self.assertLogs("tutor.messaging", "INFO") as logs:
            messaging.send("sms", "+919812345678", "Your code is 123456")
        self.assertEqual(list(messaging.OUTBOX), [])
        line = logs.output[0]
        self.assertNotIn("123456", line)
        self.assertNotIn("9812345678", line)
        self.assertIn("+91******5678", line)

    def test_outbox_is_bounded(self):
        for n in range(messaging.OUTBOX.maxlen + 10):
            messaging.send("sms", "+919000000001", f"message {n}")
        self.assertEqual(len(messaging.OUTBOX), messaging.OUTBOX.maxlen)


class OpenApiContractTests(SimpleTestCase):
    def test_export_and_check(self):
        from io import StringIO

        from django.core.management import call_command
        from django.core.management.base import CommandError

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "openapi.json"
            with self.assertRaises(CommandError):
                call_command("export_openapi", "--check", "--path", str(path), stdout=StringIO())
            call_command("export_openapi", "--path", str(path), stdout=StringIO())
            self.assertIn('"openapi"', path.read_text())
            call_command("export_openapi", "--check", "--path", str(path), stdout=StringIO())  # now up to date
            path.write_text(path.read_text().replace('"TUTOR API"', '"Changed"'))
            with self.assertRaises(CommandError):
                call_command("export_openapi", "--check", "--path", str(path), stdout=StringIO())
