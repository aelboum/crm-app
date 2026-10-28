"""Every product route declares the intended SaaS-OS route policy.

Checked with SaaS-OS's own startup check (`saas_os.api.route_policy.
assert_route_policies`) on the fully assembled application, built in a fresh
interpreter with placeholder settings, so no service is contacted. Whether
the policy then admits or refuses a given caller is tested against a real
database in `tests/integration/test_workspace_routes.py`.
"""

from __future__ import annotations

import json
from pathlib import Path

from crm_app.permissions import PERMISSIONS
from crm_app.roles import ROLE_TEMPLATES, Role
from tests.support import PLACEHOLDER_SETTINGS, clean_environment, run_python

PRODUCT_PREFIX = "/v1/workspaces"

MEMBER = "/v1/workspaces/{tenant_id}/members/{membership_id}"
EXPECTED = {
    "GET /v1/workspaces/{tenant_id}": "crm_app.workspace:read",
    "GET /v1/workspaces/{tenant_id}/members": "membership:read",
    "GET /v1/workspaces/{tenant_id}/access": "crm_app.workspace:read",
    # Workspace settings (decision P2-F 1): read for every role, change for
    # Owner and Admin.
    "GET /v1/workspaces/{tenant_id}/settings": "crm_app.workspace:read",
    "PATCH /v1/workspaces/{tenant_id}/settings": "crm_app.workspace:update",
    f"POST {MEMBER}/roles": "membership_role:create",
    f"DELETE {MEMBER}/roles/{{role}}": "membership_role:delete",
    f"POST {MEMBER}/suspend": "membership:suspend",
    f"POST {MEMBER}/reactivate": "membership:reactivate",
    f"POST {MEMBER}/revoke": "membership:revoke",
}
# Membership and role changes (gate G-LOCK): Owner and Admin only.
CHANGING = {key for key in EXPECTED if not key.startswith("GET ")}

# Contact and company records (slice 3A, decision P3-A): reads for every role,
# create and update (including archive and restore) for Owner, Admin and
# Member, permanent delete for Owner and Admin (Q6).
RECORDS: dict[str, str] = {}
for _path, _resource in (("contacts", "crm_app.contact"), ("companies", "crm_app.company")):
    _collection = f"/v1/workspaces/{{tenant_id}}/{_path}"
    _item = f"{_collection}/{{record_id}}"
    RECORDS |= {
        f"GET {_collection}": f"{_resource}:read",
        f"POST {_collection}": f"{_resource}:create",
        f"GET {_item}": f"{_resource}:read",
        f"PATCH {_item}": f"{_resource}:update",
        f"POST {_item}/archive": f"{_resource}:update",
        f"POST {_item}/restore": f"{_resource}:update",
        # Replacing the record's tags (decision P3-C 5): a record update.
        f"PUT {_item}/tags": f"{_resource}:update",
        f"DELETE {_item}": f"{_resource}:delete",
        # The record's history and notes (slice 3B, decision P3-B): reads for
        # every role; adding notes for Owner, Admin and Member.
        f"GET {_item}/activity": "crm_app.activity:read",
        f"GET {_item}/notes": "crm_app.activity:read",
        f"POST {_item}/notes": "crm_app.activity:create",
    }
# Editing and deleting a note: declared with `activity:create`; the service
# allows the author or a holder of `activity:update`/`activity:delete` (D3).
_NOTE = "/v1/workspaces/{tenant_id}/notes/{note_id}"
RECORDS |= {
    f"PATCH {_NOTE}": "crm_app.activity:create",
    f"DELETE {_NOTE}": "crm_app.activity:create",
}
EDITORS = {Role.OWNER, Role.ADMIN, Role.MEMBER}

# Contacts and companies exports (slices 3E1, 3E2): the catalogue's existing
# `crm_data:export`, Owner and Admin only (Q6); no new permission.
EXPORTS = {
    "GET /v1/workspaces/{tenant_id}/contacts/export.csv": "crm_app.crm_data:export",
    "GET /v1/workspaces/{tenant_id}/companies/export.csv": "crm_app.crm_data:export",
}

# Tags (decision P3-C 4): every role reads the vocabulary; changing it is
# workspace configuration, for Owner and Admin.
_TAGS = "/v1/workspaces/{tenant_id}/tags"
CONFIGURATION = {
    f"GET {_TAGS}": "crm_app.contact:read",
    f"POST {_TAGS}": "crm_app.workspace:update",
    f"PATCH {_TAGS}/{{tag_id}}": "crm_app.workspace:update",
    f"DELETE {_TAGS}/{{tag_id}}": "crm_app.workspace:update",
}

