"""Product code imports SaaS-OS only through its public surface.

SaaS-OS's public surface (ADR-0038; `saas_os.infra.update.policy`) is
`saas_os.api.*`, `saas_os.inference`, `saas_os.contracts` and the `__init__`
of each `saas_os.core.*`, `saas_os.infra.*` and `saas_os.control_plane.*`
package. Everything below a package `__init__` is internal.
import-linter cannot express submodule rules for an external package, so
this test parses every import in `src/` instead.
"""

from __future__ import annotations

import ast
from pathlib import Path

from tests.support import REPO_ROOT

SOURCE_ROOT = REPO_ROOT / "src" / "crm_app"

# Public packages the product is allowed to import from (PHASE1-PLAN.md §3).
PUBLIC_PACKAGES = frozenset(
    {
        "saas_os.infra.db",
        "saas_os.infra.jobs",
        "saas_os.infra.secrets",
        "saas_os.infra.observability",
        "saas_os.infra.egress",
        "saas_os.core.identity",
        "saas_os.core.tenancy",
        "saas_os.core.rbac",
        "saas_os.core.authority",
        "saas_os.core.audit_log",
        "saas_os.core.idempotency",
        "saas_os.core.email",
        "saas_os.core.crypto",
        "saas_os.core.billing",
        "saas_os.core.webhooks",
        "saas_os.core.usage",
        "saas_os.core.notifications",
        "saas_os.inference",
        "saas_os.contracts",
    }
)

# Never imported, even though they sit under the public `saas_os.api`.
FORBIDDEN_PREFIXES = ("saas_os.api.main", "saas_os.api.server", "saas_os.control_plane")


def _is_allowed(module: str) -> bool:
    if module.startswith(FORBIDDEN_PREFIXES):
        return False
    return module in PUBLIC_PACKAGES or module.startswith("saas_os.api.")


def _saas_os_imports(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.append((node.lineno, node.module))
    return [(line, module) for line, module in found if module.split(".")[0] == "saas_os"]


def test_every_saas_os_import_is_public() -> None:
    violations = [
        f"{path.relative_to(REPO_ROOT)}:{line} imports {module}"
        for path in sorted(SOURCE_ROOT.rglob("*.py"))
        for line, module in _saas_os_imports(path)
        if not _is_allowed(module)
    ]
    assert violations == []


def test_the_check_rejects_internal_modules() -> None:
    assert not _is_allowed("saas_os")
    assert not _is_allowed("saas_os.infra.db.rls")
    assert not _is_allowed("saas_os.infra.jobs.queue")
    assert not _is_allowed("saas_os.core.tenancy.purge_participants")
    assert not _is_allowed("saas_os.api.main")
    assert not _is_allowed("saas_os.control_plane.inference")
    assert _is_allowed("saas_os.api.platform")
    assert _is_allowed("saas_os.infra.db")


def test_the_check_sees_this_products_imports() -> None:
    modules = {module for path in SOURCE_ROOT.rglob("*.py") for _, module in _saas_os_imports(path)}
    assert {"saas_os.api.platform", "saas_os.api.worker", "saas_os.infra.db"} <= modules
