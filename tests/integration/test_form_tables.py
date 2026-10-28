"""The form, form_submission and consent_record tables (migration 0013;
decision P7-A, slice 7A).

The structural guards (`test_tenant_table_guard.py`) prove forced RLS, the
platform policy, the runtime role's privileges (consent records are
append-only) and purge coverage from the catalogs. These tests prove the
behaviour: what the runtime role can see and write, the composite links with
RLS bypassed, the value rules, what deleting a form or a contact does, the
real purge through the installed operator command, and the migration's
rollback.
"""

from __future__ import annotations

import json
import secrets
import uuid
from pathlib import Path

import psycopg
import pytest
from psycopg import errors
from psycopg.types.json import Jsonb

from crm_app.purge import EXPECTED_PURGE_PARTICIPANTS
from tests.integration.test_crm_tables import (
    MIGRATIONS_DIR,
    _as_workspace,
    _contact,
    _count,
    _insert,
    _visible,
    _workspace,
    env,  # noqa: F401 (fixture)
    runtime,  # noqa: F401 (fixture)
)
from tests.integration.test_purge import OPERATOR_SETUP, _operator, _status
from tests.support import run_module, run_python

pytestmark = pytest.mark.usefixtures("migrated")

FIELDS = [{"key": "first", "type": "text", "label": "First name"}]


def _form(connection: psycopg.Connection, tenant: object, **values: object) -> uuid.UUID:
    row: dict[str, object] = {
        "id": uuid.uuid4(),
        "tenant_id": tenant,
        "name": "Contact us",
        "public_key": secrets.token_urlsafe(16),
        "fields": Jsonb(FIELDS),
        "thank_you": "Thanks!",
        "contact_owner_user_id": uuid.uuid4(),
        **values,
    }
    return _insert(connection, "form", row)


def _submission(
    connection: psycopg.Connection, tenant: object, form: object, **values: object
) -> uuid.UUID:
    row: dict[str, object] = {
        "id": uuid.uuid4(),
        "tenant_id": tenant,
        "form_id": form,
        "answers": Jsonb({"first": "Sam"}),
        "outcome": "created",
        **values,
    }
    return _insert(connection, "form_submission", row)


def _consent(
    connection: psycopg.Connection, tenant: object, contact: object, **values: object
) -> uuid.UUID:
    row: dict[str, object] = {
        "id": uuid.uuid4(),
        "tenant_id": tenant,
        "contact_id": contact,
        "channel": "email",
        "status": "granted",
        "method": "web_form",
        "wording": "Email me.",
        **values,
    }
    return _insert(connection, "consent_record", row)


def test_form_rows_are_visible_only_inside_their_own_workspace(
    env: dict[str, str],  # noqa: F811
    runtime: psycopg.Connection,  # noqa: F811
) -> None:
    a, b = _workspace(env)["tenant"], _workspace(env)["tenant"]
    with _as_workspace(runtime, a):
        form = _form(runtime, a)
        contact = _contact(runtime, a)
        _submission(runtime, a, form, contact_id=contact)
        _consent(runtime, a, contact, form_id=form)
    for table in ("form", "form_submission", "consent_record"):
        assert _visible(runtime, table) == 0
        with _as_workspace(runtime, b):
            assert _visible(runtime, table) == 0
        with _as_workspace(runtime, a):
            assert _visible(runtime, table) == 1


def test_the_runtime_role_cannot_write_into_another_workspace(
    env: dict[str, str],  # noqa: F811
    runtime: psycopg.Connection,  # noqa: F811
) -> None:
    a, b = _workspace(env)["tenant"], _workspace(env)["tenant"]
    with pytest.raises(errors.InsufficientPrivilege), _as_workspace(runtime, a):
        _form(runtime, b)
    with pytest.raises(errors.InsufficientPrivilege):
        _form(runtime, b)  # no workspace set at all


