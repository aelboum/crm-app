"""Inbox search and paging (decision P6-C1).

Drives `conversation_search_probe` in a fresh interpreter: subject, message
and note text by word prefix in any case and order; contact names and
email; closed threads only under their status; search input taken
literally (wildcards, quotes, query syntax and backslashes match nothing);
other workspaces' threads never found and their members refused; length and
NUL limits; cursor paging that visits every thread once and refuses a
cursor issued for other filters.
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
    env.pop("EMAIL_SENDING_ENABLED", None)
    tmp = tmp_path_factory.mktemp("conversation_search")
    result = run_module("tests.integration.conversation_search_probe", [], env, tmp, timeout=600)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def test_message_subject_and_note_text_are_found_by_word_prefix(probe: Probe) -> None:
    assert probe["message_text"] == ["t1"]
    assert probe["prefix_any_case"] == ["t1"]
    assert probe["two_words"] == ["t1"]
    assert probe["words_in_any_order"] == ["t1"]
    assert probe["subject"] == ["t2"]
    assert probe["note_text"] == ["t2"]
    assert probe["percent_in_text"] == ["t2"]
    assert probe["unicode"] == ["t3"]


def test_contacts_are_found_by_name_and_email(probe: Probe) -> None:
    assert probe["contact_last_name"] == ["t1", "t2"]
    assert probe["contact_first_name"] == ["t3"]
    assert probe["contact_email"] == ["t3"]


def test_closed_threads_are_found_only_under_their_status(probe: Probe) -> None:
    assert probe["closed_hidden_from_open"] == []
    assert probe["closed_found_in_closed"] == ["t2"]


def test_search_input_is_literal_and_empty_results_are_empty(probe: Probe) -> None:
    for key in (
        "no_match",
        "only_percent",
        "only_underscore",
        "quote_injection",
        "query_syntax",
        "backslash",
    ):
        assert probe[key] == [], key
    assert probe["blank"] == ["t1", "t2", "t3"]
    assert probe["too_long"] == 422
    assert probe["nul"] == 422


def test_search_stays_inside_the_workspace(probe: Probe) -> None:
    assert probe["reader"] == ["t1"]
    assert probe["other_workspace_own"] == ["tb"]
    assert probe["other_workspace_lastname"] == ["tb"]
    assert probe["other_owner_on_a"] == 404
    assert probe["outsider_on_a"] == 404


def test_paging_visits_every_thread_once_latest_first(probe: Probe) -> None:
    assert probe["paged"] == ["t3", "t2", "t1"]
    assert probe["paged"] == probe["unpaged"]
    assert probe["unpaged_cursor"] is None
    assert probe["search_paged"] is True
    assert probe["cursor_other_filter"] == 400
    assert probe["cursor_garbage"] == 400
    assert probe["limit_zero"] == 422
    assert probe["limit_over"] == 422
