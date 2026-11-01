"""Sending domain rules and the Resend adapter (decision P6-D)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from crm_app.domains import sending_domains as rules
from crm_app.domains.records import InvalidValue
from crm_app.settings import ConfigurationError, Process, validate_settings
from tests.support import PLACEHOLDER_SETTINGS, clean_environment, run_python

RECORDS = [
    {"record": "SPF", "name": "send", "type": "MX", "value": "feedback-smtp.eu-west-1.example.org",
     "ttl": "Auto", "status": "not_started", "priority": 10},
    {"record": "DKIM", "name": "resend._domainkey", "type": "TXT", "value": "p=MIGf",
     "ttl": "Auto", "status": "pending"},
]  # fmt: skip


def test_a_sending_domain_is_a_plain_domain_outside_the_platform() -> None:
    assert rules.domain(" Acme.NL ", parent="leadstack.io") == "acme.nl"
    for value in ("acme", "*.acme.nl", "www.example.com", "mail.leadstack.io", "leadstack.io"):
        with pytest.raises(InvalidValue):
            rules.domain(value, parent="leadstack.io")


def test_sender_addresses_are_bare_and_have_no_plus() -> None:
    assert rules.address("Jan", "acme.nl") == "jan@acme.nl"
    with pytest.raises(InvalidValue):
        rules.address("jan+news", "acme.nl")


def test_the_providers_records_are_kept_exactly() -> None:
    kept = rules.records(RECORDS)
    assert [r.as_dict()["value"] for r in kept] == [
        "feedback-smtp.eu-west-1.example.org",
        "p=MIGf",
    ]
    assert kept[0].priority == 10
    assert kept[1].status == "pending"


@pytest.mark.parametrize(
    "bad",
    [
        "not a list",
        [{"record": "SPF", "name": "x", "type": "A", "value": "1.2.3.4"}],
        [{"record": "SPF", "name": "x", "type": "TXT", "value": "a\nb"}],
        [{"record": "<script>", "name": "x", "type": "TXT", "value": "v"}],
        [{"record": "SPF", "name": "", "type": "TXT", "value": "v"}],
        [RECORDS[0]] * 21,
    ],
)
def test_untrustworthy_records_are_refused(bad: Any) -> None:
    with pytest.raises(rules.ProviderAnswerError):
        rules.records(bad)


def test_unknown_states_never_count_as_verified() -> None:
    assert rules.status("verified") == "verified"
    assert rules.status("VERIFIED") == "unknown"
    assert rules.status(None) == "unknown"


def test_domain_events_are_parsed_and_others_ignored() -> None:
    event = rules.domain_event(
        {"type": "domain.updated", "data": {"id": "d_1", "name": "Acme.nl", "status": "verified"}}
    )
    assert event is not None
    assert (event.domain.provider_id, event.domain.name, event.domain.status) == (
        "d_1",
        "acme.nl",
        "verified",
    )
    assert event.domain.records is None
    assert rules.domain_event({"type": "email.sent", "data": {}}) is None
    with pytest.raises(rules.ProviderAnswerError):
        rules.domain_event({"type": "domain.updated", "data": {"id": "bad id"}})


_ADAPTER_PROBE = """
import json, os
from dataclasses import dataclass
import saas_os.infra.secrets as secrets_module
from crm_app import sending_domains

RECORDS = json.loads(os.environ["PROBE_RECORDS"])

@dataclass
class Response:
    status_code: int
    body: bytes

class Client:
    def __init__(self, status, body):
        self.calls, self.status, self.body = [], status, body
    async def post(self, url, *, headers, content, deadline):
        self.calls.append([url, json.loads(content)])
        return Response(self.status, json.dumps(self.body).encode())

class Secrets:
    def get(self, name):
        return "re_test_key" if name == "RESEND_API_KEY" else None  # pragma: allowlist secret

secrets_module.get_secrets_provider = Secrets
out = {}
client = Client(200, {"id": "d_1", "name": "acme.nl", "status": "not_started", "records": RECORDS})
created = sending_domains.ResendDomains(client=client).create("acme.nl")
out["create"] = [client.calls, created.provider_id, len(created.records or [])]
client = Client(200, {"object": "domain", "id": "d_1"})
sending_domains.ResendDomains(client=client).verify("d_1")
out["verify"] = client.calls[0][0]
refusals = []
for status in (429, 403, 500):
    try:
        sending_domains.ResendDomains(client=Client(status, {})).verify("d_1")
    except sending_domains.ProviderError as error:
        refusals.append(str(error))
try:
    sending_domains.ResendDomains(client=Client(200, {"id": "bad id"})).create("acme.nl")
except sending_domains.ProviderError as error:
    refusals.append(str(error))
out["refusals"] = refusals
os.environ.pop(sending_domains.FLAG, None)
providers = [sending_domains.configured_provider()]
os.environ[sending_domains.FLAG] = "true"
os.environ["ENVIRONMENT"] = "production"
providers.append(sending_domains.configured_provider())
out["providers"] = providers
print(json.dumps(out))
"""


@pytest.fixture(scope="module")
def adapter(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    # SaaS-OS reads configuration at import, so the adapter runs in a fresh
    # interpreter with placeholder settings; no service is contacted.
    env = clean_environment({**PLACEHOLDER_SETTINGS, "PROBE_RECORDS": json.dumps(RECORDS)})
    result = run_python(_ADAPTER_PROBE, env, tmp_path_factory.mktemp("adapter"))
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_the_adapter_creates_a_sending_only_domain_and_keeps_its_records(
    adapter: dict[str, Any],
) -> None:
    calls, provider_id, kept = adapter["create"]
    assert calls == [
        [
            "https://api.resend.com/domains",
            {"name": "acme.nl", "capabilities": {"sending": "enabled", "receiving": "disabled"}},
        ]
    ]
    assert (provider_id, kept) == ("d_1", 2)


def test_the_adapter_verifies_by_id_and_maps_refusals(adapter: dict[str, Any]) -> None:
    assert adapter["verify"] == "https://api.resend.com/domains/d_1/verify"
    codes = ("rate_limited", "refused", "refused", "malformed_answer")
    assert len(adapter["refusals"]) == len(codes)
    for message, code in zip(adapter["refusals"], codes, strict=True):
        assert code in message


def test_no_provider_is_configured_by_default_or_in_production(adapter: dict[str, Any]) -> None:
    assert adapter["providers"] == [None, None]


def test_the_customer_domain_switch_is_refused_in_production() -> None:
    env = {
        **PLACEHOLDER_SETTINGS,
        "ENVIRONMENT": "production",
        "EMAIL_CUSTOMER_DOMAINS_ENABLED": "true",
    }
    with pytest.raises(ConfigurationError) as caught:
        validate_settings(Process.APP, environ=env, secret_lookup=env.get)
    assert "EMAIL_CUSTOMER_DOMAINS_ENABLED=true is refused in production" in str(caught.value)
