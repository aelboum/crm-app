"""Calls the contact and company routes as different callers against the
integration database and prints one `RESULT <json>` line.

Run in a fresh interpreter by `tests/integration/test_record_routes.py`
(SaaS-OS caches configuration per process). Workspaces, roles and members
are created with `workspace_route_probe`'s helpers (`SystemCaller
(PROVISIONING)`, whose documented purposes include test fixtures); marking a
workspace deleted uses a test operator enrolled with `PLATFORM_BOOTSTRAP`,
as SaaS-OS's own scaffold test does. All values are made up. Refuses to run
unless ENVIRONMENT=test.
"""

from __future__ import annotations

import json
import os
import secrets
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from fastapi.testclient import TestClient
from saas_os.core.authority import SystemAuthority, SystemCaller, UserCaller
from saas_os.core.identity import add_tenant_membership, issue_session
from saas_os.core.platform_authority import (
    PlatformPermission,
    enroll_operator,
    grant_platform_permission,
)
from saas_os.core.rbac import assign_role
from saas_os.core.tenancy import TenantStatus, transition_tenant_status

from crm_app.app import create_app
from crm_app.roles import Role
from tests.integration.workspace_route_probe import PROVISIONING, _new_user, _new_workspace

ROLES = (Role.OWNER, Role.ADMIN, Role.MEMBER, Role.READ_ONLY)
LEAK_MARKER = "leak-check-7f3a@example.test"


def _email() -> str:
    return f"person.{secrets.token_hex(6)}@example.test"


