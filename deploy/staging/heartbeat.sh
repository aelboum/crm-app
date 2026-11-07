#!/bin/sh
# The monitoring heartbeat (decision D-STG.3; brief H exit criterion E9).
#
# Pings HEARTBEAT_URL only when both hold:
#   1. the worker answers its health probe (`crm-app-worker --check` reads
#      the sentinel the running worker refreshes in Redis every 15 seconds);
#   2. no queued work is overdue (`python -m crm_app.health_check`).
# Otherwise it exits non-zero and sends nothing: the monitoring service
# alerts on the missing ping. Run by leadstack-heartbeat.timer on the host.
#
# Settings, from the environment (never arguments):
#   STACK_DIR      the directory holding compose.yaml
#   ENV_FILE       the Compose environment file
#   HEARTBEAT_URL  the monitoring service's heartbeat address (a secret)
#   COMPOSE_EXTRA  optional extra Compose arguments (local: the profile)
set -eu

: "${STACK_DIR:?}"
: "${ENV_FILE:?}"
: "${HEARTBEAT_URL:?}"

compose() {
    # shellcheck disable=SC2086 # COMPOSE_EXTRA is deliberately split.
    docker compose --env-file "$ENV_FILE" -f "$STACK_DIR/compose.yaml" ${COMPOSE_EXTRA:-} "$@"
}

if ! compose run --rm --no-deps -T worker crm-app-worker --check >/dev/null 2>&1; then
    echo "heartbeat: the worker is not running; no ping" >&2
    exit 1
fi
if ! compose run --rm --no-deps -T app python -m crm_app.health_check; then
    echo "heartbeat: queued work is overdue; no ping" >&2
    exit 1
fi
# The address is not echoed: it carries the monitor's token.
curl -fsS --max-time 10 --retry 2 "$HEARTBEAT_URL" >/dev/null
echo "heartbeat: sent"
