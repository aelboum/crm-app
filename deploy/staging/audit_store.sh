#!/bin/sh
# Keep the worker's audit_digest lines in append-only files on the host
# (decision D-STG.7; SaaS-OS ADR-0053; staging backup report finding S-10).
#
# The worker logs one `audit_digest` line per settled audit window. Those
# lines are the evidence `python -m saas_os.ops.audit_digest verify` checks
# the audit tables against, so they must outlive the worker's container log,
# which Docker rotates (5 x 10 MB) and loses on every redeploy. `collect`
# copies every line not yet kept into $STORE_DIR/audit_digest.log, which
# carries the ext4 append-only attribute: it can grow, never be rewritten.
#
# A stand-in, not the external store ADR-0053 asks for: the files live on
# the same host, and root can clear the attribute. An external log store is
# an owner decision (hosting brief S11).
#
#   audit_store.sh collect   copy new lines (leadstack-audit-store.timer,
#                            and by hand before every redeploy)
#   audit_store.sh seed      once: keep the records the database already
#                            holds (`core.audit_digests`) in seed.log, for
#                            windows whose log lines rotated away before
#                            this store existed. Refused when seed.log exists.
#
# The seed is the database's own copy: it proves nothing about changes made
# before it was taken, only that later changes to those windows are
# detectable. Its time is the file's, and is written in PROGRESS.md.
#
# Settings, from the environment:
#   STORE_DIR    default /var/lib/leadstack/audit-digests
#   WORKER       default crm-app-staging-worker-1
#   POSTGRES     default crm-app-staging-postgres-1 (seed only)
#   PGPASSWORD   the stand-in's superuser password (seed only; never echoed)
# Digest lines hold window times, hashes and row counts per workspace ID:
# no names, no message text, no secret.
set -eu

STORE_DIR="${STORE_DIR:-/var/lib/leadstack/audit-digests}"
WORKER="${WORKER:-crm-app-staging-worker-1}"
POSTGRES="${POSTGRES:-crm-app-staging-postgres-1}"
STORE="$STORE_DIR/audit_digest.log"
SEED="$STORE_DIR/seed.log"

umask 077
mkdir -p "$STORE_DIR"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

append_only() {
    # A new, empty file that can only be appended to from now on.
    : >"$1"
    chattr +a "$1"
}

case "${1:-}" in
collect)
    [ -e "$STORE" ] || append_only "$STORE"
    docker logs "$WORKER" >"$work/log" 2>&1
    grep -F '"message": "audit_digest"' "$work/log" >"$work/digests" || true
    # Lines already kept are skipped; an empty store skips nothing.
    grep -F -x -v -f "$STORE" "$work/digests" >"$work/new" || true
    cat "$work/new" >>"$STORE"
    echo "audit-store: kept $(wc -l <"$work/new") new line(s), $(wc -l <"$STORE") in all"
    ;;
seed)
    if [ -e "$SEED" ]; then
        echo "audit-store: $SEED exists; a seed is taken once" >&2
        exit 1
    fi
    : "${PGPASSWORD:?}"
    docker exec -e PGPASSWORD "$POSTGRES" psql -h 127.0.0.1 -U postgres -d crm_app \
        -X -At -v ON_ERROR_STOP=1 \
        -c "SELECT record FROM core.audit_digests ORDER BY window_start" >"$work/seed"
    if [ ! -s "$work/seed" ]; then
        echo "audit-store: the database holds no digest records" >&2
        exit 1
    fi
    append_only "$SEED"
    cat "$work/seed" >>"$SEED"
    echo "audit-store: seeded $(wc -l <"$SEED") record(s) from core.audit_digests"
    ;;
*)
    echo "usage: audit_store.sh collect|seed" >&2
    exit 2
    ;;
esac