# Custom field definitions (decision P3-D 4): every role reads them;
# changing them is workspace configuration, for Owner and Admin.
_FIELDS = "/v1/workspaces/{tenant_id}/custom-fields"
CONFIGURATION |= {
    f"GET {_FIELDS}": "crm_app.contact:read",
    f"POST {_FIELDS}": "crm_app.workspace:update",
    f"PATCH {_FIELDS}/{{field_id}}": "crm_app.workspace:update",
    f"POST {_FIELDS}/{{field_id}}/archive": "crm_app.workspace:update",
    f"POST {_FIELDS}/{{field_id}}/restore": "crm_app.workspace:update",
}

# The sales pipeline (decision P4 4A.4): every role reads it; changing it
# is for Owner and Admin, through the catalogue's `pipeline:manage`.
_PIPELINE = "/v1/workspaces/{tenant_id}/pipelines/{pipeline_id}"
CONFIGURATION |= {
    "GET /v1/workspaces/{tenant_id}/pipelines": "crm_app.pipeline:read",
    f"PATCH {_PIPELINE}": "crm_app.pipeline:manage",
    f"POST {_PIPELINE}/stages": "crm_app.pipeline:manage",
    f"PATCH {_PIPELINE}/stages/{{stage_id}}": "crm_app.pipeline:manage",
    f"DELETE {_PIPELINE}/stages/{{stage_id}}": "crm_app.pipeline:manage",
    f"PUT {_PIPELINE}/stage-order": "crm_app.pipeline:manage",
}

# Deals (decision P4-B 6, Q6): every role reads; Owner, Admin and Member
# create and update; Owner and Admin delete.
_DEALS = "/v1/workspaces/{tenant_id}/opportunities"
RECORDS |= {
    f"GET {_DEALS}": "crm_app.opportunity:read",
    f"GET {_DEALS}/summary": "crm_app.opportunity:read",
    f"POST {_DEALS}": "crm_app.opportunity:create",
    f"GET {_DEALS}/{{deal_id}}": "crm_app.opportunity:read",
    f"PATCH {_DEALS}/{{deal_id}}": "crm_app.opportunity:update",
    f"POST {_DEALS}/{{deal_id}}/outcome": "crm_app.opportunity:update",
    f"DELETE {_DEALS}/{{deal_id}}": "crm_app.opportunity:delete",
    f"GET {_DEALS}/{{deal_id}}/history": "crm_app.opportunity:read",
}

# Tasks (decision P4-C 3, Q6): every role reads; Owner, Admin and Member
# create, update and delete.
_TASKS = "/v1/workspaces/{tenant_id}/tasks"
RECORDS |= {
    f"GET {_TASKS}": "crm_app.task:read",
    f"GET {_TASKS}/counts": "crm_app.task:read",
    f"POST {_TASKS}": "crm_app.task:create",
    f"GET {_TASKS}/{{task_id}}": "crm_app.task:read",
    f"PATCH {_TASKS}/{{task_id}}": "crm_app.task:update",
    f"DELETE {_TASKS}/{{task_id}}": "crm_app.task:delete",
}

# Appointments (decision P5-A 6): every role reads; Owner, Admin and Member
# book, change and cancel; Owner and Admin delete.
_APPOINTMENTS = "/v1/workspaces/{tenant_id}/appointments"
RECORDS |= {
    f"GET {_APPOINTMENTS}": "crm_app.appointment:read",
    f"GET {_APPOINTMENTS}/upcoming": "crm_app.appointment:read",
    f"GET {_APPOINTMENTS}/conflicts": "crm_app.appointment:read",
    f"GET {_APPOINTMENTS}/availability": "crm_app.appointment:read",
    f"POST {_APPOINTMENTS}": "crm_app.appointment:create",
    f"GET {_APPOINTMENTS}/{{appointment_id}}": "crm_app.appointment:read",
    f"PATCH {_APPOINTMENTS}/{{appointment_id}}": "crm_app.appointment:update",
    f"DELETE {_APPOINTMENTS}/{{appointment_id}}": "crm_app.appointment:delete",
}

