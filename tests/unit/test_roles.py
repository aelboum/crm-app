"""The role templates (`crm_app.roles`) and the registered permissions
(`crm_app.permissions`) are consistent, least privileged, and identical to
the approved matrix in PHASE2-PLAN.md §5.2."""

from __future__ import annotations

import ast
import re

from crm_app import permissions
from crm_app.roles import CATALOGUE, PRODUCT_PERMISSIONS, ROLE_TEMPLATES, UNGRANTED, Kind, Role
from tests.support import REPO_ROOT

PLAN = REPO_ROOT / "docs" / "project" / "PHASE2-PLAN.md"
MATRIX_HEADING = "### 5.2 Role matrix"
ROLE_ORDER = (Role.OWNER, Role.ADMIN, Role.MEMBER, Role.READ_ONLY)
OWNER_ONLY = {("crm_app.owner", "manage"), ("crm_app.workspace_security", "update")}


def test_permission_identifiers_are_unique() -> None:
    keys = [p.key for p in CATALOGUE]
    assert len(keys) == len(set(keys))


def test_only_product_permissions_carry_the_product_prefix() -> None:
    assert all(p.resource.startswith(permissions.PREFIX) for p in PRODUCT_PERMISSIONS)
    platform = [p for p in CATALOGUE if p not in PRODUCT_PERMISSIONS]
    assert not any(p.resource.startswith(permissions.PREFIX) for p in platform)


def test_all_four_roles_have_a_template() -> None:
    assert len(Role) == 4
    assert set(ROLE_TEMPLATES) == set(Role)


def test_every_named_permission_is_in_the_catalogue() -> None:
    catalogue = {p.key for p in CATALOGUE}
    for template in ROLE_TEMPLATES.values():
        assert template <= catalogue
    assert catalogue >= UNGRANTED


def test_every_catalogue_entry_is_granted_or_explicitly_ungranted() -> None:
    granted = frozenset().union(*ROLE_TEMPLATES.values())
    assert granted.isdisjoint(UNGRANTED)
    assert granted | UNGRANTED == {p.key for p in CATALOGUE}


def test_roles_are_strictly_nested() -> None:
    owner, admin, member, read_only = (ROLE_TEMPLATES[r] for r in ROLE_ORDER)
    assert read_only < member < admin < owner


def test_owner_only_permissions_are_held_by_no_other_role() -> None:
    assert ROLE_TEMPLATES[Role.OWNER] - ROLE_TEMPLATES[Role.ADMIN] == OWNER_ONLY
    for role in (Role.ADMIN, Role.MEMBER, Role.READ_ONLY):
        assert ROLE_TEMPLATES[role].isdisjoint(OWNER_ONLY)


def test_admin_cannot_be_assigned_the_owner_role_by_an_admin() -> None:
    """SaaS-OS's `assign_role` refuses a role holding any permission the
    caller lacks, so Owner must hold something Admin does not."""
    assert not ROLE_TEMPLATES[Role.OWNER] <= ROLE_TEMPLATES[Role.ADMIN]


def test_read_only_holds_read_permissions_only() -> None:
    by_key = {p.key: p for p in CATALOGUE}
    assert {by_key[key].kind for key in ROLE_TEMPLATES[Role.READ_ONLY]} == {Kind.READ}


def test_member_holds_no_administrative_permission() -> None:
    by_key = {p.key: p for p in CATALOGUE}
    kinds = {by_key[key].kind for key in ROLE_TEMPLATES[Role.MEMBER]}
    assert Kind.ADMINISTRATIVE not in kinds


def test_every_administrative_permission_documents_its_safeguard() -> None:
    unguarded = [p.key for p in CATALOGUE if p.kind is Kind.ADMINISTRATIVE and not p.sensitive]
    assert unguarded == []


def test_registration_covers_exactly_the_granted_permissions() -> None:
    """The migration step registers what some role holds and nothing that
    no role may hold (PHASE2-PLAN.md §5, S1b)."""
    granted = frozenset().union(*ROLE_TEMPLATES.values())
    assert set(permissions.PERMISSIONS) == granted
    assert len(permissions.PERMISSIONS) == len(set(permissions.PERMISSIONS))
    assert UNGRANTED.isdisjoint(permissions.PERMISSIONS)


def test_registration_grants_nothing_and_creates_no_role() -> None:
    """Registration may only call SaaS-OS's `register_permission`."""
    tree = ast.parse((REPO_ROOT / "src" / "crm_app" / "permissions.py").read_text("utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("saas_os")
        for alias in node.names
    }
    assert imported == {"register_permission"}


def test_the_module_does_not_touch_saas_os() -> None:
    source = (REPO_ROOT / "src" / "crm_app" / "roles.py").read_text(encoding="utf-8")
    assert "import saas_os" not in source
    assert "from saas_os" not in source


def _plan_matrix() -> dict[tuple[str, str], tuple[bool, ...]]:
    section = PLAN.read_text(encoding="utf-8").split(MATRIX_HEADING, 1)[1].split("\n### ", 1)[0]
    rows: dict[tuple[str, str], tuple[bool, ...]] = {}
    for line in section.splitlines():
        match = re.fullmatch(r"\| `([^`]+)` \|(.+)\|", line.strip())
        if not match:
            continue
        resource, _, action = match.group(1).rpartition(":")
        cells = [cell.strip() for cell in match.group(2).split("|")][:4]
        rows[(resource, action)] = tuple(cell == "✓" for cell in cells)
    return rows


def test_the_plan_matrix_matches_the_templates() -> None:
    matrix = _plan_matrix()
    assert set(matrix) == {p.key for p in CATALOGUE}
    for key, cells in matrix.items():
        assert cells == tuple(key in ROLE_TEMPLATES[r] for r in ROLE_ORDER), key
