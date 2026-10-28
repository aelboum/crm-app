"""Form routes, members' and public (decision P7-A, slice 7A;
`crm_app.api.forms`).

Drives `form_route_probe` in a fresh interpreter and checks the audit log
directly. Covers: the roles (every role reads; Owner and Admin manage);
tenant isolation on every route; validation and publishing rules; the
public page and its 404s; submissions (idempotency, refusals that never
echo answers, the honeypot, creating and matching contacts, the tag and
consent); reading submissions and consent; unpublishing and deleting; and
audit entries that name the form and never its text.
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
    tmp = tmp_path_factory.mktemp("forms")
    result = run_module("tests.integration.form_route_probe", [], env, tmp, timeout=600)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


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


def test_a_form_is_created_as_a_draft_owned_by_its_creator(probe: Probe) -> None:
    status, etag, form = probe["created"]
    assert (status, etag) == (201, '"1"')
    assert form["name"] == "Contact us"
    assert form["status"] == "draft"
    assert len(form["public_key"]) == 22
    assert form["contact_owner_user_id"] == probe["admin_id"]
    assert form["tag"]["name"] == "Web lead"
    assert form["thank_you"] == "Thanks! We will be in touch soon."
    assert form["fields"][3]["options"] == ["Sales", "Support"]
    assert probe["create_replay"] == [201, "true", True]


def test_forms_outside_the_rules_are_refused_by_code(probe: Probe) -> None:
    assert probe["refusals"] == {
        "blank_name": {"code": "invalid_name"},
        "duplicate_key": {"code": "duplicate_field_key", "field": 1},
        "bad_target": {"code": "field_target", "field": 0},
        "consent_no_email": {"code": "consent_needs_email_field"},
        "foreign_tag": {"code": "tag_not_found"},
        "foreign_owner": {"code": "contact_owner_not_member"},
    }
    assert probe["invalid"] == {"no_fields": 422, "unknown_type": 422, "extra": 422}


def test_publishing_needs_a_version_and_a_publishable_form(probe: Probe) -> None:
    assert probe["publish_guards"]["no_if_match"] == 428
    assert probe["publish_guards"]["stale"] == 409
    assert probe["unpublishable"] == {"code": "first_name_field_required"}
    assert probe["published"] == [200, "published"]


def test_the_public_page_shows_only_a_published_form(probe: Probe) -> None:
    assert probe["draft_public"] == 404
    status, page = probe["public"]
    assert status == 200
    assert set(page) == {"name", "fields", "consent_text", "thank_you"}
    assert page["consent_text"] == "Yes, email me about my enquiry."
    # The page never learns where answers go.
    assert all(
        set(field) == {"key", "type", "label", "required", "options"} for field in page["fields"]
    )
    assert probe["public_not_found"] == {
        "unknown_key": 404,
        "malformed_key": 404,
        "other_workspace": 404,
        "unknown_workspace": 404,
    }
    assert probe["unpublished"] == [404, 404]


def test_submissions_are_checked_without_echoing_answers(probe: Probe) -> None:
    assert probe["submit_guards"] == {"no_key": 400, "not_json": 422, "too_large": 400}
    status, body, echoed = probe["refused"]
    assert status == 422
    assert body["detail"] == {
        "code": "invalid_answers",
        "fields": {"extra": "unknown_field", "first": "required", "email": "invalid"},
    }
    assert echoed is False


def test_a_first_submission_creates_a_tagged_lead_with_consent(probe: Probe) -> None:
    assert probe["first"] == [201, {"thank_you": "Thanks! We will be in touch soon."}]
    assert probe["after_first"] == [[0, 0, 0], [1, 1, 1]]
    [contact] = probe["contact_after_first"]
    assert contact["first_name"] == "Sam"
    assert contact["email"] == "sam@example.test"
    assert (contact["source"], contact["lifecycle_stage"]) == ("form", "lead")
    assert contact["owner_user_id"] == probe["admin_id"]
    assert contact["tags"] == 1
    status, consent = probe["consent"]
    assert status == 200
    [record] = consent["items"]
    assert (record["channel"], record["status"], record["method"]) == (
        "email",
        "granted",
        "web_form",
    )
    assert record["wording"] == "Yes, email me about my enquiry."
    assert record["form_name"] == "Contact us"


def test_a_retried_submission_is_stored_once(probe: Probe) -> None:
    replay, reused, body = probe["replay"]
    assert replay == 201
    assert (reused, body["detail"]) == (422, {"code": "idempotency_key_reused"})
    assert probe["after_first"][1][0] == 1


def test_a_matched_contact_is_never_changed_by_a_visitor(probe: Probe) -> None:
    assert probe["second"] == 201
    assert probe["contact_after_second"] == probe["contact_after_first"]
    # Two submissions, still one consent record and one contact.
    assert probe["after_second"] == [2, 1, 1]
    newest = probe["submissions"][1]["items"][0]
    assert newest["outcome"] == "matched"
    assert newest["answers"]["first"] == "Samuel"
    assert newest["consent"] is False


def test_a_filled_honeypot_looks_accepted_but_stores_nothing(probe: Probe) -> None:
    status, body, counts = probe["honeypot"]
    assert (status, body) == (201, {"thank_you": "Thanks! We will be in touch soon."})
    assert counts == probe["after_second"]


def test_submissions_are_listed_newest_first_with_paging(probe: Probe) -> None:
    status, listed = probe["submissions"]
    assert status == 200
    assert listed["total"] == 2
    assert [item["outcome"] for item in listed["items"]] == ["matched", "created"]
    assert listed["items"][1]["contact"]["name"] == "Sam Jansen"
    first, second, cursor = probe["submission_paging"]
    assert [first, second] == [item["id"] for item in listed["items"]]
    assert cursor is None
    assert probe["bad_cursor"] == 400
    assert probe["form_after"]["submission_count"] == 2
    assert probe["form_after"]["last_submission_at"] is not None


def test_another_workspaces_forms_and_consent_are_unreachable(probe: Probe) -> None:
    assert probe["foreign"] == {
        "get": 404,
        "patch": 404,
        "delete": 404,
        "submissions": 404,
        "listed": False,
        "consent": 404,
        "submissions_of_a": 404,
    }


def test_deleting_a_form_keeps_contacts_and_consent(probe: Probe) -> None:
    assert probe["after_delete"] == [0, 1, 1]
    [record] = probe["consent_after_delete"]["items"]
    assert record["form_id"] is None
    assert record["wording"] == "Yes, email me about my enquiry."


def test_changes_are_audited_by_id_and_field_name(
    probe: Probe, owner_connection: psycopg.Connection
) -> None:
    form_rows = owner_connection.execute(
        "SELECT action, metadata, actor_user_id FROM core.audit_log WHERE tenant_id = %s"
        " AND resource_type = 'crm_app.form' AND resource_id = %s ORDER BY created_at",
        (probe["workspace"], probe["form_id"]),
    ).fetchall()
    assert [action for action, _, _ in form_rows] == [
        "crm_app.form.created",
        "crm_app.form.published",
        "crm_app.form.unpublished",
        "crm_app.form.deleted",
    ]
    contact_rows = owner_connection.execute(
        "SELECT action, metadata, actor_user_id FROM core.audit_log WHERE tenant_id = %s"
        " AND resource_type = 'crm_app.contact' AND resource_id = %s ORDER BY created_at",
        (probe["workspace"], probe["contact_id"]),
    ).fetchall()
    assert [action for action, _, _ in contact_rows] == ["crm_app.contact.created"]
    _, metadata, actor = contact_rows[0]
    assert metadata["form_id"] == probe["form_id"]
    assert str(actor) == probe["admin_id"]
    text = json.dumps([m for _, m, _ in form_rows + contact_rows])
    for secret in ("Contact us", "Sam", "sam@example.test", "email me"):
        assert secret not in text
