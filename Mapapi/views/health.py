"""Deep health-check endpoint for external monitoring.

`GET /MapApi/health/` probes every production dependency in one call so an
uptime monitor (Better Stack / UptimeRobot / …) can watch the WHOLE stack from a
single URL — not just "does the front door answer 200". It exists because the
outages that hurt this project were **silent**: the Model_deploy TLS cert
expired for a week, Celery workers died while the API still answered — neither
of which a plain uptime check would catch.

Checks:
  - database     : `SELECT 1` on the default connection.            (critical)
  - redis        : PING the Celery broker / channel-layer Redis.    (critical)
  - celery       : ping live workers (`app.control.ping`).          (degraded)
  - model_deploy : TLS cert validity + days-to-expiry of the AI     (degraded;
                   service host (the exact thing that broke).        expired ⇒ degraded)
  - predictions  : failure rate of recent AI predictions.           (degraded)

Response contract (public, no auth, so the monitor can poll it):
  - HTTP 200 + {"status": "ok",       ...}  when every check passes.
  - HTTP 200 + {"status": "degraded", ...}  when only non-critical checks fail
      (celery/model_deploy/predictions) — the API itself still serves.
  - HTTP 503 + {"status": "down",     ...}  when a CRITICAL dep (db/redis) is
      unreachable — the API cannot function.

Point the monitor at `/MapApi/health/` with a keyword assertion — alert unless
the body contains `{"status":"ok","checks"` — to be paged on `degraded` too
(cert expiry, dead workers), while the raw 503 still trips even a
status-code-only monitor on a hard outage.

The keyword must be that exact anchored form: the response is COMPACT json (no
space after the colon) and `,"checks"` pins the match to the TOP-LEVEL status,
so a healthy nested check (`{"database":{"status":"ok"}}`) cannot mask a
`degraded` overall. This view also pins `renderer_classes = [JSONRenderer]` so a
monitor's browser-like `Accept` header can never get the browsable-API HTML
instead (that page HTML-escapes the JSON and broke the assertion in testing).

Never raises: any probe error is reported as that check failing, never a 500.
"""
import os
import socket
import ssl
from datetime import datetime, timezone
from urllib.parse import urlparse

from django.conf import settings
from django.db import connection
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from drf_spectacular.utils import extend_schema, OpenApiResponse

from ..models import Prediction, PredictionStatus


# A dependency probe must never make /health itself hang or 500.
_PROBE_TIMEOUT = 3.0            # seconds for network probes (TLS, redis)
_CELERY_PING_TIMEOUT = 1.5     # seconds to wait for a worker to answer
_CERT_WARN_DAYS = 14           # cert expiring sooner than this ⇒ warn
_PREDICTION_SAMPLE = 20        # look at the most recent N predictions
_PREDICTION_FAIL_RATIO = 0.5   # >50% failed ⇒ degraded


def _check_database():
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return {"status": "ok"}
    except Exception as exc:
        return {"status": "fail", "detail": str(exc)[:200]}


def _check_redis():
    try:
        import redis  # noqa: PLC0415

        client = redis.from_url(
            settings.CELERY_BROKER_URL,
            socket_connect_timeout=_PROBE_TIMEOUT,
            socket_timeout=_PROBE_TIMEOUT,
        )
        client.ping()
        return {"status": "ok"}
    except Exception as exc:
        return {"status": "fail", "detail": str(exc)[:200]}


def _check_celery():
    """At least one worker must answer a ping (guards the silent-worker-death)."""
    try:
        from backend.celery import app  # noqa: PLC0415

        replies = app.control.ping(timeout=_CELERY_PING_TIMEOUT) or []
        worker_count = len(replies)
        if worker_count == 0:
            return {"status": "fail", "detail": "no celery workers responded", "workers": 0}
        return {"status": "ok", "workers": worker_count}
    except Exception as exc:
        return {"status": "fail", "detail": str(exc)[:200]}


