"""Drives the form routes, members' and public, against the integration
database and prints one `RESULT <json>` line.

Run in a fresh interpreter by `tests/integration/test_form_routes.py`.
Seeds throwaway workspaces with made-up records. Refuses to run unless
ENVIRONMENT=test.
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Any

from fastapi.testclient import TestClient
from saas_os.core.identity import issue_session
from saas_os.infra.db import tenant_session_scope
from sqlalchemy import text

from crm_app.app import create_app
from crm_app.roles import Role
from tests.integration.opportunity_route_probe import _member
from tests.integration.workspace_route_probe import _new_workspace

FIELDS = [
    {"key": "first", "type": "text", "label": "First name", "required": True,
     "target": "first_name"},
    {"key": "last", "type": "text", "label": "Last name", "target": "last_name"},
    {"key": "email", "type": "email", "label": "Email", "required": True, "target": "email"},
    {"key": "topic", "type": "select", "label": "Topic", "options": ["Sales", "Support"]},
    {"key": "message", "type": "textarea", "label": "Message"},
]  # fmt: skip
WORDING = "Yes, email me about my enquiry."

_CONTACTS = """
SELECT c.id, c.first_name, c.last_name, c.email, c.source, c.lifecycle_stage,
       c.owner_user_id, c.version,
       (SELECT count(*) FROM crm_app.contact_tag t
         WHERE t.tenant_id = c.tenant_id AND t.contact_id = c.id) AS tags
  FROM crm_app.contact c
 WHERE c.tenant_id = :tenant AND lower(c.email) = :email
"""
_COUNTS = """
SELECT (SELECT count(*) FROM crm_app.form_submission WHERE tenant_id = :tenant),
       (SELECT count(*) FROM crm_app.consent_record WHERE tenant_id = :tenant),
       (SELECT count(*) FROM crm_app.contact WHERE tenant_id = :tenant)
