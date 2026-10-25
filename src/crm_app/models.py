"""Mappings of this product's tables (`PHASE3-PLAN.md` §19.2, §21).

Migrations `0002_contacts_companies` to `0006_signup` own the
schema: the constraints, the partial
unique indexes, the grants and the Row-Level Security policies live there,
and these classes never create tables. They declare the columns the
services read and write, and register every table in SaaS-OS's shared
metadata, which `crm_app.purge` resolves its manifest against.

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
    JSON,
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


def _parent_keys(table: str) -> tuple[ForeignKeyConstraint, ForeignKeyConstraint]:
    """A note or activity entry belongs to exactly one contact or company."""
    return (
        ForeignKeyConstraint(
            ["tenant_id", "contact_id"],
            [f"{SCHEMA}.contact.tenant_id", f"{SCHEMA}.contact.id"],
            name=f"{table}_contact_fkey",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "company_id"],
            [f"{SCHEMA}.company.tenant_id", f"{SCHEMA}.company.id"],
            name=f"{table}_company_fkey",
            ondelete="CASCADE",
        ),
    )


class Note(Base):
    """A plain-text note on one contact or company (decision P3-B)."""

    __tablename__ = "note"
    __table_args__ = (*_parent_keys("note"), {"schema": SCHEMA})

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column()
    contact_id: Mapped[uuid.UUID | None] = mapped_column()
    company_id: Mapped[uuid.UUID | None] = mapped_column()
    body: Mapped[str] = mapped_column(Text)
    author_user_id: Mapped[uuid.UUID] = mapped_column()
    updated_by_user_id: Mapped[uuid.UUID] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer)


class Activity(Base):
    """One entry of a record's history. The application only inserts these:
    the runtime role holds no UPDATE on the table (decision P3-B D6)."""

    __tablename__ = "activity"
    __table_args__ = (
        *_parent_keys("activity"),
        ForeignKeyConstraint(
            ["tenant_id", "note_id"],
            [f"{SCHEMA}.note.tenant_id", f"{SCHEMA}.note.id"],
            name="activity_note_fkey",
            ondelete="CASCADE",
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column()
    contact_id: Mapped[uuid.UUID | None] = mapped_column()
    company_id: Mapped[uuid.UUID | None] = mapped_column()
    kind: Mapped[str] = mapped_column(Text)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column()
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Field names only (an allow-list in migration 0003), never values.
    fields: Mapped[list[str] | None] = mapped_column(JSON)
    stage_from: Mapped[str | None] = mapped_column(Text)
    stage_to: Mapped[str | None] = mapped_column(Text)
    owner_from: Mapped[uuid.UUID | None] = mapped_column()
    owner_to: Mapped[uuid.UUID | None] = mapped_column()
    company_ref_id: Mapped[uuid.UUID | None] = mapped_column()
    note_id: Mapped[uuid.UUID | None] = mapped_column()


class WorkspaceSettings(Base):
    """A workspace's locale, time zone and default currency (migration
    0004, decision P2-F 1). No row means the product defaults."""

    __tablename__ = "workspace_settings"
    __table_args__ = ({"schema": SCHEMA},)

    tenant_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    locale: Mapped[str] = mapped_column(Text)
    time_zone: Mapped[str] = mapped_column(Text)
    currency: Mapped[str] = mapped_column(Text)
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer)


class InvitationIntent(Base):
    """The role an invitation is for and how its link was delivered
    (migration 0005, decisions Q4, Q5, P2-F 1). No token, link or email."""

    __tablename__ = "invitation_intent"
    __table_args__ = ({"schema": SCHEMA},)

    tenant_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    invitation_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    role: Mapped[str] = mapped_column(Text)
    invited_by_user_id: Mapped[uuid.UUID] = mapped_column()
    delivery: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Signup(Base):
    """One person's request to create a workspace, while it is provisioned
    (migration 0006, decision S-1). A pre-tenant global table: forced RLS
    limits every row to the person in `crm_app.signup_user_id`
    (`crm_app.signups`). No email, password or token."""

    __tablename__ = "signup"
    __table_args__ = ({"schema": SCHEMA},)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column()
    idempotency_key: Mapped[str] = mapped_column(Text)
    request_fingerprint: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(Text)
    step: Mapped[str] = mapped_column(Text)
    workspace_name: Mapped[str | None] = mapped_column(Text)
    workspace_id: Mapped[uuid.UUID | None] = mapped_column()
    step_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer)
    last_error_code: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