def test_consent_records_cannot_be_changed(
    env: dict[str, str],  # noqa: F811
    runtime: psycopg.Connection,  # noqa: F811
) -> None:
    a = _workspace(env)["tenant"]
    with _as_workspace(runtime, a):
        record = _consent(runtime, a, _contact(runtime, a))
    with pytest.raises(errors.InsufficientPrivilege), _as_workspace(runtime, a):
        runtime.execute(
            "UPDATE crm_app.consent_record SET wording = 'Changed' WHERE id = %s", (record,)
        )


def test_links_stay_inside_their_workspace(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
) -> None:
    a, b = _workspace(env)["tenant"], _workspace(env)["tenant"]
    form_b = _form(owner_connection, b)
    contact_b = _contact(owner_connection, b)
    tag_b = _insert(owner_connection, "tag", {"id": uuid.uuid4(), "tenant_id": b, "name": "Theirs"})
    form_a = _form(owner_connection, a)
    refused = (
        lambda: _form(owner_connection, a, tag_id=tag_b),
        lambda: _submission(owner_connection, a, form_b),
        lambda: _submission(owner_connection, a, form_a, contact_id=contact_b),
        lambda: _consent(owner_connection, a, contact_b),
        lambda: _consent(owner_connection, a, _contact(owner_connection, a), form_id=form_b),
    )
    for insert in refused:
        with pytest.raises(errors.ForeignKeyViolation), owner_connection.transaction():
            insert()


@pytest.mark.parametrize(
    ("table", "values"),
    [
        ("form", {"name": ""}),
        ("form", {"name": " Padded"}),
        ("form", {"name": "x" * 121}),
        ("form", {"status": "live"}),
        ("form", {"public_key": "short"}),
        ("form", {"fields": Jsonb([])}),
        ("form", {"fields": Jsonb({"key": "first"})}),
        ("form", {"thank_you": ""}),
        ("form", {"consent_text": "tab\there"}),
        ("form", {"submission_count": -1}),
        ("form_submission", {"outcome": "updated"}),
        ("form_submission", {"answers": Jsonb(["Sam"])}),
        ("consent_record", {"channel": "sms"}),
        # Migration 0017 (P7-B 3) adds `withdrawn` and `manual`, nothing else.
        ("consent_record", {"status": "revoked"}),
        ("consent_record", {"method": "import"}),
        ("consent_record", {"wording": ""}),
        # Given consent keeps its wording.
        ("consent_record", {"wording": None}),
    ],
    ids=lambda value: value if isinstance(value, str) else next(iter(value)),
)
def test_rows_outside_the_rules_are_refused(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
    table: str,
    values: dict[str, object],
) -> None:
    a = _workspace(env)["tenant"]
    form, contact = _form(owner_connection, a), _contact(owner_connection, a)
    inserts = {
        "form": lambda: _form(owner_connection, a, **values),
        "form_submission": lambda: _submission(owner_connection, a, form, **values),
        "consent_record": lambda: _consent(owner_connection, a, contact, **values),
    }
    with pytest.raises(errors.CheckViolation), owner_connection.transaction():
        inserts[table]()


def test_public_keys_are_unique_across_workspaces(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
) -> None:
    a, b = _workspace(env)["tenant"], _workspace(env)["tenant"]
    key = secrets.token_urlsafe(16)
    _form(owner_connection, a, public_key=key)
    with pytest.raises(errors.UniqueViolation), owner_connection.transaction():
        _form(owner_connection, b, public_key=key)


