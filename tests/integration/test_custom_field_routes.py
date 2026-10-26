"""Custom field definition routes (decision P3-D; `crm_app.api.custom_fields`).

Drives `custom_field_route_probe` in a fresh interpreter and checks the
audit log directly. Covers: every role reads, only Owner and Admin change;
another workspace's fields are unreachable; keys, labels, types and options
are validated, a key and a type never change; versions; archive and restore;
the 50-active limit per entity; audit entries with entity, key and type.
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
    tmp = tmp_path_factory.mktemp("custom-fields")
    result = run_module("tests.integration.custom_field_route_probe", [], env, tmp, timeout=600)
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
    assert probe["update"]["member"] == 403
    assert probe["archive"][3] == 403


def test_a_field_is_created_normalised(probe: Probe) -> None:
    (status, carrier, etag), (tier_status, tier), (seats_status, seats_type), company = probe[
        "created"
    ]
    assert status == tier_status == seats_status == 201
    assert carrier["label"] == "Insurance carrier"
    assert carrier["options"] is None
    assert carrier["archived"] is False
    assert carrier["version"] == 1
    assert etag == '"1"'
    assert tier["options"] == ["Gold", "Silver"]
    assert seats_type == "number"
    assert company == 201  # the same key on the other entity


def test_a_key_is_unique_per_entity(probe: Probe) -> None:
    status, body = probe["duplicate"]
    assert status == 409
    assert body["detail"] == {"code": "duplicate_custom_field_key"}


def test_invalid_definitions_are_refused(probe: Probe) -> None:
    invalid = probe["invalid"]
    for label in ("bad_key", "bad_type", "bad_entity", "repeated_options", "blank_label", "extra"):
        assert invalid[label][0] == 422, label
    for label in ("select_without_options", "text_with_options"):
        assert invalid[label] == [422, {"detail": {"code": "invalid_options"}}], label


def test_the_list_is_by_entity_and_position(probe: Probe) -> None:
    pairs, max_active = probe["listed"]
    assert pairs == [
        ["company", "seats"],
        ["company", "carrier"],
        ["contact", "carrier"],
        ["contact", "tier"],
    ]
    assert max_active == 50
    assert probe["contact_only"] == ["carrier", "tier"]
    assert probe["bad_filter"] == [422, 422]


def test_a_key_and_a_type_never_change_and_versions_are_required(probe: Probe) -> None:
    update = probe["update"]
    assert update["no_version"] == 428
    assert update["stale"]["detail"] == {"code": "stale_version", "current_version": 1}
    assert update["key"] == 422
    assert update["type"] == 422
    assert update["null_label"] == 422
    assert update["options_on_text"]["detail"] == {"code": "invalid_options"}
    status, changed, same_version, options = probe["changed"]
    assert status == 200
    assert (changed["label"], changed["position"], changed["version"]) == ("Carrier", 5, 2)
    assert same_version == 2  # nothing changed
    assert options["options"] == ["Gold", "Silver", "Bronze"]


def test_archiving_and_restoring(probe: Probe) -> None:
    (status, archived, version), again, (restored, restored_version), _ = probe["archive"]
    assert status == 200
    assert archived is True
    assert version == 3
    assert again == 3  # archiving twice changes nothing
    assert (restored, restored_version) == (False, 4)


def test_another_workspaces_field_is_unreachable(probe: Probe) -> None:
    for body in probe["foreign"]:
        assert body["detail"] == {"code": "custom_field_not_found"}


def test_at_most_50_active_fields_per_entity(probe: Probe) -> None:
    fiftieth, (over, body), company, room, (restore, restore_body) = probe["limit"]
    assert fiftieth == 201
    assert over == 409
    assert body["detail"] == {"code": "custom_field_limit_reached"}
    assert company == 201  # the other entity has its own limit
    assert room == 201  # archiving made room
    assert restore == 409
    assert restore_body["detail"] == {"code": "custom_field_limit_reached"}


def test_changes_are_audited_with_entity_key_and_type(
    probe: Probe, owner_connection: psycopg.Connection
) -> None:
    rows = owner_connection.execute(
        "SELECT action, metadata FROM core.audit_log WHERE tenant_id = %s"
        " AND resource_id = %s ORDER BY created_at",
        (probe["workspace"], probe["ids"]["carrier"]),
    ).fetchall()
    assert [action for action, _ in rows] == [
        "crm_app.custom_field.created",
        "crm_app.custom_field.updated",
        "crm_app.custom_field.archived",
        "crm_app.custom_field.restored",
    ]
    assert all(
        metadata == {"entity": "contact", "key": "carrier", "field_type": "text"}
        for _, metadata in rows
    )
