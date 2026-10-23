"""Mappings of this product's tables (`PHASE3-PLAN.md` §19.2).

Migration `0002_contacts_companies` owns the schema: the constraints, the
partial unique indexes and the Row-Level Security policies live there, and
these classes never create tables. They declare the columns the services
read and write, and register both tables in SaaS-OS's shared metadata, which
`crm_app.purge` resolves its manifest against.

The foreign key into `core.tenants` exists in the database only: declaring it
here would make every flush depend on Core's own table definitions being
imported first.

SaaS-OS resolves configuration at import time, so only code that already
runs after validation imports this module (the services and
`crm_app.purge`'s participant).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from saas_os.infra.db import (
    Base,
    DateTime,
    ForeignKeyConstraint,
    Integer,
    Mapped,
    Text,
    mapped_column,
)

SCHEMA = "crm_app"


class _Record:
    """Columns every tenant-owned record has (`PHASE3-PLAN.md` §19.2)."""

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column()
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column()
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column()
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Company(_Record, Base):
    __tablename__ = "company"
    __table_args__ = ({"schema": SCHEMA},)

    name: Mapped[str] = mapped_column(Text)
    domain: Mapped[str | None] = mapped_column(Text)
    website: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)
    industry: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(Text)
    country_code: Mapped[str | None] = mapped_column(Text)


class Contact(_Record, Base):
    __tablename__ = "contact"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            [f"{SCHEMA}.company.tenant_id", f"{SCHEMA}.company.id"],
            name="contact_company_fkey",
        ),
        {"schema": SCHEMA},
    )

    first_name: Mapped[str] = mapped_column(Text)
    last_name: Mapped[str | None] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)
    job_title: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(Text)
    lifecycle_stage: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)
    company_id: Mapped[uuid.UUID | None] = mapped_column()
