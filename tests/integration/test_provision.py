"""The provisioning command (`crm_app.provision`; PHASE2-PLAN.md §7.4).

Runs the real command in a fresh interpreter against the integration
database, then checks the result in the catalogue tables as the owner
connection. Partial states are prepared with the same public SaaS-OS calls
the command uses, under `SystemCaller(PROVISIONING)`, whose documented
purposes include test fixtures.
"""

from __future__ import annotations

import secrets
from pathlib import Path

import psycopg
import pytest

from crm_app.roles import ROLE_TEMPLATES, Role
from tests.support import run_module, run_python

pytestmark = pytest.mark.usefixtures("migrated")

ISSUER = "https://identity.invalid/provision-test"
_PARTIAL = (
    "from saas_os.core.authority import SystemAuthority, SystemCaller\n"
    "from saas_os.core.rbac import create_role\n"
    "from saas_os.core.tenancy import TenantStatus, create_tenant, transition_tenant_status\n"
    "caller = SystemCaller(SystemAuthority.PROVISIONING)\n"
    "name, stage = {name!r}, {stage!r}\n"
    "tenant = create_tenant(name, caller=caller)\n"
    "if stage in ('active', 'roles'):\n"
    "    transition_tenant_status(tenant.id, TenantStatus.ACTIVE, caller=caller)\n"
    "if stage == 'roles':\n"
    "    create_role(tenant.id, 'Owner', caller=caller)\n"
    "    create_role(tenant.id, 'Admin', caller=caller)\n"
)


def _provision(
    env: dict[str, str], cwd: Path, name: str, subject: str, *extra: str
) -> tuple[int, str, str]:
    args = ["--name", name, "--owner-issuer", ISSUER, "--owner-subject", subject, *extra]
    result = run_module("crm_app.provision", args, env, cwd)
    return result.returncode, result.stdout, result.stderr


def _field(stdout: str, label: str) -> str:
    line = next(x for x in stdout.splitlines() if x.startswith(label))
    return line.split(":", 1)[1].strip()


def _tenant_ids(connection: psycopg.Connection, name: str) -> list[str]:
    rows = connection.execute("SELECT id FROM core.tenants WHERE name = %s", (name,)).fetchall()
    return [str(row[0]) for row in rows]


def _grants(connection: psycopg.Connection, tenant_id: str) -> dict[str, set[tuple[str, str]]]:
    rows = connection.execute(
        "SELECT r.name, p.resource, p.action FROM core.roles r"
        " JOIN core.role_permissions rp ON rp.role_id = r.id"
        " JOIN core.permissions p ON p.id = rp.permission_id"
        " WHERE r.tenant_id = %s",
        (tenant_id,),
    ).fetchall()
    grants: dict[str, set[tuple[str, str]]] = {}
    for role, resource, action in rows:
        grants.setdefault(role, set()).add((resource, action))
    return grants


def _member_roles(connection: psycopg.Connection, tenant_id: str) -> list[tuple[str, str, str]]:
    rows = connection.execute(
        "SELECT m.user_id::text, m.status, r.name FROM core.tenant_memberships m"
        " JOIN core.membership_roles mr ON mr.membership_id = m.id"
        " JOIN core.roles r ON r.id = mr.role_id WHERE m.tenant_id = %s",
        (tenant_id,),
    ).fetchall()
    return [(str(user), str(status), str(role)) for user, status, role in rows]


def _name() -> str:
    return f"provision-test-{secrets.token_hex(6)}"


@pytest.fixture
def env(integration_env: dict[str, str]) -> dict[str, str]:
    return dict(integration_env)


def test_a_dry_run_changes_nothing(
    env: dict[str, str], tmp_path: Path, owner_connection: psycopg.Connection
) -> None:
    name = _name()
    code, stdout, stderr = _provision(env, tmp_path, name, secrets.token_hex(8), "--dry-run")
    assert code == 0, stderr
    assert stdout.startswith("DRY RUN")
    assert _tenant_ids(owner_connection, name) == []


def test_a_run_creates_the_workspace_roles_grants_and_owner(
    env: dict[str, str], tmp_path: Path, owner_connection: psycopg.Connection
) -> None:
    name = _name()
    code, stdout, stderr = _provision(env, tmp_path, name, secrets.token_hex(8))
    assert code == 0, stderr
    tenant_id = _field(stdout, "workspace id")
    owner_id = _field(stdout, "owner user id")
    assert _tenant_ids(owner_connection, name) == [tenant_id]
    status = owner_connection.execute(
        "SELECT status FROM core.tenants WHERE id = %s", (tenant_id,)
    ).fetchone()
    assert status == ("active",)
    assert _grants(owner_connection, tenant_id) == {
        role.value: set(keys) for role, keys in ROLE_TEMPLATES.items()
    }
    assert _member_roles(owner_connection, tenant_id) == [(owner_id, "active", Role.OWNER.value)]


def test_a_rerun_changes_nothing(
    env: dict[str, str], tmp_path: Path, owner_connection: psycopg.Connection
) -> None:
    name, subject = _name(), secrets.token_hex(8)
    assert _provision(env, tmp_path, name, subject)[0] == 0
    code, stdout, stderr = _provision(env, tmp_path, name, subject)
    assert code == 0, stderr
    assert _field(stdout, "performed") == "nothing"
    assert len(_tenant_ids(owner_connection, name)) == 1


@pytest.mark.parametrize("stage", ["pending", "active", "roles"])
def test_an_interrupted_run_is_completed(
    env: dict[str, str], tmp_path: Path, owner_connection: psycopg.Connection, stage: str
) -> None:
    name = _name()
    prepared = run_python(_PARTIAL.format(name=name, stage=stage), env, tmp_path)
    assert prepared.returncode == 0, prepared.stderr
    code, stdout, stderr = _provision(env, tmp_path, name, secrets.token_hex(8))
    assert code == 0, stderr
    tenant_id = _field(stdout, "workspace id")
    assert _tenant_ids(owner_connection, name) == [tenant_id]
    assert _grants(owner_connection, tenant_id) == {
        role.value: set(keys) for role, keys in ROLE_TEMPLATES.items()
    }
    assert [row[2] for row in _member_roles(owner_connection, tenant_id)] == [Role.OWNER.value]


def test_another_owners_workspace_is_never_claimed(
    env: dict[str, str], tmp_path: Path, owner_connection: psycopg.Connection
) -> None:
    name = _name()
    assert _provision(env, tmp_path, name, secrets.token_hex(8))[0] == 0
    code, _, stderr = _provision(env, tmp_path, name, secrets.token_hex(8))
    assert code == 2
    assert "other members" in stderr
    tenant_id = _tenant_ids(owner_connection, name)[0]
    assert len(_member_roles(owner_connection, tenant_id)) == 1


def test_the_output_holds_identifiers_only(env: dict[str, str], tmp_path: Path) -> None:
    code, stdout, _ = _provision(env, tmp_path, _name(), secrets.token_hex(8))
    assert code == 0
    for value in (env["DATABASE_URL"], env["MIGRATIONS_DATABASE_URL"], env["REDIS_URL"]):
        assert value not in stdout
    assert "://" not in stdout
