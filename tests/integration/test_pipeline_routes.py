"""Pipeline routes (decision P4, slice 4A; `crm_app.api.pipelines`).

Drives `pipeline_route_probe` in a fresh interpreter and checks the audit
log directly. Covers: every role reads, only Owner and Admin change; the
default pipeline is created once, even by concurrent first reads; every
change needs the current version and bumps it; stage names are unique
regardless of case and validated, probabilities are strict whole
percentages; reordering must name every stage once; positions stay
contiguous; the 15-stage limit and the last stage; another workspace's
pipeline and stages are unreachable; audit entries never hold names.
"""

from __future__ import annotations

import json
from typing import Any

import psycopg
import pytest

from tests.support import REPO_ROOT, run_module

pytestmark = pytest.mark.usefixtures("migrated")

Probe = dict[str, Any]

DEFAULT_STAGES = [
    ["Qualified", 20, 0],
    ["Meeting", 40, 1],
    ["Proposal", 60, 2],
    ["Negotiation", 75, 3],
]


@pytest.fixture(scope="module")
def probe(integration_env: dict[str, str], tmp_path_factory: pytest.TempPathFactory) -> Probe:
    env = {**integration_env, "PYTHONPATH": str(REPO_ROOT)}
    tmp = tmp_path_factory.mktemp("pipelines")
    result = run_module("tests.integration.pipeline_route_probe", [], env, tmp, timeout=600)
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
    assert probe["refused"] == {
        "member": [403] * 5,
        "reader": [403] * 5,
        "other_owner": [404] * 5,
    }


def test_the_first_read_creates_the_default_pipeline_once(probe: Probe) -> None:
    assert probe["default"] == {
        "count": 1,
        "same_on_reread": True,
        "name": "Sales",
        "version": 1,
        "stages": DEFAULT_STAGES,
        "max_stages": 15,
        "keys": ["created_at", "id", "name", "stages", "updated_at", "version"],
        "stage_keys": ["id", "name", "position", "probability"],
    }
    # Six concurrent first reads: one pipeline, four stages.
    assert probe["concurrent"] == [1, 1, 4]


def test_renaming_needs_the_current_version(probe: Probe) -> None:
    assert probe["rename_no_version"] == 428
    status, body = probe["rename_stale"]
    assert status == 409
    assert body["detail"] == {"code": "stale_version", "current_version": 1}
    assert probe["renamed"] == [200, "New business", 2, '"2"']
    assert probe["rename_same"] == [200, 2]  # the same name changes nothing


def test_a_stage_is_added_at_the_end_with_a_new_version(probe: Probe) -> None:
    status, stages, version = probe["added"]
    assert status == 201
    assert stages == [*DEFAULT_STAGES, ["Closing", 90, 4]]
    assert version == 3


def test_stage_names_are_unique_regardless_of_case(probe: Probe) -> None:
    for key in ("duplicate", "rename_clash"):
        status, body = probe[key]
        assert status == 409
        assert body["detail"] == {"code": "duplicate_stage"}


def test_invalid_stages_are_refused(probe: Probe) -> None:
    assert probe["invalid"] == dict.fromkeys(
        (
            "empty",
            "long",
            "control",
            "over",
            "under",
            "text",
            "bool",
            "fraction",
            "extra",
            "missing",
        ),
        422,
    )
    assert probe["empty_patch"] == 422


def test_a_stage_is_changed_and_an_equal_value_changes_nothing(probe: Probe) -> None:
    status, stages, version = probe["changed"]
    assert status == 200
    assert stages[1] == ["Demo", 45, 1]
    assert version == 4
    assert probe["unchanged"] == [200, 4]
    status, body = probe["unknown_stage"]
    assert status == 404
    assert body["detail"] == {"code": "stage_not_found"}


def test_another_workspaces_pipeline_is_unreachable(probe: Probe) -> None:
    foreign = probe["foreign"]
    assert foreign["rename"]["detail"] == {"code": "pipeline_not_found"}
    assert foreign["stage_by_own_pipeline"]["detail"] == {"code": "stage_not_found"}
    assert foreign["delete"]["detail"] == {"code": "pipeline_not_found"}
    assert foreign["listed"] is False
    assert foreign["untouched"] == 1


def test_reordering_names_every_stage_once(probe: Probe) -> None:
    status, stages, version = probe["reordered"]
    assert status == 200
    assert stages == [
        ["Closing", 90, 0],
        ["Negotiation", 75, 1],
        ["Proposal", 60, 2],
        ["Demo", 45, 3],
        ["Qualified", 20, 4],
    ]
    assert version == 5
    refused = [422, {"code": "invalid_stage_order"}]
    assert probe["bad_order"] == {"missing": refused, "repeated": refused, "foreign": refused}


def test_removing_a_stage_keeps_positions_contiguous(probe: Probe) -> None:
    status, stages, version = probe["removed"]
    assert status == 200
    assert stages == [
        ["Closing", 90, 0],
        ["Negotiation", 75, 1],
        ["Demo", 45, 2],
        ["Qualified", 20, 3],
    ]
    assert version == 6


def test_a_pipeline_holds_1_to_15_stages(probe: Probe) -> None:
    assert probe["limit"] == [11, 409]
    assert probe["over_limit"]["detail"] == {"code": "stage_limit_reached"}
    status, body = probe["last_stage"]
    assert status == 409
    assert body["detail"] == {"code": "last_stage"}
    assert probe["counts"] == [1, 1]


def test_changes_are_audited_by_id_without_names(
    probe: Probe, owner_connection: psycopg.Connection
) -> None:
    rows = owner_connection.execute(
        "SELECT action, resource_id, metadata FROM core.audit_log"
        " WHERE tenant_id = %s AND resource_type = 'crm_app.pipeline' ORDER BY created_at",
        (probe["workspace"],),
    ).fetchall()
    assert {resource for _, resource, _ in rows} == {probe["pipeline_id"]}
    ids = probe["ids"]
    assert [(action, metadata) for action, _, metadata in rows[:4]] == [
        ("crm_app.pipeline.updated", {"fields": ["name"]}),
        ("crm_app.pipeline.stage_created", {"stage_id": ids["closing"]}),
        (
            "crm_app.pipeline.stage_updated",
            {"stage_id": ids["meeting"], "fields": ["name", "probability"]},
        ),
        ("crm_app.pipeline.stages_reordered", {}),
    ]
    assert rows[4][0] == "crm_app.pipeline.stage_deleted"
    # The default pipeline's creation is not a user action.
    assert len(rows) == 4 + 1 + 11 + 14
    text = json.dumps([metadata for _, _, metadata in rows])
    for name in ("New business", "Closing", "Demo", "Sales"):
        assert name not in text
