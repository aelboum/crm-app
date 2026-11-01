"""Drives the Inbox search and paging (decision P6-C1); prints one
`RESULT <json>` line.

Run in a fresh interpreter by `tests/integration/test_conversation_search.py`.
Seeds throwaway workspaces; email sending stays off and no email reply is
made. Refuses to run unless ENVIRONMENT=test.
"""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import quote

from fastapi.testclient import TestClient
from saas_os.core.identity import issue_session

from crm_app.app import create_app
from crm_app.roles import Role
from tests.integration.opportunity_route_probe import _member
from tests.integration.workspace_route_probe import _new_user, _new_workspace


def main() -> None:  # noqa: PLR0915 - one scenario script, read top to bottom
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("conversation_search_probe runs only with ENVIRONMENT=test")
    os.environ.pop("EMAIL_SENDING_ENABLED", None)
    a = _new_workspace("search-a")
    b = _new_workspace("search-b")
    _, reader = _member(a, Role.READ_ONLY)
    tokens = {
        "owner": issue_session(a.owner_id)[1],
        "reader": reader,
        "other_owner": issue_session(b.owner_id)[1],
        "outsider": issue_session(_new_user())[1],
    }

    def auth(caller: str = "owner", version: int | None = None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {tokens[caller]}"}
        if version is not None:
            headers["If-Match"] = f'"{version}"'
        return headers

    result: dict[str, Any] = {}
    with TestClient(create_app(), follow_redirects=False) as client:

        def contact(base: str, caller: str, first: str, last: str, email: str) -> str:
            made = client.post(
                f"{base}/contacts",
                json={"first_name": first, "last_name": last, "email": email},
                headers=auth(caller),
            )
            return str(made.json()["id"])

        def thread(base: str, caller: str, who: str, subject: str, body: str) -> dict[str, Any]:
            made = client.post(
                f"{base}/conversations",
                json={
                    "contact_id": who,
                    "channel": "other",
                    "subject": subject,
                    "kind": "inbound",
                    "body": body,
                },
                headers=auth(caller),
            )
            return dict(made.json())

        base_a = f"/v1/workspaces/{a.id}"
        base_b = f"/v1/workspaces/{b.id}"
        ada = contact(base_a, "owner", "Ada", "Lovelace", "ada@example.test")
        grace = contact(base_a, "owner", "Grace", "Hopper", "grace@example.test")
        t1 = thread(base_a, "owner", ada, "Invoice overdue", "The parcel arrived broken")
        t2 = thread(base_a, "owner", ada, "Kitchen renovation", "When can you start?")
        client.post(
            f"{base_a}/conversations/{t2['id']}/messages",
            json={"kind": "note", "body": "Budget 50% approved"},
            headers=auth(),
        )
        closed = client.get(f"{base_a}/conversations/{t2['id']}", headers=auth()).json()
        client.patch(
            f"{base_a}/conversations/{t2['id']}",
            json={"status": "closed"},
            headers=auth(version=closed["version"]),
        )
        t3 = thread(base_a, "owner", grace, "Café crème order", "Two boxes, please")
        bob = contact(base_b, "other_owner", "Bob", "Lovelace", "bob@example.test")
        tb = thread(base_b, "other_owner", bob, "Invoice overdue", "The parcel arrived broken")
        names = {t1["id"]: "t1", t2["id"]: "t2", t3["id"]: "t3", tb["id"]: "tb"}

        def search(
            q: str, status: str = "all", caller: str = "owner", base: str = base_a
        ) -> list[str] | int:
            response = client.get(
                f"{base}/conversations?status={status}&q={quote(q, safe='')}",
                headers=auth(caller),
            )
            if response.status_code != 200:
                return response.status_code
            return sorted(names.get(i["id"], "?") for i in response.json()["items"])

        result["message_text"] = search("parcel")
        result["prefix_any_case"] = search("PARC")
        result["two_words"] = search("parcel broken")
        result["words_in_any_order"] = search("broken parcel")
        result["subject"] = search("renovation")
        result["closed_hidden_from_open"] = search("renovation", "open")
        result["closed_found_in_closed"] = search("renovation", "closed")
        result["note_text"] = search("budget")
        result["percent_in_text"] = search("50%")
        result["unicode"] = search("café")
        result["contact_last_name"] = search("lovelace")
        result["contact_first_name"] = search("Grace")
        result["contact_email"] = search("grace@exa")
        result["no_match"] = search("zebra")
        result["only_percent"] = search("%")
        result["only_underscore"] = search("_")
        result["quote_injection"] = search("' OR 1=1 --")
        result["query_syntax"] = search("zebra & !parcel | (x:*)")
        result["backslash"] = search("\\")
        result["blank"] = search("   ")
        result["reader"] = search("parcel", caller="reader")
        result["other_workspace_own"] = search("parcel", caller="other_owner", base=base_b)
        result["other_workspace_lastname"] = search("lovelace", caller="other_owner", base=base_b)
        result["other_owner_on_a"] = search("parcel", caller="other_owner")
        result["outsider_on_a"] = search("parcel", caller="outsider")
        result["too_long"] = search("x" * 101)
        result["nul"] = search("a\x00b")

        # Paging: one at a time visits every thread once, latest first.
        seen: list[str] = []
        cursor: str | None = None
        for _ in range(5):
            path = f"{base_a}/conversations?status=all&limit=1"
            if cursor:
                path += f"&cursor={cursor}"
            page = client.get(path, headers=auth()).json()
            seen += [names.get(i["id"], "?") for i in page["items"]]
            cursor = page["next_cursor"]
            if cursor is None:
                break
        result["paged"] = seen
        everything = client.get(f"{base_a}/conversations?status=all", headers=auth()).json()
        result["unpaged"] = [names.get(i["id"], "?") for i in everything["items"]]
        result["unpaged_cursor"] = everything["next_cursor"]
        first = client.get(f"{base_a}/conversations?status=all&limit=1", headers=auth()).json()
        result["cursor_other_filter"] = client.get(
            f"{base_a}/conversations?status=open&limit=1&cursor={first['next_cursor']}",
            headers=auth(),
        ).status_code
        result["cursor_garbage"] = client.get(
            f"{base_a}/conversations?cursor=not-a-cursor", headers=auth()
        ).status_code
        result["limit_zero"] = client.get(
            f"{base_a}/conversations?limit=0", headers=auth()
        ).status_code
        result["limit_over"] = client.get(
            f"{base_a}/conversations?limit=101", headers=auth()
        ).status_code
        result["search_paged"] = (
            client.get(
                f"{base_a}/conversations?status=all&q=lovelace&limit=1", headers=auth()
            ).json()["next_cursor"]
            is not None
        )

    print("RESULT " + json.dumps(result, default=str))


if __name__ == "__main__":
    main()
