"""Prepares and runs workspace purges against the integration database;
prints one `RESULT <json>` line.

Run in a fresh interpreter by `tests/integration/test_purge.py` (SaaS-OS
caches configuration and the purge-participant registry per process).
Every SaaS-OS call is public. Marking a workspace deleted needs a person,
an enrolled platform operator holding `platform.tenant:delete` (SaaS-OS
ADR-0045), so `deleted` enrols a fresh test operator through
`SystemCaller(PLATFORM_BOOTSTRAP)`, as SaaS-OS's own consumer-scaffold test
does. Refuses to run unless ENVIRONMENT=test.

    python -m tests.integration.purge_probe deleted
    python -m tests.integration.purge_probe active
    python -m tests.integration.purge_probe probe-table <schema>
    python -m tests.integration.purge_probe seed <schema> <tenant> <count>
    python -m tests.integration.purge_probe purge <tenant> <schema> (probe|failing|unmapped)
"""

from __future__ import annotations

import json
import os
import secrets
import sys
import uuid

PROBE_TABLE = "items"
PROBE_PARTICIPANT = "crm_app.purge_probe"


class ProbeFailureError(RuntimeError):
    """Raised by the failing participant; only its type name is recorded."""


class FailingParticipant:
    @property
    def name(self) -> str:
        return PROBE_PARTICIPANT

    def purge_tenant_data(self, tenant_id: uuid.UUID) -> None:
        raise ProbeFailureError(f"probe failure for {tenant_id}")


def _probe_table(schema: str) -> None:
    """Declare the probe table in SaaS-OS's metadata, so the participant can
    resolve `<schema>.items` exactly as it resolves product tables."""
    from saas_os.infra.db import Base  # noqa: PLC0415
    from sqlalchemy import Column, Table, Uuid  # noqa: PLC0415

    if f"{schema}.{PROBE_TABLE}" not in Base.metadata.tables:
        Table(
            PROBE_TABLE,
            Base.metadata,
            Column("id", Uuid, primary_key=True),
            Column("tenant_id", Uuid, nullable=False),
            schema=schema,
        )


def _new_active_tenant() -> uuid.UUID:
    from saas_os.core.authority import SystemAuthority, SystemCaller  # noqa: PLC0415
    from saas_os.core.tenancy import (  # noqa: PLC0415
        TenantStatus,
        create_tenant,
        transition_tenant_status,
    )

    provisioning = SystemCaller(SystemAuthority.PROVISIONING)
    tenant = create_tenant(f"purge-test-{secrets.token_hex(6)}", caller=provisioning)
    transition_tenant_status(tenant.id, TenantStatus.ACTIVE, caller=provisioning)
    return tenant.id


def active() -> dict[str, str]:
    return {"tenant": str(_new_active_tenant())}


def deleted() -> dict[str, str]:
    from saas_os.core.authority import SystemAuthority, SystemCaller, UserCaller  # noqa: PLC0415
    from saas_os.core.identity import get_or_create_user_for_external_identity  # noqa: PLC0415
    from saas_os.core.platform_authority import (  # noqa: PLC0415
        PlatformPermission,
        enroll_operator,
        grant_platform_permission,
    )
    from saas_os.core.tenancy import TenantStatus, transition_tenant_status  # noqa: PLC0415

    tenant_id = _new_active_tenant()
    bootstrap = SystemCaller(SystemAuthority.PLATFORM_BOOTSTRAP)
    user = get_or_create_user_for_external_identity(
        "https://identity.invalid/purge-test-operators", f"operator-{secrets.token_hex(8)}"
    )
    operator = enroll_operator(user.id, caller=bootstrap, reason="crm-app purge test")
    grant_platform_permission(
        operator.id, PlatformPermission.TENANT_DELETE, caller=bootstrap, reason="crm-app purge test"
    )
    transition_tenant_status(tenant_id, TenantStatus.DELETED, caller=UserCaller(user.id))
    return {"tenant": str(tenant_id), "actor": str(user.id)}


