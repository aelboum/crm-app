"""Drives the workspace AI settings routes against the integration database
and prints one `RESULT <json>` line.

Run in a fresh interpreter by `tests/integration/test_ai_settings_routes.py`.
Seeds throwaway workspaces. No AI provider or model is configured, so no
model can be granted and nothing is ever sent to a provider. Refuses to run
unless ENVIRONMENT=test.
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


def _out(response: Any) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text[:300]


CALLERS = ("owner", "admin", "member", "reader", "other_owner")


def main() -> None:
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("ai_settings_probe runs only with ENVIRONMENT=test")
    a = _new_workspace("ai-a")
    b = _new_workspace("ai-b")
    _, admin = _member(a, Role.ADMIN)
    _, member = _member(a, Role.MEMBER)
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

    base = f"/v1/workspaces/{a.id}/ai"
    result: dict[str, Any] = {"workspace": str(a.id), "other": str(b.id)}
    with TestClient(create_app(), follow_redirects=False) as client:

        def settings(caller: str = "owner") -> Any:
            response = client.get(base, headers=auth(caller))
            if response.status_code != 200:
                return [response.status_code, response.text[:500]]
            return response.json()

        # --- Defaults: off, nothing allowed, no model in the catalogue ---------------------
        result["initial"] = settings()

        # --- Who may do what ----------------------------------------------------------------
        result["read"] = {c: client.get(base, headers=auth(c)).status_code for c in CALLERS}
        result["enable"] = {
            c: client.put(f"{base}/enabled", json={"enabled": False}, headers=auth(c)).status_code
            for c in CALLERS
        }
        result["budget_read"] = {
            c: client.get(f"{base}/budget", headers=auth(c)).status_code for c in CALLERS
        }
        result["budget_set"] = {
            c: client.put(
                f"{base}/budget", json={"currency": "EUR", "amount": None}, headers=auth(c)
            ).status_code
            for c in CALLERS
        }
        access = client.get(f"/v1/workspaces/{a.id}/access", headers=auth("admin")).json()
        result["admin_actions"] = {
            k: v for k, v in access["actions"].items() if "ai" in k.split("_")
        }
        access = client.get(f"/v1/workspaces/{a.id}/access", headers=auth("member")).json()
        result["member_actions"] = {
            k: v for k, v in access["actions"].items() if "ai" in k.split("_")
        }

        # --- Turning AI and the contact brief on, then off ----------------------------------
        result["on"] = client.put(
            f"{base}/enabled", json={"enabled": True}, headers=auth("admin")
        ).status_code
        result["feature_on"] = client.put(
            f"{base}/features/contact_brief", json={"enabled": True}, headers=auth("owner")
        ).status_code
        result["after_on"] = settings("admin")
        other = client.get(f"/v1/workspaces/{b.id}/ai", headers=auth("other_owner"))
        result["other_untouched"] = [other.status_code, other.text[:300]]
        result["feature_unknown"] = client.put(
            f"{base}/features/send_email", json={"enabled": True}, headers=auth("owner")
        ).status_code
        result["feature_off"] = client.put(
            f"{base}/features/contact_brief", json={"enabled": False}, headers=auth("owner")
        ).status_code
        result["off"] = client.put(
            f"{base}/enabled", json={"enabled": False}, headers=auth("owner")
        ).status_code
        result["after_off"] = settings()

        # --- Preferences ---------------------------------------------------------------------
        result["prefs"] = client.put(
            f"{base}/preferences",
            json={
                "allowed_residency": ["eu"],
                "max_retention_days": 0,
                "exclude_training_use": True,
            },
            headers=auth("admin"),
        ).status_code
        result["after_prefs"] = settings()
        result["prefs_invalid"] = {
            "residency": client.put(
                f"{base}/preferences", json={"allowed_residency": ["EU!"]}, headers=auth("owner")
            ).status_code,
            "retention": client.put(
                f"{base}/preferences", json={"max_retention_days": 4000}, headers=auth("owner")
            ).status_code,
            "extra": client.put(
                f"{base}/preferences", json={"provider": "x"}, headers=auth("owner")
            ).status_code,
            "member": client.put(
                f"{base}/preferences", json={}, headers=auth("member")
            ).status_code,
        }

        # --- Models: none in the catalogue, so a grant is refused ----------------------------
        unknown = client.put(
            f"{base}/models",
            json={
                "feature": "contact_brief",
                "provider_key": "groq",
                "model_id": "openai/gpt-oss-20b",
                "enabled": True,
                "rank": 0,
            },
            headers=auth("owner"),
        )
        result["model_unknown"] = [unknown.status_code, _out(unknown)]
        result["model_invalid"] = client.put(
            f"{base}/models",
            json={"feature": "contact_brief", "provider_key": "", "model_id": "m", "enabled": True},
            headers=auth("owner"),
        ).status_code
        result["model_member"] = client.put(
            f"{base}/models",
            json={
                "feature": "contact_brief",
                "provider_key": "p",
                "model_id": "m",
                "enabled": True,
            },
            headers=auth("member"),
        ).status_code

        # --- The monthly cap -----------------------------------------------------------------
        result["cap"] = client.put(
            f"{base}/budget",
            json={"currency": "EUR", "amount": "25.00", "warn_thresholds": [50, 80]},
            headers=auth("owner"),
        ).status_code
        result["cap_invalid"] = {
            "currency": client.put(
                f"{base}/budget", json={"currency": "eur", "amount": "1"}, headers=auth("owner")
            ).status_code,
            "negative": client.put(
                f"{base}/budget", json={"currency": "EUR", "amount": "-1"}, headers=auth("owner")
            ).status_code,
            "thresholds": client.put(
                f"{base}/budget",
                json={"currency": "EUR", "amount": "1", "warn_thresholds": [80, 50]},
                headers=auth("owner"),
            ).status_code,
        }
        budget = client.get(f"{base}/budget", headers=auth("admin"))
        result["budget"] = [budget.status_code, _out(budget)]

    print("RESULT " + json.dumps(result, default=str))


if __name__ == "__main__":
    main()
