"""In-app notifications (decision N-1).

Drives `notification_probe` in a fresh interpreter. A member hears of the
tasks, conversations and appointments someone else assigns them, and of
nothing they did themselves or that only replayed; reads and marks only
their own; labels follow the record and vanish with it; another workspace
sees nothing; old rows are removed. Bookings are covered by
`test_booking_page_routes.py`.
"""

from __future__ import annotations

import json
from typing import Any

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
    tmp = tmp_path_factory.mktemp("notifications")
    result = run_module("tests.integration.notification_probe", [], env, tmp, timeout=600)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def test_an_empty_inbox(probe: Probe) -> None:
    assert probe["empty"] == {"items": [], "next_cursor": None, "unread": 0, "unread_capped": False}


def test_only_assignments_by_someone_else_notify_once(probe: Probe) -> None:
    owner, member = probe["owner"], probe["member"]
    assert probe["task_replayed"] == "true"
    # The replay, the owner's own task, the rename and the member taking a
    # task themselves add nothing.
    assert probe["after_tasks"] == [["task_assigned", member, owner]]
    assert probe["after_all"] == [
        ["task_assigned", member, owner],
        ["conversation_assigned", member, owner],
        ["appointment_assigned", member, owner],
        ["appointment_assigned", owner, member],
    ]


def test_a_member_lists_their_own_newest_first_with_current_names(probe: Probe) -> None:
    page = probe["member_page"]
    assert page["unread"] == 3
    assert page["unread_capped"] is False
    assert page["next_cursor"] is None
    assert [(i["kind"], i["subject_type"], i["subject_label"]) for i in page["items"]] == [
        ("appointment_assigned", "appointment", "Intro"),
        ("conversation_assigned", "conversation", "Your quote"),
        ("task_assigned", "task", probe["labels_follow_renames"]),
    ]
    assert {i["actor_user_id"] for i in page["items"]} == {probe["owner"]}
    assert all(i["read_at"] is None for i in page["items"])
    owner_items = probe["owner_page"]["items"]
    assert [(i["kind"], i["actor_user_id"]) for i in owner_items] == [
        ("appointment_assigned", probe["member"])
    ]
    assert probe["reader_page"]["items"] == []


def test_pages_follow_the_cursor_and_refuse_bad_input(probe: Probe) -> None:
    first, second, more = probe["paging"]
    assert more is True
    assert len(first) == len(second) == 1
    assert first != second
    # Garbage, a cursor from another filter, a limit over 50, a member ID.
    assert probe["bad_cursor"] == [400, 400, 422, 422]


def test_a_member_marks_only_their_own_read(probe: Probe) -> None:
    # Another member's, an unknown one, and one from outside the workspace.
    assert probe["mark_others"] == [404, 404, 404]
    # Marking twice is the same; the owner's own stays unread.
    assert probe["mark_one"] == [204, 204, 2, 2, 1]
    assert probe["mark_all"] == [200, {"marked": 2}, 0, 1, {"marked": 0}]


def test_a_deleted_record_shows_as_unavailable(probe: Probe) -> None:
    assert probe["deleted_label"] == [None]


def test_another_workspace_sees_nothing(probe: Probe) -> None:
    assert probe["foreign"] == [404, 404, []]
    assert probe["rows_b"] == 0


def test_rows_older_than_ninety_days_are_removed_on_the_next_write(probe: Probe) -> None:
    assert probe["retention"] == [5, 5, 0]
