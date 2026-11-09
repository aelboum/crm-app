"""AI suggestions through SaaS-OS's governed inference (decisions P9-0, P9-P).

LeadStack owns use cases, never providers. Provider, model, credential,
endpoint trust, retention and training declarations, routing and metering
all belong to SaaS-OS (`saas_os.inference`); this module registers the
product's use cases and turns an outcome into one of a few plain states.
It holds no key and never calls a provider directly.

Suggestions only: a brief's text is returned to be shown to a member. It
is never stored, sent or acted on here, and neither the prompt nor the
output is logged (only the state).
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from saas_os.inference import (
    ContentPart,
    InferenceCapacityExhaustedError,
    InferenceEntitlementDeniedError,
    InferenceError,
    InferenceInvalidRequestError,
    InferenceNotAuthorizedError,
    InferencePolicyDeniedError,
    InferenceQuotaExceededError,
    InferenceRateLimitedError,
    InferenceRequest,
    InferenceResult,
    InferenceUnsupportedCapabilityError,
    Message,
    UseCase,
    register_use_case,
)
from saas_os.inference import run_inference as _run_inference

from crm_app.domains import ai_brief

Runner = Callable[..., Awaitable[InferenceResult]]

CONTACT_BRIEF = UseCase(
    name=ai_brief.USE_CASE,
    max_classification="tenant_data",
    part_kinds=frozenset({"text"}),
    max_parts=2,
    max_input_bytes=ai_brief.MAX_INPUT_BYTES,
)


class BriefState(StrEnum):
    """What a member is told. None of them carries provider detail."""

    READY = "ready"
    # AI is not turned on for the workspace, not in its plan, or the member
    # may not use it (policy, entitlement, authority, capability).
    UNAVAILABLE = "unavailable"
    QUOTA_REACHED = "quota_reached"
    BUSY = "busy"
    FAILED = "failed"


@dataclass(frozen=True)
class BriefOutcome:
    state: BriefState
    text: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


_UNAVAILABLE: tuple[type[InferenceError], ...] = (
    InferencePolicyDeniedError,
    InferenceEntitlementDeniedError,
    InferenceNotAuthorizedError,
    InferenceUnsupportedCapabilityError,
)
_BUSY: tuple[type[InferenceError], ...] = (
    InferenceRateLimitedError,
    InferenceCapacityExhaustedError,
)


def register() -> None:
    """Declare the product's use cases at start-up. Registration authorizes
    nothing: the workspace's AI policy must still grant the use case and a
    destination, and installation policy must allow it (SaaS-OS ADR-0055)."""
    register_use_case(CONTACT_BRIEF)


def state_for(error: InferenceError) -> BriefState:
    if isinstance(error, _UNAVAILABLE):
        return BriefState.UNAVAILABLE
    if isinstance(error, InferenceQuotaExceededError):
        return BriefState.QUOTA_REACHED
    if isinstance(error, _BUSY):
        return BriefState.BUSY
    return BriefState.FAILED


def brief_request(facts: ai_brief.ContactFacts, *, today: date) -> InferenceRequest:
    """The governed-inference request for one contact brief: the fixed
    instructions as `none`, the facts as `tenant_data`, the highest the use
    case allows. Raises `ai_brief.BriefTooLarge`."""
    data = ai_brief.brief_data(facts, today=today)
    return InferenceRequest(
        alias=ai_brief.ALIAS,
        use_case=ai_brief.USE_CASE,
        messages=(
            Message("system", (ContentPart("text", "none", text=ai_brief.INSTRUCTIONS),)),
            Message("user", (ContentPart("text", "tenant_data", text=data),)),
        ),
        max_output_tokens=ai_brief.MAX_OUTPUT_TOKENS,
    )


def _text(result: InferenceResult) -> str:
    return "".join(p.text or "" for p in result.output if p.kind == "text").strip()


async def contact_brief(
    caller: object,
    *,
    tenant_id: uuid.UUID,
    facts: ai_brief.ContactFacts,
    today: date,
    run: Runner = _run_inference,
) -> BriefOutcome:
    """One contact brief for the calling member in their workspace."""
    try:
        request = brief_request(facts, today=today)
    except ai_brief.BriefTooLarge:
        return BriefOutcome(BriefState.FAILED)
    try:
        result = await run(caller, tenant_id=tenant_id, request=request)
    except InferenceInvalidRequestError:
        return BriefOutcome(BriefState.FAILED)
    except InferenceError as error:
        return BriefOutcome(state_for(error))
    text = _text(result)
    if not text:
        return BriefOutcome(BriefState.FAILED)
    return BriefOutcome(
        BriefState.READY,
        text=text,
        input_tokens=result.usage.input_tokens,
        output_tokens=result.usage.output_tokens,
    )
