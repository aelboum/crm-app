"""The Resend receiving adapter (decision P6-R), with a client double:
no service is contacted."""

from __future__ import annotations

import json
from typing import Any

import pytest

from tests.support import PLACEHOLDER_SETTINGS, clean_environment, run_python

_PROBE = """
import json, os
from dataclasses import dataclass, field
import saas_os.infra.secrets as secrets_module
from saas_os.infra.egress import EgressResponseTooLargeError, EgressTimeoutError
from crm_app import inbound

ANSWER = {"from": "rita@example.com", "to": ["reply+t@inbound.example.org"], "text": "Hi"}

@dataclass
class Response:
    status_code: int
    body: bytes
    headers: dict = field(default_factory=dict)

class Client:
    def __init__(self, status=200, body=ANSWER, headers=None, error=None):
        self.calls, self.status, self.body = [], status, body
        self.headers, self.error = headers or {}, error
    async def get(self, url, *, headers, deadline):
        self.calls.append([url, sorted(headers)])
        if self.error is not None:
            raise self.error
        raw = self.body if isinstance(self.body, bytes) else json.dumps(self.body).encode()
        return Response(self.status, raw, self.headers)

class Secrets:
    def __init__(self, key="re_test_key"):  # pragma: allowlist secret
        self.key = key
    def get(self, name):
        return self.key if name == "RESEND_API_KEY" else None

secrets_module.get_secrets_provider = Secrets
out = {}
client = Client()
out["answer"] = inbound.ResendReceiving(client=client).fetch("em_123")
out["call"] = client.calls[0]
failures = []
cases = [
    ({"status": 404}, "em_1"),
    ({"status": 429, "headers": {"retry-after": "30"}}, "em_1"),
    ({"status": 503, "headers": {"retry-after": "soon"}}, "em_1"),
    ({"status": 401}, "em_1"),
    ({"status": 422}, "em_1"),
    ({"body": b"not json"}, "em_1"),
    ({"error": EgressResponseTooLargeError()}, "em_1"),
    ({"error": EgressTimeoutError("deadline_expired", phase="total",
                                  request_may_have_been_sent=True)}, "em_1"),
    ({}, "../domains"),
]
for kwargs, email_id in cases:
    probe = Client(**kwargs)
    try:
        inbound.ResendReceiving(client=probe).fetch(email_id)
    except inbound.FetchError as exc:
        failures.append([exc.code, exc.transient, exc.retry_after, len(probe.calls)])
out["failures"] = failures

configured = []
os.environ.pop("EMAIL_INBOUND_ENABLED", None)
configured.append(type(inbound.configured_client()).__name__)
os.environ["EMAIL_INBOUND_ENABLED"] = "true"
configured.append(type(inbound.configured_client()).__name__)
secrets_module.get_secrets_provider = lambda: Secrets(None)
configured.append(type(inbound.configured_client()).__name__)
secrets_module.get_secrets_provider = Secrets
os.environ["ENVIRONMENT"] = "production"
configured.append(type(inbound.configured_client()).__name__)
out["configured"] = configured
print(json.dumps(out))
"""


@pytest.fixture(scope="module")
def probe(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    # SaaS-OS reads configuration at import, so the adapter runs in a fresh
    # interpreter with placeholder settings.
    env = clean_environment(PLACEHOLDER_SETTINGS)
    result = run_python(_PROBE, env, tmp_path_factory.mktemp("receiving"))
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_the_adapter_gets_one_received_email_by_id(probe: dict[str, Any]) -> None:
    assert probe["call"] == [
        "https://api.resend.com/emails/receiving/em_123",
        ["Accept", "Authorization"],
    ]
    assert probe["answer"]["from"] == "rita@example.com"


def test_the_adapter_maps_each_failure_to_a_code_and_retry(probe: dict[str, Any]) -> None:
    assert probe["failures"] == [
        ["not_found", False, None, 1],
        ["rate_limited", True, 30.0, 1],
        ["provider_error", True, None, 1],
        ["unauthorized", True, None, 1],
        ["refused", False, None, 1],
        ["malformed_answer", False, None, 1],
        ["answer_too_large", False, None, 1],
        ["unreachable", True, None, 1],
        # An id that could leave the path is refused before any request.
        ["invalid_email_id", False, None, 0],
    ]


def test_the_client_exists_only_when_inbound_is_on_outside_production_with_a_key(
    probe: dict[str, Any],
) -> None:
    assert probe["configured"] == ["NoneType", "ResendReceiving", "NoneType", "NoneType"]
