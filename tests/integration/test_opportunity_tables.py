"""The deal tables (migration 0011; decision P4-B, slice 4B).

The structural guards (`test_tenant_table_guard.py`) prove forced RLS, the
platform policy, the runtime role's privileges (the history is append-only)
and purge coverage from the catalogs. These tests prove the behaviour: what
the runtime role can see and write, the composite foreign keys with RLS
bypassed, the value and outcome rules, the history's rules and order, the
stage, contact, company and deal deletions, the real purge through the
installed operator command, and the migration's rollback.

Rows are written with plain SQL as the runtime role or the migration role,
as in `test_crm_tables.py`, in the disposable integration database.
"""

from __future__ import annotations

import json
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
import pytest
from psycopg import errors
from psycopg.types.json import Jsonb

from crm_app.purge import EXPECTED_PURGE_PARTICIPANTS
from tests.integration.test_crm_tables import (
    MIGRATIONS_DIR,
    _as_workspace,
    _company,
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


def _setup(connection: psycopg.Connection, tenant: object) -> tuple[uuid.UUID, list[uuid.UUID]]:
    """A pipeline with two stages."""
    pipeline = _insert(
        connection,
        "pipeline",
        {"id": uuid.uuid4(), "tenant_id": tenant, "name": f"P {uuid.uuid4().hex[:6]}"},
    )
    stages = [
        _insert(
            connection,
            "pipeline_stage",
            {
                "id": uuid.uuid4(),
                "tenant_id": tenant,
                "pipeline_id": pipeline,
                "name": name,
                "probability": 50,
                "position": position,
            },
        )
        for position, name in enumerate(("First", "Second"))
    ]
    return pipeline, stages


def _deal(
    connection: psycopg.Connection,
    tenant: object,
    pipeline: object,
    stage: object,
    **values: object,
) -> uuid.UUID:
    row: dict[str, object] = {
        "id": uuid.uuid4(),
        "tenant_id": tenant,
        "title": "Website redesign",
        "currency": "EUR",
        "pipeline_id": pipeline,
        "stage_id": stage,
        **values,
    }
    return _insert(connection, "opportunity", row)


def _event(
    connection: psycopg.Connection, tenant: object, deal: object, kind: str, **values: object
) -> uuid.UUID:
    return _insert(
        connection,
        "opportunity_event",
        {"id": uuid.uuid4(), "tenant_id": tenant, "opportunity_id": deal, "kind": kind, **values},
    )


def _created(connection: psycopg.Connection, tenant: object, deal: object, stage: object) -> None:
    _event(connection, tenant, deal, "created", stage_to=stage, stage_to_name="First")


# --- Row-level security, as the runtime role ---------------------------------------


def test_deals_and_history_are_visible_only_inside_their_own_workspace(
    env: dict[str, str],  # noqa: F811
    runtime: psycopg.Connection,  # noqa: F811
) -> None:
    a, b = _workspace(env)["tenant"], _workspace(env)["tenant"]
    with _as_workspace(runtime, a):
        pipeline, stages = _setup(runtime, a)
        _created(runtime, a, _deal(runtime, a, pipeline, stages[0]), stages[0])
    for table in ("opportunity", "opportunity_event"):
        assert _visible(runtime, table) == 0
        with _as_workspace(runtime, b):
            assert _visible(runtime, table) == 0
        with _as_workspace(runtime, a):
            assert _visible(runtime, table) == 1


def test_the_runtime_role_cannot_write_into_another_workspace(
    env: dict[str, str],  # noqa: F811
    runtime: psycopg.Connection,  # noqa: F811
    owner_connection: psycopg.Connection,
) -> None:
    a, b = _workspace(env)["tenant"], _workspace(env)["tenant"]
    pipeline_b, stages_b = _setup(owner_connection, b)
    with pytest.raises(errors.InsufficientPrivilege), _as_workspace(runtime, a):
        _deal(runtime, b, pipeline_b, stages_b[0])
    with pytest.raises(errors.InsufficientPrivilege):
        _deal(runtime, b, pipeline_b, stages_b[0])  # no workspace set at all


def test_the_history_is_append_only_for_the_runtime_role(
    env: dict[str, str],  # noqa: F811
    runtime: psycopg.Connection,  # noqa: F811
) -> None:
    a = _workspace(env)["tenant"]
    with _as_workspace(runtime, a):
        pipeline, stages = _setup(runtime, a)
        deal = _deal(runtime, a, pipeline, stages[0])
        _created(runtime, a, deal, stages[0])
    with pytest.raises(errors.InsufficientPrivilege), _as_workspace(runtime, a):
        runtime.execute(
            "UPDATE crm_app.opportunity_event SET actor_user_id = NULL WHERE opportunity_id = %s",
            (deal,),
        )


# --- Composite foreign keys, with RLS bypassed --------------------------------------


def test_a_deal_references_only_its_own_workspaces_stage_contact_and_company(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
) -> None:
    a, b = _workspace(env)["tenant"], _workspace(env)["tenant"]
    pipeline_a, stages_a = _setup(owner_connection, a)
    other_a, others_a = _setup(owner_connection, a)
    pipeline_b, stages_b = _setup(owner_connection, b)
    refused: list[tuple[object, object, dict[str, Any]]] = [
        (pipeline_b, stages_b[0], {}),  # another workspace's stage
        (pipeline_a, others_a[0], {}),  # a stage of another pipeline
        (other_a, stages_a[0], {}),
        (pipeline_a, stages_a[0], {"contact_id": _contact(owner_connection, b)}),
        (pipeline_a, stages_a[0], {"company_id": _company(owner_connection, b)}),
    ]
    for pipeline, stage, values in refused:
        with pytest.raises(errors.ForeignKeyViolation), owner_connection.transaction():
            _deal(owner_connection, a, pipeline, stage, **values)


# --- Values -------------------------------------------------------------------------

_CLOSED = "2026-10-27T10:00:00Z"


@pytest.mark.parametrize(
    "values",
    [
        {"title": ""},
        {"title": " Padded"},
        {"title": "x" * 201},
        {"title": "line\nbreak"},
        {"amount": Decimal("-1")},
        {"currency": "eur"},
        {"currency": "EURO"},
        {"outcome": "pending"},
        {"outcome": "lost", "closed_at": _CLOSED},
        {"outcome": "won"},
        {"lost_reason": "Too expensive"},
        {"outcome": "lost", "lost_reason": "", "closed_at": _CLOSED},
        {"outcome": "lost", "lost_reason": "x" * 501, "closed_at": _CLOSED},
        {"closed_at": _CLOSED},
    ],
    ids=[
        "empty-title",
        "padded-title",
        "long-title",
        "control-title",
        "negative",
        "lower-currency",
        "long-currency",
        "unknown-outcome",
        "lost-without-reason",
        "won-without-closed-at",
        "open-with-reason",
        "empty-reason",
        "long-reason",
        "open-but-closed",
    ],
)
def test_deals_outside_the_rules_are_refused(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
    values: dict[str, object],
) -> None:
    a = _workspace(env)["tenant"]
    pipeline, stages = _setup(owner_connection, a)
    with pytest.raises(errors.CheckViolation), owner_connection.transaction():
        _deal(owner_connection, a, pipeline, stages[0], **values)


def test_amounts_are_stored_exactly(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
) -> None:
    a = _workspace(env)["tenant"]
    pipeline, stages = _setup(owner_connection, a)
    deal = _deal(owner_connection, a, pipeline, stages[0], amount=Decimal("999999999999.999"))
    row = owner_connection.execute(
        "SELECT amount FROM crm_app.opportunity WHERE id = %s", (deal,)
    ).fetchone()
    assert row == (Decimal("999999999999.999"),)
    # Thirteen whole digits do not fit numeric(15,3).
    with pytest.raises(errors.NumericValueOutOfRange), owner_connection.transaction():
        _deal(owner_connection, a, pipeline, stages[0], amount=Decimal("1000000000000"))
    _deal(
        owner_connection,
        a,
        pipeline,
        stages[0],
        outcome="lost",
        lost_reason="Budget cut",
        closed_at=_CLOSED,
    )


# --- History ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "values",
    [
        {"kind": "deleted"},
        {"kind": "updated"},
        {"kind": "updated", "fields": Jsonb(["lost_reason"])},
        {"kind": "updated", "fields": Jsonb(["title", "stage_id"])},
        {"kind": "stage_changed", "stage_cause": "moved"},
        {"kind": "outcome_changed", "outcome_from": "won", "outcome_to": "lost"},
        {"kind": "outcome_changed", "outcome_from": "open", "outcome_to": "open"},
        {"kind": "owner_changed"},
        {"kind": "created"},
    ],
    ids=[
        "unknown-kind",
        "updated-without-fields",
        "lost-reason-field",
        "stage-field",
        "stage-change-without-stages",
        "won-to-lost",
        "open-to-open",
        "owner-unchanged",
        "created-without-stage",
    ],
)
def test_history_entries_outside_the_rules_are_refused(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
    values: dict[str, Any],
) -> None:
    a = _workspace(env)["tenant"]
    pipeline, stages = _setup(owner_connection, a)
    deal = _deal(owner_connection, a, pipeline, stages[0])
    entry = dict(values)
    kind = entry.pop("kind")
    with pytest.raises(errors.CheckViolation), owner_connection.transaction():
        _event(owner_connection, a, deal, kind, **entry)