def probe_table(schema: str) -> dict[str, str]:
    """Create `<schema>.items` the way a product migration creates a
    tenant-owned table: forced Row-Level Security, DML for the runtime role."""
    import psycopg  # noqa: PLC0415
    from psycopg import sql  # noqa: PLC0415
    from saas_os.infra.db import tenant_rls_statements  # noqa: PLC0415

    url = os.environ["MIGRATIONS_DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
    role = sql.Identifier(os.environ["APP_DB_USER"])
    qualified = sql.Identifier(schema, PROBE_TABLE)
    with psycopg.connect(url, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        connection.execute(
            sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(sql.Identifier(schema), role)
        )
        connection.execute(
            sql.SQL("CREATE TABLE {} (id uuid PRIMARY KEY, tenant_id uuid NOT NULL)").format(
                qualified
            )
        )
        connection.execute(
            sql.SQL("GRANT SELECT, INSERT, UPDATE, DELETE ON {} TO {}").format(qualified, role)
        )
        for statement in tenant_rls_statements(PROBE_TABLE, schema=schema):
            # Trusted DDL built by SaaS-OS from the identifiers above.
            connection.execute(sql.SQL(statement))  # pyright: ignore[reportArgumentType]
    return {"table": f"{schema}.{PROBE_TABLE}"}


def seed(schema: str, tenant: str, count: int) -> dict[str, int]:
    from saas_os.infra.db import Base, tenant_session_scope  # noqa: PLC0415

    _probe_table(schema)
    table = Base.metadata.tables[f"{schema}.{PROBE_TABLE}"]
    tenant_id = uuid.UUID(tenant)
    with tenant_session_scope(tenant_id) as session:
        session.execute(
            table.insert(), [{"id": uuid.uuid4(), "tenant_id": tenant_id} for _ in range(count)]
        )
    return {"seeded": count}


def purge(tenant: str, schema: str, participant: str) -> dict[str, object]:
    from saas_os.core.authority import SystemAuthority, SystemCaller  # noqa: PLC0415
    from saas_os.core.tenancy import purge_tenant, register_purge_participant  # noqa: PLC0415

    from crm_app.purge import CrmDataPurgeParticipant  # noqa: PLC0415

    _probe_table(schema)
    if participant == "failing":
        register_purge_participant(FailingParticipant())
    elif participant == "unmapped":
        register_purge_participant(
            CrmDataPurgeParticipant(("not_mapped",), schema=schema, name=PROBE_PARTICIPANT)
        )
    else:
        register_purge_participant(
            CrmDataPurgeParticipant((PROBE_TABLE,), schema=schema, name=PROBE_PARTICIPANT)
        )
    try:
        result = purge_tenant(uuid.UUID(tenant), caller=SystemCaller(SystemAuthority.TENANT_PURGE))
    except Exception as exc:  # noqa: BLE001 - the test asserts on the type only
        return {"error": type(exc).__name__}
    return {
        "already_purged": result.already_purged,
        "participant_names": list(result.participant_names),
    }


def main(argv: list[str]) -> None:
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("purge_probe runs only with ENVIRONMENT=test")
    # For its table definitions: `core.audit_log` has foreign keys onto RBAC
    # tables, so audit writes in a fresh process need them loaded (the
    # operator command does the same).
    import saas_os.core.rbac  # noqa: F401, PLC0415

    command, *args = argv
    if command == "deleted":
        result: object = deleted()
    elif command == "active":
        result = active()
    elif command == "probe-table":
        result = probe_table(args[0])
    elif command == "seed":
        result = seed(args[0], args[1], int(args[2]))
    elif command == "purge":
        result = purge(args[0], args[1], args[2])
    else:
        raise SystemExit(f"unknown command {command!r}")
    print("RESULT " + json.dumps(result))


if __name__ == "__main__":
    main(sys.argv[1:])
