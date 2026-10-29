"""Record history (slice 3B.2, `PHASE3-PLAN.md` §21.2, decision P3-B).

Drives `history_probe` in a fresh interpreter against the integration
database. Covers: every contact and company change writes its entries in
the same transaction (a refused change writes none), the payload carries
field names, stages, user IDs and company references only (D5), a deleted
company leaves `company_unlinked` on its contacts, keyset paging, and who
may read a history (every role of the workspace; nobody else), and the
workspace's feed across contacts and companies for the Home page (P4-D 4).
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from tests.integration.history_probe import FEED_NOTE, LEAK_CITY, LEAK_EMAIL
from tests.support import REPO_ROOT, run_module

pytestmark = pytest.mark.usefixtures("migrated")

Probe = dict[str, Any]


@pytest.fixture(scope="module")
def probe(integration_env: dict[str, str], tmp_path_factory: pytest.TempPathFactory) -> Probe:
    env = {**integration_env, "PYTHONPATH": str(REPO_ROOT)}
    cwd: Path = tmp_path_factory.mktemp("history")
    result = run_module("tests.integration.history_probe", [], env, cwd, timeout=900)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def _of(entries: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    return [e for e in entries if e["kind"] == kind]


def test_every_contact_change_writes_its_entries(probe: Probe) -> None:
    assert probe["contact_steps"] == [200] * 8
    assert probe["contact_history_status"] == 200
    entries = probe["contact_history"]
    assert Counter(e["kind"] for e in entries) == {
        "created": 1,
        "updated": 2,
        "stage_changed": 1,
        "owner_changed": 1,
        "company_unlinked": 2,
        "company_linked": 1,
        "archived": 1,
        "restored": 1,
    }
    # Newest first: the last two changes lead, creation is last.
    assert [e["kind"] for e in entries[:2]] == ["restored", "archived"]
    assert entries[-1]["kind"] == "created"
    assert all(e["actor_user_id"] == probe["owner"] for e in entries)


def test_entries_carry_names_stages_ids_and_references_only(probe: Probe) -> None:
    entries = probe["contact_history"]
    assert sorted(e["fields"] for e in _of(entries, "updated")) == [
        ["city", "email"],
        ["job_title"],
    ]
    (stage,) = _of(entries, "stage_changed")
    assert (stage["stage_from"], stage["stage_to"]) == ("lead", "customer")
    (owner,) = _of(entries, "owner_changed")
    assert (owner["owner_from"], owner["owner_to"]) == (None, probe["member"])
    first, second = probe["companies"]["first"], probe["companies"]["second"]
    (linked,) = _of(entries, "company_linked")
    assert (linked["company_id"], linked["company_name"]) == (second, "Second BV")
    assert sorted(e["company_id"] for e in _of(entries, "company_unlinked")) == sorted(
        [first, second]
    )
    for entry in entries:
        if entry["kind"] != "updated":
            assert entry["fields"] is None
        assert entry["note_id"] is None
        assert entry["note_excerpt"] is None


def test_history_never_contains_field_values(probe: Probe) -> None:
    text = probe["contact_history_text"]
    assert LEAK_CITY not in text
    assert LEAK_EMAIL not in text


def test_a_refused_change_writes_no_entry(probe: Probe) -> None:
    status, count = probe["refused"]
    assert status == 409
    assert count == len(probe["contact_history"])


def test_company_changes_write_their_entries(probe: Probe) -> None:
    entries = probe["company_history"]
    assert [e["kind"] for e in entries] == ["restored", "archived", "updated", "created"]
    assert entries[2]["fields"] == ["industry", "name"]


def test_deleting_a_company_unlinks_its_contacts_in_their_history(probe: Probe) -> None:
    assert probe["company_deleted"] == 204
    entries = probe["unlinked_by_delete"]
    assert [e["kind"] for e in entries] == ["company_unlinked", "created"]
    assert entries[0]["company_id"] == probe["doomed"]
    assert entries[0]["company_name"] is None  # the company is gone
    assert probe["deleted_company_history"] == 404


def test_history_pages_by_cursor_without_gaps_or_repeats(probe: Probe) -> None:
    pages = probe["pages"]
    assert all(len(page) <= 2 for page in pages)
    seen = [entry for page in pages for entry in page]
    assert len(seen) == len(set(seen))
    assert seen == [e["id"] for e in probe["contact_history"]]


def test_cursors_and_parameters_are_checked(probe: Probe) -> None:
    assert probe["cursor_other_record"] == 400
    assert probe["cursor_garbage"] == 400
    assert probe["limit_too_high"] == 422
    assert probe["unknown_param"] == 422


def test_every_role_reads_history_and_nobody_else_does(probe: Probe) -> None:
    assert probe["access"] == {
        "member": 200,
        "read_only": 200,
        "outsider": 404,
        "other_owner": 404,
        "anonymous": 401,
        "foreign_path": 404,
        "unknown_record": 404,
        "company_path_for_contact": 404,
    }


def test_the_feed_lists_the_newest_entries_of_the_workspace(probe: Probe) -> None:
    assert probe["feed_status"] == [201, 200]
    feed = probe["feed"]
    # 16 or more entries were written above; the limit caps the answer.
    assert 16 <= len(feed) <= 20
    assert probe["feed_default"] == 10
    stamps = [entry["occurred_at"] for entry in feed]
    assert stamps == sorted(stamps, reverse=True)
    newest = feed[0]
    assert (newest["kind"], newest["record_type"]) == ("note_added", "contact")
    assert (newest["record_id"], newest["record_name"]) == (probe["contact"], "Hist")
    assert newest["note_excerpt"] is None
    records = probe["feed_records"]
    plural = {"contact": "contacts", "company": "companies"}
    for entry in feed:
        assert entry["record_id"] in records[plural[entry["record_type"]]]
    assert {e["record_name"] for e in feed if e["record_type"] == "contact"} <= {
        "Hist",
        "Taken",
        "Linked",
    }


def test_the_feed_carries_no_values_or_note_text(probe: Probe) -> None:
    text = probe["feed_text"]
    assert FEED_NOTE not in text
    assert LEAK_CITY not in text
    assert LEAK_EMAIL not in text


def test_the_feed_is_for_members_of_the_workspace_only(probe: Probe) -> None:
    assert probe["feed_access"] == {
        "member": 200,
        "outsider": 404,
        "other_owner": 404,
        "anonymous": 401,
        "limit_zero": 422,
        "limit_too_high": 422,
        "unknown_param": 422,
    }
    assert probe["other_feed"] == ["Elsewhere"]