def _check_model_deploy():
    """Validate the Model_deploy TLS cert (host from MODEL_DEPLOY_ANALYZE_URL).

    Directly guards the incident that took prediction + chat down for a week: an
    expired Let's Encrypt cert on model.map-action.com. Reports days-to-expiry.
    """
    url = os.environ.get("MODEL_DEPLOY_ANALYZE_URL") or getattr(
        settings, "MODEL_DEPLOY_ANALYZE_URL", ""
    )
    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        return {"status": "skip", "detail": "MODEL_DEPLOY_ANALYZE_URL not configured"}
    if parsed.scheme != "https":
        return {"status": "skip", "detail": f"non-https model URL ({parsed.scheme})"}
    port = parsed.port or 443
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, port), timeout=_PROBE_TIMEOUT) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                cert = ssock.getpeercert()
        not_after = ssl.cert_time_to_seconds(cert["notAfter"])
        days_left = int((not_after - datetime.now(timezone.utc).timestamp()) // 86400)
        result = {"status": "ok", "host": host, "cert_days_remaining": days_left}
        if days_left < 0:
            result["status"] = "fail"
            result["detail"] = "TLS certificate has expired"
        elif days_left < _CERT_WARN_DAYS:
            result["status"] = "warn"
            result["detail"] = f"TLS certificate expires in {days_left} day(s)"
        return result
    except ssl.SSLCertVerificationError as exc:
        # An expired/invalid cert surfaces here on some platforms.
        return {"status": "fail", "host": host, "detail": f"TLS verify failed: {exc}"[:200]}
    except Exception as exc:
        return {"status": "fail", "host": host, "detail": str(exc)[:200]}


def _check_predictions():
    """Failure rate of the most recent AI predictions (guards the 413/cert class
    of downstream breakage that leaves the API up but predictions all failing)."""
    try:
        recent = list(
            Prediction.objects.order_by("-created_at")
            .values_list("status", flat=True)[:_PREDICTION_SAMPLE]
        )
        if not recent:
            return {"status": "ok", "detail": "no predictions yet", "sample": 0}
        failed = sum(1 for s in recent if s == PredictionStatus.FAILED)
        ratio = failed / len(recent)
        result = {
            "status": "ok",
            "sample": len(recent),
            "failed": failed,
            "failure_ratio": round(ratio, 2),
        }
        if ratio > _PREDICTION_FAIL_RATIO:
            result["status"] = "warn"
            result["detail"] = f"{failed}/{len(recent)} recent predictions failed"
        return result
    except Exception as exc:
        return {"status": "fail", "detail": str(exc)[:200]}


class HealthCheckView(APIView):
    """GET /MapApi/health/ — deep multi-dependency health probe (public)."""

    permission_classes = ()
    authentication_classes = ()
    # ALWAYS answer JSON. Uptime monitors send a browser-like `Accept:
    # text/html,...`, and DRF content negotiation would then render the
    # *browsable API HTML page* instead — where the JSON is pretty-printed and
    # HTML-escaped (`&quot;status&quot;: &quot;ok&quot;`). A keyword assertion then
    # matches a NESTED check and the monitor stays green through a real
    # degradation (observed 2026-08-25 during a live celery-down test).
    renderer_classes = [JSONRenderer]

    # Critical checks fail the whole endpoint (503); the rest only mark it degraded.
    _CRITICAL = ("database", "redis")

    @extend_schema(
        tags=["Référentiel & Statistiques"],
        operation_id="health_check",
        summary="Health-check profond (monitoring)",
        description=(
            "Sonde toutes les dépendances de prod (DB, Redis, workers Celery, cert "
            "TLS du service IA Model_deploy, taux d'échec des prédictions récentes) "
            "en un seul appel, pour un monitoring uptime. Public. Renvoie 200 "
            "`ok`/`degraded`, ou 503 `down` si une dépendance critique (DB/Redis) "
            "est injoignable."
        ),
        responses={
            200: OpenApiResponse(description="status ok ou degraded"),
            503: OpenApiResponse(description="status down (dépendance critique KO)"),
        },
    )
    def get(self, request):
        checks = {
            "database": _check_database(),
            "redis": _check_redis(),
            "celery": _check_celery(),
            "model_deploy": _check_model_deploy(),
            "predictions": _check_predictions(),
        }

        critical_down = any(
            checks[name]["status"] == "fail" for name in self._CRITICAL
        )
        any_problem = any(
            c["status"] in ("fail", "warn") for c in checks.values()
        )

        if critical_down:
            overall, http_status = "down", 503
        elif any_problem:
            overall, http_status = "degraded", 200
        else:
            overall, http_status = "ok", 200

        return Response(
            {"status": overall, "checks": checks},
            status=http_status,
        )
