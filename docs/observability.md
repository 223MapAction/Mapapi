# API observability with Sentry

The API, Channels WebSockets, Celery workers, and Celery beat all initialize
Sentry from `backend.settings`. Nothing is transmitted unless `SENTRY_DSN` is
set.

## Default policy

- **Errors:** 100% of uncaught Django/Channels/Celery exceptions and explicit
  `logger.exception()` / `logger.error()` records become Sentry Issues.
- **Context:** INFO-and-higher application logs are retained as breadcrumbs only
  when an error event occurs. They are not separate Sentry Logs charges.
- **Console:** stdout uses one redacted JSON object per line at INFO and above.
  Daphne/Django access logs default to WARNING to avoid one log per request.
- **Sentry Logs:** disabled by default. When explicitly enabled, only WARNING and
  higher records are ingested; duplicate access/task lifecycle loggers remain
  excluded.
- **Performance:** tracing and profiling are off by default. An optional trace
  rate skips OPTIONS, static/media, schema/health, and long-lived WebSocket
  traffic.
- **Privacy:** request bodies, local variables, source snippets, default PII,
  credentials, JWTs, query strings, email addresses, and phone numbers are
  removed or disabled. Event strings and structured values are bounded before
  transmission.

This policy preserves application failures while controlling volume at the
sources that usually dominate cost: access logs, routine task logs, traces,
profiles, and oversized payloads.

## Runtime variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `SENTRY_DSN` | empty | Enables Sentry. Store it as a deployment secret. |
| `SENTRY_ENVIRONMENT` | `development` with DEBUG, otherwise `production` | Separates staging and production events. |
| `SENTRY_RELEASE` | empty | Deployed commit SHA; CI sets this automatically. |
| `SENTRY_SERVER_NAME` | `map-action-api` | Stable, low-cardinality service name. |
| `SENTRY_TRACES_SAMPLE_RATE` | `0.0` | Optional transaction rate from `0.0` to `1.0`. Start at `0.01` only if APM is needed. |
| `SENTRY_ENABLE_LOGS` | `False` | Opts WARNING+ Python logs into the separately metered Sentry Logs product. |
| `LOG_LEVEL` | `INFO` | Application stdout threshold. |
| `ACCESS_LOG_LEVEL` | `WARNING` | Daphne/Django access-log threshold. |

Error sampling is intentionally fixed at `1.0`; an exception should not vanish
randomly. If a proven noisy failure consumes quota, filter that exact condition
after fixing or classifying it instead of globally sampling all errors.

## Production activation

1. Create/select a Python (Django) project in Sentry and copy its client DSN.
2. Add the DSN as the `SENTRY_DSN` GitHub Actions secret. The deployment workflow
   writes it into the runtime-only `.env`, sets `SENTRY_ENVIRONMENT=production`,
   and tags the release with the deployed commit SHA.
3. Deploy with traces and standalone Sentry Logs still off.
4. In a staging environment, send one deliberate event:

   ```bash
   python manage.py shell -c 'import sentry_sdk; sentry_sdk.capture_message("map-action-api Sentry smoke test", level="error"); sentry_sdk.flush(timeout=5)'
   ```

5. Confirm the event has environment, release, and service tags; confirm no
   request body, token, email, or phone value appears.
6. Configure Sentry alerts for new production Issues, regressions, and error
   spikes. Route them to the team's actual on-call destination.

Do not run the smoke command against production unless a deliberate production
test Issue is acceptable.

## Local verification and the Sentry plugin

The Codex Sentry plugin is read-only. It is for verifying Issues/events after
deployment; it does not need and must not receive the API's DSN.

1. Create a read-only Sentry auth token at
   <https://sentry.io/settings/account/api/auth-tokens/> with `project:read`,
   `event:read`, and `org:read`.
2. Set `SENTRY_AUTH_TOKEN`, `SENTRY_ORG`, and `SENTRY_PROJECT` in the local shell.
   Never paste the full token into chat and never deploy it with the API.
3. Ask Codex to inspect the staging smoke Issue with the Sentry plugin.

Local tests do not send events:

```bash
SENTRY_DSN= python -m pytest -q Mapapi/tests/test_observability.py -p no:cacheprovider
SENTRY_DSN= SECRET_KEY=test python manage.py check
```

References: [Sentry Django](https://docs.sentry.io/platforms/python/integrations/django/),
[Python logging](https://docs.sentry.io/platforms/python/integrations/logging/),
[data collected](https://docs.sentry.io/platforms/python/data-management/data-collected/),
and [SDK configuration](https://docs.sentry.io/platforms/python/configuration/options/).
