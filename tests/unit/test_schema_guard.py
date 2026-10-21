"""No product migration creates a table that has not been approved.

Phase 2 may not add a tenant-owned table before the purge decision
(PHASE2-PLAN.md gate G1). This reads the migration sources only, so it runs
without a database; `tests/integration/test_tenant_table_guard.py` checks
the migrated database itself.
"""

from __future__ import annotations

import ast
import re

from tests.support import PRODUCT_TABLES, REPO_ROOT

VERSIONS = REPO_ROOT / "src" / "crm_app" / "migrations" / "versions"
_CREATE_TABLE = re.compile(
    r"\bCREATE\s+(?:UNLOGGED\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([\w.\"]+)", re.IGNORECASE
)


def _created_tables(source: str) -> set[str]:
    tables: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "create_table"
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ):
            tables.add(str(node.args[0].value))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            for name in _CREATE_TABLE.findall(node.value):
                tables.add(name.replace('"', "").rsplit(".", 1)[-1])
    return tables


def test_migrations_create_only_approved_tables() -> None:
    created = {
        table
        for path in sorted(VERSIONS.glob("*.py"))
        for table in _created_tables(path.read_text(encoding="utf-8"))
    }
    assert created <= PRODUCT_TABLES


def test_the_scan_recognises_both_forms() -> None:
    sample = (
        'op.create_table("contacts", sa.Column("id"))\n'
        'op.execute("CREATE TABLE IF NOT EXISTS crm_app.notes (id uuid)")\n'
    )
    assert _created_tables(sample) == {"contacts", "notes"}
