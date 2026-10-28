"""Appointment routes (decision P5-A, slice 5A; `crm_app.api.appointments`).

Drives `appointment_route_probe` in a fresh interpreter and checks the audit
log directly. Covers: the roles (P5-A 6: Owner and Admin delete); tenant
isolation on every route, link and conflict check; validation (titles,
aware times, lengths, kinds, statuses); conflicts on booking and moving,
back-to-back bookings, booking over a conflict on purpose and the live
check; idempotent creation; versions; status changes and cancelling (final,
and freeing the slot); the range, its filters and limits; upcoming
appointments; and audit entries without titles, locations or notes.
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
    tmp = tmp_path_factory.mktemp("appointments")
    result = run_module("tests.integration.appointment_route_probe", [], env, tmp, timeout=600)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def test_every_role_reads_members_and_up_book_and_admins_delete(probe: Probe) -> None:
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
    assert probe["delete"] == {"reader": 403, "member": 403, "admin": 204, "again": 404}


def test_an_appointment_is_booked_with_normalised_text(probe: Probe) -> None:
    status, etag, appointment = probe["created"]
    assert (status, etag) == (201, '"1"')
    assert appointment["title"] == "Intro call with Sam"
    assert appointment["location"] == "https://meet.example.test/sam"
    assert appointment["note"] == "Bring the quote\nand the plan"
    assert (appointment["kind"], appointment["status"]) == ("video", "pending")
    assert appointment["contact"]["name"] == "Sam Jansen"
    assert appointment["starts_at"].endswith("Z")
    assert (appointment["cancelled_at"], appointment["version"]) == (None, 1)


def test_contacts_and_hosts_must_be_the_workspaces_own(probe: Probe) -> None:
    assert {k: v["code"] for k, v in probe["references"].items()} == {
        "foreign_contact": "contact_not_found",
        "archived_contact": "contact_not_found",
        "unknown_contact": "contact_not_found",
        "foreign_host": "host_not_member",
    }


def test_invalid_bodies_times_and_lengths_are_refused(probe: Probe) -> None:
    assert set(probe["invalid"].values()) == {422}
    assert probe["invalid_times_code"] == {"code": "invalid_times"}
    assert set(probe["update_invalid"].values()) == {422}


def test_a_hosts_overlapping_booking_is_refused_with_the_conflicts(probe: Probe) -> None:
    status, detail = probe["conflict"]
    assert status == 409
    assert detail["code"] == "appointment_conflict"
    assert [c["title"] for c in detail["conflicts"]] == ["Intro call with Sam"]
    assert set(detail["conflicts"][0]) == {"id", "title", "starts_at", "ends_at"}
    # Back to back is no conflict; another host is free; a conflict may be
    # booked on purpose.
    assert (probe["back_to_back"], probe["other_host"], probe["forced"]) == (201, 201, 201)


def test_the_live_check_lists_the_hosts_conflicts(probe: Probe) -> None:
    assert probe["check"] == {
        "busy": ["Intro call with Sam", "Forced"],
        "excluded": ["Intro call with Sam"],
        "free": [],
        "bad_times": 422,
    }


def test_a_repeated_booking_with_the_same_key_books_once(probe: Probe) -> None:
    assert probe["idempotent"] == [201, "true", True]


def test_changes_need_the_current_version(probe: Probe) -> None:
    assert probe["no_version"] == 428
    assert probe["stale"] == [409, {"code": "stale_version", "current_version": 1}]


def test_moving_into_a_conflict_is_refused(probe: Probe) -> None:
    assert probe["reschedule_conflict"] == [409, ["Next"]]


def test_reschedule_status_and_cancel(probe: Probe) -> None:
    lifecycle = probe["lifecycle"]
    starts, ends, version = lifecycle["moved"]
    assert (starts[11:16], ends[11:16], version) == ("10:00", "10:45", 2)
    assert lifecycle["confirmed"] == ["confirmed", 3]
    assert lifecycle["unchanged_version"] == 3  # nothing changed
    assert lifecycle["cleared"] == [None, None, None, 4]
    assert lifecycle["cancelled"] == [200, "cancelled", True, True]
    # Cancelling is final, and the slot is free again.
    assert lifecycle["after_cancel"] == [409, {"code": "appointment_cancelled"}]
    assert lifecycle["rebooked"] == 201


def test_the_range_its_filters_and_limits(probe: Probe) -> None:
    found = probe["range"]
    assert found["day"] == [
        "Sam follow-up",
        "Owner's own",
        "Next",
        "Rebooked",
        "By owner",
        "By admin",
        "By member",
        "Once",
    ]
    assert found["with_cancelled"] is True
    assert found["member_hosted"] == ["Next", "Rebooked"]
    assert found["mine"] == ["Sam follow-up", "Owner's own"]
    assert found["contact"] == ["Sam follow-up"]
    assert (found["too_wide"], found["backwards"], found["naive"], found["missing"]) == (
        422,
        422,
        422,
        422,
    )


def test_upcoming_leaves_out_what_has_ended(probe: Probe) -> None:
    assert probe["upcoming"] == probe["upcoming_expected"]
    assert probe["past_id"] not in probe["upcoming"]


def test_another_workspaces_appointment_is_unreachable(probe: Probe) -> None:
    foreign = probe["foreign"]
    assert foreign["get"]["detail"] == {"code": "appointment_not_found"}
    assert (foreign["patch"], foreign["delete"]) == (404, 404)
    assert foreign["listed"] is False
    assert foreign["conflict_check"] == []


def test_changes_are_audited_without_titles_locations_or_notes(
    probe: Probe, owner_connection: psycopg.Connection
) -> None:
    rows = owner_connection.execute(
        "SELECT action, metadata FROM core.audit_log WHERE tenant_id = %s"
        " AND resource_type = 'crm_app.appointment' AND resource_id = %s ORDER BY created_at",
        (probe["workspace"], probe["appointment_id"]),
    ).fetchall()
    assert [action for action, _ in rows] == [
        "crm_app.appointment.created",
        "crm_app.appointment.updated",
        "crm_app.appointment.status_changed",
        "crm_app.appointment.updated",
        "crm_app.appointment.cancelled",
        "crm_app.appointment.deleted",
    ]
    assert rows[0][1]["status"] == "pending"
    assert rows[1][1] == {"fields": ["ends_at", "starts_at"]}
    assert rows[2][1] == {"previous": "pending", "status": "confirmed"}
    assert rows[3][1] == {"fields": ["contact_id", "location", "note"]}
    assert rows[4][1] == {"previous_status": "confirmed"}
    text = json.dumps([metadata for _, metadata in rows])
    for secret in ("Intro call", "meet.example", "Bring the quote"):
        assert secret not in text


def test_without_business_hours_nothing_is_closed(probe: Probe) -> None:
    availability, outside = probe["hours_unset"]
    assert availability == {"hours_set": False, "time_zone": "Europe/Amsterdam", "open": []}
    assert outside is False


def test_business_hours_are_open_intervals_in_the_workspace_zone(probe: Probe) -> None:
    hours = probe["hours"]
    day = datetime.fromisoformat(probe["hours_day"])
    assert hours["reader"]["hours_set"] is True
    assert hours["reader"]["time_zone"] == "Asia/Tokyo"
    assert [
        (datetime.fromisoformat(i["starts_at"]), datetime.fromisoformat(i["ends_at"]))
        for i in hours["reader"]["open"]
    ] == [(day, day + timedelta(hours=8))]
    assert (hours["inside"], hours["straddling"], hours["after"]) == (False, True, True)


def test_booking_outside_business_hours_is_a_warning_not_a_refusal(probe: Probe) -> None:
    assert probe["hours"]["booked_outside"] == [201, None]


def test_availability_needs_a_bounded_aware_range_and_a_member(probe: Probe) -> None:
    hours = probe["hours"]
    assert (hours["too_long"], hours["naive"]) == (422, 422)
    assert (hours["anonymous"], hours["other_owner"]) == (401, 404)
    assert hours["theirs"] is False
