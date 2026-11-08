"""Reports against a known dataset (decision P10-A, `crm_app.reports`).

Drives `report_probe` in a fresh interpreter. Every figure below follows
from the rows the probe seeds; see its comments. Covers the period's edges
in the workspace's time zone, the comparison period, per-currency values,
the definitions of win rate, on-time tasks and no-show rate, another
workspace's rows, who may read which report, and refused periods.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from tests.support import REPO_ROOT, run_module

pytestmark = pytest.mark.usefixtures("migrated")

Probe = dict[str, Any]
PERIOD = {"start": "2026-10-01", "end": "2026-10-31", "days": 31}


@pytest.fixture(scope="module")
def probe(integration_env: dict[str, str], tmp_path_factory: pytest.TempPathFactory) -> Probe:
    env = {
        **integration_env,
        "PYTHONPATH": str(REPO_ROOT),
        "RATE_LIMIT_REQUESTS_PER_WINDOW": "1000",
    }
    tmp = tmp_path_factory.mktemp("reports")
    result = run_module("tests.integration.report_probe", [], env, tmp, timeout=600)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def test_contacts_count_by_the_workspaces_calendar_days(probe: Probe) -> None:
    assert probe["contacts"] == {
        "period": PERIOD,
        "capped": False,
        # 00:30 on 1 October in Amsterdam counts; 23:30 on 30 September does not.
        "created": 2,
        "created_before": 1,
        "sources": [{"source": "manual", "count": 1}, {"source": "referral", "count": 1}],
    }
    assert probe["one_day"]["created"] == 1
    assert probe["one_day"]["created_before"] == 1


def test_another_workspaces_rows_are_never_counted(probe: Probe) -> None:
    assert probe["contacts"]["created"] == 2
    assert probe["other_workspace_contacts"] == 1


def test_deals_won_and_lost_by_close_time_with_values_per_currency(probe: Probe) -> None:
    deals = probe["deals"]
    owner, admin = probe["owner"], probe["admin"]
    assert deals["period"] == PERIOD
    assert (deals["created"], deals["created_before"]) == (3, 2)
    assert (deals["won"], deals["won_before"], deals["lost"], deals["lost_before"]) == (2, 1, 1, 0)
    assert (deals["win_rate"], deals["win_rate_before"]) == (67, 100)
    assert deals["won_value"] == [
        {"currency": "EUR", "amount": "1000.50"},
        {"currency": "USD", "amount": "300.00"},
    ]
    assert deals["lost_value"] == [{"currency": "EUR", "amount": "200.00"}]
    by_owner = {row["user_id"]: row for row in deals["owners"]}
    assert by_owner[owner]["won_value"] == [{"currency": "EUR", "amount": "1000.50"}]
    assert by_owner[admin]["won_value"] == [{"currency": "USD", "amount": "300.00"}]
    assert [row["won"] for row in deals["owners"]] == [1, 1]


def test_tasks_completed_against_their_due_time(probe: Probe) -> None:
    tasks = probe["tasks"]
    assert (tasks["created"], tasks["created_before"]) == (3, 2)
    assert (tasks["completed"], tasks["completed_before"]) == (3, 1)
    assert (tasks["on_time"], tasks["late"], tasks["no_due"]) == (1, 1, 1)
    assert tasks["overdue_now"] == 1
    assert tasks["completed_by"] == [
        {"user_id": probe["owner"], "count": 2},
        {"user_id": probe["admin"], "count": 1},
    ]


def test_appointments_by_status_and_the_no_show_rate(probe: Probe) -> None:
    appointments = probe["appointments"]
    assert (appointments["held"], appointments["held_before"]) == (3, 1)
    assert appointments["statuses"] == [
        {"status": "cancelled", "count": 1},
        {"status": "completed", "count": 1},
        {"status": "confirmed", "count": 1},
        {"status": "no_show", "count": 1},
    ]
    assert appointments["no_show_rate"] == 50
    assert appointments["hosts"] == [
        {"user_id": probe["owner"], "count": 2},
        {"user_id": probe["admin"], "count": 1},
    ]


def test_the_funnel_follows_the_periods_contacts_to_appointments_and_deals(
    probe: Probe,
) -> None:
    assert probe["funnel"] == {
        "period": PERIOD,
        "capped": False,
        # C0 and C1 were created in the period, C2 before it.
        "created": 2,
        "created_before": 1,
        # C0's appointment counts; C1's was cancelled.
        "booked": 1,
        "booked_before": 0,
        # C0 (won) and C1 (open) have deals; C2's deal is won.
        "with_deal": 2,
        "with_deal_before": 1,
        "won": 1,
        "won_before": 1,
    }
    assert probe["funnel_refused"] == {"detail": {"code": "invalid_period"}}
    assert probe["funnel_csv"] == [
        "total,created,2,1",
        "total,booked,1,0",
        "total,with_deal,2,1",
        "total,won,1,1",
    ]


def test_the_lead_trend_counts_whole_weeks_ending_with_this_one(probe: Probe) -> None:
    trend = probe["trend"]
    assert trend["capped"] is False
    weeks = trend["weeks"]
    assert len(weeks) == 12
    # Ninety days ago falls before the first week.
    assert sum(week["created"] for week in weeks) == 3
    assert (weeks[-1]["created"], weeks[-1]["won"]) == (1, 0)
    # Three weeks back (a time-zone change may move it by a week edge).
    assert sorted((w["created"], w["won"]) for w in weeks[:-1] if w["created"]) == [(2, 1)]
    starts = [week["start"] for week in weeks]
    assert starts == sorted(starts)
    assert len(probe["trend_four"]["weeks"]) == 4
    assert probe["trend_four"]["weeks"][-1] == weeks[-1]


def test_the_lead_trend_is_for_the_workspaces_members_with_bounded_weeks(probe: Probe) -> None:
    assert probe["trend_access"] == {"owner": 404, "outsider": 404, "anonymous": 401}
    assert probe["trend_refused"] == [422, 422, 422]


def test_every_role_reads_its_workspaces_reports_and_nobody_else_does(probe: Probe) -> None:
    every = dict.fromkeys(("contacts", "deals", "tasks", "appointments", "funnel"), 200)
    assert probe["access"]["admin"] == every
    assert probe["access"]["reader"] == every
    for caller in ("other_owner", "outsider"):
        assert set(probe["access"][caller].values()) == {404}, caller
    assert set(probe["access"]["anonymous"].values()) == {401}


def test_a_report_downloads_as_csv_with_its_comparison(probe: Probe) -> None:
    csv = probe["csv"]
    assert csv["status"] == 200
    assert csv["type"] == "text/csv; charset=utf-8"
    assert csv["disposition"].startswith('attachment; filename="report-deals-')
    assert csv["header"] == "section,item,value,previous"
    assert csv["won_line"] == "total,won,2,1"
    assert csv["period_start"] == "period,start,2026-10-01,"
    assert csv["has_email"] is False


def test_the_csv_has_the_reports_permission_and_period_rules(probe: Probe) -> None:
    every = dict.fromkeys(("contacts", "deals", "tasks", "appointments"), 200)
    assert probe["csv_access"]["reader"] == every
    assert set(probe["csv_access"]["other_owner"].values()) == {404}
    assert set(probe["csv_access"]["anonymous"].values()) == {401}
    assert probe["csv_refused"] == {"detail": {"code": "invalid_period"}}


def test_periods_outside_the_rules_are_refused(probe: Probe) -> None:
    refusals = probe["refusals"]
    for name in ("end_before_start", "too_long", "year"):
        assert refusals[name] == {"detail": {"code": "invalid_period"}}, name
    assert (refusals["missing"], refusals["extra"], refusals["not_a_date"]) == (422, 422, 422)
