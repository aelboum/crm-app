"""Mappings of this product's tables (`PHASE3-PLAN.md` §19.2, §21).

Migrations `0002_contacts_companies` to `0015_business_hours` own the
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
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from saas_os.infra.db import (
    JSON,
    Base,
    Boolean,
    DateTime,
    ForeignKeyConstraint,
    Integer,
    Mapped,
    Numeric,
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
    # Values of the workspace's custom fields, `{key: value}` (migration 0008,
    # decision P3-D); validated by `crm_app.custom_fields`.
    custom_fields: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


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


class Tag(Base):
    """A tag of the workspace's vocabulary (migration 0007, decision P3-C).
    Names are unique per workspace regardless of case."""

    __tablename__ = "tag"
    __table_args__ = ({"schema": SCHEMA},)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column()
    name: Mapped[str] = mapped_column(Text)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column()
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer)


def _tag_keys(table: str, parent: str) -> tuple[ForeignKeyConstraint, ForeignKeyConstraint]:
    """A tag assignment joins a record and a tag of the same workspace."""
    return (
        ForeignKeyConstraint(
            ["tenant_id", f"{parent}_id"],
            [f"{SCHEMA}.{parent}.tenant_id", f"{SCHEMA}.{parent}.id"],
            name=f"{table}_{parent}_fkey",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "tag_id"],
            [f"{SCHEMA}.tag.tenant_id", f"{SCHEMA}.tag.id"],
            name=f"{table}_tag_fkey",
            ondelete="CASCADE",
        ),
    )


class ContactTag(Base):
    """A tag on a contact."""

    __tablename__ = "contact_tag"
    __table_args__ = (*_tag_keys("contact_tag", "contact"), {"schema": SCHEMA})

    tenant_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    contact_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tag_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CompanyTag(Base):
    """A tag on a company."""

    __tablename__ = "company_tag"
    __table_args__ = (*_tag_keys("company_tag", "company"), {"schema": SCHEMA})

    tenant_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    company_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tag_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CustomFieldDefinition(Base):
    """A custom field of contacts or companies (migration 0008, decision
    P3-D). The key and type never change; archiving hides the field."""

    __tablename__ = "custom_field_definition"
    __table_args__ = ({"schema": SCHEMA},)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column()
    entity: Mapped[str] = mapped_column(Text)
    key: Mapped[str] = mapped_column(Text)
    label: Mapped[str] = mapped_column(Text)
    field_type: Mapped[str] = mapped_column(Text)
    # SQL NULL, not JSON null, for a field that is not a select.
    options: Mapped[list[str] | None] = mapped_column(JSON(none_as_null=True))
    position: Mapped[int] = mapped_column(Integer)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column()
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ImportJob(Base):
    """One CSV import of contacts or companies (migration 0009, decision
    P3-F): status, counts, the mapping by column position, the checkpoint.
    No cell value."""

    __tablename__ = "import_job"
    __table_args__ = ({"schema": SCHEMA},)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column()
    entity: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    mapping: Mapped[dict[str, int]] = mapped_column(JSON)
    total_rows: Mapped[int] = mapped_column(Integer, default=0)
    valid_rows: Mapped[int] = mapped_column(Integer, default=0)
    invalid_rows: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_rows: Mapped[int] = mapped_column(Integer, default=0)
    created_rows: Mapped[int] = mapped_column(Integer, default=0)
    skipped_rows: Mapped[int] = mapped_column(Integer, default=0)
    failed_rows: Mapped[int] = mapped_column(Integer, default=0)
    checkpoint: Mapped[int] = mapped_column(Integer, default=0)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=1)


class ImportRow(Base):
    """One data row of an import: normalised values or error codes, and the
    record it created. Personal data; deleted after 7 days (P3-F 7)."""

    __tablename__ = "import_row"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "import_id"],
            [f"{SCHEMA}.import_job.tenant_id", f"{SCHEMA}.import_job.id"],
            name="import_row_job_fkey",
            ondelete="CASCADE",
        ),
        {"schema": SCHEMA},
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    import_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    row_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[str] = mapped_column(Text)
    # SQL NULL, not JSON null: the table's payload check tells them apart.
    data: Mapped[dict[str, Any] | None] = mapped_column(JSON(none_as_null=True))
    errors: Mapped[list[dict[str, str]] | None] = mapped_column(JSON(none_as_null=True))
    record_id: Mapped[uuid.UUID | None] = mapped_column()


class ImportExpiry(Base):
    """When an import's rows are due for deletion, and in which workspace
    (migration 0009). A global table without personal data; only a
    transaction without a workspace sees it."""

    __tablename__ = "import_expiry"
    __table_args__ = ({"schema": SCHEMA},)

    import_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column()
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class WorkspaceSettings(Base):
    """A workspace's locale, time zone and default currency (migration
    0004, decision P2-F 1) and business hours (migration 0015, decision
    P5-B). No row means the product defaults."""

    __tablename__ = "workspace_settings"
    __table_args__ = ({"schema": SCHEMA},)

    tenant_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    locale: Mapped[str] = mapped_column(Text)
    time_zone: Mapped[str] = mapped_column(Text)
    currency: Mapped[str] = mapped_column(Text)
    # SQL NULL, not JSON null, while the hours are not set (P5-B 3).
    business_hours: Mapped[list[dict[str, str] | None] | None] = mapped_column(
        JSON(none_as_null=True)
    )
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


class Pipeline(Base):
    """A sales pipeline (migration 0010, decision P4). Its version covers
    the whole configuration, stages included."""

    __tablename__ = "pipeline"
    __table_args__ = ({"schema": SCHEMA},)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column()
    name: Mapped[str] = mapped_column(Text)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column()
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer)


class PipelineStage(Base):
    """An open stage of a pipeline (migration 0010, decision P4). Won and
    lost are a deal's outcome, not stages."""

    __tablename__ = "pipeline_stage"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "pipeline_id"],
            [f"{SCHEMA}.pipeline.tenant_id", f"{SCHEMA}.pipeline.id"],
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column()
    pipeline_id: Mapped[uuid.UUID] = mapped_column()
    name: Mapped[str] = mapped_column(Text)
    probability: Mapped[int] = mapped_column(Integer)
    position: Mapped[int] = mapped_column(Integer)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column()
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Opportunity(Base):
    """A deal (migration 0011, decision P4-B). Its stage is a stage of its
    own pipeline; won and lost are its outcome, not stages."""

    __tablename__ = "opportunity"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "pipeline_id", "stage_id"],
            [
                f"{SCHEMA}.pipeline_stage.tenant_id",
                f"{SCHEMA}.pipeline_stage.pipeline_id",
                f"{SCHEMA}.pipeline_stage.id",
            ],
            name="opportunity_stage_fkey",
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column()
    title: Mapped[str] = mapped_column(Text)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(15, 3, asdecimal=True))
    currency: Mapped[str] = mapped_column(Text)
    pipeline_id: Mapped[uuid.UUID] = mapped_column()
    stage_id: Mapped[uuid.UUID] = mapped_column()
    stage_entered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column()
    expected_close_date: Mapped[date | None] = mapped_column()
    contact_id: Mapped[uuid.UUID | None] = mapped_column()
    company_id: Mapped[uuid.UUID | None] = mapped_column()
    outcome: Mapped[str] = mapped_column(Text)
    lost_reason: Mapped[str | None] = mapped_column(Text)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column()
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer)