def main() -> None:  # noqa: PLR0915 - one scenario script, read top to bottom
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("record_route_probe runs only with ENVIRONMENT=test")
    a = _new_workspace("records-a")
    b = _new_workspace("records-b")
    users: dict[str, uuid.UUID] = {"owner": a.owner_id, "other_owner": b.owner_id}
    for role in (Role.ADMIN, Role.MEMBER, Role.READ_ONLY):
        user = _new_user()
        membership = add_tenant_membership(a.id, user, caller=PROVISIONING)
        assign_role(a.id, membership.id, a.role_ids[role], caller=UserCaller(a.owner_id))
        users[role.value] = user
    users["Owner"] = a.owner_id
    users["outsider"] = _new_user()
    tokens = {name: issue_session(user)[1] for name, user in users.items()}

    def auth(caller: str | None) -> dict[str, str]:
        return {"Authorization": f"Bearer {tokens[caller]}"} if caller else {}

    base = f"/v1/workspaces/{a.id}"
    other = f"/v1/workspaces/{b.id}"
    result: dict[str, Any] = {"workspace": str(a.id), "other_workspace": str(b.id)}

    with TestClient(create_app(), follow_redirects=False) as client:

        def post(path: str, caller: str | None, body: object, **headers: str) -> Any:
            return client.post(path, json=body, headers={**auth(caller), **headers})

        def contact(caller: str = "owner", **values: object) -> Any:
            return post(
                f"{base}/contacts", caller, {"first_name": "Sam", "email": _email(), **values}
            )

        # --- Role matrix ------------------------------------------------------------
        matrix: dict[str, dict[str, int]] = {}
        for role in ROLES:
            name = role.value
            created = contact(name)
            row: dict[str, int] = {"create": created.status_code}
            target = contact().json()["id"]  # each role acts on its own record
            item = f"{base}/contacts/{target}"
            row["read"] = client.get(item, headers=auth(name)).status_code
            row["update"] = client.patch(
                item, json={"city": "Utrecht"}, headers={**auth(name), "If-Match": '"1"'}
            ).status_code
            row["archive"] = post(f"{item}/archive", name, None).status_code
            row["restore"] = post(f"{item}/restore", name, None).status_code
            row["delete"] = client.delete(item, headers=auth(name)).status_code
            company = post(f"{base}/companies", "owner", {"name": "Role Test BV"}).json()["id"]
            row["company_create"] = post(f"{base}/companies", name, {"name": "X"}).status_code
            row["company_delete"] = client.delete(
                f"{base}/companies/{company}", headers=auth(name)
            ).status_code
            matrix[name] = row
        result["matrix"] = matrix

        # --- Other workspaces, outsiders, anonymous ---------------------------------
        mine = contact().json()
        item = f"{base}/contacts/{mine['id']}"
        foreign_item = f"{other}/contacts/{mine['id']}"
        result["cross"] = {
            "outsider_read": client.get(item, headers=auth("outsider")).status_code,
            "other_owner_read": client.get(item, headers=auth("other_owner")).status_code,
            "anonymous_read": client.get(item).status_code,
            # A member of B naming A's record through B's own path.
            "foreign_get": client.get(foreign_item, headers=auth("other_owner")).status_code,
            "foreign_patch": client.patch(
                foreign_item,
                json={"city": "Elsewhere"},
                headers={**auth("other_owner"), "If-Match": '"1"'},
            ).status_code,
            "foreign_archive": post(f"{foreign_item}/archive", "other_owner", None).status_code,
            "foreign_delete": client.delete(foreign_item, headers=auth("other_owner")).status_code,
            "unknown_record": client.get(
                f"{base}/contacts/{uuid.uuid4()}", headers=auth("owner")
            ).status_code,
            "after": client.get(item, headers=auth("owner")).json(),
        }

        # --- Mass assignment and validation -----------------------------------------
        def status_of(body: dict[str, object]) -> int:
            return post(f"{base}/contacts", "owner", {"first_name": "Sam", **body}).status_code

        result["refused_fields"] = {
            field: status_of({"email": _email(), field: value})
            for field, value in {
                "tenant_id": str(b.id),
                "id": str(uuid.uuid4()),
                "version": 7,
                "archived_at": "2026-01-01T00:00:00Z",
                "created_by_user_id": str(users["outsider"]),
                "source": "import",
            }.items()
        }
        invalid = post(
            f"{base}/contacts",
            "owner",
            {"first_name": "Sam", "email": "not-an-email " + LEAK_MARKER},
        )
        result["validation"] = {
            "no_email_or_phone": status_of({}),
            "bad_email": invalid.status_code,
            "bad_email_body": invalid.text,
            "stage_patient": status_of({"email": _email(), "lifecycle_stage": "patient"}),
            "blank_first_name": post(
                f"{base}/contacts", "owner", {"first_name": "  ", "email": _email()}
            ).status_code,
            "phone_only": status_of({"phone": "+31 20 123 4567"}),
            "nul_name": post(
                f"{base}/contacts", "owner", {"first_name": "Sa\0m", "email": _email()}
            ).status_code,
            "website_credentials": post(
                f"{base}/companies",
                "owner",
                # A made-up user name and password: the URL form under test.
                {
                    "name": "Creds BV",
                    "website": "https://user:secret@creds.example.test",  # pragma: allowlist secret
                },
            ).status_code,
            "normalised": contact(email="  Mixed.Case@Example.TEST ").json()["email"],
        }

        # --- Duplicates ----------------------------------------------------------------
        taken = contact(email="taken@example.test").json()
        duplicate = contact(email=" TAKEN@example.test")
        company = post(
            f"{base}/companies",
            "owner",
            {"name": "Acme", "website": "https://www.acme.example.test/about"},
        ).json()
        duplicate_company = post(
            f"{base}/companies", "owner", {"name": "Acme 2", "domain": "ACME.example.test."}
        )
        same_name = post(f"{base}/companies", "owner", {"name": "Acme"})
        result["duplicates"] = {
            "contact": [duplicate.status_code, duplicate.json()["detail"]],
            "taken_id": taken["id"],
            "company_domain": company["domain"],
            "company": [duplicate_company.status_code, duplicate_company.json()["detail"]],
            "company_id": company["id"],
            "same_name": same_name.status_code,
        }

        barrier = threading.Barrier(2)
        racing_email = _email()

        def race() -> int:
            barrier.wait()
            return contact(email=racing_email).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            result["concurrent_duplicate"] = sorted(
                f.result() for f in [pool.submit(race), pool.submit(race)]
            )

        # --- Versions --------------------------------------------------------------------
        record = contact().json()
        item = f"{base}/contacts/{record['id']}"
        no_version = client.patch(item, json={"city": "Delft"}, headers=auth("owner"))
        changed = client.patch(
            item, json={"city": "Delft"}, headers={**auth("owner"), "If-Match": '"1"'}
        )
        stale = client.patch(
            item, json={"city": "Leiden"}, headers={**auth("owner"), "If-Match": '"1"'}
        )
        unchanged = client.patch(
            item, json={"city": "Delft"}, headers={**auth("owner"), "If-Match": '"2"'}
        )
        cleared = client.patch(
            item, json={"email": None, "phone": None}, headers={**auth("owner"), "If-Match": '"2"'}
        )
        result["versions"] = {
            "missing": no_version.status_code,
            "changed": [
                changed.status_code,
                changed.json()["version"],
                changed.headers.get("etag"),
            ],
            "stale": [stale.status_code, stale.json()["detail"]],
            "unchanged": [unchanged.status_code, unchanged.json()["version"]],
            "cleared_both": [cleared.status_code, cleared.json()["detail"]],
            "malformed": client.patch(
                item, json={}, headers={**auth("owner"), "If-Match": "abc"}
            ).status_code,
        }

        # --- Idempotency ------------------------------------------------------------
        key = secrets.token_hex(16)
        body = {"first_name": "Once", "email": _email()}
        first = post(f"{base}/contacts", "owner", body, **{"Idempotency-Key": key})
        second = post(f"{base}/contacts", "owner", body, **{"Idempotency-Key": key})
        reused = post(
            f"{base}/contacts", "owner", {**body, "city": "Gouda"}, **{"Idempotency-Key": key}
        )
        result["idempotency"] = {
            "first": [
                first.status_code,
                first.json()["id"],
                first.headers.get("idempotent-replayed"),
            ],
            "second": [
                second.status_code,
                second.json()["id"],
                second.headers.get("idempotent-replayed"),
            ],
            "reused": [reused.status_code, reused.json()["detail"]],
            "email": body["email"],
        }

        # --- Archive and restore ------------------------------------------------------
        record = contact(email="archive.me@example.test").json()
        item = f"{base}/contacts/{record['id']}"
        archived = post(f"{item}/archive", "owner", None).json()
        again = post(f"{item}/archive", "owner", None).json()
        replacement = contact(email="archive.me@example.test")
        blocked = post(f"{item}/restore", "owner", None)
        result["archive"] = {
            "archived": [archived["archived_at"] is not None, archived["version"]],
            "again_version": again["version"],
            "replacement": replacement.status_code,
            "restore_blocked": [blocked.status_code, blocked.json()["detail"]],
        }

        # --- Links and owners ------------------------------------------------------------
        company_b = post(f"{other}/companies", "other_owner", {"name": "Other BV"}).json()["id"]
        acme = result["duplicates"]["company_id"]
        archived_company = post(f"{base}/companies", "owner", {"name": "Gone BV"}).json()["id"]
        post(f"{base}/companies/{archived_company}/archive", "owner", None)
        linked = contact(company_id=acme).json()
        result["links"] = {
            "foreign_company": [contact(company_id=company_b).status_code],
            "archived_company": [contact(company_id=archived_company).status_code],
            "linked_summary": linked["company"],
            "owner_outsider": contact(owner_user_id=str(users["outsider"])).status_code,
            "owner_member": contact(owner_user_id=str(users[Role.MEMBER.value])).status_code,
        }
        deleted = client.delete(f"{base}/companies/{acme}", headers=auth("owner"))
        after = client.get(f"{base}/contacts/{linked['id']}", headers=auth("owner")).json()
        result["links"]["company_deleted"] = deleted.status_code
        result["links"]["contact_after"] = [after["company_id"], after["company"]]

        # --- Idempotency keys belong to the acting member -----------------------------
        shared_key = secrets.token_hex(16)
        shared_body = {"first_name": "Shared", "phone": "+31 6 5555 0000"}
        by_owner = post(f"{base}/contacts", "owner", shared_body, **{"Idempotency-Key": shared_key})
        by_member = post(
            f"{base}/contacts", Role.MEMBER.value, shared_body, **{"Idempotency-Key": shared_key}
        )
        result["idempotency_members"] = {
            "owner": [by_owner.status_code, by_owner.json()["id"]],
            "member": [
                by_member.status_code,
                by_member.json()["id"],
                by_member.headers.get("idempotent-replayed"),
                by_member.json()["created_by_user_id"],
            ],
            "member_user": str(users[Role.MEMBER.value]),
        }

        # Two simultaneous requests by one member with one key: one record.
        same_key = secrets.token_hex(16)
        same_body = {"first_name": "Twice", "phone": "+31 6 5555 0001"}
        key_barrier = threading.Barrier(2)

        def same_key_create() -> list[Any]:
            key_barrier.wait()
            response = post(f"{base}/contacts", "owner", same_body, **{"Idempotency-Key": same_key})
            return [
                response.status_code,
                response.json().get("id"),
                response.headers.get("idempotent-replayed"),
            ]

        with ThreadPoolExecutor(max_workers=2) as pool:
            result["idempotency_concurrent"] = [
                f.result() for f in [pool.submit(same_key_create), pool.submit(same_key_create)]
            ]

        # --- Deleting a company is a versioned change of its contacts -----------------
        doomed = post(f"{base}/companies", "owner", {"name": "Doomed BV"}).json()["id"]
        kept = post(f"{base}/companies", "owner", {"name": "Kept BV"}).json()["id"]
        linked_a = contact(company_id=doomed).json()
        linked_b = contact(company_id=doomed).json()
        bystander = contact(company_id=kept).json()
        deleted_company = client.delete(f"{base}/companies/{doomed}", headers=auth("Admin"))
        after_a = client.get(f"{base}/contacts/{linked_a['id']}", headers=auth("owner")).json()
        after_b = client.get(f"{base}/contacts/{linked_b['id']}", headers=auth("owner")).json()
        after_bystander = client.get(
            f"{base}/contacts/{bystander['id']}", headers=auth("owner")
        ).json()
        stale_after_unlink = client.patch(
            f"{base}/contacts/{linked_a['id']}",
            json={"city": "Haarlem"},
            headers={**auth("owner"), "If-Match": '"1"'},
        )
        result["company_delete"] = {
            "status": deleted_company.status_code,
            "company_id": doomed,
            "admin": str(users["Admin"]),
            "before": [linked_a, linked_b],
            "after": [after_a, after_b],
            "bystander": [after_bystander["version"], after_bystander["company_id"], kept],
            "stale": [stale_after_unlink.status_code, stale_after_unlink.json()["detail"]],
        }

        # A contact update linking to a company races that company's deletion.
        rounds = []
        for _ in range(8):
            target_company = post(f"{base}/companies", "owner", {"name": "Race BV"}).json()["id"]
            racer = contact(email=None, phone="+31 6 5555 0002").json()["id"]
            race_barrier = threading.Barrier(2)

            def link(
                contact_id: str = racer,
                company_id: str = target_company,
                barrier: threading.Barrier = race_barrier,
            ) -> int:
                barrier.wait()
                return client.patch(
                    f"{base}/contacts/{contact_id}",
                    json={"company_id": company_id},
                    headers={**auth("owner"), "If-Match": '"1"'},
                ).status_code

            def drop(
                company_id: str = target_company, barrier: threading.Barrier = race_barrier
            ) -> int:
                barrier.wait()
                return client.delete(
                    f"{base}/companies/{company_id}", headers=auth("owner")
                ).status_code

            with ThreadPoolExecutor(max_workers=2) as pool:
                linking, dropping = pool.submit(link), pool.submit(drop)
                statuses = [linking.result(), dropping.result()]
            final = client.get(f"{base}/contacts/{racer}", headers=auth("owner")).json()
            company_left = client.get(
                f"{base}/companies/{target_company}", headers=auth("owner")
            ).status_code
            rounds.append(
                {
                    "patch": statuses[0],
                    "delete": statuses[1],
                    "company_id": final["company_id"],
                    "version": final["version"],
                    "company_status": company_left,
                    "company": target_company,
                }
            )
        result["race"] = rounds

        # --- A deleted workspace refuses writes ---------------------------------------
        bootstrap = SystemCaller(SystemAuthority.PLATFORM_BOOTSTRAP)
        operator_user = _new_user()
        operator = enroll_operator(operator_user, caller=bootstrap, reason="crm-app record test")
        grant_platform_permission(
            operator.id,
            PlatformPermission.TENANT_DELETE,
            caller=bootstrap,
            reason="crm-app record test",
        )
        transition_tenant_status(b.id, TenantStatus.DELETED, caller=UserCaller(operator_user))
        result["deleted_workspace"] = post(
            f"{other}/companies", "other_owner", {"name": "Late BV"}
        ).status_code

    print("RESULT " + json.dumps(result, default=str))


if __name__ == "__main__":
    main()
