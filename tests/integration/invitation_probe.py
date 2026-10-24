"""Drives the invitation flow end to end against the integration database
and prints one `RESULT <json>` line.

Run in a fresh interpreter by `tests/integration/test_invitations.py`
(SaaS-OS caches configuration per process). Workspaces and members are
created as in `record_route_probe`; invitees get sessions carrying the
verified email SaaS-OS checks at acceptance. Email mode uses SaaS-OS's
`FakeEmailProvider` (no network); no real email is ever sent. All values
are made up. Refuses to run unless ENVIRONMENT=test.
"""

from __future__ import annotations

import json
import os
import secrets
import uuid
from typing import Any
from urllib.parse import urlsplit

from fastapi.testclient import TestClient
from saas_os.core.authority import UserCaller
from saas_os.core.email import FakeEmailProvider
from saas_os.core.identity import add_tenant_membership, issue_session
from saas_os.core.rbac import assign_role

import crm_app.invitations
from crm_app.app import create_app
from crm_app.roles import Role
from tests.integration.workspace_route_probe import PROVISIONING, _new_user, _new_workspace


def _address(label: str) -> str:
    return f"{label}.{secrets.token_hex(5)}@example.test"


def main() -> None:  # noqa: PLR0915 - one scenario script, read top to bottom
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("invitation_probe runs only with ENVIRONMENT=test")
    a = _new_workspace("invite-a")
    b = _new_workspace("invite-b")
    users: dict[str, uuid.UUID] = {"Owner": a.owner_id, "other_owner": b.owner_id}
    for role in (Role.ADMIN, Role.MEMBER, Role.READ_ONLY):
        user = _new_user()
        membership = add_tenant_membership(a.id, user, caller=PROVISIONING)
        assign_role(a.id, membership.id, a.role_ids[role], caller=UserCaller(a.owner_id))
        users[role.value] = user
    users["outsider"] = _new_user()
    tokens = {name: issue_session(user)[1] for name, user in users.items()}

    invitee_email, stranger_email = _address("invitee"), _address("stranger")
    invitee, stranger = _new_user(), _new_user()
    tokens["invitee"] = issue_session(invitee, verified_email=invitee_email)[1]
    tokens["stranger"] = issue_session(stranger, verified_email=stranger_email)[1]
    tokens["unverified"] = issue_session(_new_user())[1]

    def auth(caller: str | None) -> dict[str, str]:
        return {"Authorization": f"Bearer {tokens[caller]}"} if caller else {}

    base = f"/v1/workspaces/{a.id}"
    result: dict[str, Any] = {
        "workspace": str(a.id),
        "invitee": str(invitee),
        "invitee_email": invitee_email,
        "secrets": [],
    }

    with TestClient(create_app(), follow_redirects=False) as client:

        def invite(email: str, role: str, caller: str | None = "Owner") -> Any:
            return client.post(
                f"{base}/invitations", json={"email": email, "role": role}, headers=auth(caller)
            )

        def accept(workspace: uuid.UUID, token: str, caller: str | None) -> int:
            return client.post(
                f"/v1/tenants/{workspace}/invitations/accept",
                json={"token": token},
                headers=auth(caller),
            ).status_code

        # --- Who may invite and see invitations ------------------------------------
        result["create"] = {
            name: invite(_address(name.lower()), "Member", name).status_code
            for name in ("Owner", "Admin", "Member", "Read-only", "outsider", "other_owner")
        }
        result["create"]["anonymous"] = invite(_address("anon"), "Member", None).status_code
        result["list"] = {
            name: client.get(f"{base}/invitations", headers=auth(name)).status_code
            for name in ("Owner", "Admin", "Member", "Read-only", "outsider")
        }
        result["owner_invites"] = {
            "admin_invites_owner": [
                invite(_address("o1"), "Owner", "Admin").status_code,
                invite(_address("o2"), "Owner", "Admin").json()["detail"],
            ],
            "owner_invites_owner": invite(_address("o3"), "Owner", "Owner").status_code,
        }

        # --- A manual-mode invitation (decision Q4) ---------------------------------
        created = invite(f"  {invitee_email.upper()} ", "Member")
        body = created.json()
        link = body["link"]
        split = urlsplit(link)
        token = split.fragment
        result["secrets"].append(token)
        result["manual"] = {
            "status": created.status_code,
            "cache": created.headers.get("cache-control"),
            "invitation": body["invitation"],
            "link_path": split.path,
            "link_origin": f"{split.scheme}://{split.netloc}",
            "token_length": len(token),
        }
        result["validation"] = {
            "duplicate": [
                invite(invitee_email, "Admin").status_code,
                invite(invitee_email, "Admin").json()["detail"],
            ],
            "bad_email": invite("not-an-address", "Member").status_code,
            "bad_role": invite(_address("r"), "Superuser").status_code,
            "extra_field": client.post(
                f"{base}/invitations",
                json={"email": _address("x"), "role": "Member", "tenant_id": str(b.id)},
                headers=auth("Owner"),
            ).status_code,
        }
        listing = client.get(f"{base}/invitations", headers=auth("Owner")).json()["items"]
        result["listed"] = next(i for i in listing if i["id"] == body["invitation"]["id"])
        result["listing_text"] = json.dumps(listing)

        # --- Acceptance (SaaS-OS's route) -------------------------------------------
        result["accept"] = {
            "anonymous": accept(a.id, token, None),
            "unverified_session": accept(a.id, token, "unverified"),
            "wrong_email": accept(a.id, token, "stranger"),
            "wrong_workspace": accept(b.id, token, "invitee"),
            "tampered": accept(a.id, token[:-2] + "xx", "invitee"),
            "invitee": accept(a.id, token, "invitee"),
            "again": accept(a.id, token, "invitee"),
        }
        members = client.get(f"{base}/members", headers=auth("Owner")).json()["items"]
        joined = next(m for m in members if m["user_id"] == str(invitee))
        result["after_accept"] = {
            "member": joined,
            "open_workspace": client.get(base, headers=auth("invitee")).status_code,
            "directory": [
                item["id"]
                for item in client.get("/v1/workspaces", headers=auth("invitee")).json()["items"]
            ],
            "status_listed": next(
                i["status"]
                for i in client.get(f"{base}/invitations", headers=auth("Owner")).json()["items"]
                if i["id"] == body["invitation"]["id"]
            ),
        }

        # --- Role confirmation by an Owner or Admin (decision Q5) --------------------
        confirm_path = f"{base}/members/{joined['membership_id']}/roles"
        result["confirm"] = {
            "by_member": client.post(
                confirm_path, json={"role": "Member"}, headers=auth("Member")
            ).status_code,
            "by_invitee": client.post(
                confirm_path, json={"role": "Member"}, headers=auth("invitee")
            ).status_code,
            "by_admin": client.post(
                confirm_path, json={"role": "Member"}, headers=auth("Admin")
            ).status_code,
            "open_workspace": client.get(base, headers=auth("invitee")).status_code,
        }

        # --- Revocation -----------------------------------------------------------------
        revoked = invite(_address("revoked"), "Read-only").json()
        revoked_token = urlsplit(revoked["link"]).fragment
        result["secrets"].append(revoked_token)
        revoke_path = f"{base}/invitations/{revoked['invitation']['id']}/revoke"
        result["revoke"] = {
            "by_member": client.post(revoke_path, headers=auth("Member")).status_code,
            "by_admin": client.post(revoke_path, headers=auth("Admin")).json()["status"],
            "again": client.post(revoke_path, headers=auth("Admin")).status_code,
            "accepted_one": client.post(
                f"{base}/invitations/{body['invitation']['id']}/revoke", headers=auth("Owner")
            ).status_code,
            "unknown": client.post(
                f"{base}/invitations/{uuid.uuid4()}/revoke", headers=auth("Owner")
            ).status_code,
            "other_workspace": client.post(
                f"/v1/workspaces/{b.id}/invitations/{revoked['invitation']['id']}/revoke",
                headers=auth("other_owner"),
            ).status_code,
        }

        # --- Email mode with SaaS-OS's fake provider (decision P2-F 3) -----------------
        fake = FakeEmailProvider()
        os.environ["INVITATION_DELIVERY"] = "email"
        crm_app.invitations.get_email_provider = lambda: fake  # type: ignore[assignment]
        crm_app.invitations.get_email_default_sender = lambda: "crm@example.test"  # type: ignore[assignment]
        emailed_to = _address("emailed")
        sent = invite(emailed_to, "Admin")
        message = fake.sent[0] if fake.sent else None
        result["email"] = {
            "status": sent.status_code,
            "link_in_response": sent.json()["link"],
            "delivery": sent.json()["invitation"]["delivery"],
            "messages": len(fake.sent),
            "to": list(message.to) if message else None,
            "link_in_body": bool(message and f"/app/invite/{a.id}#" in message.text_body),
        }
        if message:
            result["secrets"].append(message.text_body.split("#", 1)[1].split()[0])
        failing = FakeEmailProvider(fail=True)
        crm_app.invitations.get_email_provider = lambda: failing  # type: ignore[assignment]
        failed_to = _address("failed")
        failed = invite(failed_to, "Member")
        result["email_failure"] = {
            "status": failed.status_code,
            "detail": failed.json()["detail"],
            "status_listed": [
                i["status"]
                for i in client.get(f"{base}/invitations", headers=auth("Owner")).json()["items"]
                if i["email"] == failed_to
            ],
        }
        os.environ["INVITATION_DELIVERY"] = "manual"

    print("RESULT " + json.dumps(result, default=str))


if __name__ == "__main__":
    main()
