"""Production-safe logging and Sentry configuration.

The API handles phone numbers, email addresses, JWTs, incident locations, and
private chat content.  Keep observability useful without copying that data into
logs or error events.  Sentry is deliberately disabled when ``SENTRY_DSN`` is
empty so local development and tests never send data accidentally.
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


FILTERED = "[Filtered]"

_SENSITIVE_KEY_NAMES = {
    "apikey",
    "authorization",
    "cookie",
    "credentials",
    "email",
    "fcmtoken",
    "password",
    "passwd",
    "phone",
    "phonenumber",
    "pin",
    "querystring",
    "recordingurl",
    "refreshtoken",
    "secret",
    "secretkey",
    "setcookie",
    "signedurl",
    "token",
}
_SENSITIVE_KEY_SUFFIXES = (
    "apikey",
    "authorization",
    "cookie",
    "credential",
    "credentials",
    "email",
    "password",
    "phone",
    "pin",
    "recordingurl",
    "secret",
    "signedurl",
    "token",
)

_EMAIL_RE = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])")
_PHONE_RE = re.compile(r"(?<![\w-])\+?(?:\d[\s().-]?){8,15}\d(?![\w-])")
_JWT_RE = re.compile(r"(?<![\w-])eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")
_AUTH_RE = re.compile(r"(?i)\b(Bearer|Basic)\s+[^\s,;]+")
_COOKIE_HEADER_RE = re.compile(r"(?i)\b(set-cookie|cookie)\s*:\s*[^\r\n]+")
_DSN_RE = re.compile(r"https?://[^@\s]+@[^/\s]+/\d+")
_URL_QUERY_RE = re.compile(r"((?:https?|wss?)://[^\s?#]+)\?[^\s#]*")
_QUERY_SECRET_RE = re.compile(
    r"(?i)([?&](?:access_token|api[_-]?key|auth|jwt|password|refresh_token|secret|signature|token)=)[^&\s]+"
)
_ASSIGNED_SECRET_RE = re.compile(
    r"(?i)\b(password|passwd|pin|otp|secret|token|authorization|api[_-]?key)\s*[:=]\s*([^\s,;&]+)"
)

_IGNORED_TRACE_PREFIXES = (
    "/static/",
    "/uploads/",
    "/MapApi/api/schema",
    "/MapApi/schema/",
    "/health",
    "/healthz",
    "/live",
    "/livez",
    "/ready",
    "/readyz",
)


def _normalized_key(key: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(key).lower())


def _is_sensitive_key(key: Any) -> bool:
    normalized = _normalized_key(key)
    return normalized in _SENSITIVE_KEY_NAMES or normalized.endswith(_SENSITIVE_KEY_SUFFIXES)


def redact_text(value: str) -> str:
    """Remove common credentials and direct identifiers from free-form text."""

    value = _AUTH_RE.sub(lambda match: f"{match.group(1)} {FILTERED}", value)
    value = _COOKIE_HEADER_RE.sub(lambda match: f"{match.group(1)}: {FILTERED}", value)
    value = _JWT_RE.sub(FILTERED, value)
    value = _DSN_RE.sub("https://[Filtered]@sentry.invalid/0", value)
    value = _QUERY_SECRET_RE.sub(lambda match: f"{match.group(1)}{FILTERED}", value)
    value = _URL_QUERY_RE.sub(lambda match: f"{match.group(1)}?[Filtered query]", value)
    value = _ASSIGNED_SECRET_RE.sub(lambda match: f"{match.group(1)}={FILTERED}", value)
    value = _EMAIL_RE.sub("[Filtered email]", value)
    value = _PHONE_RE.sub("[Filtered phone]", value)
    return value


def redact_data(value: Any, *, key: Any = None) -> Any:
    """Recursively scrub a Sentry payload or structured logging value."""

    seen: set[int] = set()

    def _redact(item: Any, item_key: Any = None) -> Any:
        if item_key is not None and _is_sensitive_key(item_key):
            return FILTERED
        if isinstance(item, str):
            return redact_text(item)
        if isinstance(item, Mapping):
            identity = id(item)
            if identity in seen:
                return "[Circular]"
            seen.add(identity)
            try:
                return {map_key: _redact(map_value, map_key) for map_key, map_value in item.items()}
            finally:
                seen.remove(identity)
        if isinstance(item, list):
            identity = id(item)
            if identity in seen:
                return "[Circular]"
            seen.add(identity)
            try:
                return [_redact(child) for child in item]
            finally:
                seen.remove(identity)
        if isinstance(item, tuple):
            identity = id(item)
            if identity in seen:
                return "[Circular]"
            seen.add(identity)
            try:
                return tuple(_redact(child) for child in item)
            finally:
                seen.remove(identity)
        return item

    return _redact(value, key)


def _json_safe(value: Any, *, depth: int = 0) -> Any:
    """Bound arbitrary ``LogRecord`` extras without calling sensitive reprs."""

    if depth > 3:
        return "[Truncated]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return redact_text(value[:8192])
    if isinstance(value, Mapping):
        return {
            str(key): _json_safe(child, depth=depth + 1)
            for key, child in list(value.items())[:25]
        }
    if isinstance(value, (list, tuple)):
        return [_json_safe(child, depth=depth + 1) for child in value[:25]]
    return f"<{type(value).__name__}>"


class SafeJsonFormatter(logging.Formatter):
    """One JSON object per line, with secrets and direct identifiers removed."""

    _STANDARD_FIELDS = frozenset(logging.makeLogRecord({}).__dict__)

    def format(self, record: logging.LogRecord) -> str:
        try:
            message = record.getMessage()
        except Exception:  # pragma: no cover - logging must never break the app
            message = "<unformattable log message>"

        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "service": "map-action-api",
            "process": record.process,
            "thread": record.threadName,
            "source": f"{record.pathname}:{record.lineno}",
            "message": redact_text(message),
        }

        extras = {
            key: _json_safe(value)
            for key, value in record.__dict__.items()
            if key not in self._STANDARD_FIELDS and not key.startswith("_")
        }
        if extras:
            payload["extra"] = redact_data(extras)
        if record.exc_info:
            payload["exception"] = redact_text(self.formatException(record.exc_info))
        if record.stack_info:
            payload["stack"] = redact_text(self.formatStack(record.stack_info))

        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)


def _environment_rate(name: str, default: float) -> float:
    raw = os.environ.get(name, str(default)).strip()
    try:
        rate = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number between 0 and 1") from exc
    if not 0.0 <= rate <= 1.0:
        raise ValueError(f"{name} must be between 0 and 1")
    return rate


def _environment_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be true or false")


def build_traces_sampler(sample_rate: float) -> Callable[[dict[str, Any]], float]:
    """Create a low-cost sampler that skips noisy/non-actionable traffic."""

    if not 0.0 <= sample_rate <= 1.0:
        raise ValueError("sample_rate must be between 0 and 1")

    def traces_sampler(sampling_context: dict[str, Any]) -> float:
        asgi_scope = sampling_context.get("asgi_scope") or {}
        if asgi_scope.get("type") == "websocket":
            return 0.0

        environ = sampling_context.get("wsgi_environ") or {}
        method = (asgi_scope.get("method") or environ.get("REQUEST_METHOD") or "").upper()
        if method == "OPTIONS":
            return 0.0

        path = asgi_scope.get("path") or environ.get("PATH_INFO") or ""
        if any(path.startswith(prefix) for prefix in _IGNORED_TRACE_PREFIXES):
            return 0.0
        return sample_rate

    return traces_sampler


def _before_send(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any]:
    del hint
    return redact_data(event)


def _before_breadcrumb(crumb: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any]:
    del hint
    return redact_data(crumb)


def _before_send_log(log: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any]:
    del hint
    return redact_data(log)


def _drop_sentry_log(log: dict[str, Any], hint: dict[str, Any]) -> None:
    del log, hint
    return None


def init_sentry(*, debug: bool, project_root: str | Path) -> bool:
    """Initialize Sentry once when a DSN is configured.

    Error events are never sampled. Performance traces and separately-billed
    Sentry Logs are opt-in via environment variables.
    """

    dsn = os.environ.get("SENTRY_DSN", "").strip()
    if not dsn:
        return False

    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.logging import (
        LoggingIntegration,
        ignore_logger_for_sentry_logs,
    )

    enable_logs = _environment_bool("SENTRY_ENABLE_LOGS", False)
    trace_sample_rate = _environment_rate("SENTRY_TRACES_SAMPLE_RATE", 0.0)
    environment = os.environ.get(
        "SENTRY_ENVIRONMENT",
        "development" if debug else "production",
    ).strip()
    release = os.environ.get("SENTRY_RELEASE", "").strip() or None
    server_name = os.environ.get("SENTRY_SERVER_NAME", "map-action-api").strip() or "map-action-api"
    performance_options = (
        {"traces_sampler": build_traces_sampler(trace_sample_rate)}
        if trace_sample_rate > 0.0
        else {}
    )

    # Access logs and Celery's task lifecycle logs are already represented by
    # Django/Celery error events. Excluding them from the paid Logs product
    # prevents duplicate ingestion when SENTRY_ENABLE_LOGS is explicitly on.
    for logger_name in (
        "celery.app.trace",
        "celery.redirected",
        "celery.worker.job",
        "daphne.access",
        "django.db.backends",
        "django.request",
        "django.server",
    ):
        ignore_logger_for_sentry_logs(logger_name)

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        release=release,
        server_name=server_name,
        project_root=str(project_root),
        integrations=[
            DjangoIntegration(transaction_style="url"),
            # Queue propagation correlates a web error with a later task error;
            # it does not ingest performance transactions while tracing is off.
            CeleryIntegration(propagate_traces=True, monitor_beat_tasks=False),
            LoggingIntegration(
                level=logging.INFO,
                event_level=logging.ERROR,
                sentry_logs_level=logging.WARNING,
                capture_sentry_logs=enable_logs,
            ),
        ],
        # Preserve every actionable failure. Cost controls are applied to logs,
        # traces, profiles, and payload size instead of sampling errors away.
        sample_rate=1.0,
        before_send=_before_send,
        before_breadcrumb=_before_breadcrumb,
        # SDK-native logger calls are always active in sentry-sdk 2.68+, even
        # when stdlib auto-capture is disabled. Drop them here as well unless
        # the operator explicitly opts into the Logs product.
        before_send_log=_before_send_log if enable_logs else _drop_sentry_log,
        send_default_pii=False,
        include_local_variables=False,
        include_source_context=False,
        max_request_body_size="never",
        max_breadcrumbs=50,
        max_value_length=4096,
        attach_stacktrace=False,
        auto_session_tracking=False,
        strict_trace_continuation=True,
        trace_propagation_targets=[],
        shutdown_timeout=5,
        in_app_include=["Mapapi", "backend"],
        debug=False,
        **performance_options,
    )
    return True