"""


def _contacts(workspace: uuid.UUID, email: str) -> list[dict[str, Any]]:
    with tenant_session_scope(workspace) as session:
        rows = session.execute(text(_CONTACTS), {"tenant": workspace, "email": email})
        return [dict(row._mapping) for row in rows]


def _counts(workspace: uuid.UUID) -> list[int]:
    with tenant_session_scope(workspace) as session:
        return list(session.execute(text(_COUNTS), {"tenant": workspace}).one())


def main() -> None:  # noqa: PLR0915 - one scenario script, read top to bottom
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("form_route_probe runs only with ENVIRONMENT=test")
    a = _new_workspace("forms-a")
    b = _new_workspace("forms-b")
    admin_id, admin = _member(a, Role.ADMIN)
    _, member = _member(a, Role.MEMBER)
    _, reader = _member(a, Role.READ_ONLY)
    tokens = {
        "owner": issue_session(a.owner_id)[1],
        "admin": admin,
        "member": member,
        "reader": reader,
        "other_owner": issue_session(b.owner_id)[1],
    }

    def auth(caller: str, version: int | None = None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {tokens[caller]}"}
        if version is not None:
            headers["If-Match"] = f'"{version}"'
        return headers

    def key(value: str) -> dict[str, str]:
        return {"Idempotency-Key": value}

    base = f"/v1/workspaces/{a.id}/forms"
    result: dict[str, Any] = {
        "workspace": str(a.id),
        "owner_id": str(a.owner_id),
        "admin_id": str(admin_id),
    }
    with TestClient(create_app(), follow_redirects=False) as client:
        tag = client.post(
            f"/v1/workspaces/{a.id}/tags", json={"name": "Web lead"}, headers=auth("owner")
        ).json()
        foreign_tag = client.post(
            f"/v1/workspaces/{b.id}/tags", json={"name": "Theirs"}, headers=auth("other_owner")
        ).json()

        # --- Who may do what ------------------------------------------------------------
        result["read"] = {
            caller: client.get(base, headers=auth(caller)).status_code
            for caller in ("owner", "admin", "member", "reader", "other_owner")
        }
        result["create"] = {
            caller: client.post(
                base, json={"name": f"By {caller}", "fields": FIELDS}, headers=auth(caller)
            ).status_code
            for caller in ("owner", "admin", "member", "reader", "other_owner")
        }

        # --- Create and its refusals -------------------------------------------------------
        body = {"name": "  Contact us ", "fields": FIELDS, "tag_id": tag["id"]}
        body["consent_text"] = WORDING
        made = client.post(base, json=body, headers={**auth("admin"), **key("form-create-1")})
        form = made.json()
        result["created"] = [made.status_code, made.headers.get("etag"), form]
        again = client.post(base, json=body, headers={**auth("admin"), **key("form-create-1")})
        result["create_replay"] = [
            again.status_code,
            again.headers.get("idempotent-replayed"),
            again.json()["id"] == form["id"],
        ]
        first_only = [FIELDS[0]]
        result["refusals"] = {
            label: client.post(base, json=refused, headers=auth("owner")).json()["detail"]
            for label, refused in (
                ("blank_name", {"name": " ", "fields": FIELDS}),
                ("duplicate_key", {"name": "F", "fields": [FIELDS[0], FIELDS[0]]}),
                ("bad_target", {"name": "F", "fields": [{**FIELDS[3], "target": "email"}]}),
                ("consent_no_email", {"name": "F", "fields": first_only, "consent_text": "Ok"}),
                ("foreign_tag", {"name": "F", "fields": FIELDS, "tag_id": foreign_tag["id"]}),
                (
                    "foreign_owner",
                    {"name": "F", "fields": FIELDS, "contact_owner_user_id": str(b.owner_id)},
                ),
            )
        }
        result["invalid"] = {
            label: client.post(base, json=refused, headers=auth("owner")).status_code
            for label, refused in (
                ("no_fields", {"name": "F", "fields": []}),
                ("unknown_type", {"name": "F", "fields": [{**FIELDS[0], "type": "rating"}]}),
                ("extra", {"name": "F", "fields": FIELDS, "status": "published"}),
            )
        }

        # --- Publish -------------------------------------------------------------------------
        item = f"{base}/{form['id']}"
        public = f"/v1/public/forms/{a.id}/{form['public_key']}"
        result["draft_public"] = client.get(public).status_code
        result["publish_guards"] = {
            "no_if_match": client.patch(
                item, json={"status": "published"}, headers=auth("owner")
            ).status_code,
            "member": client.patch(
                item, json={"status": "published"}, headers=auth("member", 1)
            ).status_code,
            "stale": client.patch(
                item, json={"status": "published"}, headers=auth("owner", 9)
            ).status_code,
        }
        unpublishable = client.post(
            base, json={"name": "No first name", "fields": [FIELDS[2]]}, headers=auth("owner")
        ).json()
        result["unpublishable"] = client.patch(
            f"{base}/{unpublishable['id']}",
            json={"status": "published"},
            headers=auth("owner", 1),
        ).json()["detail"]
        published = client.patch(item, json={"status": "published"}, headers=auth("owner", 1))
        result["published"] = [published.status_code, published.json()["status"]]

        # --- The public page ---------------------------------------------------------------
        page = client.get(public)
        result["public"] = [page.status_code, page.json()]
        result["public_not_found"] = {
            "unknown_key": client.get(f"/v1/public/forms/{a.id}/{'x' * 22}").status_code,
            "malformed_key": client.get(f"/v1/public/forms/{a.id}/short").status_code,
            "other_workspace": client.get(
                f"/v1/public/forms/{b.id}/{form['public_key']}"
            ).status_code,
            "unknown_workspace": client.get(
                f"/v1/public/forms/{uuid.uuid4()}/{form['public_key']}"
            ).status_code,
        }

        # --- Submissions ----------------------------------------------------------------------
        answers = {
            "first": "Sam",
            "last": "Jansen",
            "email": "Sam@Example.TEST",
            "topic": "Sales",
            "message": "Please call me.",
        }
        result["submit_guards"] = {
            "no_key": client.post(public, json={"answers": answers}).status_code,
            "not_json": client.post(
                public,
                content=b"{",
                headers={**key("bad-json"), "Content-Type": "application/json"},
            ).status_code,
            "too_large": client.post(
                public, json={"answers": {"message": "x" * 17000}}, headers=key("too-large")
            ).status_code,
        }
        refused = client.post(
            public,
            json={"answers": {"first": "", "email": "not-an-email", "extra": "secret-value"}},
            headers=key("refused-1"),
        )
        result["refused"] = [refused.status_code, refused.json(), "secret-value" in refused.text]
        before = _counts(a.id)
        first = client.post(
            public, json={"answers": answers, "consent": True}, headers=key("visit-1")
        )
        result["first"] = [first.status_code, first.json()]
        replay = client.post(
            public, json={"answers": answers, "consent": True}, headers=key("visit-1")
        )
        reused = client.post(
            public, json={"answers": {**answers, "topic": "Support"}}, headers=key("visit-1")
        )
        result["replay"] = [replay.status_code, reused.status_code, reused.json()]
        result["after_first"] = [before, _counts(a.id)]
        result["contact_after_first"] = _contacts(a.id, "sam@example.test")
        # The same person again, with a different name and no consent: matched,
        # never changed, the tag not added twice.
        second = client.post(
            public,
            json={"answers": {**answers, "first": "Samuel", "email": "sam@example.test"}},
            headers=key("visit-2"),
        )
        result["second"] = second.status_code
        result["contact_after_second"] = _contacts(a.id, "sam@example.test")
        result["after_second"] = _counts(a.id)
        bot = client.post(
            public,
            json={"answers": {"first": "Bot", "email": "bot@example.test"}, "website": "x"},
            headers=key("bot-1"),
        )
        result["honeypot"] = [bot.status_code, bot.json(), _counts(a.id)]

        # --- Reading submissions and consent ------------------------------------------------
        listed = client.get(f"{item}/submissions", headers=auth("reader"))
        result["submissions"] = [listed.status_code, listed.json()]
        page_one = client.get(f"{item}/submissions", params={"limit": 1}, headers=auth("owner"))
        cursor = page_one.json()["next_cursor"]
        page_two = client.get(
            f"{item}/submissions", params={"limit": 1, "cursor": cursor}, headers=auth("owner")
        ).json()
        result["submission_paging"] = [
            page_one.json()["items"][0]["id"],
            page_two["items"][0]["id"],
            page_two["next_cursor"],
        ]
        result["bad_cursor"] = client.get(
            f"{item}/submissions", params={"cursor": "x"}, headers=auth("owner")
        ).status_code
        contact_id = str(result["contact_after_first"][0]["id"])
        consent = client.get(
            f"/v1/workspaces/{a.id}/contacts/{contact_id}/consent", headers=auth("reader")
        )
        result["consent"] = [consent.status_code, consent.json()]
        result["form_after"] = client.get(item, headers=auth("owner")).json()

        # --- Another workspace ----------------------------------------------------------------
        theirs = client.post(
            f"/v1/workspaces/{b.id}/forms",
            json={"name": "Secret form", "fields": FIELDS},
            headers=auth("other_owner"),
        ).json()
        foreign = f"{base}/{theirs['id']}"
        result["foreign"] = {
            "get": client.get(foreign, headers=auth("owner")).status_code,
            "patch": client.patch(
                foreign, json={"name": "Mine"}, headers=auth("owner", 1)
            ).status_code,
            "delete": client.delete(foreign, headers=auth("owner")).status_code,
            "submissions": client.get(f"{foreign}/submissions", headers=auth("owner")).status_code,
            "listed": "Secret form" in client.get(base, headers=auth("owner")).text,
            "consent": client.get(
                f"/v1/workspaces/{b.id}/contacts/{contact_id}/consent",
                headers=auth("other_owner"),
            ).status_code,
            "submissions_of_a": client.get(
                f"/v1/workspaces/{b.id}/forms/{form['id']}/submissions",
                headers=auth("other_owner"),
            ).status_code,
        }

        # --- Unpublish and delete ----------------------------------------------------------
        version = result["form_after"]["version"]
        client.patch(item, json={"status": "draft"}, headers=auth("owner", version))
        result["unpublished"] = [
            client.get(public).status_code,
            client.post(public, json={"answers": answers}, headers=key("visit-3")).status_code,
        ]
        result["delete"] = {
            "member": client.delete(item, headers=auth("member")).status_code,
            "admin": client.delete(item, headers=auth("admin")).status_code,
            "again": client.delete(item, headers=auth("admin")).status_code,
        }
        result["after_delete"] = _counts(a.id)
        result["consent_after_delete"] = client.get(
            f"/v1/workspaces/{a.id}/contacts/{contact_id}/consent", headers=auth("owner")
        ).json()
        result["form_id"] = form["id"]
        result["contact_id"] = contact_id

    print("RESULT " + json.dumps(result, default=str))


if __name__ == "__main__":
    main()
