"""Deal routes (decision P4-B, slice 4B; `crm_app.api.opportunities`).

Drives `opportunity_route_probe` in a fresh interpreter and checks the
audit log directly. Covers: Q6's roles; tenant isolation on every route
and every reference (stage, contact, company, owner); exact money in the
workspace's currency at creation; validation and stable errors; versions
and idempotent creation; the outcome lifecycle and lost reasons; history
order, content and paging; filters, orders, cursors and the summary's
parity with the list; removing a stage that holds deals; and concurrent
updates and stage removals.
"""

from __future__ import annotations

import json
from typing import Any

import psycopg
import pytest

from tests.support import REPO_ROOT, run_module

pytestmark = pytest.mark.usefixtures("migrated")

Probe = dict[str, Any]
VALIDATION = "validation"


@pytest.fixture(scope="module")
def probe(integration_env: dict[str, str], tmp_path_factory: pytest.TempPathFactory) -> Probe:
    env = {**integration_env, "PYTHONPATH": str(REPO_ROOT)}
    tmp = tmp_path_factory.mktemp("deals")
    result = run_module("tests.integration.opportunity_route_probe", [], env, tmp, timeout=600)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def _code(detail: object) -> object:
    """A refusal's stable code, or `validation` for a field-level 422."""
    return detail["code"] if isinstance(detail, dict) else VALIDATION


def test_every_role_reads_members_and_up_write_and_owners_and_admins_delete(probe: Probe) -> None:
    assert probe["read"] == {
        "owner": 200,
        "admin": 200,
        "member": 200,
        "reader": 200,
        "other_owner": 404,
    }
    assert probe["anonymous"] == 401
    assert probe["create"] == {
        "owner": 201,
        "admin": 201,
        "member": 201,
        "reader": 403,
        "other_owner": 404,
    }
    assert probe["update_reader"] == 403
    assert probe["delete"] == {"member": 403, "reader": 403, "admin": 204}
    assert probe["deleted_get"] == 404
    assert probe["stage_removal"]["member_cannot"] == 403


def test_a_deal_is_created_with_its_links_and_exact_value(probe: Probe) -> None:
    status, etag, deal = probe["created"]
    assert (status, etag) == (201, '"1"')
    assert deal["title"] == "Website redesign"
    assert deal["amount"] == "12500.50"
    assert deal["currency"] == "EUR"
    assert deal["weighted_amount"] == "5000.20"  # 40 % of 12500.50
    assert deal["stage"]["name"] == "Meeting"
    assert deal["expected_close_date"] == "2026-12-15"
    assert deal["contact"]["name"] == "Sam Jansen"
    assert deal["company"]["name"] == "Acme"
    assert (deal["outcome"], deal["lost_reason"], deal["closed_at"]) == ("open", None, None)
    bare = probe["bare"]
    assert (bare["stage"]["position"], bare["amount"], bare["owner_user_id"]) == (0, None, None)


def test_amounts_are_decimal_strings_never_rounded(probe: Probe) -> None:
    money = {label: [status, _code(detail)] for label, (status, detail) in probe["money"].items()}
    assert money == {
        "three_decimals": [422, "invalid_amount"],
        "negative": [422, VALIDATION],
        "number": [422, VALIDATION],
        "exponent": [422, VALIDATION],
        "thirteen_digits": [422, "invalid_amount"],
        "comma": [422, VALIDATION],
        "leading_zero": [422, "invalid_amount"],
    }
    assert probe["money_max"] == "999999999999.99"


def test_references_must_be_the_workspaces_own(probe: Probe) -> None:
    assert {k: v["detail"]["code"] for k, v in probe["references"].items()} == {
        "foreign_stage": "stage_not_found",
        "unknown_stage": "stage_not_found",
        "foreign_contact": "contact_not_found",
        "archived_contact": "contact_not_found",
        "foreign_company": "company_not_found",
        "foreign_owner": "owner_not_member",
    }


def test_invalid_bodies_are_refused(probe: Probe) -> None:
    assert set(probe["invalid"].values()) == {422}
    assert {k: [s, d] for k, (s, d) in probe["update_invalid"].items()} == {
        "null_title": [422, VALIDATION],
        "null_stage": [422, VALIDATION],
        "foreign_stage": [422, {"code": "stage_not_found"}],
        "foreign_company": [422, {"code": "company_not_found"}],
        "too_precise": [422, {"code": "invalid_amount"}],
        "outcome_field": [422, VALIDATION],
    }
    assert probe["list_params_refused"] == 422


def test_a_repeated_create_with_the_same_key_creates_once(probe: Probe) -> None:
    assert probe["idempotent"] == [201, 201, "true", True, 422, {"code": "idempotency_key_reused"}]


def test_updates_need_the_current_version_and_equal_values_change_nothing(probe: Probe) -> None:
    assert probe["update_no_version"] == 428
    assert probe["update_stale"] == [409, {"code": "stale_version", "current_version": 1}]
    assert probe["changed"] == ["Website rebuild", "13000.00", "Proposal", 2]
    assert probe["update_same"] == [200, 2]
    owner, amount, contact, version = probe["cleared"]
    assert (amount, contact, version) == (None, None, 4)
    assert owner is not None


def test_outcomes_follow_their_lifecycle(probe: Probe) -> None:
    assert {k: [s, d["code"]] for k, (s, d) in probe["outcome_refusals"].items()} == {
        "lost_without_reason": [422, "lost_reason_required"],
        "won_with_reason": [422, "lost_reason_not_allowed"],
    }
    # A won deal has no weighted value; it cannot go straight to lost, nor
    # change stage, but its other fields can change.
    assert probe["won"] == [200, "won", True, None]
    assert probe["won_to_lost"] == [409, {"code": "invalid_outcome_transition"}]
    assert probe["closed_stage_change"] == [409, {"code": "deal_closed"}]
    assert probe["closed_title_change"] == [200, 6]
    # Reopen, then lose with a trimmed reason; the same request again is a no-op.
    assert probe["lifecycle"] == ["open", None, 200, "Chose a competitor", 200, 8]
    assert probe["reopened_clears_reason"] == ["open", None, 9]


