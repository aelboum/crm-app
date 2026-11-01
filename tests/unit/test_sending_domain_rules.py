"""Sending domain rules and the Resend adapter (decision P6-D)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pytest

from crm_app import sending_domains
from crm_app.domains import sending_domains as rules
from crm_app.domains.records import InvalidValue
from crm_app.settings import ConfigurationError, Process, validate_settings
from tests.support import PLACEHOLDER_SETTINGS

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


@dataclass
class _Response:
    status_code: int
    body: bytes


class _Client:
    def __init__(self, status: int, body: object) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.status = status
        self.body = body

    async def post(
        self, url: str, *, headers: dict[str, str], content: bytes, deadline: Any
    ) -> Any:
        self.calls.append((url, json.loads(content)))
        return _Response(self.status, json.dumps(self.body).encode())


class _Secrets:
    def get(self, name: str) -> str | None:
        return "re_test_key" if name == "RESEND_API_KEY" else None  # pragma: allowlist secret


def _adapter(monkeypatch: pytest.MonkeyPatch, client: _Client) -> sending_domains.ResendDomains:
    monkeypatch.setattr("saas_os.infra.secrets.get_secrets_provider", _Secrets)
    return sending_domains.ResendDomains(client=client)


def test_the_adapter_creates_a_sending_only_domain_and_keeps_its_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _Client(
        200, {"id": "d_1", "name": "acme.nl", "status": "not_started", "records": RECORDS}
    )
    created = _adapter(monkeypatch, client).create("acme.nl")
    assert client.calls == [
        (
            "https://api.resend.com/domains",
            {"name": "acme.nl", "capabilities": {"sending": "enabled", "receiving": "disabled"}},
        )
    ]
    assert created.provider_id == "d_1"
    assert created.records is not None
    assert len(created.records) == 2


def test_the_adapter_verifies_by_id_and_maps_refusals(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _Client(200, {"object": "domain", "id": "d_1"})
    _adapter(monkeypatch, client).verify("d_1")
    assert client.calls[0][0] == "https://api.resend.com/domains/d_1/verify"
    for status, code in ((429, "rate_limited"), (403, "refused"), (500, "refused")):
        with pytest.raises(sending_domains.ProviderError, match=code):
            _adapter(monkeypatch, _Client(status, {})).verify("d_1")
    with pytest.raises(sending_domains.ProviderError, match="malformed_answer"):
        _adapter(monkeypatch, _Client(200, {"id": "bad id"})).create("acme.nl")


def test_no_provider_is_configured_by_default_or_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(sending_domains.FLAG, raising=False)
    assert sending_domains.configured_provider() is None
    monkeypatch.setenv(sending_domains.FLAG, "true")
    monkeypatch.setenv("ENVIRONMENT", "production")
    assert sending_domains.configured_provider() is None


def test_the_customer_domain_switch_is_refused_in_production() -> None:
    env = {
        **PLACEHOLDER_SETTINGS,
        "ENVIRONMENT": "production",
        "EMAIL_CUSTOMER_DOMAINS_ENABLED": "true",
    }
    with pytest.raises(ConfigurationError) as caught:
        validate_settings(Process.APP, environ=env, secret_lookup=env.get)
    assert "EMAIL_CUSTOMER_DOMAINS_ENABLED=true is refused in production" in str(caught.value)
