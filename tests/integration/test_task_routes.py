"""Task routes (decision P4-C, slice 4C; `crm_app.api.tasks`).

Drives `task_route_probe` in a fresh interpreter and checks the audit log
directly. Covers: Q6's roles (Members may delete tasks); tenant isolation on
every route and link; validation (titles, aware times, priorities, `done`);
idempotent creation; versions; completing and reopening; filters, due
windows, counts, order and paging; and audit entries without titles.
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
    tmp = tmp_path_factory.mktemp("tasks")
    result = run_module("tests.integration.task_route_probe", [], env, tmp, timeout=600)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def test_every_role_reads_and_members_and_up_write_and_delete(probe: Probe) -> None:
    assert probe["read"] == {
        "owner": 200,
        "admin": 200,
        "member": 200,
        "reader": 200,
        "other_owner": 404,
    }
    assert probe["create"] == {
        "owner": 201,
        "admin": 201,
        "member": 201,
        "reader": 403,
        "other_owner": 404,
    }
    assert probe["reader_update"] == 403
    assert probe["delete"] == {"reader": 403, "member": 204, "again": 404}


def test_a_task_is_created_with_its_links(probe: Probe) -> None:
    status, etag, task = probe["created"]
    assert (status, etag) == (201, '"1"')
    assert task["title"] == "Call Sam about the proposal"
    assert task["priority"] == "high"
    assert task["due_at"].endswith("Z")
    assert task["contact"]["name"] == "Sam Jansen"
    assert task["company"]["name"] == "Acme"
    assert task["opportunity"]["name"] == "Website redesign"
    assert (task["done"], task["completed_at"], task["version"]) == (False, None, 1)


def test_links_and_assignees_must_be_the_workspaces_own(probe: Probe) -> None:
    assert {k: v["code"] for k, v in probe["references"].items()} == {
        "foreign_contact": "contact_not_found",
        "archived_contact": "contact_not_found",
        "foreign_deal": "opportunity_not_found",
        "unknown_company": "company_not_found",
        "foreign_assignee": "assignee_not_member",
    }


def test_invalid_bodies_and_naive_times_are_refused(probe: Probe) -> None:
    assert set(probe["invalid"].values()) == {422}
    assert set(probe["update_invalid"].values()) == {422}
    assert probe["naive_window"] == 422


def test_a_repeated_create_with_the_same_key_creates_once(probe: Probe) -> None:
    assert probe["idempotent"] == [201, "true", True]


def test_changes_need_the_current_version(probe: Probe) -> None:
    assert probe["no_version"] == 428
    assert probe["stale"] == [409, {"code": "stale_version", "current_version": 1}]


def test_completing_and_reopening(probe: Probe) -> None:
    done, again, reopened = probe["lifecycle"]
    assert done == [True, True, True, 2]  # done, when, by whom, new version
    assert again == 2  # completing a done task changes nothing
    assert reopened == [False, None, "low", 3]
    assert probe["cleared"] == [None, None, None, 4]


def test_filters_counts_order_and_paging(probe: Probe) -> None:
    filters = probe["filters"]
    assert filters["overdue"] == ["Overdue call"]
    assert filters["window"] == ["Today email"]
    assert filters["done"] == ["Done already"]
    assert filters["assignee"] == ["Next week demo", "Overdue call"]
    assert filters["contact_none"] == []  # the link was cleared
    assert filters["deal"] == ["Call Sam about the proposal"]
    # Due first, in order; tasks without a due time last.
    assert filters["due_order"][:3] == ["Overdue call", "Today email", "Next week demo"]
    assert probe["counts"] == {"open": 8, "mine": 2, "overdue": 1, "done": 1}
    assert probe["counts_assignee"] == {"open": 2, "mine": 0, "overdue": 1, "done": 0}
    assert probe["paging"] == [9, 9, 9]
    assert probe["bad_cursor"] == 400


def test_another_workspaces_task_is_unreachable(probe: Probe) -> None:
    foreign = probe["foreign"]
    assert foreign["get"]["detail"] == {"code": "task_not_found"}
    assert (foreign["patch"], foreign["delete"]) == (404, 404)
    assert foreign["listed"] is False


def test_changes_are_audited_without_titles(
    probe: Probe, owner_connection: psycopg.Connection
) -> None:
    rows = owner_connection.execute(
        "SELECT action, metadata FROM core.audit_log WHERE tenant_id = %s"
        " AND resource_type = 'crm_app.task' AND resource_id = %s ORDER BY created_at",
        (probe["workspace"], probe["task_id"]),
    ).fetchall()
    assert [action for action, _ in rows] == [
        "crm_app.task.created",
        "crm_app.task.completed",
        "crm_app.task.reopened",
        "crm_app.task.updated",
        "crm_app.task.deleted",
    ]
    assert rows[2][1] == {"fields": ["priority"]}
    assert rows[3][1] == {"fields": ["assignee_user_id", "contact_id", "due_at"]}
    text = json.dumps([metadata for _, metadata in rows])
    assert "Call Sam" not in text
