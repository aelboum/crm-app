"""Normalisation and validation of record values (`crm_app.domains.records`).

These produce the only forms the migration's CHECKs accept and the partial
unique indexes compare (`PHASE3-PLAN.md` §19.4), so each case pins the exact
stored value.
"""

from __future__ import annotations

import ast

import pytest

from crm_app.domains import records as values
from tests.support import REPO_ROOT

MIGRATION = REPO_ROOT / "src" / "crm_app" / "migrations" / "versions" / "0002_contacts_companies.py"


@pytest.mark.parametrize(
    ("raw", "stored"),
    [
        ("  Sam.Jones@Example.TEST ", "sam.jones@example.test"),
        ("a@b.co", "a@b.co"),
        ("", None),
        ("   ", None),
        (None, None),
    ],
)
def test_email_is_trimmed_and_lower_cased(raw: str | None, stored: str | None) -> None:
    assert values.email(raw) == stored


@pytest.mark.parametrize("raw", ["no-at-sign", "a@b", "a b@c.test", "a@@c.test", "x" * 321])
def test_an_invalid_email_is_refused_without_echoing_it(raw: str) -> None:
    with pytest.raises(values.InvalidValue) as raised:
        values.email(raw)
    assert raw not in str(raised.value)


@pytest.mark.parametrize(
    ("raw", "stored"),
    [
        ("Example.TEST", "example.test"),
        ("www.example.test.", "example.test"),
        (" sub.example.test ", "sub.example.test"),
        ("bücher.example", "xn--bcher-kva.example"),
    ],
)
def test_domain_is_normalised_to_one_ascii_form(raw: str, stored: str) -> None:
    assert values.domain(raw) == stored


@pytest.mark.parametrize("raw", ["example", "-bad.test", "bad-.test", "a_b.test", "exa mple.test"])
def test_an_invalid_domain_is_refused(raw: str) -> None:
    with pytest.raises(values.InvalidValue):
        values.domain(raw)


@pytest.mark.parametrize(
    ("url", "domain"),
    [
        ("https://www.Example.test/path?q=1", "example.test"),
        ("http://shop.example.test:8080", "shop.example.test"),
        ("https://192.0.2.1/", None),
        (None, None),
    ],
)
def test_the_domain_is_derived_from_the_website(url: str | None, domain: str | None) -> None:
    assert values.domain_from_website(url) == domain


@pytest.mark.parametrize(
    "raw", ["ftp://example.test", "javascript:alert(1)", "example.test", "https://", "https://a b"]
)
def test_only_http_and_https_websites_with_a_host_are_accepted(raw: str) -> None:
    with pytest.raises(values.InvalidValue):
        values.website(raw)


@pytest.mark.parametrize("raw", ["+31 20 123 4567", "(020) 123-4567", "0612345678"])
def test_phone_numbers_are_kept_as_entered(raw: str) -> None:
    assert values.phone(f" {raw} ") == raw


@pytest.mark.parametrize("raw", ["call me", "12", "+", "1" * 33])
def test_an_invalid_phone_number_is_refused(raw: str) -> None:
    with pytest.raises(values.InvalidValue):
        values.phone(raw)


def test_optional_text_is_trimmed_and_empty_becomes_none() -> None:
    assert values.text("  Utrecht ", 100) == "Utrecht"
    assert values.text("   ", 100) is None
    with pytest.raises(values.InvalidValue):
        values.text("   ", 100, required=True)
    with pytest.raises(values.InvalidValue):
        values.text("x" * 101, 100)


def test_country_codes_are_two_upper_case_letters() -> None:
    assert values.country_code(" nl ") == "NL"
    for raw in ("NLD", "N1", "1"):
        with pytest.raises(values.InvalidValue):
            values.country_code(raw)


def test_stages_and_user_sources_follow_p3a() -> None:
    assert values.STAGES == ("lead", "prospect", "customer", "inactive")
    assert values.SOURCES == ("manual", "import", "form", "referral", "other")
    for source in ("manual", "referral", "other"):
        assert values.user_source(source) == source
    for reserved in ("import", "form", "web"):
        with pytest.raises(values.InvalidValue):
            values.user_source(reserved)
    with pytest.raises(values.InvalidValue):
        values.stage("patient")


def test_the_migration_checks_exactly_these_stages_and_sources() -> None:
    tree = ast.parse(MIGRATION.read_text(encoding="utf-8"))
    constants = {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id in {"STAGES", "SOURCES"}
    }
    assert constants == {"STAGES": values.STAGES, "SOURCES": values.SOURCES}
