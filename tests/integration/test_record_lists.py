"""Contact and company lists (slice 3A.3, `PHASE3-PLAN.md` §19.5).

Drives `record_list_probe` in a fresh interpreter, then checks every paged
order against the order PostgreSQL itself produces for the same columns,
collation and NULL placement, read as the owner connection. Also covers
filters, prefix search with escaped wildcards, cursor refusal, parameter
validation, paging under concurrent inserts, and workspace isolation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import psycopg
import pytest
from psycopg import sql

from tests.support import REPO_ROOT, run_module

pytestmark = pytest.mark.usefixtures("migrated")

Probe = dict[str, Any]
ICU = sql.SQL('COLLATE "und-x-icu"')


@pytest.fixture(scope="module")
def probe(integration_env: dict[str, str], tmp_path_factory: pytest.TempPathFactory) -> Probe:
    # The probe pages through every order and filter: about 100 requests to
    # one path, above SaaS-OS's default 60 per minute per workspace and path.
    # Raised for this probe's process only, through the platform's own setting.
    env = {
        **integration_env,
        "PYTHONPATH": str(REPO_ROOT),
        "RATE_LIMIT_REQUESTS_PER_WINDOW": "1000",
    }
    cwd: Path = tmp_path_factory.mktemp("lists")
    result = run_module("tests.integration.record_list_probe", [], env, cwd, timeout=900)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def _order(
    connection: psycopg.Connection, table: str, workspace: str, sort: str, direction: str
) -> list[str]:
    """The database's own order for the probe's original rows (the row
    inserted during the consistency check, "Aaron", is left out)."""
    way = sql.SQL("DESC") if direction == "desc" else sql.SQL("ASC")
    if sort == "name" and table == "contact":
        keys = [
            sql.SQL("{} {} {}").format(sql.Identifier("last_name"), ICU, way),
            sql.SQL("{} {} {}").format(sql.Identifier("first_name"), ICU, way),
        ]
    elif sort == "name":
        keys = [sql.SQL("{} {} {}").format(sql.Identifier("name"), ICU, way)]
    else:
        keys = [sql.SQL("{} {}").format(sql.Identifier(sort), way)]
    keys.append(sql.SQL("id {}").format(way))
    extra = sql.SQL(" AND first_name <> 'Aaron'") if table == "contact" else sql.SQL("")
    query = sql.SQL(
        "SELECT id::text FROM {} WHERE tenant_id = %s AND archived_at IS NULL{} ORDER BY {}"
    ).format(sql.Identifier("crm_app", table), extra, sql.SQL(", ").join(keys))
    return [row[0] for row in connection.execute(query, (workspace,)).fetchall()]


@pytest.mark.parametrize("sort", ["name", "created_at", "updated_at"])
@pytest.mark.parametrize("direction", ["asc", "desc"])
def test_contact_pages_follow_the_database_order_without_gaps_or_repeats(
    probe: Probe, owner_connection: psycopg.Connection, sort: str, direction: str
) -> None:
    paged = probe["contact_orders"][f"{sort}:{direction}"]
    expected = _order(owner_connection, "contact", probe["workspace"], sort, direction)
    assert paged["ids"] == expected
    assert len(expected) == 11
    assert paged["total"] == 11


@pytest.mark.parametrize("sort", ["name", "created_at"])
@pytest.mark.parametrize("direction", ["asc", "desc"])
def test_company_pages_follow_the_database_order(
    probe: Probe, owner_connection: psycopg.Connection, sort: str, direction: str
) -> None:
    paged = probe["company_orders"][f"{sort}:{direction}"]
    assert paged["ids"] == _order(owner_connection, "company", probe["workspace"], sort, direction)


def test_names_sort_case_insensitively_with_null_last_names_last(
    probe: Probe, owner_connection: psycopg.Connection
) -> None:
    ids = probe["contact_orders"]["name:asc"]["ids"]
    rows = dict(
        owner_connection.execute(
            "SELECT id::text, coalesce(last_name, '') || '/' || first_name FROM crm_app.contact"
            " WHERE tenant_id = %s",
            (probe["workspace"],),
        ).fetchall()
    )
    names = [rows[i] for i in ids]
    assert names[:2] == ["Bakker/Femke", "Bakker/Gijs"]
    assert {names[2], names[3]} == {"de Vries/dirk", "de vries/Eva"}
    assert names[-2:] == ["/Bert", "/Carla"]


def test_read_only_members_can_list(probe: Probe) -> None:
    assert len(probe["reader"]["ids"]) == 11


def test_filters_narrow_the_list(probe: Probe, owner_connection: psycopg.Connection) -> None:
    filters, ids, workspace = probe["filters"], probe["ids"], probe["workspace"]

    def where(condition: str, *args: object) -> set[str]:
        fixed = sql.SQL(condition)  # pyright: ignore[reportArgumentType] - fixed test text
        query = sql.SQL(
            "SELECT id::text FROM crm_app.contact WHERE tenant_id = %s AND first_name <> 'Aaron'"
            " AND {}"
        ).format(fixed)
        return {row[0] for row in owner_connection.execute(query, (workspace, *args)).fetchall()}

    active = "archived_at IS NULL"
    assert set(filters["stage"]["ids"]) == where(
        f"{active} AND lifecycle_stage IN ('customer', 'inactive')"
    )
    assert set(filters["owner_me"]["ids"]) == where(f"{active} AND owner_user_id IS NOT NULL")
    assert set(filters["company"]["ids"]) == where(f"{active} AND company_id = %s", ids["acme"])
    assert filters["archived_true"]["ids"] == [ids["archived"]]
    assert len(filters["archived_all"]["ids"]) == 12


def test_search_is_a_case_insensitive_prefix_with_wildcards_taken_literally(
    probe: Probe,
) -> None:
    filters, ids = probe["filters"], probe["ids"]
    assert len(filters["q_anna"]["ids"]) == 2  # the third Anna is archived
    assert len(filters["q_last"]["ids"]) == 2  # de Vries, de vries
    assert len(filters["q_email"]["ids"]) == 1  # p1. but not p10., p11.
    assert filters["q_percent"]["ids"] == [ids["percent"]]
    assert filters["q_underscore"]["ids"] == [ids["underscore"]]
    assert filters["q_underscore_wild"]["ids"] == []
    assert filters["q_injection"]["ids"] == []
    assert len(filters["company_q"]["ids"]) == 2  # acme, Acme


def test_a_row_inserted_before_the_cursor_neither_appears_nor_shifts_the_rest(
    probe: Probe, owner_connection: psycopg.Connection
) -> None:
    consistency = probe["consistency"]
    seen = consistency["first"] + consistency["rest"]["ids"]
    expected = _order(owner_connection, "contact", probe["workspace"], "name", "asc")
    assert seen == expected


def test_cursors_are_refused_outside_their_own_order_and_filters(probe: Probe) -> None:
    assert probe["cursors"] == {
        "other_filters": 400,
        "other_order": 400,
        "tampered": 400,
        "garbage": 400,
        "too_long": 422,
    }


def test_list_parameters_are_validated(probe: Probe) -> None:
    assert probe["validation"] == dict.fromkeys(
        (
            "unknown_param",
            "bad_sort",
            "bad_stage",
            "limit_zero",
            "limit_high",
            "q_long",
            "bad_owner",
            "company_stage",
        ),
        422,
    )


def test_lists_hold_only_the_callers_workspace(probe: Probe) -> None:
    isolation = probe["isolation"]
    assert isolation["other_owner_on_a"] == 404
    assert isolation["other_list"] == ["Other"]
    assert isolation["unknown_workspace"] == 404