# Forms (decision P7-A 4): every role reads forms and their submissions;
# Owner and Admin manage them, through the new `form:manage`.
_FORMS = "/v1/workspaces/{tenant_id}/forms"
CONFIGURATION |= {
    f"GET {_FORMS}": "crm_app.form:read",
    f"POST {_FORMS}": "crm_app.form:manage",
    f"GET {_FORMS}/{{form_id}}": "crm_app.form:read",
    f"PATCH {_FORMS}/{{form_id}}": "crm_app.form:manage",
    f"DELETE {_FORMS}/{{form_id}}": "crm_app.form:manage",
    f"GET {_FORMS}/{{form_id}}/submissions": "crm_app.form:read",
}
# Booking pages (decision P5-C 8): every role reads them; Owner and Admin
# manage them, through the new `booking_page:manage`.
_BOOKING_PAGES = "/v1/workspaces/{tenant_id}/booking-pages"
CONFIGURATION |= {
    f"GET {_BOOKING_PAGES}": "crm_app.booking_page:read",
    f"POST {_BOOKING_PAGES}": "crm_app.booking_page:manage",
    f"GET {_BOOKING_PAGES}/{{page_id}}": "crm_app.booking_page:read",
    f"PATCH {_BOOKING_PAGES}/{{page_id}}": "crm_app.booking_page:manage",
    f"DELETE {_BOOKING_PAGES}/{{page_id}}": "crm_app.booking_page:manage",
}
# A contact's consent records (P7-A 10): a contact read.
RECORDS["GET /v1/workspaces/{tenant_id}/contacts/{record_id}/consent"] = "crm_app.contact:read"

# CSV import (decision P3-F 1): Owner and Admin only, through the
# catalogue's `crm_data:import`.
_IMPORTS = "/v1/workspaces/{tenant_id}/imports"
EXPORTS |= {
    f"POST {_IMPORTS}": "crm_app.crm_data:import",
    f"GET {_IMPORTS}": "crm_app.crm_data:import",
    f"GET {_IMPORTS}/{{import_id}}": "crm_app.crm_data:import",
    f"GET {_IMPORTS}/{{import_id}}/errors.csv": "crm_app.crm_data:import",
    f"POST {_IMPORTS}/{{import_id}}/commit": "crm_app.crm_data:import",
    f"POST {_IMPORTS}/{{import_id}}/cancel": "crm_app.crm_data:import",
    f"POST {_IMPORTS}/{{import_id}}/resume": "crm_app.crm_data:import",
}

# Invitations (decisions Q4, Q5, P2-F): reading, creating and revoking are
# for Owner and Admin only; inviting an Owner is checked again in the
# handler (`crm_app.owner:manage`).
_INVITATIONS = "/v1/workspaces/{tenant_id}/invitations"
INVITATIONS = {
    f"GET {_INVITATIONS}": "invitation:read",
    f"POST {_INVITATIONS}": "invitation:create",
    f"POST {_INVITATIONS}/{{invitation_id}}/revoke": "invitation:revoke",
}

_PROBE = (
    "import json\n"
    "from crm_app.app import create_app\n"
    "from saas_os.api.route_policy import assert_route_policies\n"
    "policies = assert_route_policies(create_app(), production=False)\n"
    "print('POLICIES ' + json.dumps({k: [str(p.kind), p.detail, p.accepts_api_key]"
    " for k, p in policies.items()}))\n"
)


# The frontend's static files (crm_app.api.spa): public, read-only, no data.
FRONTEND = {"GET,HEAD /", "GET,HEAD /app", "GET,HEAD /app/{requested:path}"}


def _policies(tmp_path: Path) -> dict[str, tuple[str, str, bool]]:
    result = run_python(_PROBE, clean_environment(PLACEHOLDER_SETTINGS), tmp_path)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("POLICIES "))
    policies = json.loads(line.removeprefix("POLICIES "))
    return {k: (v[0], v[1], v[2]) for k, v in policies.items()}


def _product_policies(tmp_path: Path) -> dict[str, tuple[str, str, bool]]:
    return {k: v for k, v in _policies(tmp_path).items() if PRODUCT_PREFIX in k}


# The workspace directory (decision P2-F 2): the one product route that
# needs only a signed-in person, because it names no workspace. It lists the
# caller's own active memberships and grants nothing.
DIRECTORY = "GET /v1/workspaces"


def test_the_directory_needs_only_a_signed_in_person(tmp_path: Path) -> None:
    kind, _, accepts_api_key = _product_policies(tmp_path)[DIRECTORY]
    assert kind == "authenticated"
    assert not accepts_api_key


def test_product_routes_require_exactly_the_intended_permission(tmp_path: Path) -> None:
    policies = {k: v for k, v in _product_policies(tmp_path).items() if k != DIRECTORY}
    assert {key: detail for key, (_, detail, _) in policies.items()} == (
        EXPECTED | RECORDS | INVITATIONS | EXPORTS | CONFIGURATION
    )
    assert {kind for kind, _, _ in policies.values()} == {"permission"}
    assert not any(accepts_api_key for _, _, accepts_api_key in policies.values())
    changing = {key for key in policies if not key.startswith("GET ")}
    assert changing == CHANGING | {
        key for key in RECORDS | INVITATIONS | CONFIGURATION | EXPORTS if not key.startswith("GET ")
    }


