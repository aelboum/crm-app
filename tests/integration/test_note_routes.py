"""The note routes (slice 3B.3, `PHASE3-PLAN.md` §21.2, decision P3-B).

Drives `note_route_probe` in a fresh interpreter against the integration
database, then checks the audit trail as the owner connection. Covers who
may add, read, edit and delete (Q6 as amended by D3), optimistic
concurrency, the text rules, history and the record's version (D4, D5),
archived records (D8), idempotency including a concurrent pair, other
workspaces, paging, and that no error or audit entry carries note text.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import psycopg
import pytest

from tests.integration.note_route_probe import MARKER
from tests.support import REPO_ROOT, run_module

pytestmark = pytest.mark.usefixtures("migrated")

Probe = dict[str, Any]


@pytest.fixture(scope="module")
def probe(integration_env: dict[str, str], tmp_path_factory: pytest.TempPathFactory) -> Probe:
    env = {
        **integration_env,
        "PYTHONPATH": str(REPO_ROOT),
        # The probe adds about forty notes to one record within a minute; the
        # platform's per-route limit (60 a minute) is raised for this process
        # only, as in `test_record_lists.py`.
        "RATE_LIMIT_REQUESTS_PER_WINDOW": "1000",
    }
    cwd: Path = tmp_path_factory.mktemp("notes")
    result = run_module("tests.integration.note_route_probe", [], env, cwd, timeout=900)
    assert result.returncode == 0, result.stderr
    assert MARKER not in result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def test_owners_admins_and_members_add_notes_and_nobody_else(probe: Probe) -> None:
    assert probe["create"] == {
        "owner": 201,
        "admin": 201,
        "member": 201,
        "read_only": 403,
        "outsider": 404,
        "other_owner": 404,
        "anonymous": 401,
    }


def test_every_role_reads_notes_and_nobody_else(probe: Probe) -> None:
    assert probe["read"] == {
        "owner": 200,
        "member": 200,
        "read_only": 200,
        "outsider": 404,
        "other_owner": 404,
    }
    assert {tuple(v) for v in probe["read_only_view"]} == {(False, False)}


def test_the_author_or_an_admin_edits_and_deletes(probe: Probe) -> None:
    assert probe["views"] == {
        "member_own": [[True, True]],
        "member_others": [[False, False]],
        "admin_all": [[True, True]],
    }
    rule = probe["author_rule"]
    assert rule["member2_edit"] == [403, {"code": "not_note_author"}]
    assert rule["member2_delete"] == 403
    assert rule["read_only_edit"] == 403
    assert rule["read_only_delete"] == 403
    assert rule["own_stale"] == 409
    own = rule["own_edit"]
    assert (own["body"], own["version"], own["edited"]) == ("Fixed typo.", 2, True)
    assert own["updated_by_user_id"] == probe["users"]["member"]
    assert rule["same_text"] == 2  # unchanged text: no new version
    admin = rule["admin_edit"]
    assert (admin["body"], admin["version"]) == ("Admin tidied.", 3)
    assert admin["author_user_id"] == probe["users"]["member"]
    assert admin["updated_by_user_id"] == probe["users"]["admin"]
    assert rule["missing_version"] == 428
    assert probe["deletes"] == {
        "admin_deletes_members": 204,
        "member_deletes_own": 204,
        "again": 404,
    }


def test_concurrent_edits_of_one_version_let_one_win(probe: Probe) -> None:
    assert probe["concurrent_edit"] == [200, 409]


def test_the_text_rules(probe: Probe) -> None:
    validation = probe["validation"]
    assert {k: v for k, v in validation.items() if k not in ("control_body", "longest")} == {
        "empty": 422,
        "blank": 422,
        "too_long": 422,
        "control": 422,
        "nul": 422,
        "unknown_field": 422,
        "not_text": 422,
    }
    assert validation["longest"] == 201
    assert MARKER not in validation["control_body"]
    assert probe["stored"] == {
        "crlf": "Line one\nLine two\nLine three",
        "html": '<img src=x onerror="alert(1)"> & <b>bold</b>',  # stored as text
    }


def test_history_shows_added_notes_and_forgets_deleted_text(probe: Probe) -> None:
    history = probe["history"]
    assert history["doomed_id"] not in history["note_added_ids"]
    assert history["deleted_entries"] >= 3
    excerpt, truncated = history["long"]
    assert (len(excerpt), truncated) == (280, True)
    assert MARKER not in history["text"]
    before, after = probe["record_version_unchanged"]
    assert before == after


def test_archived_records_keep_notes_readable_and_deletable_only(probe: Probe) -> None:
    archived = probe["archived"]
    assert archived["add"] == [409, {"code": "record_archived"}]
    assert archived["edit"] == [409, {"code": "record_archived"}]
    assert archived["list"] == [True, [False, True]]
    assert archived["delete"] == 204
    assert archived["after_restore"] == 201


def test_a_retried_create_makes_one_note(probe: Probe) -> None:
    idem = probe["idempotency"]
    assert idem["first"][0] == 201
    assert idem["first"][2] is None
    assert idem["second"] == [201, idem["first"][1], "true"]
    assert idem["reused"] == [422, {"code": "idempotency_key_reused"}]
    assert idem["other_member"][0] == 201
    assert idem["other_member"][1] != idem["first"][1]
    statuses = sorted(status for status, _ in probe["idempotency_concurrent"])
    ids = {note_id for status, note_id in probe["idempotency_concurrent"] if status == 201}
    assert statuses in ([201, 201], [201, 409])
    assert len(ids) == 1
    assert probe["twice_count"] == 1


def test_other_workspaces_see_nothing(probe: Probe) -> None:
    assert probe["cross"] == {
        "list_via_b": 404,
        "add_via_b": 404,
        "edit_via_b": 404,
        "delete_via_b": 404,
        "edit_outsider": 404,
        "unknown_note": 404,
        "unknown_record": 404,
        "company_path_for_contact": 404,
        "after": "Private to A.",
    }


def test_notes_page_newest_first_without_gaps(probe: Probe) -> None:
    paging = probe["paging"]
    seen = [note for page in paging["pages"] for note in page]
    assert all(len(page) <= 2 for page in paging["pages"])
    assert sorted(seen) == sorted(paging["made"])
    assert len(seen) == len(set(seen))
    assert probe["cursor_other_record"] == 400


def test_deleting_a_record_deletes_its_notes(probe: Probe) -> None:
    assert probe["company_deleted"] == [204, 404, 404]


def test_audit_entries_name_the_note_and_record_but_never_the_text(
    probe: Probe, owner_connection: psycopg.Connection
) -> None:
    rows = owner_connection.execute(
        "SELECT action, resource_id, metadata::text FROM core.audit_log"
        " WHERE tenant_id = %s AND resource_type = 'crm_app.note'",
        (probe["workspace"],),
    ).fetchall()
    actions = {action for action, _, _ in rows}
    assert actions == {"crm_app.note.created", "crm_app.note.updated", "crm_app.note.deleted"}
    for _, _, metadata in rows:
        assert MARKER not in metadata
        assert set(json.loads(metadata)) == {"record_type", "record_id"}
