"""What happens to this product's data when a workspace is purged.

SaaS-OS's `purge_tenant()` deletes Core's data, then runs every purge
participant registered in the same process while the tenant is locked in
`PURGING` (SaaS-OS CONSUMER-GUIDE §11). This module is the product's one
participant, `crm_app.crm_data`, registered through the public API in
`saas_os.core.tenancy` (SaaS-OS v0.5.0, decision K3.2).

The registry is per process. The supported purge entry points are the
operator command and a direct `purge_tenant()` call; no route and no worker
job purges a tenant. So:

- the operator command registers through
  `saas-os-operator purge-tenant --setup crm_app.purge:register_purge_participants`;
- `create_app()` also registers, as the SaaS-OS scaffold does, so a direct
  call made from an application process is covered too;
- any other code that calls `purge_tenant()` must call
  `register_purge_participants()` first.

`PURGE_TABLES` is the manifest: every tenant-owned table in the `crm_app`
schema, in deletion order (children before parents). The integration guard
(`tests/integration/test_tenant_table_guard.py`) fails if a tenant-owned
table is missing from it, so a new table cannot ship without being purged.

The participant imports `crm_app.models` itself before resolving the
manifest, so a process that never built the application (the installed
operator command) still knows the product's tables.

SaaS-OS resolves configuration at import time, so this module imports
SaaS-OS (and `crm_app.models`) only inside its functions.
"""

from __future__ import annotations

import re
import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

    from saas_os.infra.db import Session

PARTICIPANT_NAME = "crm_app.crm_data"
EXPECTED_PURGE_PARTICIPANTS: tuple[str, ...] = (PARTICIPANT_NAME,)

SCHEMA = "crm_app"
# Children before parents: `activity` references `note`, `contact` and
# `company`; `note` references both records; `contact_tag` and
# `company_tag` reference their record and `tag`; `contact` references
# `company`; the form tables reference `contact`, `tag` and each other.
# `workspace_settings` and `invitation_intent` reference no
# product table.
PURGE_TABLES: tuple[str, ...] = (
    "consent_record",
    "form_submission",
    "form",
    "activity",
    "note",
    "import_row",
    "import_job",
    "contact_tag",
    "company_tag",
    "task",
    "opportunity_event",
    "opportunity",
    "contact",
    "company",
    "tag",
    "custom_field_definition",
    "pipeline_stage",
    "pipeline",
    "workspace_settings",
    "invitation_intent",
)

_IDENTIFIER = re.compile(r"[a-z_][a-z0-9_]*")


# Global tables that name a workspace without a tenant_id or a foreign key
# (a key into core.tenants would block the purge): the participant removes
# their rows for the purged workspace after the tenant tables, outside any
# tenant context, because their RLS hides them from every tenant
# transaction (migration 0006, `SIGNUP-PLAN.md` §4b).
# `import_expiry` (migration 0009) only schedules the deletion of import
# rows; it holds no personal data, and its rows go with the workspace.
PURGE_GLOBAL_REFERENCES: tuple[str, ...] = ("signup", "import_expiry")


def _forget_signups(tenant_id: uuid.UUID) -> None:
    from crm_app import signups  # noqa: PLC0415

    signups.forget_workspace(tenant_id)
    if signups.remaining_for_workspace(tenant_id):
        raise PurgeIncompleteError("Rows remain in: signup")


def _forget_import_expiry(tenant_id: uuid.UUID) -> None:
    from saas_os.infra.db import delete, select, session_scope  # noqa: PLC0415

    from crm_app.models import ImportExpiry  # noqa: PLC0415

    with session_scope() as session:
        session.execute(delete(ImportExpiry).where(ImportExpiry.workspace_id == tenant_id))
    with session_scope() as session:
        left = session.execute(
            select(ImportExpiry.import_id).where(ImportExpiry.workspace_id == tenant_id).limit(1)
        ).first()
    if left is not None:
        raise PurgeIncompleteError("Rows remain in: import_expiry")


class PurgeIncompleteError(RuntimeError):
    """Rows of the purged workspace are still present after deletion. SaaS-OS
    records only this type name (`participant_error`) and leaves the
    workspace in `PURGING`, so a re-run retries."""


