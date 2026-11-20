"""Workspace AI settings routes (decision P9-S; `crm_app.api.ai_settings`).

Drives `ai_settings_probe` in a fresh interpreter and checks the audit log
directly. Covers: AI is off and nothing is allowed by default; only Owners
and Admins read or change the settings, the budget and the cap; another
workspace's owner is answered 404 and its own settings stay untouched;
turning AI and the contact brief on and off; data preferences; refusals of
invalid input, an unknown feature and a model the catalogue lacks; the
monthly cap and the budget read; and SaaS-OS's audit rows for each change.

Not covered here: granting a model the catalogue holds and an AI call with
it. That needs a platform operator to configure a provider and model
(`saas-os-operator ai-*`); SaaS-OS's own tests cover grant-time validation,
support access and the platform hold against its fake adapter.
"""

from __future__ import annotations

import json
from typing import Any

import psycopg
import pytest

from tests.support import REPO_ROOT, run_module

pytestmark = pytest.mark.usefixtures("migrated")

Probe = dict[str, Any]

ONLY_OWNERS_AND_ADMINS = {
    "owner": 200,
    "admin": 200,
    "member": 403,
    "reader": 403,
    "other_owner": 404,
}
CHANGES = {"owner": 204, "admin": 204, "member": 403, "reader": 403, "other_owner": 404}


@pytest.fixture(scope="module")
def probe(integration_env: dict[str, str], tmp_path_factory: pytest.TempPathFactory) -> Probe:
    env = {
        **integration_env,
        "PYTHONPATH": str(REPO_ROOT),
        "RATE_LIMIT_REQUESTS_PER_WINDOW": "1000",
    }
    tmp = tmp_path_factory.mktemp("ai_settings")
    result = run_module("tests.integration.ai_settings_probe", [], env, tmp, timeout=600)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def _settings(enabled: bool, feature: bool, preferences: dict[str, Any]) -> dict[str, Any]:
    return {
        "enabled": enabled,
        "features": [{"feature": "contact_brief", "enabled": feature}],
        "preferences": preferences,
        "models": [{"feature": "contact_brief", "models": []}],
    }


DEFAULT_PREFERENCES = {
    "allowed_residency": [],
    "max_retention_days": None,
    "exclude_training_use": False,
}


def test_ai_is_off_and_nothing_is_allowed_by_default(probe: Probe) -> None:
    assert probe["initial"] == _settings(False, False, DEFAULT_PREFERENCES)


def test_only_owners_and_admins_see_or_change_ai_settings(probe: Probe) -> None:
    assert probe["read"] == ONLY_OWNERS_AND_ADMINS
    assert probe["enable"] == CHANGES
    assert probe["budget_read"] == ONLY_OWNERS_AND_ADMINS
    assert probe["budget_set"] == CHANGES
    names = {"read_ai_settings", "manage_ai_settings", "read_ai_usage", "manage_ai_budget"}
    # Members may ask for a contact brief (P9-B), never change the settings.
    assert probe["admin_actions"] == {**dict.fromkeys(names, True), "use_ai_brief": True}
    assert probe["member_actions"] == {**dict.fromkeys(names, False), "use_ai_brief": True}
    assert probe["prefs_invalid"]["member"] == 403
    assert probe["model_member"] == 403


def test_ai_and_the_contact_brief_turn_on_and_off(probe: Probe) -> None:
    assert (probe["on"], probe["feature_on"]) == (204, 204)
    assert probe["after_on"] == _settings(True, True, DEFAULT_PREFERENCES)
    status, other = probe["other_untouched"]
    assert status == 200
    assert json.loads(other)["enabled"] is False
    assert probe["feature_unknown"] == 422
    assert (probe["feature_off"], probe["off"]) == (204, 204)
    assert probe["after_off"] == _settings(False, False, DEFAULT_PREFERENCES)


def test_preferences_are_saved_and_invalid_ones_refused(probe: Probe) -> None:
    assert probe["prefs"] == 204
    assert probe["after_prefs"]["preferences"] == {
        "allowed_residency": ["eu"],
        "max_retention_days": 0,
        "exclude_training_use": True,
    }
    invalid = {k: v for k, v in probe["prefs_invalid"].items() if k != "member"}
    assert invalid == {"residency": 422, "retention": 422, "extra": 422}


def test_a_model_the_catalogue_lacks_is_refused(probe: Probe) -> None:
    assert probe["model_unknown"] == [404, {"detail": {"code": "unknown_model"}}]
    assert probe["model_invalid"] == 422


def test_the_monthly_cap_sets_the_budget(probe: Probe) -> None:
    assert probe["cap"] == 204
    assert probe["cap_invalid"] == {"currency": 422, "negative": 422, "thresholds": 422}
    status, budget = probe["budget"]
    assert status == 200
    assert budget["state"] == "ok"
    assert budget["source"] == "tenant_cap"
    assert (budget["currency"], budget["limit"], budget["remaining"]) == ("EUR", "25", "25")
    assert (budget["settled"], budget["reserved"]) == ("0", "0")
    assert budget["warn_thresholds"] == [50, 80]


def test_saas_os_audits_each_change_in_the_workspace(
    probe: Probe, owner_connection: psycopg.Connection
) -> None:
    rows = owner_connection.execute(
        "SELECT action, outcome, metadata FROM core.audit_log WHERE tenant_id = %s"
        " AND action LIKE 'ai.%%' AND outcome = 'success' ORDER BY created_at",
        (probe["workspace"],),
    ).fetchall()
    actions = [action for action, _, _ in rows]
    # Owner and Admin in the role check, then on and off.
    assert actions.count("ai.policy.set") == 4
    assert actions.count("ai.policy.grant_use_case") == 2
    assert actions.count("ai.policy.set_preferences") == 1
    assert actions.count("ai.budget.set_cap") == 3
    grant = next(meta for action, _, meta in rows if action == "ai.policy.grant_use_case")
    assert grant["use_case"] == "crm.contact_brief"
    other = owner_connection.execute(
        "SELECT count(*) FROM core.audit_log WHERE tenant_id = %s AND action LIKE 'ai.policy.%%'"
        " AND outcome = 'success'",
        (probe["other"],),
    ).fetchone()
    assert other == (0,)


def test_owners_and_admins_read_ai_usage_through_saas_os(probe: Probe) -> None:
    """Decision P9-U: SaaS-OS's usage router, mounted as is. Owners and
    Admins hold `ai.usage:read`; another workspace's Owner gets 404."""
    allowed = [200, 200, 200]
    assert probe["usage_read"] == {
        "owner": allowed,
        "admin": allowed,
        "member": [403, 403, 403],
        "reader": [403, 403, 403],
        "other_owner": [404, 404, 404],
    }
    # Twelve months, none used; this month by feature, empty.
    assert probe["usage"] == ["month", 12, 0, "use_case", []]
    assert probe["usage_bad_group"] in (400, 422)
    assert probe["usage_no_session"] == 401
