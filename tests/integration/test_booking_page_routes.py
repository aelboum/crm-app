"""Booking page routes, members' and public (decision P5-C, slice 5C;
`crm_app.api.booking_pages`).

Drives `booking_page_route_probe` in a fresh interpreter and checks the
audit log directly. Covers: the roles (every role reads; Owner and Admin
manage); tenant isolation on every route; validation and publishing rules
(business hours required); the public page, its free times and its 404s;
booking (idempotency, refusals that never echo details, the time checked
again, the honeypot, creating and matching contacts, the per-contact
limit); what members see; the visitor's link (view, cancel, the token's
404s, an appointment that has started); unpublishing and deleting; and
audit entries that name the page and act as the host.
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
    env = {
        **integration_env,
        "PYTHONPATH": str(REPO_ROOT),
        "RATE_LIMIT_REQUESTS_PER_WINDOW": "1000",
    }
    tmp = tmp_path_factory.mktemp("booking-pages")
    result = run_module("tests.integration.booking_page_route_probe", [], env, tmp, timeout=600)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def _hours(times: list[str]) -> list[str]:
    return [time[11:16] for time in times]


def test_every_role_reads_and_owners_and_admins_manage(probe: Probe) -> None:
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
        "member": 403,
        "reader": 403,
        "other_owner": 404,
    }
    assert probe["publish_guards"]["member"] == 403
    assert probe["delete"] == {"member": 403, "admin": 204, "again": 404}


def test_a_page_is_created_as_a_draft_hosted_by_its_creator(probe: Probe) -> None:
    status, etag, page = probe["created"]
    assert (status, etag) == (201, '"1"')
    assert page["name"] == "Intro call"
    assert page["description"] == "Thirty minutes\nto get to know you."
    assert page["status"] == "draft"
    assert len(page["public_key"]) == 22
    assert page["host_user_id"] == probe["admin_id"]
    assert (page["length_minutes"], page["step_minutes"], page["kind"]) == (30, 30, "video")
    assert (page["notice_minutes"], page["horizon_days"]) == (0, 30)
    assert probe["create_replay"] == [201, "true", True]


def test_pages_outside_the_rules_are_refused_by_code(probe: Probe) -> None:
    assert probe["refusals"] == {
        "blank_name": {"code": "invalid_name"},
        "length": {"code": "invalid_length_minutes"},
        "step": {"code": "invalid_step_minutes"},
        "notice": {"code": "invalid_notice_minutes"},
        "horizon": {"code": "invalid_horizon_days"},
        "description": {"code": "invalid_description"},
        "foreign_host": {"code": "host_not_member"},
    }
    assert probe["invalid"] == {"unknown_kind": 422, "extra": 422}


def test_publishing_needs_the_version_and_the_business_hours(probe: Probe) -> None:
    assert probe["draft_public"] == 404
    guards = probe["publish_guards"]
    assert (guards["no_if_match"], guards["stale"]) == (428, 409)
    assert guards["no_hours"] == {"code": "business_hours_required"}
    assert probe["published"] == [200, "published"]


def test_the_public_page_shows_no_host_location_or_workspace(probe: Probe) -> None:
    assert probe["public"] == [
        200,
        {
            "name": "Intro call",
            "description": "Thirty minutes\nto get to know you.",
            "length_minutes": 30,
            "kind": "video",
            "time_zone": "UTC",
            "horizon_days": 30,
        },
    ]
    assert set(probe["public_not_found"].values()) == {404}


def test_free_times_follow_the_hours_and_the_hosts_appointments(probe: Probe) -> None:
    every_half_hour = [f"{h:02d}:{m:02d}" for h in range(9, 17) for m in (0, 30)]
    assert _hours(probe["times_first"]) == every_half_hour
    # The host's own appointment, 10:00-10:45, hides 10:00 and 10:30.
    busy = [t for t in every_half_hour if t not in {"10:00", "10:30"}]
    assert _hours(probe["times_busy"]) == busy
    assert probe["times_invalid"] == {"too_long": 422, "backwards": 422, "naive": 422}
    # Booked at 09:00, then freed by the visitor's cancellation; 11:00 and
    # 11:30 booked by the same visitor.
    assert "09:00" not in _hours(probe["times_after_booking"])
    after_cancel = _hours(probe["times_after_cancel"])
    assert after_cancel == [t for t in busy if t not in {"11:00", "11:30"}]


def test_a_booking_creates_a_lead_and_a_confirmed_appointment(probe: Probe) -> None:
    status, booking, token_length = probe["first"]
    assert (status, token_length) == (201, 43)
    assert booking == {
        "page_name": "Intro call",
        "starts_at": booking["starts_at"],
        "ends_at": booking["ends_at"],
        "kind": "video",
        "location": "https://meet.example.test/intro",
        "cancelled": False,
        "cancelled_by_visitor": False,
        "can_cancel": True,
    }
    assert booking["starts_at"].endswith("T09:00:00Z")
    assert booking["ends_at"].endswith("T09:30:00Z")
    before, after = probe["after_first"]
    assert [x - y for x, y in zip(after, before, strict=True)] == [1, 1, 1]
    [contact] = probe["contact_after_first"]
    assert contact["first_name"] == "Ada"
    assert contact["email"] == "ada@example.test"
    assert (contact["source"], contact["lifecycle_stage"]) == ("booking", "lead")
    assert contact["owner_user_id"] == probe["admin_id"]


def test_a_replay_answers_the_same_booking_without_the_token(probe: Probe) -> None:
    assert probe["replay"] == [201, None, True, 422]


def test_booking_needs_a_key_a_bounded_body_and_valid_details(probe: Probe) -> None:
    assert probe["book_guards"] == {"no_key": 400, "not_json": 422, "too_large": 400, "naive": 422}
    status, body, echoed = probe["refused"]
    assert status == 422
    assert body["detail"] == {
        "code": "invalid_visitor",
        "fields": {"first_name": "invalid", "email": "invalid"},
    }
    assert echoed is False


def test_only_free_times_can_be_booked(probe: Probe) -> None:
    cases = ("same_time", "off_grid", "after_hours", "busy_host", "beyond_horizon")
    assert probe["taken"] == {case: {"code": "time_unavailable"} for case in cases}


def test_a_matched_contact_is_never_changed_and_is_limited(probe: Probe) -> None:
    assert probe["second"] == 201
    assert probe["contact_after_second"] == probe["contact_after_first"]
    assert probe["limit"] == [201, 409, {"code": "booking_limit"}]


def test_the_honeypot_looks_like_a_taken_time_and_stores_nothing(probe: Probe) -> None:
    status, detail, counts = probe["honeypot"]
    assert (status, detail) == (409, {"code": "time_unavailable"})
    assert counts == [3, 4, 1]


def test_members_see_how_an_appointment_was_booked(probe: Probe) -> None:
    online = [item for item in probe["members_see"] if item["booking"] is not None]
    assert len(online) == 3
    first = online[0]
    assert first["title"] == "Intro call — Ada Lovelace"
    assert first["status"] == "confirmed"
    assert first["host_user_id"] == probe["admin_id"]
    assert first["note"] == "About the engine."
    assert first["booking"]["page_name"] == "Intro call"
    assert first["booking"]["cancelled_by_visitor"] is False
    assert first["contact"]["id"] == probe["contact_id"]
    # The matched visitor's own name is the title, never the contact's.
    assert {item["title"] for item in online} == {
        "Intro call — Ada Lovelace",
        "Intro call — Augusta Lovelace",
    }
    staff = [item for item in probe["members_see"] if item["booking"] is None]
    assert [item["title"] for item in staff] == ["Team sync"]


def test_the_visitor_views_and_cancels_by_their_token(probe: Probe) -> None:
    assert probe["view"]["cancelled"] is False
    assert probe["view_not_found"] == {
        "unknown": 404,
        "malformed": 404,
        "other_workspace": 404,
        "too_long": 422,
    }
    status, cancelled = probe["cancelled"]
    assert status == 200
    assert cancelled["cancelled"] is True
    assert cancelled["cancelled_by_visitor"] is True
    assert cancelled["can_cancel"] is False
    assert probe["cancelled_again"] == cancelled
    assert probe["members_after_cancel"] == [
        {
            "status": "cancelled",
            "cancelled_by_user_id": None,
            "updated_by_user_id": None,
            "booking": {
                "page_id": probe["page_id"],
                "page_name": "Intro call",
                "cancelled_by_visitor": True,
            },
        }
    ]
    assert probe["started"] == [False, 409]


def test_another_workspace_cannot_reach_the_pages(probe: Probe) -> None:
    assert probe["foreign"] == {
        "get": 404,
        "patch": 404,
        "delete": 404,
        "listed": False,
        "a_from_b": 404,
    }


def test_unpublished_and_deleted_pages_keep_their_appointments(probe: Probe) -> None:
    assert probe["page_after"]["booking_count"] == 3
    assert probe["page_after"]["last_booked_at"] is not None
    assert probe["unpublished"] == [404, 404, 404]
    # Four bookings (three online, one seeded), five appointments, one contact.
    assert probe["after_delete"] == [4, 5, 1]
    view = probe["view_after_delete"]
    assert view["page_name"] is None
    assert view["cancelled"] is True


def test_changes_are_audited_by_id_and_act_as_the_host(
    probe: Probe, owner_connection: psycopg.Connection
) -> None:
    page_rows = owner_connection.execute(
        "SELECT action, metadata FROM core.audit_log WHERE tenant_id = %s"
        " AND resource_type = 'crm_app.booking_page' AND resource_id = %s ORDER BY created_at",
        (probe["workspace"], probe["page_id"]),
    ).fetchall()
    assert [action for action, _ in page_rows] == [
        "crm_app.booking_page.created",
        "crm_app.booking_page.published",
        "crm_app.booking_page.unpublished",
        "crm_app.booking_page.deleted",
    ]
    assert "Intro call" not in json.dumps([meta for _, meta in page_rows])
    appointment_rows = owner_connection.execute(
        "SELECT action, metadata, actor_user_id FROM core.audit_log WHERE tenant_id = %s"
        " AND resource_type = 'crm_app.appointment' AND resource_id = %s ORDER BY created_at",
        (probe["workspace"], probe["cancelled_appointment_id"]),
    ).fetchall()
    assert [action for action, _, _ in appointment_rows] == [
        "crm_app.appointment.created",
        "crm_app.appointment.cancelled",
    ]
    created, cancelled = appointment_rows
    assert created[1]["booking_page_id"] == probe["page_id"]
    assert created[1]["by"] == "visitor"
    assert str(created[2]) == probe["admin_id"]
    assert cancelled[1] == {
        "previous_status": "confirmed",
        "by": "visitor",
        "booking_page_id": probe["page_id"],
    }
    assert str(cancelled[2]) == probe["admin_id"]
    text = json.dumps([meta for _, meta, _ in appointment_rows])
    assert "Lovelace" not in text
    assert "engine" not in text
    contact_rows = owner_connection.execute(
        "SELECT action, metadata FROM core.audit_log WHERE tenant_id = %s"
        " AND resource_type = 'crm_app.contact' AND resource_id = %s ORDER BY created_at",
        (probe["workspace"], probe["contact_id"]),
    ).fetchall()
    assert [action for action, _ in contact_rows] == ["crm_app.contact.created"]
    assert contact_rows[0][1]["booking_page_id"] == probe["page_id"]
