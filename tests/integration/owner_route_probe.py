"""Exercises the membership and role routes, including competing Owner
changes, against the integration database; prints one `RESULT <json>` line.

Run in a fresh interpreter by `tests/integration/test_owner_protection.py`
(SaaS-OS caches configuration per process). Workspaces are created with the
product's own provisioning command (`crm_app.provision`); extra members get
roles from their Owner through the public SaaS-OS API. Every invariant is
read back from the database after the requests finish, not inferred from
HTTP status codes. Refuses to run unless ENVIRONMENT=test.
"""

from __future__ import annotations

import json
import os
import secrets
import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from fastapi.testclient import TestClient
from saas_os.core.authority import SystemAuthority, SystemCaller, UserCaller
from saas_os.core.identity import (
    add_tenant_membership,
    get_or_create_user_for_external_identity,
    issue_session,
    list_tenant_members,
)
from saas_os.core.rbac import assign_role, list_membership_roles, list_roles

from crm_app.app import create_app
from crm_app.provision import Request, provision
from crm_app.roles import Role

PROVISIONING = SystemCaller(SystemAuthority.PROVISIONING)
ISSUER = "https://identity.invalid/owner-probe"
ROUNDS = 5


@dataclass(frozen=True)
class Person:
    user_id: uuid.UUID
    membership_id: uuid.UUID
    token: str


@dataclass(frozen=True)
class Workspace:
    id: uuid.UUID
    people: dict[str, Person]


def _workspace(extra: dict[str, Role]) -> Workspace:
    """`owner` from provisioning, plus one member per entry in `extra`."""
    subject = secrets.token_hex(12)
    result = provision(Request(f"owner-probe-{secrets.token_hex(6)}", ISSUER, subject))
    if result.tenant_id is None or result.owner_user_id is None or result.membership_id is None:
        raise RuntimeError("provisioning returned no identifiers")
    tenant = result.tenant_id
    role_ids = {r.name: r.id for r in list_roles(tenant)}
    people = {
        "owner": Person(
            result.owner_user_id, result.membership_id, issue_session(result.owner_user_id)[1]
        )
    }
    for name, role in extra.items():
        user = get_or_create_user_for_external_identity(ISSUER, secrets.token_hex(12)).id
        membership = add_tenant_membership(tenant, user, caller=PROVISIONING).id
        assign_role(
            tenant, membership, role_ids[role.value], caller=UserCaller(result.owner_user_id)
        )
        people[name] = Person(user, membership, issue_session(user)[1])
    return Workspace(tenant, people)


def _active_owners(tenant: uuid.UUID) -> int:
    owner_role = next(r.id for r in list_roles(tenant) if r.name == Role.OWNER.value)
    return sum(
        1
        for m in list_tenant_members(tenant)
        if m.status == "active"
        and any(a.role_id == owner_role for a in list_membership_roles(tenant, m.id))
    )


def _roles(tenant: uuid.UUID, membership: uuid.UUID) -> list[str]:
    names = {r.id: r.name for r in list_roles(tenant)}
    return sorted(names[a.role_id] for a in list_membership_roles(tenant, membership))