def test_deleting_keeps_the_evidence_and_clears_links(
    env: dict[str, str],  # noqa: F811
    runtime: psycopg.Connection,  # noqa: F811
) -> None:
    a = _workspace(env)["tenant"]
    with _as_workspace(runtime, a):
        tag = _insert(runtime, "tag", {"id": uuid.uuid4(), "tenant_id": a, "name": "Lead"})
        form = _form(runtime, a, tag_id=tag)
        contact = _contact(runtime, a)
        submission = _submission(runtime, a, form, contact_id=contact)
        consent = _consent(runtime, a, contact, form_id=form, submission_id=submission)
        runtime.execute("DELETE FROM crm_app.tag WHERE id = %s", (tag,))
        tag_after = runtime.execute(
            "SELECT tag_id FROM crm_app.form WHERE id = %s", (form,)
        ).fetchone()
        runtime.execute("DELETE FROM crm_app.form WHERE id = %s", (form,))
        kept = runtime.execute(
            "SELECT tenant_id, form_id, submission_id FROM crm_app.consent_record WHERE id = %s",
            (consent,),
        ).fetchone()
        submissions = _visible(runtime, "form_submission")
        # Deleting the contact deletes its consent records.
        runtime.execute("DELETE FROM crm_app.contact WHERE id = %s", (contact,))
        records = _visible(runtime, "consent_record")
    assert tag_after == (None,)
    assert kept == (uuid.UUID(a), None, None)
    assert submissions == 0
    assert records == 0


def test_deleting_a_contact_keeps_its_submissions(
    env: dict[str, str],  # noqa: F811
    runtime: psycopg.Connection,  # noqa: F811
) -> None:
    a = _workspace(env)["tenant"]
    with _as_workspace(runtime, a):
        contact = _contact(runtime, a)
        submission = _submission(runtime, a, _form(runtime, a), contact_id=contact)
        runtime.execute("DELETE FROM crm_app.contact WHERE id = %s", (contact,))
        row = runtime.execute(
            "SELECT contact_id FROM crm_app.form_submission WHERE id = %s", (submission,)
        ).fetchone()
    assert row == (None,)


def test_the_operator_purge_removes_forms_of_that_workspace_only(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
) -> None:
    target = _workspace(env, deleted=True)
    other = _workspace(env)["tenant"]
    for tenant in (target["tenant"], other):
        form = _form(owner_connection, tenant)
        contact = _contact(owner_connection, tenant)
        submission = _submission(owner_connection, tenant, form, contact_id=contact)
        _consent(owner_connection, tenant, contact, form_id=form, submission_id=submission)

    purged = _operator(env, target["tenant"], target["actor"], *OPERATOR_SETUP)

    assert purged.returncode == 0, purged.stderr
    result = json.loads(purged.stdout)["result"]
    assert result["participant_names"] == list(EXPECTED_PURGE_PARTICIPANTS)
    assert _status(owner_connection, target["tenant"]) == "purged"
    for table in ("form", "form_submission", "consent_record"):
        assert _count(owner_connection, table, target["tenant"]) == 0
        assert _count(owner_connection, table, other) == 1


_DOWNGRADE = (
    "from alembic import command\n"
    "from alembic.config import Config\n"
    "config = Config()\n"
    "config.set_main_option('script_location', {path!r})\n"
    "command.downgrade(config, '0012_tasks')\n"
)
_TABLES = (
    "SELECT relname FROM pg_class WHERE relnamespace = 'crm_app'::regnamespace AND relkind = 'r'"
)


def test_the_migration_rolls_back_and_forward(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
    tmp_path: Path,
) -> None:
    """Downgrades to 0012 (dropping the form tables and their rows), then
    upgrades, leaving the schema as the other tests need it."""
    forms = {"form", "form_submission", "consent_record"}
    down = run_python(_DOWNGRADE.format(path=str(MIGRATIONS_DIR)), env, tmp_path)
    try:
        assert down.returncode == 0, down.stderr
        tables = {name for (name,) in owner_connection.execute(_TABLES).fetchall()}
        assert not forms & tables
        assert {"task", "contact"} <= tables
    finally:
        up = run_module("crm_app.migrate", [], env, tmp_path)
        assert up.returncode == 0, up.stderr
    tables = {name for (name,) in owner_connection.execute(_TABLES).fetchall()}
    assert forms <= tables