def test_route_permissions_are_registered() -> None:
    for detail in (EXPECTED | RECORDS | INVITATIONS | EXPORTS | CONFIGURATION).values():
        resource, _, action = detail.rpartition(":")
        assert (resource, action) in PERMISSIONS


def test_configuration_is_read_by_every_role_and_changed_by_owners_and_admins() -> None:
    for key, detail in CONFIGURATION.items():
        resource, _, action = detail.rpartition(":")
        holders = {
            role for role, template in ROLE_TEMPLATES.items() if (resource, action) in template
        }
        expected = set(Role) if key.startswith("GET ") else {Role.OWNER, Role.ADMIN}
        assert holders == expected, key


def test_contact_export_is_for_owners_and_admins_only() -> None:
    for key, detail in EXPORTS.items():
        resource, _, action = detail.rpartition(":")
        holders = {
            role for role, template in ROLE_TEMPLATES.items() if (resource, action) in template
        }
        assert holders == {Role.OWNER, Role.ADMIN}, key


def test_reading_routes_are_open_to_every_role_and_changes_to_owner_and_admin() -> None:
    for key, detail in EXPECTED.items():
        resource, _, action = detail.rpartition(":")
        holders = {
            role for role, template in ROLE_TEMPLATES.items() if (resource, action) in template
        }
        expected = set(Role) if key not in CHANGING else {Role.OWNER, Role.ADMIN}
        assert holders == expected, key


def test_frontend_routes_are_public_and_read_only(tmp_path: Path) -> None:
    policies = _policies(tmp_path)
    frontend = {key: kind for key, (kind, _, _) in policies.items() if key in FRONTEND}
    assert frontend == dict.fromkeys(FRONTEND, "public")
    assert not any(
        key.split(" ", 1)[1].startswith("/app") for key in policies if key not in FRONTEND
    )


def test_record_routes_follow_the_role_matrix() -> None:
    for key, detail in RECORDS.items():
        resource, _, action = detail.rpartition(":")
        holders = {
            role for role, template in ROLE_TEMPLATES.items() if (resource, action) in template
        }
        expected = {
            "read": set(Role),
            "create": EDITORS,
            "update": EDITORS,
            # Q6: Members may delete tasks, not other records.
            "delete": EDITORS if resource == "crm_app.task" else {Role.OWNER, Role.ADMIN},
        }[action]
        assert holders == expected, key


def test_invitation_routes_are_for_owners_and_admins() -> None:
    for key, detail in INVITATIONS.items():
        resource, _, action = detail.rpartition(":")
        holders = {
            role for role, template in ROLE_TEMPLATES.items() if (resource, action) in template
        }
        assert holders == {Role.OWNER, Role.ADMIN}, key


# Self-service signup (decision S-1): the person is the signed-in session's
# user, never a workspace member yet, so the routes need only a session and
# name no workspace. They answer 404 while SIGNUP_ENABLED is off
# (tests/integration/test_signups.py). Only the status flag is public
# (tests/unit/test_signup_status.py).
SIGNUPS = {"POST /v1/signups", "GET /v1/signups/current"}
SIGNUP_STATUS = "GET /v1/signups/status"


def test_signup_routes_need_only_a_signed_in_person(tmp_path: Path) -> None:
    policies = {k: v for k, v in _policies(tmp_path).items() if "/v1/signups" in k}
    assert policies.pop(SIGNUP_STATUS)[0] == "public"
    assert set(policies) == SIGNUPS
    assert {kind for kind, _, _ in policies.values()} == {"authenticated"}
    assert not any(accepts_api_key for _, _, accepts_api_key in policies.values())


# A published form's page and submission (decision P7-A 5) and a published
# booking page, its times, a booking and the visitor's own booking (decision
# P5-C 5): public, with their own limits; nothing else under /v1/public.
PUBLIC_FORMS = {
    "GET /v1/public/forms/{workspace_id}/{key}",
    "POST /v1/public/forms/{workspace_id}/{key}",
    "GET /v1/public/booking-pages/{workspace_id}/{key}",
    "GET /v1/public/booking-pages/{workspace_id}/{key}/times",
    "POST /v1/public/booking-pages/{workspace_id}/{key}",
    "POST /v1/public/bookings/{workspace_id}/view",
    "POST /v1/public/bookings/{workspace_id}/cancel",
}


def test_public_form_routes_are_the_only_public_api_routes(tmp_path: Path) -> None:
    policies = _policies(tmp_path)
    public = {
        key
        for key, (kind, _, _) in policies.items()
        if kind == "public" and key not in FRONTEND and key != SIGNUP_STATUS
    }
    platform = {key for key in public if "/v1/public/" not in key}
    assert public - platform == PUBLIC_FORMS
    assert not any("/v1/workspaces" in key for key in platform)
