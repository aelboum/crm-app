"""Import retention (decision P3-F 7; `crm_app.import_maintenance`).

Covers: a finished import's staged rows are deleted when due and its
created records stay; a never-committed preview's rows are deleted and the
import becomes `expired`; a queued import is left alone and checked a day
later; an import not yet due is untouched; an entry without an import is
removed; a second run finds nothing to do; the command prints counts only.
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
    tmp = tmp_path_factory.mktemp("import-maintenance")
    result = run_module("tests.integration.import_maintenance_probe", [], env, tmp, timeout=600)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def test_due_rows_are_deleted_and_created_records_stay(probe: Probe) -> None:
    assert probe["finished"] == {
        "status": "completed",
        "rows": 0,
        "imported_contacts": 2,
        "entry_later": None,
    }


def test_a_preview_never_committed_expires(probe: Probe) -> None:
    assert probe["abandoned"]["status"] == "expired"
    assert probe["abandoned"]["rows"] == 0
    assert probe["abandoned"]["entry_later"] is None


def test_a_queued_import_is_left_alone_and_checked_later(probe: Probe) -> None:
    assert probe["queued"]["status"] == "queued"
    assert probe["queued"]["rows"] == 2
    assert probe["queued"]["entry_later"] is True


def test_an_import_not_yet_due_is_untouched(probe: Probe) -> None:
    assert probe["recent"]["status"] == "previewed"
    assert probe["recent"]["rows"] == 2
    assert probe["recent"]["entry_later"] is True


def test_the_runs_report_counts_and_a_second_run_finds_nothing(probe: Probe) -> None:
    report = probe["report"]
    assert report["cleared"] >= 2
    assert report["expired"] >= 1
    assert report["postponed"] >= 1
    assert report["orphans"] >= 1
    assert probe["again"] == {"cleared": 0, "expired": 0, "postponed": 0, "orphans": 0}


def test_the_command_prints_counts_only(integration_env: dict[str, str], tmp_path: Path) -> None:
    env = {**integration_env, "PYTHONPATH": str(REPO_ROOT)}
    result = run_module("crm_app.import_maintenance", [], env, tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().startswith("imports: cleared ")
    refused = run_module("crm_app.import_maintenance", ["--now"], env, tmp_path)
    assert refused.returncode == 2
