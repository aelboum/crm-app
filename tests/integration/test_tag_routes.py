"""Tag vocabulary routes (decision P3-C; `crm_app.api.tags`).

Drives `tag_route_probe` in a fresh interpreter and checks the audit log
directly. Covers: every role reads, only Owner and Admin change; another
workspace's tags are unreachable; names are normalised, unique regardless
of case and validated; renaming needs the current version; deleting removes
the tag from records without changing them; the 500-tag limit; and audit
entries that never hold a tag's name.
"""

from __future__ import annotations

import json
from typing import Any

import psycopg
import pytest

from tests.support import REPO_ROOT, run_module

pytestmark = pytest.mark.usefixtures("migrated")

Probe = dict[str, Any]


@pytest.fixture(scope="module")
def probe(integration_env: dict[str, str], tmp_path_factory: pytest.TempPathFactory) -> Probe:
    env = {**integration_env, "PYTHONPATH": str(REPO_ROOT)}
    tmp = tmp_path_factory.mktemp("tags")
    result = run_module("tests.integration.tag_route_probe", [], env, tmp, timeout=600)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def test_every_role_reads_and_only_owners_and_admins_change(probe: Probe) -> None:
    assert probe["read"] == {
        "owner": 200,
        "admin": 200,
        "member": 200,
        "reader": 200,
        "other_owner": 404,
    }
    assert probe["anonymous"] == 401
    assert probe["create_refused"] == {"member": 403, "reader": 403, "other_owner": 404}
    assert probe["rename_member"] == 403
    assert probe["delete_member"] == 403


def test_a_created_tag_is_trimmed_and_versioned(probe: Probe) -> None:
    (status, vip, etag), (hot_status, hot) = probe["created"]
    assert status == hot_status == 201
    assert vip["name"] == "VIP"
    assert vip["version"] == 1
    assert etag == '"1"'
    assert set(vip) == {"id", "name", "version", "created_at", "updated_at"}
    assert hot["name"] == "Hot lead"


def test_names_are_unique_regardless_of_case(probe: Probe) -> None:
    status, body = probe["duplicate"]
    assert status == 409
    assert body["detail"] == {"code": "duplicate_tag", "existing_id": probe["ids"]["vip"]}
    clash_status, clash = probe["rename_clash"]
    assert clash_status == 409
    assert clash["detail"] == {"code": "duplicate_tag", "existing_id": probe["ids"]["hot"]}


def test_invalid_names_and_unknown_fields_are_refused(probe: Probe) -> None:
    assert probe["invalid"] == {
        "empty": 422,
        "blank": 422,
        "long": 422,
        "control": 422,
        "extra": 422,
        "missing": 422,
    }


def test_the_list_is_by_name_with_its_limit(probe: Probe) -> None:
    assert probe["listed"] == [["Hot lead", "VIP"], 500]


def test_renaming_needs_the_current_version(probe: Probe) -> None:
    assert probe["rename_no_version"] == 428
    status, body = probe["rename_stale"]
    assert status == 409
    assert body["detail"] == {"code": "stale_version", "current_version": 1}
    assert probe["rename_same"] == [200, 1]  # the same name changes nothing
    status, cased, etag = probe["rename_case"]
    assert status == 200
    assert cased["name"] == "vip"
    assert cased["version"] == 2
    assert etag == '"2"'


def test_another_workspaces_tag_is_unreachable(probe: Probe) -> None:
    foreign = probe["foreign"]
    assert foreign["rename"]["detail"] == {"code": "tag_not_found"}
    assert foreign["delete"]["detail"] == {"code": "tag_not_found"}
    assert foreign["listed"] is False


def test_deleting_a_tag_removes_it_from_records_and_leaves_them_unchanged(probe: Probe) -> None:
    assert probe["deleted"] == 204
    assert probe["deleted_again"] == 404
    assert probe["left_assigned"] == [0, 0]
    assert probe["record_versions"] == [1, 1]


def test_a_workspace_holds_at_most_500_tags(probe: Probe) -> None:
    last, over, body = probe["limit"]
    assert last == 201
    assert over == 409
    assert body["detail"] == {"code": "tag_limit_reached"}


def test_changes_are_audited_by_id_without_names(
    probe: Probe, owner_connection: psycopg.Connection
) -> None:
    rows = owner_connection.execute(
        "SELECT action, resource_id, metadata FROM core.audit_log"
        " WHERE tenant_id = %s AND resource_type = 'crm_app.tag' ORDER BY created_at",
        (probe["workspace"],),
    ).fetchall()
    ids = probe["ids"]
    assert [(action, resource) for action, resource, _ in rows] == [
        ("crm_app.tag.created", ids["vip"]),
        ("crm_app.tag.created", ids["hot"]),
        ("crm_app.tag.renamed", ids["vip"]),
        ("crm_app.tag.deleted", ids["hot"]),
    ]
    assert rows[-1][2] == {"removed_from_contacts": 1, "removed_from_companies": 1}
    text = json.dumps([metadata for _, _, metadata in rows])
    for name in ("VIP", "vip", "Hot lead"):
        assert name not in text
