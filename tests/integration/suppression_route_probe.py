"""Drives the suppression and consent routes against the integration
database and prints one `RESULT <json>` line.

Run in a fresh interpreter by `tests/integration/test_suppression_routes.py`.
Seeds throwaway workspaces with made-up records. Refuses to run unless
ENVIRONMENT=test.
"""

from __future__ import annotations

import json
import os
from typing import Any

from fastapi.testclient import TestClient
from saas_os.core.identity import issue_session

from crm_app.app import create_app
from crm_app.roles import Role
from tests.integration.opportunity_route_probe import _member
from tests.integration.workspace_route_probe import _new_workspace

CALLERS = ("owner", "admin", "member", "reader", "other_owner")


def main() -> None:  # noqa: PLR0915 - one scenario script, read top to bottom
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("suppression_route_probe runs only with ENVIRONMENT=test")
    a = _new_workspace("suppression-a")
    b = _new_workspace("suppression-b")
    admin_id, admin = _member(a, Role.ADMIN)
    member_id, member = _member(a, Role.MEMBER)
    _, reader = _member(a, Role.READ_ONLY)
    tokens = {
        "owner": issue_session(a.owner_id)[1],
        "admin": admin,
        "member": member,
        "reader": reader,
        "other_owner": issue_session(b.owner_id)[1],
    }

    def auth(caller: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {tokens[caller]}"}

    base = f"/v1/workspaces/{a.id}/suppressions"
    result: dict[str, Any] = {
        "workspace": str(a.id),
        "admin_id": str(admin_id),
        "member_id": str(member_id),
    }
    with TestClient(create_app(), follow_redirects=False) as client:

        def contact(body: dict[str, Any]) -> str:
            made = client.post(f"/v1/workspaces/{a.id}/contacts", json=body, headers=auth("owner"))
            return str(made.json()["id"])

        carol = contact({"first_name": "Carol", "email": "Carol@Example.TEST"})
        sam = contact({"first_name": "Sam", "email": "sam@example.test"})
        nomail = contact({"first_name": "Nomail", "phone": "+31 20 555 0101"})
        status = f"/v1/workspaces/{a.id}/contacts/{carol}/email-status"
        consent = f"/v1/workspaces/{a.id}/contacts/{carol}/consent"

        # --- Who may do what ------------------------------------------------------------
        result["read"] = {
            caller: client.get(base, headers=auth(caller)).status_code for caller in CALLERS
        }
        result["add"] = {
            caller: client.post(
                base, json={"emails": [f"{caller}@example.test"]}, headers=auth(caller)
            ).status_code
            for caller in CALLERS
        }

        # --- Adding ------------------------------------------------------------------------
        first = client.post(
            base,
            json={
                "emails": [" Sam@Example.TEST ", "ada@example.test", "sam@example.test"],
                "reason": "bounced",
                "note": "From the old newsletter tool.",
            },
            headers=auth("admin"),
        )
        result["first"] = [first.status_code, first.json()]
        again = client.post(
            base, json={"emails": ["sam@example.test", "new@example.test"]}, headers=auth("owner")
        )
        result["again"] = [again.status_code, again.json()]
        refused = client.post(
            base, json={"emails": ["ok@example.test", "secret-bad-value"]}, headers=auth("owner")
        )
        result["refused"] = [
            refused.status_code,
            refused.json(),
            "secret-bad-value" in refused.text,
        ]
        result["invalid"] = {
            "empty": client.post(base, json={"emails": []}, headers=auth("owner")).status_code,
            "too_many": client.post(
                base,
                json={"emails": [f"x{n}@example.test" for n in range(1001)]},
                headers=auth("owner"),
            ).status_code,
            "reason": client.post(
                base,
                json={"emails": ["r@example.test"], "reason": "annoyed"},
                headers=auth("owner"),
            ).status_code,
            "note": client.post(
                base,
                json={"emails": ["r@example.test"], "note": "tab\there"},
                headers=auth("owner"),
            ).status_code,
        }

        # --- Listing -------------------------------------------------------------------------
        listed = client.get(base, headers=auth("member"))
        result["listed"] = [listed.status_code, listed.json()]
        result["search"] = client.get(
            base, params={"search": " ADA "}, headers=auth("owner")
        ).json()["items"]
        page_one = client.get(base, params={"limit": 2}, headers=auth("owner")).json()
        page_two = client.get(
            base, params={"limit": 2, "cursor": page_one["next_cursor"]}, headers=auth("owner")
        ).json()
        result["paging"] = [
            [item["email"] for item in page_one["items"]],
            [item["email"] for item in page_two["items"]],
        ]
        result["bad_cursor"] = client.get(
            base, params={"cursor": "x"}, headers=auth("owner")
        ).status_code
        result["wrong_cursor"] = client.get(
            base, params={"cursor": page_one["next_cursor"], "search": "ada"}, headers=auth("owner")
        ).status_code

        # --- A contact's consent ---------------------------------------------------------
        result["status_before"] = client.get(status, headers=auth("reader")).json()
        result["record_rights"] = {
            "reader": client.post(
                consent, json={"wording": "Yes, email me."}, headers=auth("reader")
            ).status_code,
            "blank": client.post(
                consent, json={"wording": " "}, headers=auth("member")
            ).status_code,
            "no_email": client.post(
                f"/v1/workspaces/{a.id}/contacts/{nomail}/consent",
                json={"wording": "Yes, email me."},
                headers=auth("member"),
            ).json(),
        }
        recorded = client.post(
            consent, json={"wording": " Yes, email me about offers. "}, headers=auth("member")
        )
        result["recorded"] = [recorded.status_code, recorded.json()]
        withdrawn = client.post(
            f"{consent}/withdraw", json={"note": "Asked by phone."}, headers=auth("member")
        )
        result["withdrawn"] = [withdrawn.status_code, withdrawn.json()]
        result["carol_listed"] = client.get(
            base, params={"search": "carol"}, headers=auth("owner")
        ).json()["items"]
        result["regranted"] = client.post(
            consent, json={"wording": "Yes again."}, headers=auth("member")
        ).json()
        result["history"] = client.get(consent, headers=auth("reader")).json()["items"]
        # Sam was suppressed as bounced; withdrawing keeps that first reason.
        client.post(
            f"/v1/workspaces/{a.id}/contacts/{sam}/consent/withdraw",
            json={},
            headers=auth("member"),
        )
        result["sam_listed"] = client.get(
            base, params={"search": "sam@"}, headers=auth("owner")
        ).json()["items"]
        result["nomail_withdrawn"] = client.post(
            f"/v1/workspaces/{a.id}/contacts/{nomail}/consent/withdraw",
            json={},
            headers=auth("member"),
        ).json()

        # --- Another workspace -------------------------------------------------------------
        carol_row = result["carol_listed"][0]["id"]
        result["foreign"] = {
            "list": client.get(base, headers=auth("other_owner")).status_code,
            "remove": client.delete(f"{base}/{carol_row}", headers=auth("other_owner")).status_code,
            "remove_via_b": client.delete(
                f"/v1/workspaces/{b.id}/suppressions/{carol_row}", headers=auth("other_owner")
            ).status_code,
            "status": client.get(status, headers=auth("other_owner")).status_code,
            "status_via_b": client.get(
                f"/v1/workspaces/{b.id}/contacts/{carol}/email-status", headers=auth("other_owner")
            ).status_code,
            "withdraw_via_b": client.post(
                f"/v1/workspaces/{b.id}/contacts/{carol}/consent/withdraw",
                json={},
                headers=auth("other_owner"),
            ).status_code,
            "b_list": client.get(
                f"/v1/workspaces/{b.id}/suppressions", headers=auth("other_owner")
            ).json()["total"],
        }

        # --- Removing ------------------------------------------------------------------------
        result["remove"] = {
            "member": client.delete(f"{base}/{carol_row}", headers=auth("member")).status_code,
            "admin": client.delete(f"{base}/{carol_row}", headers=auth("admin")).status_code,
            "again": client.delete(f"{base}/{carol_row}", headers=auth("admin")).status_code,
        }
        result["status_after_remove"] = client.get(status, headers=auth("owner")).json()
        result["carol"] = carol
        result["sam"] = sam
        result["carol_row"] = carol_row

    print("RESULT " + json.dumps(result, default=str))


if __name__ == "__main__":
    main()
