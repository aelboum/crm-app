"""Automations (decision P8-A): definitions, activation, the trigger, and an
execution that never acts twice.

Drives `automation_probe` in a fresh interpreter. Covers who may read and
manage; refused definitions (unknown actions, imports as a source, extra
fields, bounds); activation's checks; the yes branch (tag, owner, task,
wait, task) and the no branch; a retried job while waiting, two jobs at
once after the wait, and a replay after completion acting once; sources
that do not match; another workspace; a deleted contact; counted
failures; run history; pausing; deleting; and the sweeper's due index.
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
    env = {
        **integration_env,
        "PYTHONPATH": str(REPO_ROOT),
        "RATE_LIMIT_REQUESTS_PER_WINDOW": "1000",
    }
    tmp = tmp_path_factory.mktemp("automations")
    result = run_module("tests.integration.automation_probe", [], env, tmp, timeout=600)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def test_owners_and_admins_manage_and_every_member_reads(probe: Probe) -> None:
    assert probe["create_access"] == {"member": 403, "outsider": 404, "other_owner": 404}
    assert probe["read_access"] == {"member": 200, "other_owner": 404, "outsider": 404}
    assert probe["delete_member"] == 403


def test_definitions_are_data_checked_by_rule(probe: Probe) -> None:
    assert probe["created"] == [201, "New lead follow-up", "draft", None]
    assert set(probe["refused"].values()) == {"invalid_automation"}
    assert probe["activate_empty"] == {
        "code": "invalid_automation",
        "rule": "yes: at least one action",
    }
    assert probe["activate_gone_tag"]["rule"] == "a tag it names no longer exists"
    assert probe["activated"] == [200, "active", 1]
    assert probe["edit_active"] == {"code": "automation_active"}


def test_a_matching_contact_runs_the_yes_branch_until_its_wait(probe: Probe) -> None:
    assert probe["started"] == ["running", True]
    assert probe["first_advance"] == "waiting"
    first = probe["after_first"]
    assert (first["run"]["status"], first["run"]["branch"], first["run"]["next_step"]) == (
        "waiting",
        "yes",
        4,
    )
    assert first["tags"] == [probe["tags"]["hot"]]
    assert first["owner"] == probe["admin"]
    assert len(first["tasks"]) == 1
    task = first["tasks"][0]
    assert (task["title"], task["priority"], task["due"]) == ("Call the new lead", "high", True)
    assert task["assignee_user_id"] == probe["admin"]  # the owner the run just assigned
    assert first["due"] is True


def test_retried_and_parallel_jobs_never_act_twice(probe: Probe) -> None:
    assert probe["while_waiting"] == ["waiting", 1]
    assert probe["parallel"] == ["completed", "completed"]
    after = probe["after_wait"]
    assert after["tasks"] == ["Call the new lead", "Follow up"]
    assert after["follow_up_assignee"] == probe["admin"]
    assert after["run"]["status"] == "completed"
    assert after["due"] is False
    assert [(s["position"], s["action"], s["outcome"]) for s in after["steps"]] == [
        (0, "add_tag", "done"),
        (1, "assign_owner", "done"),
        (2, "create_task", "done"),
        (3, "wait", "done"),
        (4, "create_task", "done"),
    ]
    assert probe["replay_completed"] == ["completed", 2]


def test_the_condition_picks_the_no_branch_and_sources_filter(probe: Probe) -> None:
    assert probe["no_branch"] == ["completed", [probe["tags"]["cold"]], "no"]
    assert probe["other_source"] is None
    assert probe["other_workspace_runs"] == 0


def test_a_deleted_contact_cancels_and_failures_end_a_run(probe: Probe) -> None:
    assert probe["deleted_contact"] == "cancelled"
    statuses, run, due = probe["failures"]
    assert statuses == ["running", "running", "running", "running", "failed"]
    assert (run["status"], run["attempts"], run["last_error"]) == ("failed", 5, "operationalerror")
    assert due is False


def test_runs_are_history_and_pausing_or_deleting_stops_them(probe: Probe) -> None:
    status, count, first_step = probe["history"]
    assert (status, count) == (200, 4)
    assert (first_step["branch"], first_step["position"], first_step["action"]) == (
        "yes",
        0,
        "add_tag",
    )
    assert probe["paused"] == ["paused", None]
    assert probe["deleted"] == 204
    assert probe["after_delete"] == [0, False]
    assert probe["due_twice"] == [True, False]


def test_changes_are_audited_as_the_member(
    probe: Probe, owner_connection: psycopg.Connection
) -> None:
    rows = owner_connection.execute(
        "SELECT action, actor_user_id FROM core.audit_log"
        " WHERE resource_type = 'crm_app.automation' AND actor_user_id = %s ORDER BY created_at",
        (probe["owner"],),
    ).fetchall()
    actions = [action for action, _ in rows]
    for expected in (
        "crm_app.automation.created",
        "crm_app.automation.activated",
        "crm_app.automation.paused",
        "crm_app.automation.deleted",
    ):
        assert expected in actions


def test_each_ended_run_is_audited_once_by_the_run_worker(probe: Probe) -> None:
    audit = probe["run_audit"]
    assert all(row["no_member"] for row in audit["entries"])
    entries = {row["action"]: row["n"] for row in audit["entries"]}
    assert entries == {row["action"]: row["n"] for row in audit["runs"]}
    assert {"crm_app.automation_run.completed", "crm_app.automation_run.failed"} <= set(entries)
    assert "crm_app.automation_run.cancelled" in entries
