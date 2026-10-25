"""Drives self-service signup (decision S-1, Stage C) against the integration
database and prints one `RESULT <json>` line.

Run in a fresh interpreter by `tests/integration/test_signups.py`, once per
mode (`argv[1]`), because SaaS-OS caches configuration per process:

- `on`: the full scenario (signup enabled, limits from the environment);
- `off`: the kill switch;
- `cap`, `ratelimit`, `counter_down`, `limiter_down`: one limit each;
- `stale`: an idle signup for the maintenance command;
- `cap_concurrent`, `counter_down_concurrent`: requests released together
  by a barrier.

Every mode first empties `crm_app.signup_attempt`, so the platform cap
starts from zero (test database only). Sessions carry made-up verified
emails; workspace names are random. Refuses to run unless ENVIRONMENT=test.
"""

from __future__ import annotations

import json
import os
import secrets
import sys
import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from urllib.parse import urlsplit

from fastapi.testclient import TestClient
from saas_os.core.authority import SystemAuthority, SystemCaller, UserCaller
from saas_os.core.identity import (
    get_membership,
    get_or_create_user_for_external_identity,
    issue_session,
    list_tenant_members,
)
from saas_os.core.platform_authority import (
    PlatformPermission,
    enroll_operator,
    grant_platform_permission,
)
from saas_os.core.tenancy import (
    TenantStatus,
    find_tenants_by_name,
    get_tenant,
    purge_tenant,
    transition_tenant_status,
)
from saas_os.infra.db import session_scope, tenant_session_scope, update

import crm_app.provisioning
from crm_app import signups
from crm_app.app import create_app
from crm_app.models import Signup
from tests.integration.workspace_route_probe import _new_user, _new_workspace

ISSUER = "https://identity.invalid/signup-probe"


def _email(label: str) -> str:
    return f"{label}.{secrets.token_hex(5)}@example.test"


def _name(label: str) -> str:
    return f"signup-probe-{label}-{secrets.token_hex(4)}"


def _attempts() -> int:
    with session_scope() as session:
        return (
            session.connection()
            .exec_driver_sql("SELECT count(*) FROM crm_app.signup_attempt")
            .scalar_one()
        )


def _reset_attempts() -> None:
    with session_scope() as session:
        session.connection().exec_driver_sql("DELETE FROM crm_app.signup_attempt")


class Api:
    def __init__(self, client: TestClient) -> None:
        self.client = client
        # A fresh client address per process: the per-address limiter keeps
        # its counts in Redis across probe runs within its window.
        self.address = "10." + ".".join(str(b) for b in secrets.token_bytes(3))

    def post(self, token: str | None, key: str | None, body: Any) -> Any:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        headers["X-Forwarded-For"] = self.address
        if key:
            headers["Idempotency-Key"] = key
        return self.client.post("/v1/signups", json=body, headers=headers)

    def current(self, token: str | None) -> Any:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return self.client.get("/v1/signups/current", headers=headers)


def _verified() -> tuple[uuid.UUID, str, str]:
    user = _new_user()
    email = _email("signup")
    return user, issue_session(user, verified_email=email)[1], email


def _owner_ok(workspace: uuid.UUID, user: uuid.UUID) -> bool:
    return crm_app.provisioning.owner_verified(workspace, user)


def _patched(target: Any, name: str, fail_times: int) -> Callable[[], None]:
    """Make `target.name` raise RuntimeError `fail_times` times, then work."""
    original = getattr(target, name)
    calls = {"n": 0}

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        calls["n"] += 1
        if calls["n"] <= fail_times:
            raise RuntimeError("simulated interruption")
        return original(*args, **kwargs)

    setattr(target, name, wrapper)
    return lambda: setattr(target, name, original)


