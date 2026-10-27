"""The workspace's sales pipeline and its stages (decision P4, slice 4A).

Every role reads the pipeline; changing it needs `crm_app.pipeline:manage`
(Owner, Admin), which the routes enforce. The product offers one pipeline
per workspace (P4 4A.1): the default one is created the first time the
workspace's pipelines are read, under SaaS-OS's tenant advisory lock, so
concurrent first reads create it once (P4 4A.2). Creating it is not a user
action and has no audit entry.

The pipeline's `version` covers its whole configuration (P4 4A.5): every
change names the version it was made from, takes a row lock on the
pipeline, bumps the version and records its audit entry in the same
locked, workspace-scoped transaction. Audit entries name IDs and changed
field names, never names (P4 4A.7).

Stage positions are always 0..n-1. Removing a stage renumbers the rest;
the last stage cannot be removed (P4 4A.6).

SaaS-OS resolves configuration at import time; only code that runs after
validation imports this module.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any

from saas_os.core.audit_log import record_in_transaction
from saas_os.core.authority import UserCaller
from saas_os.core.tenancy import TenantClosedError, TenantNotFoundError, lock_open_tenant
from saas_os.infra.db import (
    IntegrityError,
    OperationalError,
    Session,
    acquire_tenant_advisory_lock,
    is_transaction_conflict,
    select,
    tenant_session_scope,
)

from crm_app.domains import pipelines as rules
from crm_app.models import Pipeline, PipelineStage
from crm_app.records import (
    ConstraintViolationError,
    RecordError,
    RecordNotFoundError,
    Scope,
    StaleVersionError,
    TransactionConflictError,
)

RESOURCE = "crm_app.pipeline"
_STAGE_NAME_KEY = "pipeline_stage_name_key"
_PIPELINE_NAME_KEY = "pipeline_name_key"


class PipelineNotFoundError(RecordError):
    status, code = 404, "pipeline_not_found"


class StageNotFoundError(RecordError):
    status, code = 404, "stage_not_found"


class DuplicateStageError(RecordError):
    status, code = 409, "duplicate_stage"


class DuplicatePipelineError(RecordError):
    status, code = 409, "duplicate_pipeline"


class StageLimitError(RecordError):
    status, code = 409, "stage_limit_reached"


class LastStageError(RecordError):
    status, code = 409, "last_stage"


class InvalidStageOrderError(RecordError):
    status, code = 422, "invalid_stage_order"


Described = dict[str, Any]


def _now() -> datetime:
    return datetime.now(UTC)


def _stages(session: Session, scope: Scope, pipeline_id: uuid.UUID) -> list[PipelineStage]:
    return list(
        session.execute(
            select(PipelineStage)
            .where(
                PipelineStage.tenant_id == scope.workspace,
                PipelineStage.pipeline_id == pipeline_id,
            )
            .order_by(PipelineStage.position, PipelineStage.id)
        ).scalars()
    )


def _out(pipeline: Pipeline, stages: Sequence[PipelineStage]) -> Described:
    return {
        "id": pipeline.id,
        "name": pipeline.name,
        "version": pipeline.version,
        "created_at": pipeline.created_at,
        "updated_at": pipeline.updated_at,
        "stages": [
            {
                "id": stage.id,
                "name": stage.name,
                "probability": stage.probability,
                "position": stage.position,
            }
            for stage in stages
        ],
    }


def _audit(
    session: Session, scope: Scope, verb: str, pipeline_id: uuid.UUID, **metadata: Any
) -> None:
    record_in_transaction(
        session,
        caller=UserCaller(scope.actor),
        tenant_id=scope.workspace,
        action=f"{RESOURCE}.{verb}",
        resource_type=RESOURCE,
        resource_id=str(pipeline_id),
        metadata=metadata,
    )


def _transaction[T](scope: Scope, fn: Callable[[Session], T]) -> T:
    """Run `fn` in one locked, workspace-scoped transaction. A name clash the
    pre-check missed becomes the matching refusal; no other database refusal
    surfaces as the driver error."""
    try:
        with tenant_session_scope(scope.workspace) as session:
            lock_open_tenant(session, scope.workspace)
            return fn(session)
    except (TenantClosedError, TenantNotFoundError):
        raise RecordNotFoundError from None
    except IntegrityError as exc:
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        if constraint == _STAGE_NAME_KEY:
            raise DuplicateStageError from None
        if constraint == _PIPELINE_NAME_KEY:
            raise DuplicatePipelineError from None
        raise ConstraintViolationError from None
    except OperationalError as exc:
        if is_transaction_conflict(exc):
            raise TransactionConflictError from None
        raise


# --- Reads ------------------------------------------------------------------------


def _pipelines(session: Session, scope: Scope) -> list[Pipeline]:
    return list(
        session.execute(
            select(Pipeline)
            .where(Pipeline.tenant_id == scope.workspace)
            .order_by(Pipeline.created_at, Pipeline.id)
        ).scalars()
    )


def _create_default(session: Session, scope: Scope) -> None:
    now = _now()
    pipeline = Pipeline(
        id=uuid.uuid4(),
        tenant_id=scope.workspace,
        name=rules.DEFAULT_PIPELINE_NAME,
        created_at=now,
        updated_at=now,
        version=1,
    )
    session.add(pipeline)
    session.flush()
    for position, (name, probability) in enumerate(rules.DEFAULT_STAGES):
        session.add(
            PipelineStage(
                id=uuid.uuid4(),
                tenant_id=scope.workspace,
                pipeline_id=pipeline.id,
                name=name,
                probability=probability,
                position=position,
                created_at=now,
                updated_at=now,
            )
        )
    session.flush()


def list_pipelines(scope: Scope) -> list[Described]:
    """The workspace's pipelines with their stages in order, creating the
    default pipeline if the workspace has none yet (P4 4A.2)."""
    with tenant_session_scope(scope.workspace) as session:
        found = _pipelines(session, scope)
        if found:
            return [_out(p, _stages(session, scope, p.id)) for p in found]

    def ensure(session: Session) -> list[Described]:
        acquire_tenant_advisory_lock(session, scope.workspace, f"{RESOURCE}.default")
        if not _pipelines(session, scope):
            _create_default(session, scope)
        return [_out(p, _stages(session, scope, p.id)) for p in _pipelines(session, scope)]

    return _transaction(scope, ensure)


# --- Changes ----------------------------------------------------------------------


def _locked(session: Session, scope: Scope, pipeline_id: uuid.UUID, expected: int) -> Pipeline:
    pipeline = session.execute(
        select(Pipeline)
        .where(Pipeline.tenant_id == scope.workspace, Pipeline.id == pipeline_id)
        .with_for_update()
    ).scalar_one_or_none()
    if pipeline is None:
        raise PipelineNotFoundError
    if pipeline.version != expected:
        raise StaleVersionError(pipeline.version)
    return pipeline


def _bump(pipeline: Pipeline, scope: Scope, now: datetime) -> None:
    pipeline.version += 1
    pipeline.updated_at = now
    pipeline.updated_by_user_id = scope.actor


def _stage(stages: Sequence[PipelineStage], stage_id: uuid.UUID) -> PipelineStage:
    found = next((stage for stage in stages if stage.id == stage_id), None)
    if found is None:
        raise StageNotFoundError
    return found


def _name_taken(
    stages: Sequence[PipelineStage], name: str, *, other_than: uuid.UUID | None = None
) -> bool:
    lowered = name.lower()
    return any(s.name.lower() == lowered and s.id != other_than for s in stages)


def rename_pipeline(
    scope: Scope, pipeline_id: uuid.UUID, name: str, *, expected_version: int
) -> Described:
    """Rename the pipeline. The same name is a no-op: no new version, no
    audit entry."""

    def apply(session: Session) -> Described:
        pipeline = _locked(session, scope, pipeline_id, expected_version)
        stages = _stages(session, scope, pipeline.id)
        if pipeline.name != name:
            pipeline.name = name
            _bump(pipeline, scope, _now())
            session.flush()
            _audit(session, scope, "updated", pipeline.id, fields=["name"])
        return _out(pipeline, stages)

    return _transaction(scope, apply)


def add_stage(
    scope: Scope,
    pipeline_id: uuid.UUID,
    name: str,
    probability: int,
    *,
    expected_version: int,
) -> Described:
    """Add a stage at the end."""

    def apply(session: Session) -> Described:
        pipeline = _locked(session, scope, pipeline_id, expected_version)
        stages = _stages(session, scope, pipeline.id)
        if _name_taken(stages, name):
            raise DuplicateStageError
        if len(stages) >= rules.MAX_STAGES:
            raise StageLimitError
        now = _now()
        stage = PipelineStage(
            id=uuid.uuid4(),
            tenant_id=scope.workspace,
            pipeline_id=pipeline.id,
            name=name,
            probability=probability,
            position=len(stages),
            created_by_user_id=scope.actor,
            updated_by_user_id=scope.actor,
            created_at=now,
            updated_at=now,
        )
        session.add(stage)
        _bump(pipeline, scope, now)
        session.flush()
        _audit(session, scope, "stage_created", pipeline.id, stage_id=str(stage.id))
        return _out(pipeline, [*stages, stage])

    return _transaction(scope, apply)


def update_stage(
    scope: Scope,
    pipeline_id: uuid.UUID,
    stage_id: uuid.UUID,
    changes: dict[str, Any],
    *,
    expected_version: int,
) -> Described:
    """Change a stage's `name` and/or `probability` (already normalised).
    Values equal to the stored ones are no change; no change at all is a
    no-op."""

    def apply(session: Session) -> Described:
        pipeline = _locked(session, scope, pipeline_id, expected_version)
        stages = _stages(session, scope, pipeline.id)
        stage = _stage(stages, stage_id)
        changed = sorted(key for key, value in changes.items() if getattr(stage, key) != value)
        if not changed:
            return _out(pipeline, stages)
        if "name" in changed and _name_taken(stages, changes["name"], other_than=stage.id):
            raise DuplicateStageError
        now = _now()
        for key in changed:
            setattr(stage, key, changes[key])
        stage.updated_at = now
        stage.updated_by_user_id = scope.actor
        _bump(pipeline, scope, now)
        session.flush()
        _audit(session, scope, "stage_updated", pipeline.id, stage_id=str(stage.id), fields=changed)
        return _out(pipeline, stages)

    return _transaction(scope, apply)


def reorder_stages(
    scope: Scope,
    pipeline_id: uuid.UUID,
    stage_ids: Sequence[uuid.UUID],
    *,
    expected_version: int,
) -> Described:
    """Put the stages in the order of `stage_ids`, which must name every
    stage of the pipeline exactly once. The same order is a no-op."""

    def apply(session: Session) -> Described:
        pipeline = _locked(session, scope, pipeline_id, expected_version)
        stages = _stages(session, scope, pipeline.id)
        if len(stage_ids) != len(stages) or set(stage_ids) != {s.id for s in stages}:
            raise InvalidStageOrderError
        if [s.id for s in stages] == list(stage_ids):
            return _out(pipeline, stages)
        by_id = {s.id: s for s in stages}
        now = _now()
        ordered = [by_id[stage_id] for stage_id in stage_ids]
        for position, stage in enumerate(ordered):
            if stage.position != position:
                stage.position = position
                stage.updated_at = now
                stage.updated_by_user_id = scope.actor
        _bump(pipeline, scope, now)
        session.flush()
        _audit(session, scope, "stages_reordered", pipeline.id)
        return _out(pipeline, ordered)

    return _transaction(scope, apply)


def delete_stage(
    scope: Scope, pipeline_id: uuid.UUID, stage_id: uuid.UUID, *, expected_version: int
) -> Described:
    """Remove a stage and renumber the rest. The last stage stays."""

    def apply(session: Session) -> Described:
        pipeline = _locked(session, scope, pipeline_id, expected_version)
        stages = _stages(session, scope, pipeline.id)
        stage = _stage(stages, stage_id)
        if len(stages) == 1:
            raise LastStageError
        session.delete(stage)
        session.flush()
        now = _now()
        remaining = [s for s in stages if s.id != stage.id]
        for position, other in enumerate(remaining):
            if other.position != position:
                other.position = position
                other.updated_at = now
                other.updated_by_user_id = scope.actor
        _bump(pipeline, scope, now)
        session.flush()
        _audit(session, scope, "stage_deleted", pipeline.id, stage_id=str(stage_id))
        return _out(pipeline, remaining)

    return _transaction(scope, apply)