class OpportunityEvent(Base):
    """One entry of a deal's history. The application only inserts these:
    the runtime role holds no UPDATE on the table (decision P4-B 7). `seq`
    is generated by the database and never written here."""

    __tablename__ = "opportunity_event"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "opportunity_id"],
            [f"{SCHEMA}.opportunity.tenant_id", f"{SCHEMA}.opportunity.id"],
            name="opportunity_event_opportunity_fkey",
            ondelete="CASCADE",
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column()
    opportunity_id: Mapped[uuid.UUID] = mapped_column()
    # An identity the database generates (GENERATED ALWAYS). Declaring a
    # server default makes the ORM leave it out of every INSERT; the value
    # is never used to create the column, which the migration owns.
    seq: Mapped[int | None] = mapped_column(Integer, server_default="0")
    kind: Mapped[str] = mapped_column(Text)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column()
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Field names only (an allow-list in migration 0011), never values.
    fields: Mapped[list[str] | None] = mapped_column(JSON(none_as_null=True))
    stage_from: Mapped[uuid.UUID | None] = mapped_column()
    stage_to: Mapped[uuid.UUID | None] = mapped_column()
    stage_from_name: Mapped[str | None] = mapped_column(Text)
    stage_to_name: Mapped[str | None] = mapped_column(Text)
    stage_cause: Mapped[str | None] = mapped_column(Text)
    owner_from: Mapped[uuid.UUID | None] = mapped_column()
    owner_to: Mapped[uuid.UUID | None] = mapped_column()
    outcome_from: Mapped[str | None] = mapped_column(Text)
    outcome_to: Mapped[str | None] = mapped_column(Text)