def test_history_entries_are_numbered_in_the_order_they_were_written(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
) -> None:
    a = _workspace(env)["tenant"]
    pipeline, stages = _setup(owner_connection, a)
    deal = _deal(owner_connection, a, pipeline, stages[0])
    with owner_connection.transaction():
        written = [
            _event(owner_connection, a, deal, "created", stage_to=stages[0], stage_to_name="A"),
            _event(owner_connection, a, deal, "updated", fields=Jsonb(["title", "amount"])),
            _event(
                owner_connection,
                a,
                deal,
                "stage_changed",
                stage_from=stages[0],
                stage_from_name="A",
                stage_to=stages[1],
                stage_to_name="B",
                stage_cause="moved",
            ),
            _event(
                owner_connection, a, deal, "outcome_changed", outcome_from="open", outcome_to="won"
            ),
        ]
    rows = owner_connection.execute(
        "SELECT id FROM crm_app.opportunity_event WHERE opportunity_id = %s ORDER BY seq", (deal,)
    ).fetchall()
    assert [row[0] for row in rows] == written


# --- Deletions ----------------------------------------------------------------------


def test_a_stage_holding_deals_cannot_be_deleted(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
) -> None:
    a = _workspace(env)["tenant"]
    pipeline, stages = _setup(owner_connection, a)
    _deal(owner_connection, a, pipeline, stages[0])
    with pytest.raises(errors.ForeignKeyViolation), owner_connection.transaction():
        owner_connection.execute("DELETE FROM crm_app.pipeline_stage WHERE id = %s", (stages[0],))
    owner_connection.execute("DELETE FROM crm_app.pipeline_stage WHERE id = %s", (stages[1],))


