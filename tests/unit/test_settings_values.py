"""Workspace settings values (`crm_app.domains.settings`, decision P2-F 1).

Each validator normalises what a client sends to the one stored form or
refuses it without echoing the value, and the stored forms satisfy
migration 0004's `CHECK` patterns.
"""

from __future__ import annotations

import ast
import re

import pytest

from crm_app.domains import settings as values
from crm_app.domains.records import InvalidValue
from tests.support import REPO_ROOT

MIGRATION = REPO_ROOT / "src" / "crm_app" / "migrations" / "versions" / "0004_workspace_settings.py"


@pytest.mark.parametrize(
    ("raw", "stored"),
    [
        ("en", "en"),
        ("nl-nl", "nl-NL"),
        (" EN-GB ", "en-GB"),
        ("zh-hant-tw", "zh-Hant-TW"),
        ("es-419", "es-419"),
    ],
)
def test_a_locale_is_normalised_to_its_conventional_case(raw: str, stored: str) -> None:
    assert values.locale(raw) == stored


@pytest.mark.parametrize(
    "raw", ["", "english", "e", "en_GB", "en-GBR", "en-GB-x-private", "nl\0", "x" * 65]
)
def test_an_invalid_locale_is_refused_without_echoing_it(raw: str) -> None:
    with pytest.raises(InvalidValue) as refused:
        values.locale(raw)
    # Short inputs can occur in any sentence; longer ones must not be echoed.
    assert len(raw.strip()) < 4 or raw not in str(refused.value)


def test_time_zones_are_iana_names() -> None:
    assert values.time_zone("Europe/Amsterdam") == "Europe/Amsterdam"
    assert values.time_zone(" UTC ") == "UTC"
    for raw in ("Mars/Olympus", "europe/amsterdam", "+01:00", "", "Europe/Amsterdam\0"):
        with pytest.raises(InvalidValue):
            values.time_zone(raw)


def test_currencies_are_active_iso_4217_codes() -> None:
    assert values.currency("eur") == "EUR"
    assert values.currency(" usd ") == "USD"
    for raw in ("EURO", "XAU", "ABC", "", "HRK"):
        with pytest.raises(InvalidValue):
            values.currency(raw)
    assert len(values.CURRENCIES) > 150
    assert all(re.fullmatch(r"[A-Z]{3}", code) for code in values.CURRENCIES)


def test_the_defaults_are_valid() -> None:
    assert values.locale(values.DEFAULT_LOCALE) == values.DEFAULT_LOCALE
    assert values.time_zone(values.DEFAULT_TIME_ZONE) == values.DEFAULT_TIME_ZONE
    assert values.currency(values.DEFAULT_CURRENCY) == values.DEFAULT_CURRENCY


def test_stored_forms_satisfy_the_migration_checks() -> None:
    tree = ast.parse(MIGRATION.read_text(encoding="utf-8"))
    patterns = {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id in {"LOCALE_PATTERN", "TIME_ZONE_PATTERN"}
    }
    for tag in ("en", "nl-NL", "zh-Hant-TW", "es-419", values.DEFAULT_LOCALE):
        assert re.match(patterns["LOCALE_PATTERN"], values.locale(tag))
    for zone in ("Europe/Amsterdam", "UTC", "America/Argentina/Buenos_Aires", "Etc/GMT+5"):
        assert re.match(patterns["TIME_ZONE_PATTERN"], values.time_zone(zone))