def interruptions() -> dict[str, Any]:
    """Interrupt each step once; the next run resumes and finishes with one
    active workspace whose Owner passes the checks."""
    points = {
        "create_tenant": (signups, "create_tenant"),
        "claim_after_create": (signups, "_claim"),
        "seed_roles": (crm_app.provisioning, "seed_roles"),
        "ensure_membership": (crm_app.provisioning, "ensure_membership"),
        "assign_owner": (crm_app.provisioning, "assign_owner"),
        "activate": (signups, "transition_tenant_status"),
    }
    out: dict[str, Any] = {}
    for label, (target, attribute) in points.items():
        user = _new_user()
        name = _name(label)
        view, _ = signups.start(user, str(uuid.uuid4()), name, max_workspaces=5)
        restore = _patched(target, attribute, 1)
        try:
            first = signups.run(view.id, user)
        finally:
            restore()
        second = signups.run(view.id, user)
        tenants = find_tenants_by_name(name)
        workspace = second.workspace_id
        out[label] = {
            "first": [first.state, first.error_code],
            "second": second.state,
            "tenants_with_name": len(tenants),
            "workspace_matches": workspace is not None and [t.id for t in tenants] == [workspace],
            "active": workspace is not None
            and get_tenant(workspace).status == TenantStatus.ACTIVE.value,
            "owner_ok": workspace is not None and _owner_ok(workspace, user),
            "members": len(list_tenant_members(workspace)) if workspace else None,
        }
    return out


def owner_checked_before_activation() -> dict[str, Any]:
    """At the moment the workspace is activated, the Owner already passes
    every check; before the Owner role, the member can do nothing."""
    user = _new_user()
    seen: dict[str, Any] = {}
    original = signups.transition_tenant_status

    def spy(workspace: uuid.UUID, *args: Any, **kwargs: Any) -> Any:
        seen["status_before"] = get_tenant(workspace).status
        seen["owner_ok_before"] = _owner_ok(workspace, user)
        return original(workspace, *args, **kwargs)

    signups.transition_tenant_status = spy  # type: ignore[assignment]
    try:
        view, _ = signups.start(user, str(uuid.uuid4()), _name("activation"), max_workspaces=5)
        done = signups.run(view.id, user)
    finally:
        signups.transition_tenant_status = original  # type: ignore[assignment]

    # Stop before the Owner role: a member without any role.
    user2 = _new_user()
    restore = _patched(crm_app.provisioning, "assign_owner", 99)
    try:
        view2, _ = signups.start(user2, str(uuid.uuid4()), _name("no-owner"), max_workspaces=5)
        stopped = signups.run(view2.id, user2)
    finally:
        restore()
    workspace2 = stopped.workspace_id
    return {
        **seen,
        "state": done.state,
        "stopped": [stopped.state, stopped.error_code],
        "stopped_status": get_tenant(workspace2).status if workspace2 else None,
        "stopped_member_exists": workspace2 is not None
        and get_membership(workspace2, user2) is not None,
        "stopped_member_can_read": workspace2 is not None
        and crm_app.provisioning.owner_verified(
            workspace2, user2, (("crm_app.workspace", "read"),)
        ),
    }


def failed_owner_check() -> dict[str, Any]:
    user = _new_user()
    original = crm_app.provisioning.owner_verified
    crm_app.provisioning.owner_verified = lambda *a, **k: False  # type: ignore[assignment]
    try:
        view, _ = signups.start(user, str(uuid.uuid4()), _name("check"), max_workspaces=5)
        done = signups.run(view.id, user)
    finally:
        crm_app.provisioning.owner_verified = original  # type: ignore[assignment]
    workspace = done.workspace_id
    return {
        "state": done.state,
        "error": done.error_code,
        "status": get_tenant(workspace).status if workspace else None,
        "rerun": signups.run(view.id, user).state,
    }