def test_deleting_a_contact_or_company_keeps_the_deal_without_the_link(
    env: dict[str, str],  # noqa: F811
    runtime: psycopg.Connection,  # noqa: F811
) -> None:
    a = _workspace(env)["tenant"]
    with _as_workspace(runtime, a):
        pipeline, stages = _setup(runtime, a)
        contact, company = _contact(runtime, a), _company(runtime, a)
        deal = _deal(runtime, a, pipeline, stages[0], contact_id=contact, company_id=company)
        runtime.execute("DELETE FROM crm_app.contact WHERE id = %s", (contact,))
        runtime.execute("DELETE FROM crm_app.company WHERE id = %s", (company,))
        row = runtime.execute(
            "SELECT tenant_id, contact_id, company_id FROM crm_app.opportunity WHERE id = %s",
            (deal,),
        ).fetchone()
    assert row == (uuid.UUID(a), None, None)


def test_deleting_a_deal_deletes_its_history(
    env: dict[str, str],  # noqa: F811
    runtime: psycopg.Connection,  # noqa: F811
) -> None:
    a = _workspace(env)["tenant"]
    with _as_workspace(runtime, a):
        pipeline, stages = _setup(runtime, a)
        deal = _deal(runtime, a, pipeline, stages[0])
        _created(runtime, a, deal, stages[0])
        runtime.execute("DELETE FROM crm_app.opportunity WHERE id = %s", (deal,))
        assert _visible(runtime, "opportunity_event") == 0


# --- Purge through the installed operator command --------------------------------


def test_the_operator_purge_removes_deals_of_that_workspace_only(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
) -> None:
    target = _workspace(env, deleted=True)
    other = _workspace(env)["tenant"]
    for tenant in (target["tenant"], other):
        pipeline, stages = _setup(owner_connection, tenant)
        _created(
            owner_connection,
            tenant,
            _deal(owner_connection, tenant, pipeline, stages[0]),
            stages[0],
        )

    purged = _operator(env, target["tenant"], target["actor"], *OPERATOR_SETUP)

    assert purged.returncode == 0, purged.stderr
    result = json.loads(purged.stdout)["result"]
    assert result["participant_names"] == list(EXPECTED_PURGE_PARTICIPANTS)
    assert _status(owner_connection, target["tenant"]) == "purged"
    for table in ("opportunity", "opportunity_event", "pipeline_stage", "pipeline"):
        assert _count(owner_connection, table, target["tenant"]) == 0
        assert _count(owner_connection, table, other) >= 1


# --- Rollback (last in this module) --------------------------------------------------

_DOWNGRADE = (
    "from alembic import command\n"
    "from alembic.config import Config\n"
    "config = Config()\n"
    "config.set_main_option('script_location', {path!r})\n"
    "command.downgrade(config, '0010_pipelines')\n"
)
_TABLES = (
    "SELECT relname FROM pg_class WHERE relnamespace = 'crm_app'::regnamespace AND relkind = 'r'"
)
_DEAL_TABLES = {"opportunity", "opportunity_event"}


def test_the_migration_rolls_back_and_forward(
    env: dict[str, str],  # noqa: F811
    owner_connection: psycopg.Connection,
    tmp_path: Path,
) -> None:
    """Downgrades to 0010 (dropping the deal tables and their rows), then
    upgrades, leaving the schema as the other tests need it."""
    down = run_python(_DOWNGRADE.format(path=str(MIGRATIONS_DIR)), env, tmp_path)
    try:
        assert down.returncode == 0, down.stderr
        tables = {name for (name,) in owner_connection.execute(_TABLES).fetchall()}
        assert not tables & _DEAL_TABLES
        assert {"pipeline", "pipeline_stage", "contact"} <= tables
    finally:
        up = run_module("crm_app.migrate", [], env, tmp_path)
        assert up.returncode == 0, up.stderr
    tables = {name for (name,) in owner_connection.execute(_TABLES).fetchall()}
    assert tables >= _DEAL_TABLES
