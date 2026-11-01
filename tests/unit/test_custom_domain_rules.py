"""Custom domain rules (decision P12-D, `crm_app.domains.custom_domains`)."""

from __future__ import annotations

import pytest

from crm_app.domains import custom_domains as rules
from crm_app.domains.records import InvalidValue

# A made-up verification token for tests only.
TOKEN = "0123456789abcdef0123456789abcdef"  # pragma: allowlist secret


def test_hostnames_are_lowercased() -> None:
    assert rules.hostname(" Forms.Acme-Shop.NL ") == "forms.acme-shop.nl"
    assert rules.hostname("xn--mnchen-3ya.de") == "xn--mnchen-3ya.de"


@pytest.mark.parametrize(
    "value",
    [
        "",
        "localhost",
        "acme",
        "*.acme.nl",
        "acme.nl.",
        "acme.nl:443",
        "https://acme.nl",
        "10.0.0.1",
        "intranet.local",
        "shop.internal",
        "www.example.com",
        "site.test",
        "münchen.de",
        ("a" * 64) + ".nl",
    ],
)
def test_unsafe_hostnames_are_refused(value: str) -> None:
    with pytest.raises(InvalidValue):
        rules.hostname(value)


def test_the_apps_own_domain_cannot_be_claimed() -> None:
    with pytest.raises(InvalidValue):
        rules.hostname("app.leadstack.io", app_host="app.leadstack.io")
    with pytest.raises(InvalidValue):
        rules.hostname("pages.app.leadstack.io", app_host="app.leadstack.io")
    assert rules.hostname("leadstack.io", app_host="app.leadstack.io") == "leadstack.io"


def test_the_challenge_record() -> None:
    assert rules.challenge_name("forms.acme.nl") == "_leadstack-challenge.forms.acme.nl"
    assert rules.challenge_value(TOKEN) == f"leadstack-verification={TOKEN}"
    with pytest.raises(ValueError, match="token"):
        rules.challenge_value("short")
    assert len(rules.new_token()) == 32


def test_only_the_exact_value_proves_ownership() -> None:
    value = rules.challenge_value(TOKEN)
    assert rules.proves([value], TOKEN)
    assert rules.proves(["v=spf1 -all", f' "{value}" '], TOKEN)
    assert not rules.proves([], TOKEN)
    assert not rules.proves([value + "x"], TOKEN)
    assert not rules.proves([value.upper()], TOKEN)
    assert not rules.proves([rules.challenge_value("f" * 32)], TOKEN)
