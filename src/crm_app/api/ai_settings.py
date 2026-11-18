"""Workspace AI settings (decision P9-S), over SaaS-OS's public
`saas_os.inference.settings` (v0.15.0, decision K3.11).

Under `/v1/workspaces/{tenant_id}`:

    GET  /ai                      ai.policy:read
    PUT  /ai/enabled              ai.policy:manage
    PUT  /ai/features/{feature}   ai.policy:manage
    PUT  /ai/preferences          ai.policy:manage
    PUT  /ai/models               ai.policy:manage
    GET  /ai/budget               ai.usage:read
    PUT  /ai/budget               ai.budget:manage

The route policy is only the first check: each SaaS-OS function checks the
same permission again for the calling user, refuses support access for
every change, validates a model at grant time against the platform's
policy and the workspace's preferences, and writes the workspace's audit
row in the same transaction. AI stays off until a member turns it on, and
a platform hold still refuses every AI call whatever is set here.

The path's `tenant_id` is only the request; handlers use `context.tenant_id`.
Only users act here: an integration's key (a service account) is refused.
Refusals carry a closed reason code, never provider detail.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from saas_os.api.context import RequestContext, RequestPrincipal
from saas_os.api.dependencies import require_permission
from saas_os.core.authority import UserCaller
from saas_os.core.rbac import AuthorityNotAuthorizedError
from saas_os.inference.settings import (
    AIBudgetError,
    AIConfigurationNotFoundError,
    AITenantPolicyError,
    BudgetStatus,
    EligibleModelView,
    grant_destination,
    grant_use_case,
    list_eligible_models,
    read_tenant_ai_policy,
    read_tenant_budget,
    set_destination_rank,
    set_tenant_ai_policy,
    set_tenant_ai_preferences,
    set_tenant_budget_cap,
)

from crm_app import ai

router = APIRouter(prefix="/v1/workspaces", tags=["ai settings"])

ReadPolicy = Annotated[RequestContext, Depends(require_permission("ai.policy", "read"))]
ManagePolicy = Annotated[RequestContext, Depends(require_permission("ai.policy", "manage"))]
ReadUsage = Annotated[RequestContext, Depends(require_permission("ai.usage", "read"))]
ManageBudget = Annotated[RequestContext, Depends(require_permission("ai.budget", "manage"))]

# The product's AI features: each is one registered SaaS-OS use case, with
# the data classifications it may carry (`crm_app.ai`). Only these can be
# allowed.
Feature = Literal["contact_brief"]


@dataclass(frozen=True)
class _UseCase:
    name: str
    classifications: tuple[str, ...]


FEATURES: dict[str, _UseCase] = {
    "contact_brief": _UseCase(ai.CONTACT_BRIEF.name, ai.CONTACT_BRIEF_CLASSIFICATIONS),
}

_KEY = r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,199}$"
_RESIDENCY = r"^[a-z0-9][a-z0-9_-]{0,63}$"


class FeatureOut(BaseModel):
    feature: Feature
    enabled: bool


class PreferencesOut(BaseModel):
    allowed_residency: list[str]
    max_retention_days: int | None
    exclude_training_use: bool


class ModelOut(BaseModel):
    provider_key: str
    model_id: str
    lifecycle: str
    granted: bool
    rank: int | None
    eligible: bool
    # Closed reason codes from SaaS-OS (`blocked_by`), e.g. `residency`.
    blocked_by: list[str]


class FeatureModels(BaseModel):
    feature: Feature
    models: list[ModelOut]


class AISettingsOut(BaseModel):
    enabled: bool
    features: list[FeatureOut]
    preferences: PreferencesOut
    models: list[FeatureModels]


class EnabledIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool


class PreferencesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed_residency: list[Annotated[str, Field(pattern=_RESIDENCY)]] = Field(
        default_factory=list, max_length=20
    )
    max_retention_days: int | None = Field(default=None, ge=0, le=3650)
    exclude_training_use: bool = True


class ModelIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feature: Feature
    provider_key: str = Field(pattern=_KEY)
    model_id: str = Field(pattern=_KEY)
    enabled: bool
    # Lower is tried first; None leaves the order unset.
    rank: int | None = Field(default=None, ge=0, le=99)


class BudgetOut(BaseModel):
    """This UTC month's AI budget. Amounts are SaaS-OS's estimated platform
    spend in `currency` as plain decimal strings, never invoice amounts."""

    # SaaS-OS's state: unconfigured, ok, warning, exhausted,
    # currency_conflict or unavailable.
    state: str
    currency: str | None
    limit: str | None
    source: str | None
    settled: str | None
    reserved: str | None
    retained: str | None
    remaining: str | None
    period_start: datetime | None
    warn_thresholds: list[int]
    threshold_reached: int | None


class BudgetIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    currency: str = Field(pattern=r"^[A-Z]{3}$")
    # None removes the workspace's own cap (the plan's budget applies).
    amount: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    warn_thresholds: list[Annotated[int, Field(ge=1, le=100)]] | None = Field(
        default=None, max_length=5
    )


_SETTINGS_ERRORS = (
    AuthorityNotAuthorizedError,
    AIConfigurationNotFoundError,
    AITenantPolicyError,
    AIBudgetError,
)


def _caller(context: RequestContext) -> UserCaller:
    if context.principal is not RequestPrincipal.USER:
        raise HTTPException(status_code=403, detail={"code": "user_only"})
    return UserCaller(context.actor_id)


def _refused(exc: Exception) -> HTTPException:
    if isinstance(exc, AIConfigurationNotFoundError):
        return HTTPException(status_code=404, detail={"code": "unknown_model"})
    if isinstance(exc, AITenantPolicyError):
        return HTTPException(
            status_code=422,
            detail={"code": exc.reason, "blocked_by": list(exc.blocked_by)},
        )
    if isinstance(exc, AIBudgetError):
        return HTTPException(status_code=422, detail={"code": exc.reason})
    return HTTPException(status_code=403, detail={"code": "not_authorized"})


def _model(view: EligibleModelView) -> ModelOut:
    return ModelOut(
        provider_key=view.provider_key,
        model_id=view.model_id,
        lifecycle=view.lifecycle,
        granted=view.granted,
        rank=view.preference_rank,
        eligible=view.eligible,
        blocked_by=list(view.blocked_by),
    )


@router.get("/{tenant_id}/ai", response_model=AISettingsOut)
def get_ai_settings(tenant_id: uuid.UUID, context: ReadPolicy) -> AISettingsOut:
    caller = _caller(context)
    workspace = context.tenant_id
    try:
        policy = read_tenant_ai_policy(workspace, caller=caller)
        models = {
            feature: [
                _model(view)
                for view in list_eligible_models(workspace, use_case=use.name, caller=caller)
            ]
            for feature, use in FEATURES.items()
        }
    except _SETTINGS_ERRORS as exc:
        raise _refused(exc) from None
    granted = {grant.use_case: grant.enabled for grant in policy.use_cases}
    preferences = policy.preferences
    return AISettingsOut(
        enabled=policy.enabled,
        features=[
            FeatureOut.model_validate({"feature": f, "enabled": granted.get(use.name, False)})
            for f, use in FEATURES.items()
        ],
        preferences=PreferencesOut(
            allowed_residency=list(preferences.allowed_residency),
            max_retention_days=preferences.max_retention_days,
            exclude_training_use=preferences.exclude_training_use,
        ),
        models=[
            FeatureModels.model_validate({"feature": f, "models": rows})
            for f, rows in models.items()
        ],
    )


@router.put("/{tenant_id}/ai/enabled", status_code=204)
def put_ai_enabled(tenant_id: uuid.UUID, body: EnabledIn, context: ManagePolicy) -> Response:
    try:
        set_tenant_ai_policy(context.tenant_id, enabled=body.enabled, caller=_caller(context))
    except _SETTINGS_ERRORS as exc:
        raise _refused(exc) from None
    return Response(status_code=204)


@router.put("/{tenant_id}/ai/features/{feature}", status_code=204)
def put_ai_feature(
    tenant_id: uuid.UUID, feature: Feature, body: EnabledIn, context: ManagePolicy
) -> Response:
    try:
        grant_use_case(
            context.tenant_id,
            use_case=FEATURES[feature].name,
            classifications=FEATURES[feature].classifications,
            enabled=body.enabled,
            caller=_caller(context),
        )
    except _SETTINGS_ERRORS as exc:
        raise _refused(exc) from None
    return Response(status_code=204)


@router.put("/{tenant_id}/ai/preferences", status_code=204)
def put_ai_preferences(
    tenant_id: uuid.UUID, body: PreferencesIn, context: ManagePolicy
) -> Response:
    try:
        set_tenant_ai_preferences(
            context.tenant_id,
            allowed_residency=body.allowed_residency,
            max_retention_days=body.max_retention_days,
            exclude_training_use=body.exclude_training_use,
            caller=_caller(context),
        )
    except _SETTINGS_ERRORS as exc:
        raise _refused(exc) from None
    return Response(status_code=204)


@router.put("/{tenant_id}/ai/models", status_code=204)
def put_ai_model(tenant_id: uuid.UUID, body: ModelIn, context: ManagePolicy) -> Response:
    """Allow or disallow one catalogue model for a feature, and set its
    place in the order. Two SaaS-OS changes, each its own transaction: if
    the order is refused after the grant, the grant stands and the refusal
    is returned; the next read shows both."""
    caller = _caller(context)
    use = FEATURES[body.feature]
    try:
        grant_destination(
            context.tenant_id,
            use_case=use.name,
            provider_key=body.provider_key,
            model_id=body.model_id,
            classifications=use.classifications,
            enabled=body.enabled,
            caller=caller,
        )
        if body.enabled:
            set_destination_rank(
                context.tenant_id,
                use_case=use.name,
                provider_key=body.provider_key,
                model_id=body.model_id,
                rank=body.rank,
                caller=caller,
            )
    except _SETTINGS_ERRORS as exc:
        raise _refused(exc) from None
    return Response(status_code=204)


def _amount(value: Decimal | None) -> str | None:
    return None if value is None else format(value.normalize(), "f")


def _budget(status: BudgetStatus) -> BudgetOut:
    return BudgetOut(
        state=str(status.state),
        currency=status.currency,
        limit=_amount(status.limit),
        source=status.source,
        settled=_amount(status.settled),
        reserved=_amount(status.reserved),
        retained=_amount(status.retained),
        remaining=_amount(status.remaining),
        period_start=status.period_start,
        warn_thresholds=list(status.warn_thresholds),
        threshold_reached=status.threshold_reached,
    )


@router.get("/{tenant_id}/ai/budget", response_model=BudgetOut)
def get_ai_budget(tenant_id: uuid.UUID, context: ReadUsage) -> BudgetOut:
    try:
        return _budget(read_tenant_budget(context.tenant_id, caller=_caller(context)))
    except _SETTINGS_ERRORS as exc:
        raise _refused(exc) from None


@router.put("/{tenant_id}/ai/budget", status_code=204)
def put_ai_budget(tenant_id: uuid.UUID, body: BudgetIn, context: ManageBudget) -> Response:
    try:
        set_tenant_budget_cap(
            context.tenant_id,
            currency=body.currency,
            amount=body.amount,
            warn_thresholds=body.warn_thresholds,
            caller=_caller(context),
        )
    except _SETTINGS_ERRORS as exc:
        raise _refused(exc) from None
    return Response(status_code=204)