def test_the_history_explains_the_deal_newest_first(probe: Probe) -> None:
    kinds = [entry[0] for entry in probe["history"]]
    assert kinds == [
        "outcome_changed",
        "outcome_changed",
        "outcome_changed",
        "updated",
        "outcome_changed",
        "updated",
        "owner_changed",
        "stage_changed",
        "updated",
        "created",
    ]
    stage = probe["history"][7]
    assert stage[2:5] == ["Meeting", "Proposal", "moved"]
    assert probe["history"][8][1] == ["amount", "title"]
    assert [entry[5:7] for entry in probe["history"][:3]] == [
        ["lost", "open"],
        ["open", "lost"],
        ["won", "open"],
    ]
    assert probe["history"][-1][3] == "Meeting"
    text = probe["history_text"]
    for secret in ("Website", "12500", "13000", "competitor"):
        assert secret not in text
    assert probe["history_paging"] == [3, True]


def test_another_workspaces_deal_is_unreachable(probe: Probe) -> None:
    foreign = probe["foreign"]
    assert {
        k: foreign[k] for k in ("get", "patch", "outcome", "history", "delete")
    } == dict.fromkeys(("get", "patch", "outcome", "history", "delete"), 404)
    assert foreign["by_their_path"] == 404
    assert foreign["listed"] is False
    assert foreign["detail"] == {"code": "opportunity_not_found"}


def test_lists_filter_order_and_page_without_gaps(probe: Probe) -> None:
    filters = probe["filters"]
    assert filters["q"] == ["Alpha"]
    assert filters["idle"] == ["Alpha"]
    assert filters["company"] == ["Website rebuild 2"]
    assert filters["owner_admin"] == ["Website rebuild 2"]
    assert filters["owner_me"] == []
    assert filters["won"] == []
    assert "Gamma" not in filters["stage"]
    assert filters["amount_asc"] == ["Alpha", "beta", "Max"]
    assert probe["nulls_last_desc"] is True  # PostgreSQL's rule: NULLs first descending
    assert probe["paging"] == [10, 10, 10]
    assert probe["bad_cursor"] == 400
    assert probe["cursor_other_filter"] == 400


def test_the_summary_matches_the_list(probe: Probe) -> None:
    for stage, (summarised, listed) in probe["parity"].items():
        assert summarised == listed, stage
    assert probe["summary_first_stage"] == [
        {"currency": "EUR", "amount": "1000000000350.74", "weighted_amount": "200000000070.15"}
    ]


def test_a_deals_currency_is_the_workspaces_when_it_was_created(probe: Probe) -> None:
    assert probe["currency"] == ["JPY", "1500", {"code": "invalid_amount"}, "EUR", ["EUR", "JPY"]]


def test_a_stage_holding_deals_is_removed_only_by_moving_them(probe: Probe) -> None:
    removal = probe["stage_removal"]
    assert removal["in_use"] == [409, {"code": "stage_in_use", "deals": 9}, 9]
    assert removal["same_target"] == [422, {"code": "invalid_move_target"}]
    assert removal["foreign_target"] == [422, {"code": "invalid_move_target"}]
    assert removal["moved"] == [200, 1, 3]
    assert removal["left"] == 0
    assert removal["alpha"] == [True, 2, "stage_changed", "stage_removed"]


def test_concurrent_writes_are_serialised(probe: Probe) -> None:
    assert probe["concurrent_updates"] == ["ok", "stale_version", "stale_version", "stale_version"]
    removal = probe["concurrent_removal"]
    assert removal["removal"] == "ok"
    assert set(removal["created"]) <= {"ok", "stage_not_found"}
    assert removal["left_in_removed_stage"] == 0


def test_changes_are_audited_without_titles_amounts_or_reasons(
    probe: Probe, owner_connection: psycopg.Connection
) -> None:
    rows = owner_connection.execute(
        "SELECT action, metadata FROM core.audit_log WHERE tenant_id = %s"
        " AND resource_type = 'crm_app.opportunity' AND resource_id = %s ORDER BY created_at",
        (probe["workspace"], probe["deal_id"]),
    ).fetchall()
    assert [action for action, _ in rows][:3] == [
        "crm_app.opportunity.created",
        "crm_app.opportunity.updated",
        "crm_app.opportunity.updated",
    ]
    assert rows[0][1]["fields"] == [
        "amount",
        "company_id",
        "contact_id",
        "expected_close_date",
        "owner_user_id",
        "stage_id",
        "title",
    ]
    assert (
        "crm_app.opportunity.outcome_changed",
        {"outcome_from": "open", "outcome_to": "won"},
    ) in [(action, metadata) for action, metadata in rows]
    text = json.dumps([metadata for _, metadata in rows])
    for secret in ("Website", "12500", "competitor"):
        assert secret not in text
    deleted = owner_connection.execute(
        "SELECT count(*) FROM core.audit_log WHERE tenant_id = %s"
        " AND action = 'crm_app.opportunity.deleted' AND resource_id = %s",
        (probe["workspace"], probe["bare_id"]),
    ).fetchone()
    assert deleted == (1,)
    removal = owner_connection.execute(
        "SELECT metadata FROM core.audit_log WHERE tenant_id = %s"
        " AND action = 'crm_app.pipeline.stage_deleted'",
        (probe["workspace"],),
    ).fetchall()
    assert [row[0]["moved_deals"] for row in removal][:1] == [9]
