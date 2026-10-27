"""Drives the deal routes against the integration database and prints one
`RESULT <json>` line.

Run in a fresh interpreter by `tests/integration/test_opportunity_routes.py`.
Seeds throwaway workspaces with made-up records. Refuses to run unless
ENVIRONMENT=test.
"""

from __future__ import annotations

import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from fastapi.testclient import TestClient
from saas_os.core.authority import UserCaller
from saas_os.core.identity import add_tenant_membership, issue_session
from saas_os.core.rbac import assign_role
from saas_os.infra.db import tenant_session_scope
from sqlalchemy import text

from crm_app import opportunities, pipelines
from crm_app.app import create_app
from crm_app.records import RecordError, Scope
from crm_app.roles import Role
from tests.integration.workspace_route_probe import PROVISIONING, _new_user, _new_workspace

_SQL = {
    "stages_in": "SELECT count(*) FROM crm_app.opportunity WHERE tenant_id = :tenant"
    " AND stage_id = :stage",
    "idle": "UPDATE crm_app.opportunity SET stage_entered_at = now() - interval '9 days'"
    " WHERE tenant_id = :tenant AND id = :deal",
    "archive": "UPDATE crm_app.contact SET archived_at = now() WHERE tenant_id = :tenant"
    " AND id = :contact",
}


def _sql(workspace: uuid.UUID, name: str, **params: object) -> Any:
    with tenant_session_scope(workspace) as session:
        result = session.execute(text(_SQL[name]), {"tenant": workspace, **params})
        return result.scalar_one() if name == "stages_in" else None


def _member(workspace: Any, role: Role) -> tuple[uuid.UUID, str]:
    user = _new_user()
    membership = add_tenant_membership(workspace.id, user, caller=PROVISIONING)
    assign_role(
        workspace.id, membership.id, workspace.role_ids[role], caller=UserCaller(workspace.owner_id)
    )
    return user, issue_session(user)[1]


