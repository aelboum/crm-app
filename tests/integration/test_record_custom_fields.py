"""Custom field values on contacts and companies (decision P3-D 5, 6).

Drives `record_custom_field_probe` in a fresh interpreter and checks the
history and audit tables directly. Covers: values are normalised by type
and merged key by key; only the record entity's active fields of the
caller's own workspace are accepted; archived fields are hidden and
refused, then shown again on restore; values follow the record's update
permission; the 32 KB limit; history and audit name keys, never values.
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
    tmp = tmp_path_factory.mktemp("custom-values")
    result = run_module("tests.integration.record_custom_field_probe", [], env, tmp, timeout=600)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def test_values_are_stored_in_one_form_on_creation(probe: Probe) -> None:
    status, sam = probe["created"]
    assert status == 201
    assert sam["custom_fields"] == {
        "carrier": "Delta",
        "seats": 4,
        "renewal": "2027-01-31",
        "vip": False,
        "tier": "Gold",
    }
    assert probe["plain"] == {}
    assert probe["company"] == [201, {"plan": "Pro"}]


def test_only_the_entitys_active_fields_of_the_workspace_are_accepted(probe: Probe) -> None:
    refused = probe["refused"]
    for label, key in (
        ("unknown", "colour"),
        ("other_entity", "plan"),
        ("other_workspace", "secret"),
    ):
        assert refused[label] == [422, {"detail": {"code": "unknown_custom_field", "key": key}}], (
            label
        )
    for label, key in (
        ("bad_number", "seats"),
        ("bad_option", "tier"),
        ("bad_date", "renewal"),
        ("bad_boolean", "vip"),
    ):
        assert refused[label] == [422, {"detail": {"code": "invalid_custom_field", "key": key}}], (
            label
        )
    assert refused["nested"][0] == 422
    assert refused["null_object"][0] == 422


def test_values_follow_the_records_update_permission(probe: Probe) -> None:
    assert probe["reader"] == 403
    assert probe["merged"][0] == 200  # a Member


def test_writes_merge_key_by_key_and_null_clears(probe: Probe) -> None:
    _, values, version = probe["merged"]
    assert values == {"seats": 5, "renewal": "2027-01-31", "vip": False, "tier": "Gold"}
    assert version == 2
    assert probe["same_version"] == 2  # the same value changes nothing


def test_an_archived_field_is_hidden_and_refused_until_restored(probe: Probe) -> None:
    archived = probe["archived"]
    assert "tier" not in archived["detail"]
    assert archived["write"] == [422, {"detail": {"code": "unknown_custom_field", "key": "tier"}}]
    assert all("tier" not in values for values in archived["list"])
    assert probe["restored"]["tier"] == "Gold"  # the stored value was kept


def test_a_records_values_are_at_most_32_kb(probe: Probe) -> None:
    status, body = probe["too_large"]
    assert status == 422
    assert body["detail"] == {"code": "custom_fields_too_large"}


def test_history_and_audit_name_fields_and_keys_never_values(
    probe: Probe, owner_connection: psycopg.Connection
) -> None:
    sam = probe["ids"]["sam"]
    history = owner_connection.execute(
        "SELECT fields FROM crm_app.activity WHERE contact_id = %s AND kind = 'updated'", (sam,)
    ).fetchall()
    assert history == [(["custom_fields"],)]
    audit = [
        row[0]
        for row in owner_connection.execute(
            "SELECT metadata FROM core.audit_log WHERE tenant_id = %s AND resource_id = %s"
            " AND action IN ('crm_app.contact.created', 'crm_app.contact.updated')"
            " ORDER BY created_at",
            (probe["workspace"], sam),
        ).fetchall()
    ]
    assert audit[0]["custom_field_keys"] == ["carrier", "renewal", "seats", "tier", "vip"]
    assert "custom_fields" in audit[0]["fields"]
    assert audit[1] == {"fields": ["custom_fields"], "custom_field_keys": ["carrier", "seats"]}
    text = json.dumps(audit)
    for value in ("Delta", "Gold", "2027-01-31"):
        assert value not in text
