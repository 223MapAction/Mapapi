import json
import logging
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.observability import (
    FILTERED,
    SafeJsonFormatter,
    build_traces_sampler,
    init_sentry,
    redact_data,
    redact_text,
)


class RedactionTests(unittest.TestCase):
    def test_redacts_identifiers_and_credentials_from_text(self):
        raw = (
            "email=agent@example.com phone=+223 76 12 34 56 "
            "Authorization: Bearer secret-token "
            "jwt=eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.signature "
            "url=https://example.test/ws?token=abc123\n"
            "Cookie: sessionid=private-session"
        )

        redacted = redact_text(raw)

        self.assertNotIn("agent@example.com", redacted)
        self.assertNotIn("76 12 34 56", redacted)
        self.assertNotIn("secret-token", redacted)
        self.assertNotIn("eyJhbGci", redacted)
        self.assertNotIn("abc123", redacted)
        self.assertNotIn("private-session", redacted)
        self.assertIn(FILTERED, redacted)

    def test_redacts_sensitive_keys_recursively(self):
        payload = {
            "request": {
                "headers": {"Authorization": "Bearer abc", "Content-Type": "application/json"},
                "data": {"password": "guess-me", "email": "person@example.com"},
            },
            "extra": {"nested": [{"refresh_token": "refresh-me"}]},
        }

        redacted = redact_data(payload)

        self.assertEqual(redacted["request"]["headers"]["Authorization"], FILTERED)
        self.assertEqual(redacted["request"]["data"]["password"], FILTERED)
        self.assertEqual(redacted["request"]["data"]["email"], FILTERED)
        self.assertEqual(redacted["extra"]["nested"][0]["refresh_token"], FILTERED)
        self.assertEqual(redacted["request"]["headers"]["Content-Type"], "application/json")

    def test_json_formatter_emits_safe_machine_readable_log(self):
        record = logging.LogRecord(
            name="Mapapi.tests",
            level=logging.ERROR,
            pathname=__file__,
            lineno=42,
            msg="Delivery failed for %s with token=%s",
            args=("person@example.com", "private-token"),
            exc_info=None,
        )

        payload = json.loads(SafeJsonFormatter().format(record))

        self.assertEqual(payload["level"], "ERROR")
        self.assertEqual(payload["logger"], "Mapapi.tests")
        self.assertEqual(payload["service"], "map-action-api")
        self.assertNotIn("person@example.com", payload["message"])
        self.assertNotIn("private-token", payload["message"])


class TraceSamplerTests(unittest.TestCase):
    def setUp(self):
        self.sampler = build_traces_sampler(0.01)

    def test_samples_normal_api_traffic_at_configured_rate(self):
        self.assertEqual(
            self.sampler({"asgi_scope": {"type": "http", "method": "GET", "path": "/MapApi/incidents/"}}),
            0.01,
        )

    def test_drops_non_actionable_or_long_lived_traffic(self):
        contexts = (
            {"asgi_scope": {"type": "websocket", "path": "/ws/notifications/"}},
            {"asgi_scope": {"type": "http", "method": "OPTIONS", "path": "/MapApi/incidents/"}},
            {"asgi_scope": {"type": "http", "method": "GET", "path": "/static/admin.css"}},
            {"asgi_scope": {"type": "http", "method": "GET", "path": "/MapApi/api/schema/"}},
            {"wsgi_environ": {"REQUEST_METHOD": "GET", "PATH_INFO": "/healthz"}},
        )
        for context in contexts:
            with self.subTest(context=context):
                self.assertEqual(self.sampler(context), 0.0)


class SentryInitializationTests(unittest.TestCase):
    def test_no_dsn_is_a_noop(self):
        with patch.dict(os.environ, {"SENTRY_DSN": ""}, clear=True):
            self.assertFalse(init_sentry(debug=False, project_root=Path("/app")))

    def test_initializes_with_cost_and_privacy_guards(self):
        environment = {
            "SENTRY_DSN": "https://public@example.ingest.sentry.io/123",
            "SENTRY_ENVIRONMENT": "staging",
            "SENTRY_RELEASE": "abc123",
            "SENTRY_TRACES_SAMPLE_RATE": "0.01",
            "SENTRY_ENABLE_LOGS": "false",
        }
        with patch.dict(os.environ, environment, clear=True), patch("sentry_sdk.init") as sentry_init:
            self.assertTrue(init_sentry(debug=False, project_root=Path("/app")))

        options = sentry_init.call_args.kwargs
        self.assertEqual(options["environment"], "staging")
        self.assertEqual(options["release"], "abc123")
        self.assertEqual(options["sample_rate"], 1.0)
        self.assertNotIn("profiles_sample_rate", options)
        self.assertFalse(options["send_default_pii"])
        self.assertFalse(options["include_local_variables"])
        self.assertFalse(options["include_source_context"])
        self.assertEqual(options["max_request_body_size"], "never")
        self.assertEqual(options["max_breadcrumbs"], 50)
        self.assertEqual(options["max_value_length"], 4096)
        self.assertEqual(options["trace_propagation_targets"], [])
        self.assertIsNone(options["before_send_log"]({"body": "not sent"}, {}))
        self.assertEqual(options["traces_sampler"]({"asgi_scope": {"path": "/MapApi/zones/"}}), 0.01)

        integration_names = {type(integration).__name__ for integration in options["integrations"]}
        self.assertEqual(integration_names, {"CeleryIntegration", "DjangoIntegration", "LoggingIntegration"})

    def test_standalone_sentry_logs_are_explicitly_opt_in(self):
        environment = {
            "SENTRY_DSN": "https://public@example.ingest.sentry.io/123",
            "SENTRY_ENABLE_LOGS": "true",
        }
        with patch.dict(os.environ, environment, clear=True), patch("sentry_sdk.init") as sentry_init:
            init_sentry(debug=True, project_root=Path("/app"))

        options = sentry_init.call_args.kwargs
        logging_integration = next(
            integration
            for integration in options["integrations"]
            if type(integration).__name__ == "LoggingIntegration"
        )
        self.assertTrue(logging_integration.capture_sentry_logs)
        self.assertEqual(logging_integration._sentry_logs_handler.level, logging.WARNING)
        self.assertIsNotNone(options["before_send_log"])
        self.assertNotIn("traces_sampler", options)

    def test_invalid_trace_rate_fails_fast(self):
        environment = {
            "SENTRY_DSN": "https://public@example.ingest.sentry.io/123",
            "SENTRY_TRACES_SAMPLE_RATE": "1.5",
        }
        with patch.dict(os.environ, environment, clear=True):
            with self.assertRaisesRegex(ValueError, "SENTRY_TRACES_SAMPLE_RATE"):
                init_sentry(debug=False, project_root=Path("/app"))


if __name__ == "__main__":
    unittest.main()