def expiry_and_maintenance() -> dict[str, Any]:
    # A signup left unfinished past its expiry is expired, never activated.
    user = _new_user()
    view, _ = signups.start(user, str(uuid.uuid4()), _name("expired"), max_workspaces=5)
    past = signups._now() - signups.EXPIRY - signups.STALE_AFTER
    with signups._as_user(user) as session:
        session.execute(
            update(Signup).where(Signup.id == view.id).values(expires_at=past, updated_at=past)
        )
    # A stale unfinished signup, interrupted earlier, is resumed.
    user2 = _new_user()
    view2, _ = signups.start(user2, str(uuid.uuid4()), _name("stale"), max_workspaces=5)
    restore = _patched(crm_app.provisioning, "seed_roles", 1)
    try:
        signups.run(view2.id, user2)
    finally:
        restore()
    old = signups._now() - signups.STALE_AFTER * 2
    with signups._as_user(user2) as session:
        session.execute(update(Signup).where(Signup.id == view2.id).values(updated_at=old))
    report = signups.maintain()
    expired = signups.view(view.id, user)
    resumed = signups.view(view2.id, user2)
    return {
        "report_resumed_at_least_two": report.resumed >= 2,
        "expired": [expired.state, expired.workspace_id is None],
        "resumed": resumed.state,
        "resumed_active": resumed.workspace_id is not None
        and get_tenant(resumed.workspace_id).status == TenantStatus.ACTIVE.value,
    }


def tenant_context_sees_nothing(workspace: uuid.UUID) -> dict[str, Any]:
    with tenant_session_scope(workspace) as session:
        session.connection().exec_driver_sql(
            "SELECT set_config('crm_app.signup_maintenance', 'on', true)"
        )
        rows = (
            session.connection().exec_driver_sql("SELECT count(*) FROM crm_app.signup").scalar_one()
        )
    return {"rows_in_tenant_context": rows}


def purge_removes_signup_rows(api: Api) -> dict[str, Any]:
    _, token, _ = _verified()
    created = api.post(token, str(uuid.uuid4()), {"workspace_name": _name("purge")}).json()
    workspace = uuid.UUID(created["workspace_id"])
    bootstrap = SystemCaller(SystemAuthority.PLATFORM_BOOTSTRAP)
    operator_user = get_or_create_user_for_external_identity(ISSUER, secrets.token_hex(8))
    operator = enroll_operator(operator_user.id, caller=bootstrap, reason="crm-app signup test")
    grant_platform_permission(
        operator.id,
        PlatformPermission.TENANT_DELETE,
        caller=bootstrap,
        reason="crm-app signup test",
    )
    transition_tenant_status(workspace, TenantStatus.DELETED, caller=UserCaller(operator_user.id))
    purge_tenant(workspace, caller=SystemCaller(SystemAuthority.TENANT_PURGE))
    return {
        "before": created["state"],
        "purge_status": get_tenant(workspace).status,
        "rows_left": signups.remaining_for_workspace(workspace),
        "current_after": api.current(token).status_code,
    }


