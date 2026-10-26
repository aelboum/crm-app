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


@pytest.mark.parametrize("check", [values.email, values.phone, values.website, values.domain])
def test_a_nul_character_is_refused_everywhere(check: object) -> None:
    with pytest.raises(values.InvalidValue):
        check("a\0b@example.test")  # type: ignore[operator]
    with pytest.raises(values.InvalidValue):
        values.text("Sam\0", 200)


@pytest.mark.parametrize(
    "url",
    # Made-up credentials: the URL forms under test.
    [
        "https://user:secret@example.test/",  # pragma: allowlist secret
        "https://user@example.test",
        "http://:pw@example.test",  # pragma: allowlist secret
    ],
)
def test_a_website_with_credentials_is_refused(url: str) -> None:
    with pytest.raises(values.InvalidValue):
        values.website(url)


# --- Notes (decision P3-B, PHASE3-PLAN.md §21.1) ----------------------------------

NOTES_MIGRATION = (
    REPO_ROOT / "src" / "crm_app" / "migrations" / "versions" / "0003_notes_activity.py"
)


@pytest.mark.parametrize(
    ("raw", "stored"),
    [
        ("Called.", "Called."),
        ("  Line one\r\nLine two\rLine three \n\t", "Line one\nLine two\nLine three"),
        ("\tIndented\n\n  kept inside", "Indented\n\n  kept inside"),
        ("<b>not html</b> & 'quotes'", "<b>not html</b> & 'quotes'"),
        ("x" * 10_000, "x" * 10_000),
    ],
)
def test_a_note_is_normalised_to_plain_lf_text(raw: str, stored: str) -> None:
    assert values.note_body(raw) == stored


@pytest.mark.parametrize(
    "raw", ["", " \n\t ", "x" * 10_001, "bell\x07", "nul\0", "escape\x1b[0m", "del\x7f"]
)
def test_an_invalid_note_is_refused_without_echoing_it(raw: str) -> None:
    with pytest.raises(values.InvalidValue) as refused:
        values.note_body(raw)
    assert raw.strip() == "" or raw[:4] not in str(refused.value)


def test_the_note_migration_matches_these_rules() -> None:
    tree = ast.parse(NOTES_MIGRATION.read_text(encoding="utf-8"))
    constants = {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id in {"STAGES", "NOTE_MAX", "UPDATED_FIELDS"}
    }
    assert constants["STAGES"] == values.STAGES
    assert constants["NOTE_MAX"] == values.NOTE_MAX
    # Every plain field of either record (`crm_app.records` CONTACT and
    # COMPANY) may appear in an `updated` entry; stage, owner and company
    # changes have their own kinds. `test_history.py` exercises the writes.
    assert set(constants["UPDATED_FIELDS"]) == {
        "first_name",
        "last_name",
        "email",
        "phone",
        "job_title",
        "city",
        "source",
        "name",
        "domain",
        "website",
        "industry",
        "country_code",
    }


# --- Tag names (decision P3-C 3) ---------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "stored"),
    [
        ("VIP", "VIP"),
        ("  Hot lead  ", "Hot lead"),
        ("张伟 客户", "张伟 客户"),
        ("x" * 50, "x" * 50),
    ],
)
def test_a_tag_name_is_trimmed(raw: str, stored: str) -> None:
    assert values.tag_name(raw) == stored


@pytest.mark.parametrize(
    "raw", ["", "   ", "x" * 51, "line\nbreak", "tab\there", "nul\x00", "\x7f"]
)
def test_a_tag_name_outside_the_rules_is_refused_without_echoing_it(raw: str) -> None:
    with pytest.raises(values.InvalidValue) as refused:
        values.tag_name(raw)
    assert raw.strip() not in str(refused.value) or not raw.strip()


def test_the_migration_checks_the_same_tag_name_length() -> None:
    migration = (
        REPO_ROOT / "src" / "crm_app" / "migrations" / "versions" / "0007_tags.py"
    ).read_text(encoding="utf-8")
    assert f"TAG_NAME_MAX = {values.TAG_NAME_MAX}" in migration


@pytest.mark.parametrize(
    "raw",
    ["\u200b", "VIP\u200b", "\u202eevil", "a\u2028b", "a\u2029b", "\x85", "soft\u00adhyphen"],
)
def test_a_tag_name_with_invisible_characters_is_refused(raw: str) -> None:
    with pytest.raises(values.InvalidValue):
        values.tag_name(raw)
