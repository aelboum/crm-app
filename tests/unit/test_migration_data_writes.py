"""Every data change in a product migration reaches the rows it means to
(decision M-RLS).

Tenant tables force Row-Level Security, which applies to the migration
owner on a managed PostgreSQL: an `UPDATE`, `INSERT ... SELECT` or `DELETE`
on one, outside a tenant context, silently changes nothing. Each such
statement in `crm_app/migrations/versions/` must therefore be one of:

- inside `with all_rows(<that table>)` (`crm_app.migrations.all_rows`);
- a per-workspace loop that sets `app.tenant_id` (migration 0003);
- on a global table (`tests.support.GLOBAL_TABLES`), which the owner sees
  in full without a tenant context.

Statements that define functions or triggers are not data changes and are
skipped. The integration test `test_migrations_as_owner.py` proves the
helper works against PostgreSQL.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from tests.support import GLOBAL_TABLES, REPO_ROOT

VERSIONS = REPO_ROOT / "src" / "crm_app" / "migrations" / "versions"
_WRITE = re.compile(r"\b(?:UPDATE|INSERT\s+INTO|DELETE\s+FROM)\s+([{\w\"][^\s(]*)", re.IGNORECASE)


def _module_strings(tree: ast.Module, source: str) -> dict[str, str]:
    """Module-level constants, by name, as their source text."""
    found: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                found[target.id] = ast.get_source_segment(source, node.value) or ""
    return found


def _wrapped_tables(stack: list[ast.With], source: str) -> str:
    """The source text of every `all_rows(...)` call enclosing a statement."""
    text = []
    for node in stack:
        for item in node.items:
            call = item.context_expr
            if isinstance(call, ast.Call) and getattr(call.func, "id", "") == "all_rows":
                text.append(ast.get_source_segment(source, call) or "")
    return " ".join(text)


def _violations(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    constants = _module_strings(tree, source)
    problems: list[str] = []

    def visit(node: ast.AST, stack: list[ast.With]) -> None:
        if isinstance(node, ast.With):
            stack = [*stack, node]
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "execute"
            and node.args
        ):
            arg = node.args[0]
            if isinstance(arg, ast.Name):
                text = constants.get(arg.id, "")
            else:
                text = ast.get_source_segment(source, arg) or ""
            if re.search(r"\bCREATE\s+(OR\s+REPLACE\s+)?(FUNCTION|TRIGGER)\b", text, re.I):
                return
            for match in _WRITE.finditer(text):
                target = match.group(1)
                table = re.sub(r"[^\w{}]", "", target.split(".")[-1])
                if table in GLOBAL_TABLES:
                    continue
                if "set_config('app.tenant_id'" in text:
                    continue
                wrapped = _wrapped_tables(stack, source)
                # `{table}` names a local variable holding the table.
                name = table.strip("{}")
                if wrapped and name in wrapped:
                    continue
                problems.append(f"{path.name}:{node.lineno}: {match.group(0)}")
        for child in ast.iter_child_nodes(node):
            visit(child, stack)

    visit(tree, [])
    return problems


def test_every_data_change_reaches_its_rows() -> None:
    problems = [p for path in sorted(VERSIONS.glob("0*.py")) for p in _violations(path)]
    assert problems == [], "data changes outside all_rows or a tenant loop:\n" + "\n".join(problems)


def test_the_guard_finds_an_unwrapped_change(tmp_path: Path) -> None:
    """The check itself: a bare UPDATE on a tenant table is reported, the
    same statement inside `all_rows` and one on a global table are not."""
    migration = tmp_path / "0999_probe.py"
    migration.write_text(
        "from alembic import op\n"
        "from crm_app.migrations.all_rows import all_rows\n"
        "SCHEMA = 'crm_app'\n"
        "def upgrade():\n"
        "    op.execute(f'UPDATE {SCHEMA}.contact SET x = 1')\n"
        "    with all_rows(f'{SCHEMA}.contact'):\n"
        "        op.execute(f'UPDATE {SCHEMA}.contact SET x = 2')\n"
        "    with all_rows(f'{SCHEMA}.company'):\n"
        "        op.execute(f'DELETE FROM {SCHEMA}.contact')\n"
        "    op.execute(f'DELETE FROM {SCHEMA}.signup')\n"
        "    op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON {SCHEMA}.contact TO x')\n",
        encoding="utf-8",
    )
    found = _violations(migration)
    assert [line.split(": ", 1)[0] for line in found] == ["0999_probe.py:5", "0999_probe.py:9"]