class Task(Base):
    """A task (migration 0012, decision P4-C). Done exactly while
    `completed_at` is set; its links to a contact, company or deal are
    cleared, not cascaded, when that record is deleted."""

    __tablename__ = "task"
    __table_args__ = ({"schema": SCHEMA},)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column()
    title: Mapped[str] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(Text)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    assignee_user_id: Mapped[uuid.UUID | None] = mapped_column()
    contact_id: Mapped[uuid.UUID | None] = mapped_column()
    company_id: Mapped[uuid.UUID | None] = mapped_column()
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column()
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_by_user_id: Mapped[uuid.UUID | None] = mapped_column()
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column()
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer)


class Appointment(Base):
    """An appointment (migration 0014, decision P5-A). Cancelled exactly
    while `cancelled_at` is set; its contact link is cleared, not cascaded,
    when the contact is deleted."""

    __tablename__ = "appointment"
    __table_args__ = ({"schema": SCHEMA},)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column()
    title: Mapped[str] = mapped_column(Text)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    kind: Mapped[str] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    host_user_id: Mapped[uuid.UUID] = mapped_column()
    contact_id: Mapped[uuid.UUID | None] = mapped_column()
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by_user_id: Mapped[uuid.UUID | None] = mapped_column()
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column()
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer)


class Form(Base):
    """A lead-capture form (migration 0013, decision P7-A). `fields` is the
    list `crm_app.domains.forms.fields` validates; the public key is random
    and never changes."""

    __tablename__ = "form"
    __table_args__ = ({"schema": SCHEMA},)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column()
    name: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    public_key: Mapped[str] = mapped_column(Text)
    fields: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    tag_id: Mapped[uuid.UUID | None] = mapped_column()
    thank_you: Mapped[str] = mapped_column(Text)
    consent_text: Mapped[str | None] = mapped_column(Text)
    contact_owner_user_id: Mapped[uuid.UUID] = mapped_column()
    submission_count: Mapped[int] = mapped_column(Integer)
    last_submission_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column()
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer)


class FormSubmission(Base):
    """One accepted submission of a form: the answers by field key, and the
    contact it created or matched."""

    __tablename__ = "form_submission"
    __table_args__ = ({"schema": SCHEMA},)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column()
    form_id: Mapped[uuid.UUID] = mapped_column()
    contact_id: Mapped[uuid.UUID | None] = mapped_column()
    answers: Mapped[dict[str, Any]] = mapped_column(JSON)
    outcome: Mapped[str] = mapped_column(Text)
    consent: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ConsentRecord(Base):
    """Evidence that a contact gave consent (decision P7-A 7). The
    application only inserts these: the runtime role holds no UPDATE."""

    __tablename__ = "consent_record"
    __table_args__ = ({"schema": SCHEMA},)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column()
    contact_id: Mapped[uuid.UUID] = mapped_column()
    channel: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    method: Mapped[str] = mapped_column(Text)
    wording: Mapped[str] = mapped_column(Text)
    form_id: Mapped[uuid.UUID | None] = mapped_column()
    submission_id: Mapped[uuid.UUID | None] = mapped_column()
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