def main() -> None:  # noqa: PLR0915 - one scenario script, read top to bottom
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("opportunity_route_probe runs only with ENVIRONMENT=test")
    a = _new_workspace("deals-a")
    b = _new_workspace("deals-b")
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

    def auth(caller: str, version: int | None = None, **extra: str) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {tokens[caller]}", **extra}
        if version is not None:
            headers["If-Match"] = f'"{version}"'
        return headers

    base = f"/v1/workspaces/{a.id}/opportunities"
    result: dict[str, Any] = {"workspace": str(a.id)}
    with TestClient(create_app(), follow_redirects=False) as client:
        pipeline = client.get(f"/v1/workspaces/{a.id}/pipelines", headers=auth("owner")).json()
        stages = [s["id"] for s in pipeline["items"][0]["stages"]]
        pipe_b = client.get(f"/v1/workspaces/{b.id}/pipelines", headers=auth("other_owner"))
        foreign_stage = pipe_b.json()["items"][0]["stages"][0]["id"]
        contact = client.post(
            f"/v1/workspaces/{a.id}/contacts",
            json={"first_name": "Sam", "last_name": "Jansen", "email": "sam@example.test"},
            headers=auth("owner"),
        ).json()
        company = client.post(
            f"/v1/workspaces/{a.id}/companies", json={"name": "Acme"}, headers=auth("owner")
        ).json()
        archived = client.post(
            f"/v1/workspaces/{a.id}/contacts",
            json={"first_name": "Old", "email": "old@example.test"},
            headers=auth("owner"),
        ).json()
        _sql(a.id, "archive", contact=archived["id"])
        foreign_contact = client.post(
            f"/v1/workspaces/{b.id}/contacts",
            json={"first_name": "Bo", "email": "bo@example.test"},
            headers=auth("other_owner"),
        ).json()
        foreign_company = client.post(
            f"/v1/workspaces/{b.id}/companies", json={"name": "Other"}, headers=auth("other_owner")
        ).json()

        # --- Who may do what -------------------------------------------------------------
        result["read"] = {
            caller: client.get(base, headers=auth(caller)).status_code
            for caller in ("owner", "admin", "member", "reader", "other_owner")
        }
        result["anonymous"] = client.get(base).status_code
        result["create"] = {
            caller: client.post(
                base, json={"title": f"By {caller}"}, headers=auth(caller)
            ).status_code
            for caller in ("owner", "admin", "member", "reader", "other_owner")
        }

        # --- Create: defaults, money, references ------------------------------------------
        full = client.post(
            base,
            json={
                "title": "  Website redesign ",
                "amount": "12500.5",
                "stage_id": stages[1],
                "owner_user_id": str(member_id),
                "expected_close_date": "2026-12-15",
                "contact_id": contact["id"],
                "company_id": company["id"],
            },
            headers=auth("member"),
        )
        deal = full.json()
        result["created"] = [full.status_code, full.headers.get("etag"), deal]
        bare = client.post(base, json={"title": "Bare"}, headers=auth("owner")).json()
        result["bare"] = bare
        result["money"] = {
            label: [response.status_code, response.json().get("detail")]
            for label, response in (
                (
                    label,
                    client.post(base, json={"title": "M", "amount": raw}, headers=auth("owner")),
                )
                for label, raw in (
                    ("three_decimals", "10.505"),
                    ("negative", "-1"),
                    ("number", 12500),
                    ("exponent", "1e3"),
                    ("thirteen_digits", "1000000000000"),
                    ("comma", "1,5"),
                    ("leading_zero", "01"),
                )
            )
        }
        result["money_max"] = client.post(
            base, json={"title": "Max", "amount": "999999999999.99"}, headers=auth("owner")
        ).json()["amount"]
        result["references"] = {
            label: client.post(base, json={"title": "R", **body}, headers=auth("owner")).json()
            for label, body in (
                ("foreign_stage", {"stage_id": foreign_stage}),
                ("unknown_stage", {"stage_id": str(uuid.uuid4())}),
                ("foreign_contact", {"contact_id": foreign_contact["id"]}),
                ("archived_contact", {"contact_id": archived["id"]}),
                ("foreign_company", {"company_id": foreign_company["id"]}),
                ("foreign_owner", {"owner_user_id": str(b.owner_id)}),
            )
        }
        result["invalid"] = {
            label: client.post(base, json=body, headers=auth("owner")).status_code
            for label, body in (
                ("missing_title", {}),
                ("blank_title", {"title": "  "}),
                ("long_title", {"title": "x" * 201}),
                ("control_title", {"title": "a\nb"}),
                ("bad_date", {"title": "D", "expected_close_date": "15/12/2026"}),
                ("extra", {"title": "E", "currency": "USD"}),
                ("outcome_on_create", {"title": "E", "outcome": "won"}),
            )
        }

        # --- Idempotent create --------------------------------------------------------------
        key = "deal-create-0001"
        first = client.post(
            base, json={"title": "Once"}, headers={**auth("owner"), "Idempotency-Key": key}
        )
        again = client.post(
            base, json={"title": "Once"}, headers={**auth("owner"), "Idempotency-Key": key}
        )
        other = client.post(
            base, json={"title": "Twice"}, headers={**auth("owner"), "Idempotency-Key": key}
        )
        result["idempotent"] = [
            first.status_code,
            again.status_code,
            again.headers.get("idempotent-replayed"),
            first.json()["id"] == again.json()["id"],
            other.status_code,
            other.json()["detail"],
        ]

        # --- Updates ---------------------------------------------------------------------------
        item = f"{base}/{deal['id']}"
        result["update_no_version"] = client.patch(
            item, json={"title": "X"}, headers=auth("owner")
        ).status_code
        stale = client.patch(item, json={"title": "X"}, headers=auth("owner", 9))
        result["update_stale"] = [stale.status_code, stale.json()["detail"]]
        result["update_reader"] = client.patch(
            item, json={"title": "X"}, headers=auth("reader", 1)
        ).status_code
        changed = client.patch(
            item,
            json={"title": "Website rebuild", "amount": "13000", "stage_id": stages[2]},
            headers=auth("member", 1),
        ).json()
        result["changed"] = [
            changed["title"],
            changed["amount"],
            changed["stage"]["name"],
            changed["version"],
        ]
        same = client.patch(item, json={"title": "Website rebuild"}, headers=auth("member", 2))
        result["update_same"] = [same.status_code, same.json()["version"]]
        owned = client.patch(
            item, json={"owner_user_id": str(admin_id)}, headers=auth("admin", 2)
        ).json()
        cleared = client.patch(
            item, json={"amount": None, "contact_id": None}, headers=auth("admin", 3)
        ).json()
        result["cleared"] = [
            owned["owner_user_id"],
            cleared["amount"],
            cleared["contact"],
            cleared["version"],
        ]
        result["update_invalid"] = {
            label: [response.status_code, response.json().get("detail")]
            for label, response in (
                (label, client.patch(item, json=body, headers=auth("owner", 4)))
                for label, body in (
                    ("null_title", {"title": None}),
                    ("null_stage", {"stage_id": None}),
                    ("foreign_stage", {"stage_id": foreign_stage}),
                    ("foreign_company", {"company_id": foreign_company["id"]}),
                    ("too_precise", {"amount": "1.234"}),
                    ("outcome_field", {"outcome": "won"}),
                )
            )
        }
        result["update_invalid"] = {
            k: [v[0], v[1] if isinstance(v[1], dict) else "validation"]
            for k, v in result["update_invalid"].items()
        }

        # --- Outcomes ----------------------------------------------------------------------
        outcome = f"{item}/outcome"
        result["outcome_refusals"] = {
            label: [response.status_code, response.json()["detail"]]
            for label, response in (
                (label, client.post(outcome, json=body, headers=auth("owner", 4)))
                for label, body in (
                    ("lost_without_reason", {"outcome": "lost"}),
                    ("won_with_reason", {"outcome": "won", "lost_reason": "No"}),
                )
            )
        }
        won = client.post(outcome, json={"outcome": "won"}, headers=auth("member", 4))
        result["won"] = [
            won.status_code,
            won.json()["outcome"],
            won.json()["closed_at"] is not None,
            won.json()["weighted_amount"],
        ]
        to_lost = client.post(
            outcome, json={"outcome": "lost", "lost_reason": "Price"}, headers=auth("member", 5)
        )
        result["won_to_lost"] = [to_lost.status_code, to_lost.json()["detail"]]
        closed_move = client.patch(item, json={"stage_id": stages[0]}, headers=auth("member", 5))
        result["closed_stage_change"] = [closed_move.status_code, closed_move.json()["detail"]]
        closed_title = client.patch(
            item, json={"title": "Website rebuild 2"}, headers=auth("member", 5)
        )
        result["closed_title_change"] = [closed_title.status_code, closed_title.json()["version"]]
        reopened = client.post(outcome, json={"outcome": "open"}, headers=auth("member", 6)).json()
        lost = client.post(
            outcome,
            json={"outcome": "lost", "lost_reason": "  Chose a competitor "},
            headers=auth("member", 7),
        )
        lost_again = client.post(
            outcome,
            json={"outcome": "lost", "lost_reason": "Chose a competitor"},
            headers=auth("member", 8),
        )
        result["lifecycle"] = [
            reopened["outcome"],
            reopened["closed_at"],
            lost.status_code,
            lost.json()["lost_reason"],
            lost_again.status_code,
            lost_again.json()["version"],
        ]
        final = client.post(outcome, json={"outcome": "open"}, headers=auth("member", 8)).json()
        result["reopened_clears_reason"] = [
            final["outcome"],
            final["lost_reason"],
            final["version"],
        ]

        # --- History -----------------------------------------------------------------------
        history = client.get(f"{item}/history", headers=auth("reader")).json()
        result["history"] = [
            [
                e["kind"],
                e["fields"],
                e["stage_from_name"],
                e["stage_to_name"],
                e["stage_cause"],
                e["outcome_from"],
                e["outcome_to"],
                e["owner_to"],
            ]
            for e in history["items"]
        ]
        result["history_text"] = json.dumps(history)
        page_one = client.get(f"{item}/history?limit=3", headers=auth("owner")).json()
        page_two = client.get(
            f"{item}/history",
            params={"limit": 3, "cursor": page_one["next_cursor"]},
            headers=auth("owner"),
        ).json()
        result["history_paging"] = [
            len(page_one["items"]),
            [e["id"] for e in page_one["items"] + page_two["items"]]
            == [e["id"] for e in history["items"]][
                : len(page_one["items"]) + len(page_two["items"])
            ],
        ]

        # --- Another workspace -----------------------------------------------------------
        foreign_deal = client.post(
            f"/v1/workspaces/{b.id}/opportunities",
            json={"title": "Secret"},
            headers=auth("other_owner"),
        ).json()
        theirs = f"{base}/{foreign_deal['id']}"
        result["foreign"] = {
            "get": client.get(theirs, headers=auth("owner")).status_code,
            "patch": client.patch(
                theirs, json={"title": "Mine"}, headers=auth("owner", 1)
            ).status_code,
            "outcome": client.post(
                f"{theirs}/outcome", json={"outcome": "won"}, headers=auth("owner", 1)
            ).status_code,
            "history": client.get(f"{theirs}/history", headers=auth("owner")).status_code,
            "delete": client.delete(theirs, headers=auth("owner")).status_code,
            "by_their_path": client.get(
                f"/v1/workspaces/{b.id}/opportunities/{deal['id']}", headers=auth("other_owner")
            ).status_code,
            "listed": "Secret" in client.get(base, headers=auth("owner")).text,
            "detail": client.get(theirs, headers=auth("owner")).json()["detail"],
        }

        # --- Lists, filters, order, paging, summary ----------------------------------------
        for title, amount, stage in (
            ("Alpha", "100", stages[0]),
            ("beta", "250.75", stages[0]),
            ("Gamma", None, stages[3]),
        ):
            body: dict[str, Any] = {"title": title, "stage_id": stage}
            if amount is not None:
                body["amount"] = amount
            client.post(base, json=body, headers=auth("owner"))
        alpha = client.get(base, params={"q": "alph"}, headers=auth("owner")).json()["items"][0]
        _sql(a.id, "idle", deal=alpha["id"])
        everything = client.get(base, params={"limit": 200}, headers=auth("owner")).json()
        result["total"] = everything["total"]

        def titles(**params: Any) -> list[str]:
            return [
                d["title"]
                for d in client.get(base, params=params, headers=auth("owner")).json()["items"]
            ]

        result["filters"] = {
            "q": titles(q="ALPH"),
            "stage": sorted(titles(stage_id=stages[0])),
            "owner_me": titles(owner="me", limit=200),
            "owner_admin": titles(owner=str(admin_id)),
            "company": titles(company_id=company["id"]),
            "idle": titles(idle="true"),
            "won": titles(outcome="won"),
            "amount_asc": titles(sort="amount", direction="asc", limit=200)[:3],
        }
        amounts_desc = client.get(
            base,
            params={"sort": "amount", "direction": "desc", "limit": 200},
            headers=auth("owner"),
        ).json()["items"]
        result["nulls_last_desc"] = amounts_desc[0]["amount"] is None
        seen: list[str] = []
        cursor = None
        while True:
            params: dict[str, Any] = {"limit": 3, "sort": "amount", "direction": "asc"}
            if cursor:
                params["cursor"] = cursor
            page = client.get(base, params=params, headers=auth("owner")).json()
            seen += [d["id"] for d in page["items"]]
            cursor = page["next_cursor"]
            if not cursor:
                break
        result["paging"] = [len(seen), len(set(seen)), everything["total"]]
        result["bad_cursor"] = client.get(
            base, params={"cursor": "nope"}, headers=auth("owner")
        ).status_code
        changed_filter = client.get(
            base, params={"limit": 3, "sort": "amount", "direction": "asc"}, headers=auth("owner")
        ).json()["next_cursor"]
        result["cursor_other_filter"] = client.get(
            base,
            params={
                "limit": 3,
                "sort": "amount",
                "direction": "asc",
                "q": "a",
                "cursor": changed_filter,
            },
            headers=auth("owner"),
        ).status_code
        summary = client.get(
            f"{base}/summary", params={"outcome": "open"}, headers=auth("reader")
        ).json()
        board = client.get(
            base, params={"outcome": "open", "limit": 200}, headers=auth("reader")
        ).json()["items"]
        result["parity"] = {
            s["stage_id"]: [s["count"], sum(1 for d in board if d["stage_id"] == s["stage_id"])]
            for s in summary["stages"]
        }
        result["summary_first_stage"] = next(
            s for s in summary["stages"] if s["stage_id"] == stages[0]
        )["totals"]
        result["list_params_refused"] = client.get(
            base, params={"tenant_id": str(b.id)}, headers=auth("owner")
        ).status_code

        # --- Currency follows the workspace at creation -------------------------------------
        settings = client.get(f"/v1/workspaces/{a.id}/settings", headers=auth("owner"))
        client.patch(
            f"/v1/workspaces/{a.id}/settings",
            json={"currency": "JPY"},
            headers=auth("owner", settings.json()["version"]),
        )
        yen = client.post(
            base,
            json={"title": "Yen", "amount": "1500", "stage_id": stages[0]},
            headers=auth("owner"),
        )
        yen_cents = client.post(
            base, json={"title": "Yen", "amount": "1500.5"}, headers=auth("owner")
        )
        kept = client.get(item, headers=auth("owner")).json()
        totals = client.get(
            f"{base}/summary", params={"outcome": "open"}, headers=auth("owner")
        ).json()
        result["currency"] = [
            yen.json()["currency"],
            yen.json()["amount"],
            yen_cents.json()["detail"],
            kept["currency"],
            [
                t["currency"]
                for t in next(s for s in totals["stages"] if s["stage_id"] == stages[0])["totals"]
            ],
        ]

        # --- Removing a stage that holds deals ------------------------------------------------
        pipe = client.get(f"/v1/workspaces/{a.id}/pipelines", headers=auth("owner")).json()[
            "items"
        ][0]
        stage_url = f"/v1/workspaces/{a.id}/pipelines/{pipe['id']}/stages/{stages[0]}"
        in_use = client.delete(stage_url, headers=auth("owner", pipe["version"]))
        same_target = client.delete(
            stage_url, params={"move_to": stages[0]}, headers=auth("owner", pipe["version"])
        )
        foreign_target = client.delete(
            stage_url, params={"move_to": foreign_stage}, headers=auth("owner", pipe["version"])
        )
        held = _sql(a.id, "stages_in", stage=stages[0])
        moved = client.delete(
            stage_url, params={"move_to": stages[1]}, headers=auth("admin", pipe["version"])
        )
        alpha_after = client.get(f"{base}/{alpha['id']}", headers=auth("owner")).json()
        alpha_history = client.get(f"{base}/{alpha['id']}/history", headers=auth("owner")).json()[
            "items"
        ][0]
        result["stage_removal"] = {
            "in_use": [in_use.status_code, in_use.json()["detail"], held],
            "same_target": [same_target.status_code, same_target.json()["detail"]],
            "foreign_target": [foreign_target.status_code, foreign_target.json()["detail"]],
            "moved": [
                moved.status_code,
                moved.json()["version"] - pipe["version"],
                len(moved.json()["stages"]),
            ],
            "left": _sql(a.id, "stages_in", stage=stages[0]),
            "alpha": [
                alpha_after["stage_id"] == stages[1],
                alpha_after["version"],
                alpha_history["kind"],
                alpha_history["stage_cause"],
            ],
            "member_cannot": client.delete(
                f"/v1/workspaces/{a.id}/pipelines/{pipe['id']}/stages/{stages[1]}",
                params={"move_to": stages[2]},
                headers=auth("member", moved.json()["version"]),
            ).status_code,
        }

        # --- Deleting deals ---------------------------------------------------------------
        result["delete"] = {
            caller: client.delete(f"{base}/{bare['id']}", headers=auth(caller)).status_code
            for caller in ("member", "reader", "admin")
        }
        result["deleted_get"] = client.get(
            f"{base}/{bare['id']}", headers=auth("owner")
        ).status_code
        result["deal_id"] = deal["id"]
        result["bare_id"] = bare["id"]

    # --- Concurrency, through the service --------------------------------------------------
    scope = Scope(workspace=a.id, actor=a.owner_id)
    racer = opportunities.create(scope, {"title": "Race"})[0]

    def bump(title: str) -> str:
        try:
            opportunities.update(scope, racer["id"], {"title": title}, expected_version=1)
        except RecordError as exc:
            return exc.code
        return "ok"

    with ThreadPoolExecutor(max_workers=4) as pool:
        outcomes = sorted(pool.map(bump, ["One", "Two", "Three", "Four"]))
    result["concurrent_updates"] = outcomes

    current = pipelines.list_pipelines(scope)[0]
    doomed, target = current["stages"][0]["id"], current["stages"][1]["id"]

    def add_deal(n: int) -> str:
        try:
            opportunities.create(scope, {"title": f"Racer {n}", "stage_id": doomed})
        except RecordError as exc:
            return exc.code
        return "ok"

    def remove_stage() -> str:
        try:
            pipelines.delete_stage(
                scope, current["id"], doomed, expected_version=current["version"], move_to=target
            )
        except RecordError as exc:
            return exc.code
        return "ok"

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(add_deal, n) for n in range(5)]
        removal = pool.submit(remove_stage)
        futures += [pool.submit(add_deal, n) for n in range(5, 10)]
        created = [f.result() for f in futures]
    result["concurrent_removal"] = {
        "removal": removal.result(),
        "created": sorted(set(created)),
        "left_in_removed_stage": _sql(a.id, "stages_in", stage=doomed),
    }

    print("RESULT " + json.dumps(result, default=str))


if __name__ == "__main__":
    main()
