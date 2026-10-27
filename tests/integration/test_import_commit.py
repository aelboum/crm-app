"""Committing CSV imports (decision P3-F 5; `crm_app.import_commit`).

Drives `import_commit_probe` in a fresh interpreter, running the worker
job's function directly, and checks the database. Covers: Owner and Admin
only; one queued or running import per workspace; rows become records with
the API's rules, duplicates that appeared after the preview are skipped,
nothing is created twice when the job is delivered again; cancel; the queue
being unreachable; batches, a failure, and resuming from the checkpoint;
the retention due date moving to seven days after the finish; history and
audit for created records.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

import psycopg
import pytest

from tests.support import REPO_ROOT, run_module

pytestmark = pytest.mark.usefixtures("migrated")

Probe = dict[str, Any]


@pytest.fixture(scope="module")
def probe(integration_env: dict[str, str], tmp_path_factory: pytest.TempPathFactory) -> Probe:
    env = {**integration_env, "PYTHONPATH": str(REPO_ROOT)}
    tmp = tmp_path_factory.mktemp("import-commit")
    result = run_module("tests.integration.import_commit_probe", [], env, tmp, timeout=900)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def test_only_owners_and_admins_commit(probe: Probe) -> None:
    assert probe["member"] == 403
    assert probe["foreign"] == 404


def test_committing_queues_once_and_one_import_runs_at_a_time(probe: Probe) -> None:
    assert probe["queued"] == [200, "queued"]
    assert probe["commit_again"]["detail"] == {"code": "import_not_previewed"}
    assert probe["one_at_a_time"]["detail"] == {"code": "import_in_progress"}
    assert probe["second_now"] == 200  # once the first finished


def test_rows_become_records_and_late_duplicates_are_skipped(probe: Probe) -> None:
    assert probe["done"] == {
        "status": "completed_with_errors",
        "created_rows": 2,
        "skipped_rows": 1,
        "failed_rows": 0,
        "invalid_rows": 1,
        "duplicate_rows": 1,
    }
    assert probe["finished"] is not None
    assert probe["rows"] == [
        [1, "created", True],
        [2, "skipped", False],
        [3, "invalid", False],
        [4, "duplicate", False],
        [5, "created", True],
    ]


def test_a_repeated_delivery_creates_nothing_twice(probe: Probe) -> None:
    assert probe["contacts"] == [
        ["Ann", "manual"],
        ["Di", "import"],
        ["Sam", "import"],
        ["Taken", "manual"],
    ]


def test_retention_is_seven_days_after_the_import_finishes(probe: Probe) -> None:
    due = datetime.fromisoformat(probe["due"])
    finished = datetime.fromisoformat(probe["finished"])
    assert due - finished == timedelta(days=7)


def test_nothing_to_import_cancel_and_an_unreachable_queue(probe: Probe) -> None:
    assert probe["nothing"]["detail"] == {"code": "nothing_to_import"}
    assert probe["cancel"] is True
    assert probe["cancelled"] == ["cancelled", 0]
    assert probe["cancel_finished"]["detail"] == {"code": "import_not_running"}
    assert probe["unqueued"] == "previewed"


def test_a_failed_import_resumes_from_its_checkpoint(probe: Probe) -> None:
    # The failing batch is rolled back whole; the first batch of 500 stays.
    assert probe["failed"] == ["failed", 500, True]
    assert probe["resumed"] == [200, "queued"]
    assert probe["big"] == ["completed", 1200, 0]
    assert probe["resume_again"]["detail"] == {"code": "import_not_failed"}


def test_created_records_have_history_and_audit_naming_the_import(
    probe: Probe, owner_connection: psycopg.Connection
) -> None:
    workspace, main = probe["workspace"], probe["ids"]["main"]
    created = owner_connection.execute(
        "SELECT count(*) FROM core.audit_log WHERE tenant_id = %s"
        " AND action = 'crm_app.contact.created' AND metadata->>'import_id' = %s",
        (workspace, main),
    ).fetchone()
    assert created == (2,)
    history = owner_connection.execute(
        "SELECT count(*) FROM crm_app.activity a JOIN crm_app.contact c"
        " ON c.tenant_id = a.tenant_id AND c.id = a.contact_id"
        " WHERE a.tenant_id = %s AND a.kind = 'created' AND c.source = 'import'",
        (workspace,),
    ).fetchone()
    assert history == (1203,)  # Sam, Di and the 1,200 bulk rows, plus Ed
    completed = owner_connection.execute(
        "SELECT action, metadata FROM core.audit_log WHERE resource_id = %s"
        " AND action LIKE 'crm_app.import.%%' ORDER BY created_at",
        (main,),
    ).fetchall()
    assert [action for action, _ in completed] == [
        "crm_app.import.previewed",
        "crm_app.import.committed",
        "crm_app.import.completed",
    ]
    assert completed[-1][1] == {
        "entity": "contact",
        "created_rows": 2,
        "skipped_rows": 1,
        "failed_rows": 0,
    }
