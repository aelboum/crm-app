"""`crm_app.ai` (decision P9-P): the contact brief's governed-inference
request and how each outcome becomes a plain state. SaaS-OS's
`run_inference` is replaced by a stub, so no provider, database or network
is used. Run in a fresh interpreter with placeholder settings, because
SaaS-OS resolves configuration at import time.
"""

from __future__ import annotations

import json
from pathlib import Path

from tests.support import PLACEHOLDER_SETTINGS, clean_environment, run_python

_PROBE = """
import asyncio, json, uuid
from datetime import date
import saas_os.inference as inf
from crm_app import ai
from crm_app.domains import ai_brief

TODAY = date(2026, 11, 9)
TENANT = uuid.uuid4()
FACTS = ai_brief.ContactFacts(
    lifecycle_stage="lead", source="form", tag_names=("vip",),
    created_on=date(2026, 10, 1), history=(), deals=(),
    open_tasks=0, overdue_tasks=0, upcoming_appointments=0,
)

def result(text):
    return inf.InferenceResult(
        request_id=uuid.uuid4(), client_request_id=None, alias=ai_brief.ALIAS,
        provider_key="fake", model_id="fake-model",
        output=(inf.ContentPart("text", "tenant_data", text=text),), tool_calls=(),
        finish_reason="stop",
        usage=inf.UsageReport(120, 40, None, None, "provider_reported"),
        attempts=1, fell_back=False,
    )

out = {}
ai.register()
ai.register()
out["registered"] = True

request = ai.brief_request(FACTS, today=TODAY)
out["request"] = {
    "alias": request.alias,
    "use_case": request.use_case,
    "max_output_tokens": request.max_output_tokens,
    "messages": [
        [m.role, [p.classification for p in m.parts]] for m in request.messages
    ],
    "system_is_instructions": request.messages[0].parts[0].text == ai_brief.INSTRUCTIONS,
    "user_is_data": request.messages[1].parts[0].text == ai_brief.brief_data(FACTS, today=TODAY),
}

seen = {}
def answering(text):
    async def run(caller, *, tenant_id, request):
        seen["tenant_id"] = str(tenant_id)
        return result(text)
    return run

def raising(error):
    async def run(caller, *, tenant_id, request):
        raise error
    return run

def brief(run):
    o = asyncio.run(ai.contact_brief(object(), tenant_id=TENANT, facts=FACTS, today=TODAY, run=run))
    return [o.state.value, o.text, o.input_tokens, o.output_tokens]

out["ready"] = brief(answering("  Warm lead.\\nCall back this week.  "))
out["tenant"] = seen["tenant_id"] == str(TENANT)
out["empty"] = brief(answering("   "))
errors = [
    "InferencePolicyDeniedError", "InferenceEntitlementDeniedError",
    "InferenceNotAuthorizedError", "InferenceUnsupportedCapabilityError",
    "InferenceQuotaExceededError", "InferenceRateLimitedError",
    "InferenceCapacityExhaustedError", "InferenceTimeoutError",
    "InferenceConnectionError", "InferenceProviderAuthError",
    "InferenceProviderUnavailableError", "InferenceOutcomeUnknownError",
    "InferenceResponseLimitError", "InferenceInvalidRequestError",
    "InferenceEndpointSecurityError", "InferenceInternalError",
]
out["errors"] = {name: brief(raising(getattr(inf, name)()))[0] for name in errors}

called = []
async def never(caller, *, tenant_id, request):
    called.append(1)
    return result("x")
ai_brief.MAX_INPUT_BYTES = 100
out["too_large"] = brief(never)[0]
out["too_large_sent"] = bool(called)
print("OUTCOME " + json.dumps(out))
"""


def test_contact_brief_request_and_states(tmp_path: Path) -> None:
    result = run_python(_PROBE, clean_environment(PLACEHOLDER_SETTINGS), tmp_path)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("OUTCOME "))
    out = json.loads(line.removeprefix("OUTCOME "))
    assert out["registered"] is True
    assert out["request"] == {
        "alias": "crm-suggest",
        "use_case": "crm.contact_brief",
        "max_output_tokens": 400,
        "messages": [["system", ["none"]], ["user", ["tenant_data"]]],
        "system_is_instructions": True,
        "user_is_data": True,
    }
    assert out["ready"] == ["ready", "Warm lead.\nCall back this week.", 120, 40]
    assert out["tenant"] is True
    assert out["empty"] == ["failed", None, None, None]
    unavailable = {
        "InferencePolicyDeniedError",
        "InferenceEntitlementDeniedError",
        "InferenceNotAuthorizedError",
        "InferenceUnsupportedCapabilityError",
    }
    busy = {"InferenceRateLimitedError", "InferenceCapacityExhaustedError"}
    for name, state in out["errors"].items():
        if name in unavailable:
            assert state == "unavailable", name
        elif name in busy:
            assert state == "busy", name
        elif name == "InferenceQuotaExceededError":
            assert state == "quota_reached", name
        else:
            assert state == "failed", name
    assert out["too_large"] == "failed"
    assert out["too_large_sent"] is False