def main() -> None:
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("owner_route_probe runs only with ENVIRONMENT=test")
    result: dict[str, object] = {}
    with TestClient(create_app()) as client:

        def call(method: str, ws: Workspace, who: str, path: str, body: object = None) -> int:
            url = f"/v1/workspaces/{ws.id}/members/{path}"
            headers = {"Authorization": f"Bearer {ws.people[who].token}"}
            return client.request(method, url, headers=headers, json=body).status_code

        def race(first: Callable[[], int], second: Callable[[], int]) -> list[int]:
            barrier = threading.Barrier(2)

            def run(action: Callable[[], int]) -> int:
                barrier.wait()
                return action()

            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(run, first), pool.submit(run, second)]
                return sorted(f.result() for f in futures)

        confirm = {"confirm_owner_change": True}
        for scenario in ("revoke", "suspend", "drop_role"):
            rounds = []
            for _ in range(ROUNDS):
                ws = _workspace({"second": Role.OWNER})
                first_owner, second_owner = ws.people["owner"], ws.people["second"]

                def act(who: str, target: Person, ws: Workspace = ws, kind: str = scenario) -> int:
                    if kind == "drop_role":
                        return call(
                            "DELETE",
                            ws,
                            who,
                            f"{target.membership_id}/roles/Owner?confirm_owner_change=true",
                        )
                    return call("POST", ws, who, f"{target.membership_id}/{kind}", confirm)

                statuses = race(
                    lambda b=second_owner: act("owner", b),
                    lambda a=first_owner: act("second", a),
                )
                rounds.append({"statuses": statuses, "active_owners": _active_owners(ws.id)})
            result[f"race_{scenario}"] = rounds

        # Mixed races (Phase 2 security review L1): the same lock must order
        # different operations too. A revokes B while B drops A's Owner role;
        # and both Owners step down at once.
        mixed: dict[str, list[dict[str, object]]] = {
            "revoke_vs_drop_role": [],
            "both_step_down": [],
        }
        for _ in range(ROUNDS):
            ws = _workspace({"second": Role.OWNER})
            first_owner, second_owner = ws.people["owner"], ws.people["second"]

            def drop(who: str, target: Person, ws: Workspace = ws) -> int:
                path = f"{target.membership_id}/roles/Owner?confirm_owner_change=true"
                return call("DELETE", ws, who, path)

            statuses = race(
                lambda ws=ws, b=second_owner: call(
                    "POST", ws, "owner", f"{b.membership_id}/revoke", confirm
                ),
                lambda a=first_owner: drop("second", a),
            )
            mixed["revoke_vs_drop_role"].append(
                {"statuses": statuses, "active_owners": _active_owners(ws.id)}
            )

            ws = _workspace({"second": Role.OWNER})
            first_owner, second_owner = ws.people["owner"], ws.people["second"]
            statuses = race(
                lambda ws=ws, a=first_owner: call(
                    "DELETE",
                    ws,
                    "owner",
                    f"{a.membership_id}/roles/Owner?confirm_owner_change=true",
                ),
                lambda ws=ws, b=second_owner: call(
                    "DELETE",
                    ws,
                    "second",
                    f"{b.membership_id}/roles/Owner?confirm_owner_change=true",
                ),
            )
            mixed["both_step_down"].append(
                {"statuses": statuses, "active_owners": _active_owners(ws.id)}
            )
        result |= {f"race_{name}": rounds for name, rounds in mixed.items()}

        # Transfer: grant Owner to an Admin, then the original Owner steps down.
        ws = _workspace({"admin": Role.ADMIN})
        admin = ws.people["admin"]
        owner_id = ws.people["owner"].membership_id
        result["transfer"] = {
            "grant": call(
                "POST", ws, "owner", f"{admin.membership_id}/roles", {"role": "Owner", **confirm}
            ),
            "step_down": call(
                "DELETE", ws, "owner", f"{owner_id}/roles/Owner?confirm_owner_change=true"
            ),
            "admin_roles": _roles(ws.id, admin.membership_id),
            "former_owner_roles": _roles(ws.id, owner_id),
            "active_owners": _active_owners(ws.id),
        }

        # Refusals, each followed by the persisted state.
        ws = _workspace({"admin": Role.ADMIN, "member": Role.MEMBER, "reader": Role.READ_ONLY})
        owner, admin, member = ws.people["owner"], ws.people["admin"], ws.people["member"]
        owner_path = f"{owner.membership_id}"
        result["refusals"] = {
            "last_owner_steps_down": call(
                "DELETE", ws, "owner", f"{owner_path}/roles/Owner?confirm_owner_change=true"
            ),
            "owner_revokes_self": call("POST", ws, "owner", f"{owner_path}/revoke", confirm),
            "admin_grants_owner": call(
                "POST", ws, "admin", f"{member.membership_id}/roles", {"role": "Owner", **confirm}
            ),
            "admin_revokes_owner": call("POST", ws, "admin", f"{owner_path}/revoke", confirm),
            "admin_suspends_owner": call("POST", ws, "admin", f"{owner_path}/suspend", confirm),
            "admin_promotes_self": call(
                "POST", ws, "admin", f"{admin.membership_id}/roles", {"role": "Owner", **confirm}
            ),
            "member_grants_admin": call(
                "POST", ws, "member", f"{member.membership_id}/roles", {"role": "Admin"}
            ),
            "reader_suspends_member": call(
                "POST", ws, "reader", f"{member.membership_id}/suspend", {}
            ),
            "owner_change_unconfirmed": call(
                "POST", ws, "owner", f"{member.membership_id}/roles", {"role": "Owner"}
            ),
            "unknown_membership": call("POST", ws, "owner", f"{uuid.uuid4()}/suspend", {}),
            "active_owners": _active_owners(ws.id),
            "owner_roles": _roles(ws.id, owner.membership_id),
            "member_roles": _roles(ws.id, member.membership_id),
            "admin_roles": _roles(ws.id, admin.membership_id),
        }

        # Allowed ordinary changes by an Admin.
        result["admin_manages_member"] = {
            "suspend": call("POST", ws, "admin", f"{member.membership_id}/suspend", {}),
            "reactivate": call("POST", ws, "admin", f"{member.membership_id}/reactivate", {}),
            "grant_admin": call(
                "POST", ws, "admin", f"{member.membership_id}/roles", {"role": "Admin"}
            ),
            "member_roles": _roles(ws.id, member.membership_id),
        }

        # A membership of another workspace is not found from this one.
        other = _workspace({})
        result["cross_workspace"] = call(
            "POST", ws, "owner", f"{other.people['owner'].membership_id}/suspend", confirm
        )
        result["other_workspace_active_owners"] = _active_owners(other.id)
    print("RESULT " + json.dumps(result))


if __name__ == "__main__":
    main()
