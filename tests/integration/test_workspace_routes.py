"""The workspace routes admit members with the permission and refuse every
other caller without revealing whether the workspace exists.

Drives `workspace_route_probe` in a fresh interpreter (SaaS-OS caches its
configuration per process) against the integration database.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.support import REPO_ROOT, run_module

pytestmark = pytest.mark.usefixtures("migrated")

Probe = dict[str, Any]


@pytest.fixture(scope="module")
def probe(integration_env: dict[str, str], tmp_path_factory: pytest.TempPathFactory) -> Probe:
    env = {**integration_env, "PYTHONPATH": str(REPO_ROOT)}
    cwd: Path = tmp_path_factory.mktemp("routes")
    result = run_module("tests.integration.workspace_route_probe", [], env, cwd)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


@pytest.mark.parametrize("route", ["workspace", "members", "access"])
def test_members_with_the_permission_are_admitted(probe: Probe, route: str) -> None:
    assert probe[route]["owner"] == 200
    assert probe[route]["reader"] == 200


@pytest.mark.parametrize("route", ["workspace", "members", "access"])
def test_a_member_without_the_permission_is_refused(probe: Probe, route: str) -> None:
    assert probe[route]["roleless"] == 403


@pytest.mark.parametrize("route", ["workspace", "members", "access"])
def test_non_members_and_other_workspaces_get_the_same_404(probe: Probe, route: str) -> None:
    assert probe[route]["outsider"] == 404
    assert probe[route]["other_owner"] == 404


@pytest.mark.parametrize("route", ["workspace", "members", "access"])
def test_suspended_and_revoked_members_lose_access_with_a_live_session(
    probe: Probe, route: str
) -> None:
    """Their sessions were issued while they were active members; after
    suspension or revocation the next request is refused (SaaS-OS `can()`
    requires an active membership). They still hold a membership row, so
    the answer is 403 rather than the non-member 404."""
    assert probe[route]["suspended"] == 403
    assert probe[route]["revoked"] == 403


@pytest.mark.parametrize("route", ["workspace", "members", "access"])
def test_anonymous_callers_are_refused(probe: Probe, route: str) -> None:
    assert probe[route]["anonymous"] == 401


def test_an_unknown_workspace_is_indistinguishable_from_a_foreign_one(
    probe: Probe,
) -> None:
    assert probe["unknown_workspace"] == 404
    assert probe["unknown_members"] == 404


def test_the_workspace_returned_is_the_requested_one(probe: Probe) -> None:
    assert probe["owner_workspace_id_matches"] is True


def test_the_member_list_holds_exactly_this_workspaces_members(probe: Probe) -> None:
    assert probe["member_user_ids"] == probe["expected_member_user_ids"]
    assert probe["other_owner_listed"] is False


def test_the_member_list_shows_each_members_roles(probe: Probe) -> None:
    roles = probe["member_roles"]
    assert isinstance(roles, dict)
    assert roles[probe["owner_id"]] == ["Owner"]
    assert roles[probe["reader_id"]] == ["Read-only"]
    assert roles[probe["roleless_id"]] == []


def test_ordinary_members_see_active_memberships_only(probe: Probe) -> None:
    assert probe["statuses_seen_by_reader"] == ["active"]
    assert probe["revoked_id"] not in probe["member_user_ids"]


def test_owners_also_see_suspended_but_never_revoked_memberships(probe: Probe) -> None:
    assert probe["owner_sees_user_ids"] == probe["owner_expected_user_ids"]
    assert probe["statuses_seen_by_owner"] == ["active", "suspended"]
    assert probe["revoked_id"] not in probe["owner_sees_user_ids"]
    assert probe["owner_sees_total"] == len(probe["owner_expected_user_ids"])


def test_page_size_is_bounded(probe: Probe) -> None:
    assert probe["page_too_large"] == 422


def test_access_reports_the_callers_own_membership_and_actions(probe: Probe) -> None:
    owner, reader = probe["access_seen"]["owner"], probe["access_seen"]["reader"]
    assert owner["roles"] == ["Owner"]
    assert all(owner["actions"].values())
    assert reader["roles"] == ["Read-only"]
    assert reader["actions"] == {
        "read_members": True,
        "assign_role": False,
        "remove_role": False,
        "suspend_member": False,
        "reactivate_member": False,
        "revoke_member": False,
        "manage_owners": False,
        "update_workspace": False,
        "read_invitations": False,
        "create_invitation": False,
        "revoke_invitation": False,
        "create_contact": False,
        "update_contact": False,
        "delete_contact": False,
        "create_company": False,
        "update_company": False,
        "delete_company": False,
        "create_note": False,
        "edit_any_note": False,
        "delete_any_note": False,
        "export_records": False,
        "import_records": False,
        "manage_pipeline": False,
        "create_opportunity": False,
        "update_opportunity": False,
        "delete_opportunity": False,
        "create_task": False,
        "update_task": False,
        "delete_task": False,
    }
    assert owner["membership_id"] != reader["membership_id"]


def test_the_frontend_is_served_from_the_api_origin(probe: Probe) -> None:
    frontend = probe["frontend"]
    assert frontend["root"] == [307, "/app"]
    assert frontend["page"] == [200, "no-cache"]
    assert "default-src 'self'" in frontend["page_csp"]
    assert frontend["asset"] == [200, "public, max-age=31536000, immutable"]
    assert frontend["missing_asset"] == 404
    assert frontend["head"] == [200, "", 200]
    assert frontend["traversal"] == 404


def test_api_responses_are_never_cached(probe: Probe) -> None:
    assert probe["api_cache"] == "no-store"
