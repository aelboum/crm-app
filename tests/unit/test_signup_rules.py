"""Self-service signup rules that need no database (decision S-1).

The workspace-name rules and the replay fingerprint
(`crm_app.domains.signup`), and two source-level guarantees the RLS design
relies on (`SIGNUP-PLAN.md` §4b):

- the person and maintenance settings are only ever set transaction-locally,
  in one place (a session-level `set_config` would outlive the transaction
  on a pooled connection: shown by the pre-migration probe);
- nothing writes inside a maintenance reader, so the read-only flag stays
  read-only in code as well as in the policies.
"""

from __future__ import annotations

import ast
import re

import pytest

from crm_app.domains.signup import (
    NAME_MAX,
    InvalidWorkspaceNameError,
    normalize_workspace_name,
    request_fingerprint,
)
from tests.support import REPO_ROOT

SOURCE = REPO_ROOT / "src" / "crm_app"


@pytest.mark.parametrize(
    ("raw", "stored"),
    [
        ("Acme", "Acme"),
        ("  Acme   Dental  ", "Acme Dental"),
        ("B" + chr(0xE4) + "ckerei", "B" + chr(0xE4) + "ckerei"),
        ("Ba" + chr(0x308) + "ckerei", "B" + chr(0xE4) + "ckerei"),  # NFD becomes NFC
        ("Studio\tNoord", "Studio Noord"),
        ("x" * NAME_MAX, "x" * NAME_MAX),
    ],
)
def test_acceptable_names_are_normalized(raw: str, stored: str) -> None:
    assert normalize_workspace_name(raw) == stored


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "x" * (NAME_MAX + 1),
        "Acme" + chr(0x0000) + "Ltd",
        "Acme" + chr(0x0007) + "Ltd",
        "Acme" + chr(0x200B) + "Ltd",
        "Acme" + chr(0x202E) + "Ltd",
        "Acme" + chr(0xFEFF) + "Ltd",
        None,
        42,
        ["Acme"],
    ],
)
def test_unacceptable_names_are_refused_without_echoing_them(raw: object) -> None:
    with pytest.raises(InvalidWorkspaceNameError) as raised:
        normalize_workspace_name(raw)
    if isinstance(raw, str) and raw.strip():
        assert raw.strip() not in str(raised.value)


def test_the_fingerprint_matches_only_the_same_normalized_request() -> None:
    assert request_fingerprint("Acme") == request_fingerprint(normalize_workspace_name(" Acme "))
    assert request_fingerprint("Acme") != request_fingerprint("Acme Ltd")
    assert re.fullmatch(r"[0-9a-f]{64}", request_fingerprint("Acme"))


def _sources() -> dict[str, str]:
    return {
        path.relative_to(SOURCE).as_posix(): path.read_text(encoding="utf-8")
        for path in SOURCE.rglob("*.py")
        if "migrations" not in path.parts
    }


def test_settings_are_set_in_one_place_and_only_transaction_locally() -> None:
    callers = {name for name, text in _sources().items() if "set_config(" in text}
    assert callers == {"signups.py"}
    signups = _sources()["signups.py"]
    calls = re.findall(r"set_config\(.*?, true\)|set_config\([^\n]*", signups)
    assert calls == ["set_config(%(name)s, %(value)s, true)"]


def _maintenance_blocks(tree: ast.AST) -> list[ast.With]:
    blocks = []
    for node in ast.walk(tree):
        if isinstance(node, ast.With):
            for item in node.items:
                call = item.context_expr
                if (
                    isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Name)
                    and call.func.id == "_maintenance_reader"
                ):
                    blocks.append(node)
    return blocks


def test_nothing_writes_inside_a_maintenance_reader() -> None:
    tree = ast.parse(_sources()["signups.py"])
    blocks = _maintenance_blocks(tree)
    assert len(blocks) >= 3  # forget_workspace, remaining_for_workspace, maintain
    writes = {"update", "delete", "insert", "add", "exec_driver_sql", "_set", "_set_local"}
    found = [
        node.func.id if isinstance(node.func, ast.Name) else node.func.attr
        for block in blocks
        for statement in block.body
        for node in ast.walk(statement)
        if isinstance(node, ast.Call)
        and (
            (isinstance(node.func, ast.Name) and node.func.id in writes)
            or (isinstance(node.func, ast.Attribute) and node.func.attr in writes)
        )
    ]
    assert found == []


def test_only_the_maintenance_reader_turns_the_flag_on() -> None:
    signups = _sources()["signups.py"]
    assert signups.count("_set_local(session, MAINTENANCE_SETTING, ") == 1
    reader = signups[signups.index("def _maintenance_reader") :]
    assert reader.index("MAINTENANCE_SETTING") < reader.index("\ndef ", 1)
