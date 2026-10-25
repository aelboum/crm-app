"""Self-service signup end to end (decisions S-1, S-1.1; `SIGNUP-PLAN.md` §4,
§4b, Stage C).

Drives `signup_probe` in fresh interpreters (one per mode) and checks the
signup table directly as the runtime role. Covers: the kill switch; who may
sign up (signed in, verified email); the body accepting only a name; the
first workspace, activated with its Owner verified; replays and reused
keys; the per-person limit; one workspace under parallel requests; every
step interrupted and resumed; activation only after the Owner checks;
expiry and maintenance; the platform cap and its counting rule; a rate
limit, the counter and the limiter failing closed; RLS between people and
against tenant transactions; purge; invitations creating no workspace; and
no name or email in any log line.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import psycopg
import pytest
from psycopg import errors, sql

from tests.integration.conftest import libpq_url
from tests.support import REPO_ROOT, run_module

pytestmark = pytest.mark.usefixtures("migrated")

Probe = dict[str, Any]


def _run(
    integration_env: dict[str, str], tmp: Path, mode: str, **overrides: str
) -> tuple[Probe, str]:
    probe_env = {
        **integration_env,
        "PYTHONPATH": str(REPO_ROOT),
        "SIGNUP_ENABLED": "true",
        "TRUST_PROXY_HEADERS": "true",
        "SIGNUP_MAX_WORKSPACES_PER_USER": "2",
        "SIGNUP_MAX_ATTEMPTS_PER_24H": "1000",
        "RATE_LIMIT_REQUESTS_PER_WINDOW": "1000",
        **overrides,
    }
    probe_env = {k: v for k, v in probe_env.items() if v != "<unset>"}
    result = run_module("tests.integration.signup_probe", [mode], probe_env, tmp, timeout=900)
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    line = next(x for x in lines if x.startswith("RESULT "))
    # Everything the process logged: JSON log lines on stdout, warnings on stderr.
    logs = " ".join(x for x in lines if not x.startswith("RESULT ")) + result.stderr
    return json.loads(line.removeprefix("RESULT ")), logs


@pytest.fixture(scope="module")
def ran(integration_env: dict[str, str], tmp_path_factory: pytest.TempPathFactory) -> Probe:
    probe, logs = _run(integration_env, tmp_path_factory.mktemp("signup-on"), "on")
    return {"probe": probe, "logs": logs}


@pytest.fixture(scope="module")
def probe(ran: Probe) -> Probe:
    return ran["probe"]


@pytest.fixture
def runtime(integration_env: dict[str, str]) -> Iterator[psycopg.Connection]:
    with psycopg.connect(libpq_url(integration_env["DATABASE_URL"]), autocommit=True) as conn:
        yield conn


@pytest.fixture
def owner(integration_env: dict[str, str]) -> Iterator[psycopg.Connection]:
    url = libpq_url(integration_env["MIGRATIONS_DATABASE_URL"])
    with psycopg.connect(url, autocommit=True) as conn:
        yield conn


# --- The kill switch and who may sign up ---------------------------------


def test_the_routes_do_not_exist_while_signup_is_off(
    integration_env: dict[str, str], tmp_path: Path
) -> None:
    off, _ = _run(integration_env, tmp_path, "off", SIGNUP_ENABLED="<unset>")
    assert off == {"post": 404, "current": 404, "anonymous": 404, "attempts": 0}


def test_only_a_signed_in_person_with_a_verified_email_may_sign_up(probe: Probe) -> None:
    assert probe["anonymous"] == [401, 401]
    assert probe["unverified"] == [403, 403]
    # An unverified request reached the operation, so it counts (owner rule).
    assert probe["unverified_counted"] == 1


def test_a_malformed_key_or_body_is_refused_and_counted(probe: Probe) -> None:
    """They passed the rate limits, so they count (owner decision S-1.2)."""
    assert probe["malformed_counted"] == {
        "bad_key": 400,
        "not_json": [422, False],
        "counted": 2,
    }


def test_the_body_holds_only_a_workspace_name(probe: Probe) -> None:
    assert probe["missing_key"] == {"detail": "idempotency_key_required"}
    status, echoes_user, echoes_name = probe["forged"]
    assert (status, echoes_user, echoes_name) == (422, False, False)
    assert set(probe["forged_fields"].values()) == {422}
    assert probe["bad_name"] == [{"detail": "invalid_workspace_name"}, 400]
    assert probe["nothing_created_yet"] == 404


# --- The workspace --------------------------------------------------------


def test_a_signup_creates_one_active_workspace_owned_by_the_person(probe: Probe) -> None:
    status, state, echoes_name = probe["first"]
    assert (status, state, echoes_name) == (201, "complete", False)
    assert probe["first_workspace"] == {
        "status": "active",
        "owner_ok": True,
        "only_member_is_a": True,
        "tenants_with_name": 1,
        "workspace_read": 200,
        "other_person_read": 404,
        "in_directory": True,
    }


def test_a_replay_returns_the_same_signup_and_a_reused_key_is_refused(probe: Probe) -> None:
    assert probe["replay"] == [200, True]
    assert probe["replay_other_body"] == [409, {"detail": "idempotency_key_reused"}]


def test_the_per_person_limit_holds(probe: Probe) -> None:
    assert probe["second"] == [201, "complete"]
    assert probe["third_over_limit"] == [409, {"detail": "workspace_limit_reached"}]
    assert probe["third_tenants"] == 0
    assert probe["current_a_is_latest"] is True


def test_parallel_requests_create_one_workspace(probe: Probe) -> None:
    for label in ("parallel_different_keys", "parallel_same_key"):
        outcome = probe[label]
        assert outcome["signups"] == 1, label
        assert outcome["tenants"] == 1, label
        assert outcome["final"] == "complete", label
        assert set(outcome["statuses"]) <= {200, 201, 202}, label


def test_every_interrupted_step_resumes_to_one_active_workspace(probe: Probe) -> None:
    for step, outcome in probe["interruptions"].items():
        assert outcome["first"] == ["provisioning", "RuntimeError"], step
        assert outcome["second"] == "complete", step
        assert outcome["tenants_with_name"] == 1, step
        assert outcome["workspace_matches"] is True, step
        assert outcome["active"] is True, step
        assert outcome["owner_ok"] is True, step
        assert outcome["members"] == 1, step


def test_the_workspace_is_activated_only_after_the_owner_checks(probe: Probe) -> None:
    activation = probe["activation"]
    assert activation["status_before"] == "pending"
    assert activation["owner_ok_before"] is True
    assert activation["state"] == "complete"
    # Interrupted before the Owner role: pending, a member who can do nothing.
    assert activation["stopped"] == ["provisioning", "RuntimeError"]
    assert activation["stopped_status"] == "pending"
    assert activation["stopped_member_exists"] is True
    assert activation["stopped_member_can_read"] is False


def test_a_failed_owner_check_stops_for_review_and_never_activates(probe: Probe) -> None:
    assert probe["failed_owner_check"] == {
        "state": "failed",
        "error": "owner_check_failed",
        "status": "pending",
        "rerun": "failed",
    }


def test_expired_signups_expire_and_stale_ones_resume(probe: Probe) -> None:
    assert probe["maintenance"] == {
        "report_resumed_at_least_two": True,
        "expired": ["expired", True],
        "resumed": "complete",
        "resumed_active": True,
    }


def test_the_maintenance_command_resumes_an_idle_signup_in_a_fresh_process(
    integration_env: dict[str, str], tmp_path: Path, runtime: psycopg.Connection
) -> None:
    """The command imports nothing else first, unlike the application."""
    stale, _ = _run(integration_env, tmp_path, "stale")
    command_env = {**integration_env, "PYTHONPATH": str(REPO_ROOT)}
    result = run_module("crm_app.signup_maintenance", [], command_env, tmp_path, timeout=600)
    assert result.returncode == 0, result.stderr
    assert "signups: resumed" in result.stdout
    with runtime.transaction():
        runtime.execute("SELECT set_config('crm_app.signup_user_id', %s, true)", (stale["user"],))
        row = runtime.execute(
            "SELECT state, workspace_id IS NOT NULL FROM crm_app.signup WHERE id = %s",
            (stale["signup"],),
        ).fetchone()
    assert row == ("complete", True)


# --- Limits ----------------------------------------------------------------


def test_the_platform_cap_refuses_without_counting_the_refusal(
    integration_env: dict[str, str], tmp_path: Path
) -> None:
    cap, _ = _run(integration_env, tmp_path, "cap", SIGNUP_MAX_ATTEMPTS_PER_24H="3")
    assert cap == {"statuses": [403, 403, 403, 429, 429], "attempts": 3}


def test_a_rate_limited_request_is_not_counted(
    integration_env: dict[str, str], tmp_path: Path
) -> None:
    limited, _ = _run(integration_env, tmp_path, "ratelimit", RATE_LIMIT_REQUESTS_PER_WINDOW="2")
    assert limited["statuses"][:2] == [403, 403]
    assert limited["statuses"][2] == 429
    assert limited["attempts"] == 2


def test_an_unavailable_counter_refuses_and_provisions_nothing(
    integration_env: dict[str, str], tmp_path: Path, owner: psycopg.Connection
) -> None:
    role = sql.Identifier(integration_env["APP_DB_USER"])
    owner.execute(sql.SQL("REVOKE INSERT ON crm_app.signup_attempt FROM {}").format(role))
    try:
        down, _ = _run(integration_env, tmp_path, "counter_down")
    finally:
        owner.execute(sql.SQL("GRANT INSERT ON crm_app.signup_attempt TO {}").format(role))
    assert down == {"status": 503, "retry_after": "5", "signup": False, "attempts": 0}


def test_concurrent_requests_never_exceed_the_cap_and_refusals_are_not_counted(
    integration_env: dict[str, str], tmp_path: Path
) -> None:
    """Requests released together by a barrier, against the real advisory
    lock and table: directly on the counter (40 at a cap of 7, ten rounds)
    and through the API (24 at a cap of 6, five rounds, mixing unverified
    sessions, invalid names, malformed keys and valid requests, each with
    its own name and key)."""
    concurrent, _ = _run(
        integration_env, tmp_path, "cap_concurrent", SIGNUP_MAX_ATTEMPTS_PER_24H="6"
    )
    for round_ in concurrent["direct"]:
        assert round_ == {"counted": 7, "refused": 33, "other": [], "stored": 7}
    for round_ in concurrent["http"]:
        assert round_["admitted"] == 6, round_
        assert round_["refused_by_cap"] == 18, round_
        assert round_["stored"] == 6, round_
        assert round_["admitted_statuses_match_kind"] is True, round_
        assert round_["unexpected"] == [], round_
        assert round_["workspaces"] == round_["valid_admitted"], round_


def test_an_unavailable_counter_refuses_concurrent_requests(
    integration_env: dict[str, str], tmp_path: Path, owner: psycopg.Connection
) -> None:
    role = sql.Identifier(integration_env["APP_DB_USER"])
    owner.execute(sql.SQL("REVOKE INSERT ON crm_app.signup_attempt FROM {}").format(role))
    try:
        down, _ = _run(integration_env, tmp_path, "counter_down_concurrent")
    finally:
        owner.execute(sql.SQL("GRANT INSERT ON crm_app.signup_attempt TO {}").format(role))
    assert down == {"statuses": [503], "signups": 0}


def test_an_unavailable_limiter_refuses_and_counts_nothing(
    integration_env: dict[str, str], tmp_path: Path
) -> None:
    down, _ = _run(integration_env, tmp_path, "limiter_down", REDIS_URL="redis://127.0.0.1:1/0")
    assert down["status"] == 503
    assert down["signup"] is False
    assert down["attempts"] == 0


# --- Isolation ---------------------------------------------------------------


def _rows(connection: psycopg.Connection, user: str | None) -> list[str]:
    with connection.transaction():
        if user is not None:
            connection.execute("SELECT set_config('crm_app.signup_user_id', %s, true)", (user,))
        return [str(r[0]) for r in connection.execute("SELECT user_id FROM crm_app.signup")]


def _insert_signup(connection: psycopg.Connection, *, as_user: str, for_user: str) -> None:
    with connection.transaction():
        connection.execute("SELECT set_config('crm_app.signup_user_id', %s, true)", (as_user,))
        connection.execute(
            "INSERT INTO crm_app.signup (user_id, idempotency_key, request_fingerprint,"
            " expires_at) VALUES (%s, 'k', 'f', now())",
            (for_user,),
        )


def _count_attempt_in_workspace(connection: psycopg.Connection) -> None:
    with connection.transaction():
        connection.execute("SELECT set_config('app.tenant_id', %s, true)", (str(uuid.uuid4()),))
        connection.execute("INSERT INTO crm_app.signup_attempt DEFAULT VALUES")


def _update_attempt(connection: psycopg.Connection) -> None:
    connection.execute("UPDATE crm_app.signup_attempt SET attempted_at = now()")


def test_one_person_never_reads_or_changes_anothers_signups(
    probe: Probe, runtime: psycopg.Connection
) -> None:
    a, b = probe["users"]["a"], probe["users"]["b"]
    assert set(_rows(runtime, a)) == {a}
    assert set(_rows(runtime, b)) == {b}
    assert _rows(runtime, None) == []
    assert _rows(runtime, str(uuid.uuid4())) == []
    with runtime.transaction():
        runtime.execute("SELECT set_config('crm_app.signup_user_id', %s, true)", (a,))
        changed = runtime.execute(
            "UPDATE crm_app.signup SET last_error_code = 'x' WHERE user_id = %s", (b,)
        ).rowcount
        removed = runtime.execute("DELETE FROM crm_app.signup WHERE user_id = %s", (b,)).rowcount
    assert (changed, removed) == (0, 0)
    with pytest.raises(errors.InsufficientPrivilege):
        _insert_signup(runtime, as_user=a, for_user=b)


def test_the_maintenance_flag_reads_but_never_writes(
    probe: Probe, runtime: psycopg.Connection
) -> None:
    with runtime.transaction():
        runtime.execute("SELECT set_config('crm_app.signup_maintenance', 'on', true)")
        visible = runtime.execute("SELECT count(*) FROM crm_app.signup").fetchone()
        changed = runtime.execute("UPDATE crm_app.signup SET last_error_code = 'x'").rowcount
        removed = runtime.execute("DELETE FROM crm_app.signup").rowcount
    assert visible is not None
    assert visible[0] >= 2
    assert (changed, removed) == (0, 0)


def test_no_workspace_transaction_reaches_the_signup_tables(
    probe: Probe, runtime: psycopg.Connection
) -> None:
    assert probe["tenant_context"] == {"rows_in_tenant_context": 0}
    a = probe["users"]["a"]
    with runtime.transaction():
        runtime.execute("SELECT set_config('app.tenant_id', %s, true)", (str(uuid.uuid4()),))
        runtime.execute("SELECT set_config('crm_app.signup_user_id', %s, true)", (a,))
        seen = runtime.execute("SELECT count(*) FROM crm_app.signup").fetchone()
        attempts = runtime.execute("SELECT count(*) FROM crm_app.signup_attempt").fetchone()
    assert seen == (0,)
    assert attempts == (0,)
    with pytest.raises(errors.InsufficientPrivilege):
        _count_attempt_in_workspace(runtime)


def test_the_runtime_role_cannot_update_an_attempt(runtime: psycopg.Connection) -> None:
    with pytest.raises(errors.InsufficientPrivilege):
        _update_attempt(runtime)


# --- Purge, invitations, logs -------------------------------------------------


def test_purging_the_workspace_removes_its_signup_rows(probe: Probe) -> None:
    assert probe["purge"] == {
        "before": "complete",
        "purge_status": "purged",
        "rows_left": 0,
        "current_after": 404,
    }


def test_accepting_an_invitation_creates_no_signup_or_workspace(probe: Probe) -> None:
    assert probe["invitation"] == {
        "sent": 201,
        "accepted": 200,
        "signup_of_invitee": 404,
        "invitee_has_signup": False,
    }


def test_no_log_line_names_a_workspace_or_an_email(ran: Probe) -> None:
    logs = ran["logs"]
    probe = ran["probe"]
    # The signup events are logged, so the check below looks at real output.
    assert "signup_started" in logs
    assert "signup_completed" in logs
    for value in probe["names"] + probe["emails"]:
        assert value not in logs
