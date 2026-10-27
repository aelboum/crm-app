"""Pipeline and stage routes (decision P4, slice 4A).

    GET    /v1/workspaces/{tenant_id}/pipelines                                   pipeline:read
    PATCH  /v1/workspaces/{tenant_id}/pipelines/{pipeline_id}                     pipeline:manage
    POST   /v1/workspaces/{tenant_id}/pipelines/{pipeline_id}/stages              pipeline:manage
    PATCH  /v1/workspaces/{tenant_id}/pipelines/{pipeline_id}/stages/{stage_id}   pipeline:manage
    DELETE /v1/workspaces/{tenant_id}/pipelines/{pipeline_id}/stages/{stage_id}   pipeline:manage
           ?move_to={stage_id} moves the stage's deals first (P4-B 8)
    PUT    /v1/workspaces/{tenant_id}/pipelines/{pipeline_id}/stage-order         pipeline:manage

Each declares exactly one `require_permission` from the existing catalogue
(`crm_app.pipeline`, read or manage; P4 4A.4). The path's `tenant_id` is
only the request; handlers use `context.tenant_id` alone, and a pipeline
or stage of another workspace is the same 404 as an unknown one.

Every change needs `If-Match: <pipeline version>` and answers with the
whole pipeline at its new version, so a client never holds a stale
configuration (P4 4A.5). Bodies forbid unknown fields; names are
normalised once (`crm_app.domains.pipelines`) and never echoed in an
error; probabilities are strict integers.
"""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from saas_os.api.context import RequestContext
from saas_os.api.dependencies import require_permission

from crm_app import pipelines
from crm_app.api.records import IfMatch, _http, _version
from crm_app.domains import pipelines as rules
from crm_app.records import RecordError, Scope

router = APIRouter(prefix="/v1/workspaces", tags=["pipelines"])

# A ceiling before trimming, so oversized input is refused early.
_RAW_MAX = 4 * rules.PIPELINE_NAME_MAX

Read = Annotated[RequestContext, Depends(require_permission("crm_app.pipeline", "read"))]
Manage = Annotated[RequestContext, Depends(require_permission("crm_app.pipeline", "manage"))]
Probability = Annotated[int, Field(strict=True, ge=0, le=100)]


class PipelineIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=_RAW_MAX)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return rules.pipeline_name(value)


class StageIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=_RAW_MAX)
    probability: Probability

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return rules.stage_name(value)


class StagePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=_RAW_MAX)
    probability: Probability | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, value: str | None) -> str | None:
        return None if value is None else rules.stage_name(value)

    @model_validator(mode="after")
    def _something(self) -> "StagePatch":
        if self.name is None and self.probability is None:
            raise ValueError("name or probability is required")
        return self


class StageOrderIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage_ids: list[uuid.UUID] = Field(min_length=1, max_length=rules.MAX_STAGES)


class StageOut(BaseModel):
    id: uuid.UUID
    name: str
    probability: int
    position: int


class PipelineOut(BaseModel):
    id: uuid.UUID
    name: str
    version: int
    created_at: datetime
    updated_at: datetime
    stages: list[StageOut]


class PipelineList(BaseModel):
    items: list[PipelineOut]
    max_stages: int


def _scope(context: RequestContext) -> Scope:
    return Scope(workspace=context.tenant_id, actor=context.actor_id)


class StageRef(BaseModel):
    """A stage named by the path: its pipeline and its own ID."""

    pipeline_id: uuid.UUID
    stage_id: uuid.UUID


def _stage_ref(pipeline_id: uuid.UUID, stage_id: uuid.UUID) -> StageRef:
    return StageRef(pipeline_id=pipeline_id, stage_id=stage_id)


Stage = Annotated[StageRef, Depends(_stage_ref)]


def _answer(response: Response, pipeline: dict[str, Any]) -> dict[str, Any]:
    response.headers["ETag"] = f'"{pipeline["version"]}"'
    return pipeline


_PIPELINES = "/{tenant_id}/pipelines"
_PIPELINE = f"{_PIPELINES}/{{pipeline_id}}"
_STAGES = f"{_PIPELINE}/stages"
_STAGE = f"{_STAGES}/{{stage_id}}"


@router.get(_PIPELINES, response_model=PipelineList, name="list_pipelines")
def list_pipelines(context: Read) -> Any:
    try:
        items = pipelines.list_pipelines(_scope(context))
    except RecordError as exc:
        raise _http(exc) from None
    return {"items": items, "max_stages": rules.MAX_STAGES}


@router.patch(_PIPELINE, response_model=PipelineOut, name="rename_pipeline")
def rename_pipeline(
    pipeline_id: uuid.UUID,
    body: PipelineIn,
    context: Manage,
    response: Response,
    if_match: IfMatch = None,
) -> Any:
    expected = _version(if_match)
    try:
        pipeline = pipelines.rename_pipeline(
            _scope(context), pipeline_id, body.name, expected_version=expected
        )
    except RecordError as exc:
        raise _http(exc) from None
    return _answer(response, pipeline)


@router.post(_STAGES, status_code=201, response_model=PipelineOut, name="add_stage")
def add_stage(
    pipeline_id: uuid.UUID,
    body: StageIn,
    context: Manage,
    response: Response,
    if_match: IfMatch = None,
) -> Any:
    expected = _version(if_match)
    try:
        pipeline = pipelines.add_stage(
            _scope(context), pipeline_id, body.name, body.probability, expected_version=expected
        )
    except RecordError as exc:
        raise _http(exc) from None
    return _answer(response, pipeline)


@router.patch(_STAGE, response_model=PipelineOut, name="update_stage")
def update_stage(
    stage: Stage,
    body: StagePatch,
    context: Manage,
    response: Response,
    if_match: IfMatch = None,
) -> Any:
    expected = _version(if_match)
    changes = body.model_dump(exclude_none=True)
    try:
        pipeline = pipelines.update_stage(
            _scope(context),
            stage.pipeline_id,
            stage.stage_id,
            changes,
            expected_version=expected,
        )
    except RecordError as exc:
        raise _http(exc) from None
    return _answer(response, pipeline)


@router.delete(_STAGE, response_model=PipelineOut, name="delete_stage")
def delete_stage(
    stage: Stage,
    context: Manage,
    response: Response,
    if_match: IfMatch = None,
    move_to: Annotated[uuid.UUID | None, Query()] = None,
) -> Any:
    """`move_to` names the stage that receives the removed stage's deals
    (P4-B 8); without it, a stage holding deals is refused with
    `stage_in_use` and the number of deals."""
    expected = _version(if_match)
    try:
        pipeline = pipelines.delete_stage(
            _scope(context),
            stage.pipeline_id,
            stage.stage_id,
            expected_version=expected,
            move_to=move_to,
        )
    except pipelines.StageInUseError as exc:
        raise HTTPException(409, detail={"code": exc.code, "deals": exc.deals}) from None
    except RecordError as exc:
        raise _http(exc) from None
    return _answer(response, pipeline)


@router.put(f"{_PIPELINE}/stage-order", response_model=PipelineOut, name="reorder_stages")
def reorder_stages(
    pipeline_id: uuid.UUID,
    body: StageOrderIn,
    context: Manage,
    response: Response,
    if_match: IfMatch = None,
) -> Any:
    expected = _version(if_match)
    try:
        pipeline = pipelines.reorder_stages(
            _scope(context), pipeline_id, body.stage_ids, expected_version=expected
        )
    except RecordError as exc:
        raise _http(exc) from None
    return _answer(response, pipeline)
