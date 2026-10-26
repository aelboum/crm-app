"""Puts tags on contacts and companies against the integration database,
filters the lists and exports by them, and prints one `RESULT <json>` line.

Run in a fresh interpreter by `tests/integration/test_record_tags.py`.
Seeds made-up records into throwaway workspaces. Refuses to run unless
ENVIRONMENT=test.
"""

from __future__ import annotations

import csv
import io
import json
import os
from typing import Any

from fastapi.testclient import TestClient
from saas_os.core.identity import issue_session

from crm_app.app import create_app
from crm_app.roles import Role
from tests.integration.contact_export_probe import _member
from tests.integration.workspace_route_probe import _new_workspace


def _ids(response: Any) -> list[str]:
    body = response.content.decode("utf-8").removeprefix("﻿")
    return [row[0] for row in list(csv.reader(io.StringIO(body, newline="")))[1:]]


def main() -> None:  # noqa: PLR0915 - one scenario script, read top to bottom
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("record_tag_probe runs only with ENVIRONMENT=test")
    a = _new_workspace("record-tags-a")
    b = _new_workspace("record-tags-b")
    tokens = {
        "owner": issue_session(a.owner_id)[1],
        "member": _member(a, Role.MEMBER),
        "reader": _member(a, Role.READ_ONLY),
        "other_owner": issue_session(b.owner_id)[1],
    }

    def auth(caller: str, version: int | None = None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {tokens[caller]}"}
        if version is not None:
            headers["If-Match"] = str(version)
        return headers

    base = f"/v1/workspaces/{a.id}"
    result: dict[str, Any] = {"workspace": str(a.id)}
    with TestClient(create_app(), follow_redirects=False) as client:

        def post(path: str, body: dict[str, object], caller: str = "owner") -> dict[str, Any]:
            response = client.post(path, json=body, headers=auth(caller))
            assert response.status_code == 201, response.text
            return response.json()

        vip = post(f"{base}/tags", {"name": "VIP"})
        hot = post(f"{base}/tags", {"name": "hot lead"})
        cold = post(f"{base}/tags", {"name": "Cold"})
        foreign = post(f"/v1/workspaces/{b.id}/tags", {"name": "Foreign"}, "other_owner")
        sam = post(f"{base}/contacts", {"first_name": "Sam", "email": "sam@example.test"})
        ria = post(f"{base}/contacts", {"first_name": "Ria", "email": "ria@example.test"})
        ann = post(f"{base}/contacts", {"first_name": "Ann", "email": "ann@example.test"})
        acme = post(f"{base}/companies", {"name": "Acme"})
        zeta = post(f"{base}/companies", {"name": "Zeta"})
        contact = f"{base}/contacts/{sam['id']}/tags"

        # --- Who may tag, and the version -------------------------------------------------
        body = {"tag_ids": [vip["id"], hot["id"]]}
        result["reader"] = client.put(contact, json=body, headers=auth("reader", 1)).status_code
        result["other_owner"] = client.put(
            contact, json=body, headers=auth("other_owner", 1)
        ).status_code
        result["no_version"] = client.put(contact, json=body, headers=auth("member")).status_code
        stale = client.put(contact, json=body, headers=auth("member", 9))
        result["stale"] = [stale.status_code, stale.json()]
        tagged = client.put(
            contact, json={"tag_ids": [vip["id"], hot["id"], vip["id"]]}, headers=auth("member", 1)
        )
        result["tagged"] = [tagged.status_code, tagged.json(), tagged.headers.get("etag")]
        same = client.put(contact, json=body, headers=auth("owner", 2))
        result["same"] = [same.status_code, same.json()["version"]]

        # --- Which tags ---------------------------------------------------------------
        result["unknown_tag"] = client.put(
            contact, json={"tag_ids": [vip["id"], foreign["id"]]}, headers=auth("owner", 2)
        ).json()
        result["too_many"] = client.put(
            contact,
            json={"tag_ids": [vip["id"]] * 21},
            headers=auth("owner", 2),
        ).status_code
        result["extra_field"] = client.put(
            contact, json={"tag_ids": [], "names": ["x"]}, headers=auth("owner", 2)
        ).status_code
        result["foreign_record"] = client.put(
            f"/v1/workspaces/{b.id}/contacts/{sam['id']}/tags",
            json={"tag_ids": []},
            headers=auth("other_owner", 2),
        ).json()

        # --- More tags, so the filters have something to choose between ---------------
        client.put(
            f"{base}/contacts/{ria['id']}/tags",
            json={"tag_ids": [cold["id"]]},
            headers=auth("owner", 1),
        )
        client.put(
            f"{base}/companies/{acme['id']}/tags",
            json={"tag_ids": [hot["id"]]},
            headers=auth("owner", 1),
        )
        company = client.put(
            f"{base}/companies/{zeta['id']}/tags",
            json={"tag_ids": [vip["id"], cold["id"]]},
            headers=auth("member", 1),
        )
        result["company"] = [company.status_code, company.json()]
        cleared = client.put(contact, json={"tag_ids": []}, headers=auth("owner", 2))
        result["cleared"] = [cleared.json()["tags"], cleared.json()["version"]]
        restored = client.put(contact, json=body, headers=auth("owner", 3))
        result["restored"] = restored.json()["version"]

        # --- Lists, details and exports ------------------------------------------------
        result["detail"] = client.get(f"{base}/contacts/{sam['id']}", headers=auth("reader")).json()
        listed = client.get(f"{base}/contacts", headers=auth("reader")).json()["items"]
        result["listed_tags"] = {item["first_name"]: item["tags"] for item in listed}

        def contacts(*tag_ids: str) -> list[str]:
            response = client.get(
                f"{base}/contacts", params={"tag_id": list(tag_ids)}, headers=auth("reader")
            )
            assert response.status_code == 200, response.text
            return [item["first_name"] for item in response.json()["items"]]

        def companies(*tag_ids: str) -> list[str]:
            response = client.get(
                f"{base}/companies", params={"tag_id": list(tag_ids)}, headers=auth("reader")
            )
            return [item["name"] for item in response.json()["items"]]

        result["filters"] = {
            "vip": contacts(vip["id"]),
            "vip_or_cold": contacts(vip["id"], cold["id"]),
            "foreign": contacts(foreign["id"]),
            "companies_hot": companies(hot["id"]),
            "companies_vip_or_hot": companies(vip["id"], hot["id"]),
            "untagged": contacts(),
        }
        result["bad_filter"] = client.get(
            f"{base}/contacts", params={"tag_id": "not-a-uuid"}, headers=auth("reader")
        ).status_code
        page = client.get(
            f"{base}/contacts",
            params={"tag_id": [vip["id"], cold["id"]], "limit": 1},
            headers=auth("reader"),
        ).json()
        second = client.get(
            f"{base}/contacts",
            params={"tag_id": [vip["id"], cold["id"]], "limit": 1, "cursor": page["next_cursor"]},
            headers=auth("reader"),
        ).json()
        result["paged"] = [
            [item["first_name"] for item in page["items"]],
            [item["first_name"] for item in second["items"]],
            page["total"],
        ]
        result["exports"] = {
            "contacts": _ids(
                client.get(
                    f"{base}/contacts/export.csv",
                    params={"tag_id": [vip["id"], cold["id"]]},
                    headers=auth("owner"),
                )
            ),
            "companies": _ids(
                client.get(
                    f"{base}/companies/export.csv",
                    params={"tag_id": hot["id"]},
                    headers=auth("owner"),
                )
            ),
        }
        result["ids"] = {
            "sam": sam["id"],
            "ria": ria["id"],
            "ann": ann["id"],
            "acme": acme["id"],
            "zeta": zeta["id"],
            "vip": vip["id"],
            "hot": hot["id"],
            "cold": cold["id"],
        }
    print("RESULT " + json.dumps(result))


if __name__ == "__main__":
    main()
