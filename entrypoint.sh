#!/bin/sh

set -e

# Compose supplies the production Daphne command (including DB readiness and
# migrations); the Dockerfile CMD remains the local fallback. Preserve signals
# by replacing the shell with the requested process.
exec "$@"
