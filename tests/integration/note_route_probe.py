"""Calls the note routes as different callers against the integration
database and prints one `RESULT <json>` line.

Run in a fresh interpreter by `tests/integration/test_note_routes.py`
(SaaS-OS caches configuration per process). Workspaces and members are
created as in `record_route_probe`. All values are made up. Refuses to run
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
from saas_os.core.authority import UserCaller
from saas_os.core.identity import add_tenant_membership, issue_session
from saas_os.core.rbac import assign_role

from crm_app.app import create_app
from crm_app.roles import Role
from tests.integration.workspace_route_probe import PROVISIONING, _new_user, _new_workspace

# Text that must never reach an error body, an audit entry or a log line.
MARKER = "note-leak-marker-5e7a"


def _email() -> str:
    return f"person.{secrets.token_hex(6)}@example.test"


def main() -> None:  # noqa: PLR0915 - one scenario script, read top to bottom
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("note_route_probe runs only with ENVIRONMENT=test")
    a = _new_workspace("notes-a")
    b = _new_workspace("notes-b")
    users: dict[str, uuid.UUID] = {"owner": a.owner_id, "other_owner": b.owner_id}
    for name, role in (
        ("admin", Role.ADMIN),
        ("member", Role.MEMBER),
        ("member2", Role.MEMBER),
        ("read_only", Role.READ_ONLY),
    ):
        user = _new_user()
        membership = add_tenant_membership(a.id, user, caller=PROVISIONING)
        assign_role(a.id, membership.id, a.role_ids[role], caller=UserCaller(a.owner_id))
        users[name] = user
    users["outsider"] = _new_user()
    tokens = {name: issue_session(user)[1] for name, user in users.items()}

    def auth(caller: str | None) -> dict[str, str]:
        return {"Authorization": f"Bearer {tokens[caller]}"} if caller else {}

    base = f"/v1/workspaces/{a.id}"
    other = f"/v1/workspaces/{b.id}"
    result: dict[str, Any] = {
        "workspace": str(a.id),
        "users": {k: str(v) for k, v in users.items()},
    }

    with TestClient(create_app(), follow_redirects=False) as client:

        def post(path: str, body: object, caller: str | None = "owner", **headers: str) -> Any:
            return client.post(path, json=body, headers={**auth(caller), **headers})

        def patch(path: str, body: object, version: object, caller: str | None = "owner") -> Any:
            return client.patch(
                path, json=body, headers={**auth(caller), "If-Match": f'"{version}"'}
            )

        def delete(path: str, caller: str | None = "owner") -> Any:
            return client.delete(path, headers=auth(caller))

        def get(path: str, caller: str | None = "owner", **params: object) -> Any:
            return client.get(path, params=params, headers=auth(caller))

        contact = post(f"{base}/contacts", {"first_name": "Noted", "email": _email()}).json()
        record = f"{base}/contacts/{contact['id']}"
        collection = f"{record}/notes"

        def note(caller: str = "owner", text: str = "A note.") -> Any:
            return post(collection, {"body": text}, caller)

        # --- Who may add and read notes ------------------------------------------
        result["create"] = {
            name: note(name).status_code
            for name in ("owner", "admin", "member", "read_only", "outsider", "other_owner")
        }
        result["create"]["anonymous"] = post(collection, {"body": "x"}, None).status_code
        result["read"] = {
            name: get(collection, name).status_code
            for name in ("owner", "member", "read_only", "outsider", "other_owner")
        }
        result["read_only_view"] = [
            [n["can_edit"], n["can_delete"]] for n in get(collection, "read_only").json()["items"]
        ]

        # --- The author rule (D3) ------------------------------------------------------
        mine = note("member", "Member's own note.").json()
        item = f"{base}/notes/{mine['id']}"
        member_id = str(users["member"])

        def view(caller: str) -> dict[str, set[tuple[bool, bool]]]:
            """The caller's rights on the member's notes and on everyone else's."""
            seen: dict[str, set[tuple[bool, bool]]] = {"members": set(), "others": set()}
            for n in get(collection, caller).json()["items"]:
                group = "members" if n["author_user_id"] == member_id else "others"
                seen[group].add((n["can_edit"], n["can_delete"]))
            return seen

        member_view, admin_view = view("member"), view("admin")
        result["views"] = {
            "member_own": sorted(member_view["members"]),
            "member_others": sorted(member_view["others"]),
            "admin_all": sorted(admin_view["members"] | admin_view["others"]),
        }
        result["author_rule"] = {
            "member2_edit": [
                patch(item, {"body": "Taken over."}, 1, "member2").status_code,
                patch(item, {"body": "Taken over."}, 1, "member2").json()["detail"],
            ],
            "member2_delete": delete(item, "member2").status_code,
            "read_only_edit": patch(item, {"body": "No."}, 1, "read_only").status_code,
            "read_only_delete": delete(item, "read_only").status_code,
            "own_stale": patch(item, {"body": "Fixed."}, 7, "member").status_code,
            "own_edit": patch(item, {"body": "Fixed typo."}, 1, "member").json(),
            "same_text": patch(item, {"body": "Fixed typo."}, 2, "member").json()["version"],
            "admin_edit": patch(item, {"body": "Admin tidied."}, 2, "admin").json(),
            "missing_version": client.patch(
                item, json={"body": "x"}, headers=auth("member")
            ).status_code,
        }
        theirs = note("member", "Admin will delete this.").json()
        own_delete = note("member", "I will delete this.").json()
        result["deletes"] = {
            "admin_deletes_members": delete(f"{base}/notes/{theirs['id']}", "admin").status_code,
            "member_deletes_own": delete(f"{base}/notes/{own_delete['id']}", "member").status_code,
            "again": delete(f"{base}/notes/{own_delete['id']}", "member").status_code,
        }

        # --- Concurrent edits: one wins ------------------------------------------------
        contested = note("owner", "Contested.").json()
        contested_item = f"{base}/notes/{contested['id']}"
        barrier = threading.Barrier(2)

        def racing_edit(text: str) -> int:
            barrier.wait()
            return patch(contested_item, {"body": text}, 1).status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            result["concurrent_edit"] = sorted(
                f.result()
                for f in [pool.submit(racing_edit, "One"), pool.submit(racing_edit, "Two")]
            )

        # --- Text rules ----------------------------------------------------------------
        def status_of(body: object) -> int:
            return post(collection, body).status_code

        refused = post(collection, {"body": f"bell\x07 {MARKER}"})
        result["validation"] = {
            "empty": status_of({"body": ""}),
            "blank": status_of({"body": " \n\t "}),
            "too_long": status_of({"body": "x" * 10_001}),
            "control": refused.status_code,
            "control_body": refused.text,
            "nul": status_of({"body": "a\x00b"}),
            "unknown_field": status_of({"body": "ok", "author_user_id": str(users["member2"])}),
            "not_text": status_of({"body": 42}),
            "longest": status_of({"body": "y" * 10_000}),
        }
        crlf = post(collection, {"body": "  Line one\r\nLine two\rLine three \n"}).json()
        html = post(collection, {"body": '<img src=x onerror="alert(1)"> & <b>bold</b>'}).json()
        result["stored"] = {"crlf": crlf["body"], "html": html["body"]}

        # --- History (D4, D5) and the record's version -----------------------------------
        long_text = "z" * 300
        long_note = post(collection, {"body": long_text}).json()
        doomed = post(collection, {"body": f"Doomed {MARKER}"}).json()
        before = get(record).json()["version"]
        delete(f"{base}/notes/{doomed['id']}")
        entries = get(f"{record}/activity", limit=100).json()["items"]
        result["history"] = {
            "note_added_ids": [e["note_id"] for e in entries if e["kind"] == "note_added"],
            "long": next(
                [e["note_excerpt"], e["note_truncated"]]
                for e in entries
                if e["note_id"] == long_note["id"]
            ),
            "deleted_entries": sum(e["kind"] == "note_deleted" for e in entries),
            "doomed_id": doomed["id"],
            "text": json.dumps(entries),
        }
        result["record_version_unchanged"] = [before, get(record).json()["version"]]

        # --- Archived records (D8) -----------------------------------------------------
        kept = note("member", "Before archiving.").json()
        post(f"{record}/archive", None)
        archived_list = get(collection, "member").json()
        result["archived"] = {
            "add": [note("member").status_code, note("member").json()["detail"]],
            "edit": [
                patch(f"{base}/notes/{kept['id']}", {"body": "Changed."}, 1, "member").status_code,
                patch(f"{base}/notes/{kept['id']}", {"body": "Changed."}, 1, "member").json()[
                    "detail"
                ],
            ],
            "list": [
                archived_list["record_archived"],
                next(
                    [n["can_edit"], n["can_delete"]]
                    for n in archived_list["items"]
                    if n["id"] == kept["id"]
                ),
            ],
            "delete": delete(f"{base}/notes/{kept['id']}", "member").status_code,
        }
        post(f"{record}/restore", None)
        result["archived"]["after_restore"] = note("member").status_code

        # --- Idempotency -----------------------------------------------------------------
        key = secrets.token_hex(16)
        first = post(collection, {"body": "Once."}, "member", **{"Idempotency-Key": key})
        second = post(collection, {"body": "Once."}, "member", **{"Idempotency-Key": key})
        reused = post(collection, {"body": "Other."}, "member", **{"Idempotency-Key": key})
        by_other = post(collection, {"body": "Once."}, "member2", **{"Idempotency-Key": key})
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
            "other_member": [by_other.status_code, by_other.json()["id"]],
        }
        same_key = secrets.token_hex(16)
        key_barrier = threading.Barrier(2)

        def same_key_create() -> Any:
            key_barrier.wait()
            response = post(
                collection, {"body": "Twice?"}, "owner", **{"Idempotency-Key": same_key}
            )
            return [response.status_code, response.json().get("id")]

        with ThreadPoolExecutor(max_workers=2) as pool:
            result["idempotency_concurrent"] = [
                f.result() for f in [pool.submit(same_key_create), pool.submit(same_key_create)]
            ]
        result["twice_count"] = sum(
            n["body"] == "Twice?" for n in get(collection, limit=100).json()["items"]
        )

        # --- Other workspaces ------------------------------------------------------------
        target = note("owner", "Private to A.").json()
        result["cross"] = {
            "list_via_b": get(f"{other}/contacts/{contact['id']}/notes", "other_owner").status_code,
            "add_via_b": post(
                f"{other}/contacts/{contact['id']}/notes", {"body": "x"}, "other_owner"
            ).status_code,
            "edit_via_b": patch(
                f"{other}/notes/{target['id']}", {"body": "x"}, 1, "other_owner"
            ).status_code,
            "delete_via_b": delete(f"{other}/notes/{target['id']}", "other_owner").status_code,
            "edit_outsider": patch(
                f"{base}/notes/{target['id']}", {"body": "x"}, 1, "outsider"
            ).status_code,
            "unknown_note": patch(f"{base}/notes/{uuid.uuid4()}", {"body": "x"}, 1).status_code,
            "unknown_record": post(
                f"{base}/contacts/{uuid.uuid4()}/notes", {"body": "x"}
            ).status_code,
            "company_path_for_contact": get(f"{base}/companies/{contact['id']}/notes").status_code,
            "after": get(collection, limit=100).json()["items"][0]["body"],
        }

        # --- Paging ----------------------------------------------------------------------
        company = post(f"{base}/companies", {"name": "Paged BV"}).json()
        company_notes = f"{base}/companies/{company['id']}/notes"
        made = [post(company_notes, {"body": f"Page {i}"}).json()["id"] for i in range(5)]
        pages: list[list[str]] = []
        cursor: str | None = None
        while True:
            response = (
                get(company_notes, limit=2, cursor=cursor)
                if cursor
                else get(company_notes, limit=2)
            ).json()
            pages.append([n["id"] for n in response["items"]])
            cursor = response["next_cursor"]
            if not cursor:
                break
        result["paging"] = {"made": made, "pages": pages}
        result["cursor_other_record"] = get(
            collection, cursor=get(company_notes, limit=2).json()["next_cursor"]
        ).status_code
        result["company_deleted"] = [
            delete(f"{base}/companies/{company['id']}").status_code,
            get(company_notes).status_code,
            patch(f"{base}/notes/{made[0]}", {"body": "x"}, 1).status_code,
        ]

    print("RESULT " + json.dumps(result, default=str))


if __name__ == "__main__":
    main()
