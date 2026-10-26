"""Tags on contacts and companies (decision P3-C 5, 7, 8).

Drives `record_tag_probe` in a fresh interpreter and checks the history
and audit tables directly. Covers: tagging is a record update (roles,
If-Match, a new version, history and audit naming `tags` only); only the
workspace's own tags; the per-record limit; records carry their tags by
name; the lists and both CSV exports filter by any of the given tags,
across pages.
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
    tmp = tmp_path_factory.mktemp("record-tags")
    result = run_module("tests.integration.record_tag_probe", [], env, tmp, timeout=600)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def test_tagging_is_a_record_update_with_its_version(probe: Probe) -> None:
    assert probe["reader"] == 403
    assert probe["other_owner"] == 404
    assert probe["no_version"] == 428
    status, body = probe["stale"]
    assert status == 409
    assert body["detail"] == {"code": "stale_version", "current_version": 1}
    status, tagged, etag = probe["tagged"]
    assert status == 200
    assert tagged["version"] == 2
    assert etag == '"2"'
    assert probe["same"] == [200, 2]  # the same set changes nothing
    assert probe["cleared"] == [[], 3]
    assert probe["restored"] == 4


def test_a_record_carries_its_tags_by_name_once_each(probe: Probe) -> None:
    ids = probe["ids"]
    _, tagged, _ = probe["tagged"]
    expected = [{"id": ids["hot"], "name": "hot lead"}, {"id": ids["vip"], "name": "VIP"}]
    assert tagged["tags"] == expected
    assert probe["detail"]["tags"] == expected
    assert probe["listed_tags"] == {
        "Ann": [],
        "Ria": [{"id": ids["cold"], "name": "Cold"}],
        "Sam": expected,
    }
    status, company = probe["company"]
    assert status == 200
    assert company["tags"] == [
        {"id": ids["cold"], "name": "Cold"},
        {"id": ids["vip"], "name": "VIP"},
    ]


def test_only_the_workspaces_own_tags_and_at_most_twenty(probe: Probe) -> None:
    assert probe["unknown_tag"]["detail"] == {"code": "tag_not_found"}
    assert probe["too_many"] == 422
    assert probe["extra_field"] == 422
    assert probe["foreign_record"]["detail"] == {"code": "not_found"}


def test_lists_filter_by_any_of_the_given_tags(probe: Probe) -> None:
    assert probe["filters"] == {
        "vip": ["Sam"],
        "vip_or_cold": ["Ria", "Sam"],
        "foreign": [],
        "companies_hot": ["Acme"],
        "companies_vip_or_hot": ["Acme", "Zeta"],
        "untagged": ["Ann", "Ria", "Sam"],
    }
    assert probe["bad_filter"] == 422


def test_the_tag_filter_pages_like_any_other(probe: Probe) -> None:
    assert probe["paged"] == [["Ria"], ["Sam"], 2]


def test_the_exports_filter_by_tag_like_their_lists(probe: Probe) -> None:
    ids = probe["ids"]
    assert probe["exports"] == {
        "contacts": [ids["ria"], ids["sam"]],
        "companies": [ids["acme"]],
    }


def test_history_and_audit_name_tags_only(
    probe: Probe, owner_connection: psycopg.Connection
) -> None:
    ids = probe["ids"]
    history = owner_connection.execute(
        "SELECT fields FROM crm_app.activity WHERE contact_id = %s AND kind = 'updated'",
        (ids["sam"],),
    ).fetchall()
    assert history == [(["tags"],)] * 3  # tagged, cleared, tagged again
    audit = owner_connection.execute(
        "SELECT metadata FROM core.audit_log WHERE tenant_id = %s"
        " AND action = 'crm_app.contact.updated' AND resource_id = %s",
        (probe["workspace"], ids["sam"]),
    ).fetchall()
    assert [row[0] for row in audit] == [{"fields": ["tags"]}] * 3
    exported = owner_connection.execute(
        "SELECT metadata FROM core.audit_log WHERE tenant_id = %s"
        " AND action = 'crm_app.contacts.exported'",
        (probe["workspace"],),
    ).fetchall()
    assert [row[0] for row in exported] == [{"row_count": 2, "filter_keys": ["tag_id"]}]
    text = json.dumps([row[0] for row in audit + exported])
    for value in ("VIP", "hot lead", "Cold", ids["vip"], ids["cold"]):
        assert value not in text