class PurgeRegistrationError(RuntimeError):
    """The participants registered in this process are not exactly the ones
    this product needs; purging now would leave product rows behind."""


class CrmDataPurgeParticipant:
    """Deletes one workspace's rows from every table in its manifest.

    Every statement runs in one `tenant_session_scope(tenant_id)`
    transaction, so forced Row-Level Security confines it to the purged
    workspace; the explicit `tenant_id` predicate is defence in depth. After
    deleting, it re-reads every table and raises if a row remains. Then,
    for each table in `global_references`, it removes the rows naming the
    workspace in transactions without a tenant (`PURGE_GLOBAL_REFERENCES`)
    and checks none remain. Idempotent: a re-run finds nothing and succeeds.
    """

    def __init__(
        self,
        tables: Sequence[str] = PURGE_TABLES,
        *,
        schema: str = SCHEMA,
        name: str = PARTICIPANT_NAME,
        global_references: Sequence[str] = (),
    ) -> None:
        for identifier in (schema, *tables):
            if not _IDENTIFIER.fullmatch(identifier):
                raise ValueError(f"Not a plain SQL identifier: {identifier!r}")
        unknown = set(global_references) - set(PURGE_GLOBAL_REFERENCES)
        if unknown:
            raise ValueError(f"No purge step for global table(s): {sorted(unknown)}")
        self._tables = tuple(tables)
        self._schema = schema
        self._name = name
        self._global_references = tuple(global_references)

    @property
    def name(self) -> str:
        return self._name

    @property
    def tables(self) -> tuple[str, ...]:
        return self._tables

    def purge_tenant_data(self, tenant_id: uuid.UUID) -> None:
        if not self._tables:
            return
        from saas_os.infra.db import tenant_session_scope  # noqa: PLC0415

        with tenant_session_scope(tenant_id) as session:
            for table in self._tables:
                self._delete(session, table, tenant_id)
            remaining = [t for t in self._tables if self._has_rows(session, t, tenant_id)]
            if remaining:
                raise PurgeIncompleteError(f"Rows remain in: {', '.join(remaining)}")
        if "signup" in self._global_references:
            _forget_signups(tenant_id)
        if "import_expiry" in self._global_references:
            _forget_import_expiry(tenant_id)

    def _table(self, table: str) -> Any:  # a SQLAlchemy Table; typed loosely to keep SQLAlchemy out
        from saas_os.infra.db import Base  # noqa: PLC0415

        import crm_app.models  # noqa: F401, PLC0415 - registers the product tables

        key = f"{self._schema}.{table}"
        if key not in Base.metadata.tables:
            # Fail closed: a manifest entry with no mapped table is never skipped.
            raise PurgeIncompleteError(f"No mapped table {key}")
        return Base.metadata.tables[key]

    def _delete(self, session: Session, table: str, tenant_id: uuid.UUID) -> None:
        from saas_os.infra.db import delete  # noqa: PLC0415

        mapped = self._table(table)
        session.execute(delete(mapped).where(mapped.c.tenant_id == tenant_id))

    def _has_rows(self, session: Session, table: str, tenant_id: uuid.UUID) -> bool:
        from saas_os.infra.db import select  # noqa: PLC0415

        mapped = self._table(table)
        query = select(mapped.c.tenant_id).where(mapped.c.tenant_id == tenant_id).limit(1)
        return session.execute(query).first() is not None


# One instance per process: registering the same object again is a no-op,
# a new instance under the same name is refused.
CRM_DATA_PURGE_PARTICIPANT = CrmDataPurgeParticipant(global_references=PURGE_GLOBAL_REFERENCES)


def register_purge_participants() -> None:
    """Register every purge participant this product needs in this process,
    then refuse unless exactly those are registered."""
    from saas_os.core.tenancy import (  # noqa: PLC0415
        register_purge_participant,
        registered_purge_participant_names,
    )

    register_purge_participant(CRM_DATA_PURGE_PARTICIPANT)
    registered = registered_purge_participant_names()
    if registered != EXPECTED_PURGE_PARTICIPANTS:
        raise PurgeRegistrationError(
            f"Expected purge participants {EXPECTED_PURGE_PARTICIPANTS}, found {registered}."
        )