def invitation_creates_no_workspace(api: Api) -> dict[str, Any]:
    workspace = _new_workspace("signup-invite")
    owner_token = issue_session(workspace.owner_id)[1]
    invitee = _new_user()
    email = _email("invitee")
    invitee_token = issue_session(invitee, verified_email=email)[1]
    sent = api.client.post(
        f"/v1/workspaces/{workspace.id}/invitations",
        json={"email": email, "role": "Member"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    token = urlsplit(sent.json()["link"]).fragment
    accepted = api.client.post(
        f"/v1/tenants/{workspace.id}/invitations/accept",
        json={"token": token},
        headers={"Authorization": f"Bearer {invitee_token}"},
    )
    return {
        "sent": sent.status_code,
        "accepted": accepted.status_code,
        "signup_of_invitee": api.current(invitee_token).status_code,
        "invitee_has_signup": signups.current(invitee) is not None,
    }


def scenario_on(api: Api) -> dict[str, Any]:  # noqa: PLR0915 - one scenario, top to bottom
    result: dict[str, Any] = {"names": [], "emails": []}
    a, token_a, email_a = _verified()
    b, token_b, email_b = _verified()
    unverified = issue_session(_new_user())[1]
    result["emails"] += [email_a, email_b]
    name1, name2, name3 = _name("a1"), _name("a2"), _name("a3")
    result["names"] += [name1, name2, name3]

    result["anonymous"] = [
        api.post(None, "k", {"workspace_name": name1}).status_code,
        api.current(None).status_code,
    ]
    before = _attempts()
    result["unverified"] = [
        api.post(unverified, "k", {"workspace_name": name1}).status_code,
        api.current(unverified).status_code,
    ]
    result["unverified_counted"] = _attempts() - before
    result["missing_key"] = api.post(token_a, None, {"workspace_name": name1}).json()
    before = _attempts()
    bad_key = api.post(token_a, "not a valid key!", {"workspace_name": name1})
    not_json = api.client.post(
        "/v1/signups",
        content=b"{not json",
        headers={
            "Authorization": f"Bearer {token_a}",
            "Idempotency-Key": str(uuid.uuid4()),
            "Content-Type": "application/json",
            "X-Forwarded-For": api.address,
        },
    )
    result["malformed_counted"] = {
        "bad_key": bad_key.status_code,
        "not_json": [not_json.status_code, "not json" in not_json.text],
        "counted": _attempts() - before,
    }
    forged = api.post(
        token_a,
        str(uuid.uuid4()),
        {
            "workspace_name": name1,
            "parent_id": str(uuid.uuid4()),
            "role": "Owner",
            "user_id": str(b),
            "tenant_id": str(uuid.uuid4()),
        },
    )
    result["forged"] = [forged.status_code, str(b) in forged.text, name1 in forged.text]
    for field in ("user_id", "tenant_id", "role", "parent_id", "workspace_id"):
        response = api.post(token_a, str(uuid.uuid4()), {"workspace_name": name1, field: "x"})
        result.setdefault("forged_fields", {})[field] = response.status_code
    result["bad_name"] = [
        api.post(token_a, str(uuid.uuid4()), {"workspace_name": " "}).json(),
        api.post(token_a, str(uuid.uuid4()), {"workspace_name": "x" * 101}).status_code,
    ]
    result["nothing_created_yet"] = api.current(token_a).status_code

    key1 = str(uuid.uuid4())
    first = api.post(token_a, key1, {"workspace_name": name1})
    body1 = first.json()
    workspace1 = uuid.UUID(body1["workspace_id"])
    result["first"] = [first.status_code, body1["state"], name1 in first.text]
    result["first_workspace"] = {
        "status": get_tenant(workspace1).status,
        "owner_ok": _owner_ok(workspace1, a),
        "only_member_is_a": [m.user_id for m in list_tenant_members(workspace1)] == [a],
        "tenants_with_name": len(find_tenants_by_name(name1)),
        "workspace_read": api.client.get(
            f"/v1/workspaces/{workspace1}", headers={"Authorization": f"Bearer {token_a}"}
        ).status_code,
        "other_person_read": api.client.get(
            f"/v1/workspaces/{workspace1}", headers={"Authorization": f"Bearer {token_b}"}
        ).status_code,
        "in_directory": str(workspace1)
        in api.client.get("/v1/workspaces", headers={"Authorization": f"Bearer {token_a}"}).text,
    }
    replay = api.post(token_a, key1, {"workspace_name": name1})
    result["replay"] = [replay.status_code, replay.json()["id"] == body1["id"]]
    result["replay_other_body"] = [
        api.post(token_a, key1, {"workspace_name": name2}).status_code,
        api.post(token_a, key1, {"workspace_name": name2}).json(),
    ]
    second = api.post(token_a, str(uuid.uuid4()), {"workspace_name": name2})
    result["second"] = [second.status_code, second.json()["state"]]
    third = api.post(token_a, str(uuid.uuid4()), {"workspace_name": name3})
    result["third_over_limit"] = [third.status_code, third.json()]
    result["third_tenants"] = len(find_tenants_by_name(name3))
    result["current_a_is_latest"] = api.current(token_a).json()["id"] == second.json()["id"]

    # Another person: no access to A's signups; A's key means nothing to them.
    result["current_b"] = api.current(token_b).status_code
    b_signup = api.post(token_b, key1, {"workspace_name": _name("b")})
    result["b_same_key"] = [b_signup.status_code, b_signup.json()["id"] != body1["id"]]

    # Parallel requests: one workspace per person.
    for label, same_key in (("different_keys", False), ("same_key", True)):
        user, token, _ = _verified()
        shared = str(uuid.uuid4())
        name = _name(label)
        with ThreadPoolExecutor(max_workers=6) as pool:
            responses = list(
                pool.map(
                    lambda _, t=token, n=name, s=same_key, k=shared: api.post(
                        t, k if s else str(uuid.uuid4()), {"workspace_name": n}
                    ),
                    range(6),
                )
            )
        ids = {r.json()["id"] for r in responses if r.status_code in (200, 201, 202)}
        latest = signups.current(user)
        result[f"parallel_{label}"] = {
            "statuses": sorted(r.status_code for r in responses),
            "signups": len(ids),
            "tenants": len(find_tenants_by_name(name)),
            "final": latest.state if latest else None,
        }

    result["interruptions"] = interruptions()
    result["activation"] = owner_checked_before_activation()
    result["failed_owner_check"] = failed_owner_check()
    result["maintenance"] = expiry_and_maintenance()
    result["tenant_context"] = tenant_context_sees_nothing(workspace1)
    result["purge"] = purge_removes_signup_rows(api)
    result["invitation"] = invitation_creates_no_workspace(api)
    result["users"] = {"a": str(a), "b": str(b)}
    return result


def scenario_off(api: Api) -> dict[str, Any]:
    _, token, _ = _verified()
    return {
        "post": api.post(token, str(uuid.uuid4()), {"workspace_name": _name("off")}).status_code,
        "current": api.current(token).status_code,
        "anonymous": api.post(None, None, {}).status_code,
        "attempts": _attempts(),
    }


def scenario_unverified_repeats(api: Api, count: int) -> dict[str, Any]:
    token = issue_session(_new_user())[1]
    statuses = [
        api.post(token, str(uuid.uuid4()), {"workspace_name": _name("cap")}).status_code
        for _ in range(count)
    ]
    return {"statuses": statuses, "attempts": _attempts()}


def scenario_down(api: Api) -> dict[str, Any]:
    user, token, _ = _verified()
    response = api.post(token, str(uuid.uuid4()), {"workspace_name": _name("down")})
    return {
        "status": response.status_code,
        "retry_after": response.headers.get("Retry-After"),
        "signup": signups.current(user) is not None,
        "attempts": _attempts(),
    }


def scenario_stale() -> dict[str, Any]:
    """A signup that never ran, idle long enough for maintenance; the test
    then runs `python -m crm_app.signup_maintenance` in a fresh process."""
    user = _new_user()
    view, _ = signups.start(user, str(uuid.uuid4()), _name("stale-command"), max_workspaces=5)
    old = signups._now() - signups.STALE_AFTER * 2
    with signups._as_user(user) as session:
        session.execute(update(Signup).where(Signup.id == view.id).values(updated_at=old))
    return {"signup": str(view.id), "user": str(user)}


def _barrier_run(tasks: list[Callable[[], Any]]) -> list[Any]:
    """Run every task in its own thread, all released at the same moment."""
    barrier = threading.Barrier(len(tasks))
    results: list[Any] = [None] * len(tasks)

    def worker(index: int) -> None:
        barrier.wait()
        try:
            results[index] = tasks[index]()
        except Exception as exc:  # noqa: BLE001 - recorded, compared by the test
            results[index] = type(exc).__name__

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(len(tasks))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return results


def _counted_directly(cap: int) -> str:
    try:
        signups.record_attempt(cap)
    except signups.SignupRefusedError:
        return "refused"
    return "counted"


_EXPECTED_STATUS = {"unverified": 403, "bad_name": 400, "bad_key": 400}


def scenario_cap_concurrent(api: Api) -> dict[str, Any]:
    """The platform cap under requests released together by a barrier."""
    direct = []
    for _ in range(10):
        _reset_attempts()
        outcomes = _barrier_run([lambda: _counted_directly(7) for _ in range(40)])
        direct.append(
            {
                "counted": outcomes.count("counted"),
                "refused": outcomes.count("refused"),
                "other": [o for o in outcomes if o not in ("counted", "refused")],
                "stored": _attempts(),
            }
        )

    rounds = []
    for _ in range(5):
        _reset_attempts()
        kinds: list[str] = []
        tasks: list[Callable[[], Any]] = []
        names: list[str] = []
        for kind in ("unverified", "bad_name", "bad_key", "valid") * 6:
            token = issue_session(_new_user())[1] if kind == "unverified" else _verified()[1]
            name = _name("concurrent")
            names.append(name)
            key = "not a valid key!" if kind == "bad_key" else str(uuid.uuid4())
            body = {"workspace_name": " " if kind == "bad_name" else name}
            kinds.append(kind)
            tasks.append(lambda t=token, k=key, b=body: api.post(t, k, b).status_code)
        statuses = _barrier_run(tasks)
        admitted = [
            (kind, status) for kind, status in zip(kinds, statuses, strict=True) if status != 429
        ]
        rounds.append(
            {
                "admitted": len(admitted),
                "refused_by_cap": statuses.count(429),
                "stored": _attempts(),
                "admitted_statuses_match_kind": all(
                    status in (201, 202) if kind == "valid" else status == _EXPECTED_STATUS[kind]
                    for kind, status in admitted
                ),
                "workspaces": sum(len(find_tenants_by_name(n)) for n in names),
                "valid_admitted": sum(1 for kind, _ in admitted if kind == "valid"),
                "unexpected": sorted({s for s in statuses if s not in (201, 202, 400, 403, 429)}),
            }
        )
    return {"direct": direct, "http": rounds}


def scenario_counter_down_concurrent(api: Api) -> dict[str, Any]:
    people = [_verified() for _ in range(8)]
    statuses = _barrier_run(
        [
            lambda t=token: (
                api.post(t, str(uuid.uuid4()), {"workspace_name": _name("down")}).status_code
            )
            for _, token, _ in people
        ]
    )
    return {
        "statuses": sorted(set(statuses)),
        "signups": sum(1 for user, _, _ in people if signups.current(user) is not None),
    }


def main() -> None:
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("signup_probe runs only with ENVIRONMENT=test")
    mode = sys.argv[1]
    _reset_attempts()
    with TestClient(create_app(), follow_redirects=False) as client:
        api = Api(client)
        scenarios: dict[str, Callable[[], dict[str, Any]]] = {
            "on": lambda: scenario_on(api),
            "off": lambda: scenario_off(api),
            "cap": lambda: scenario_unverified_repeats(api, 5),
            "ratelimit": lambda: scenario_unverified_repeats(api, 3),
            "counter_down": lambda: scenario_down(api),
            "limiter_down": lambda: scenario_down(api),
            "stale": scenario_stale,
            "cap_concurrent": lambda: scenario_cap_concurrent(api),
            "counter_down_concurrent": lambda: scenario_counter_down_concurrent(api),
        }
        result = scenarios[mode]()
    print("RESULT " + json.dumps(result, default=str))


if __name__ == "__main__":
    main()
