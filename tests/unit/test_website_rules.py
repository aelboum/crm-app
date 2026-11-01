"""Website integration rules (decision P12-W, `crm_app.domains.websites`)."""

from __future__ import annotations

import pytest

from crm_app.domains import websites as rules
from crm_app.domains.records import InvalidValue


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://www.Example.com/", "https://www.example.com"),
        ("https://shop.example.com:443", "https://shop.example.com"),
        ("https://shop.example.com:8443", "https://shop.example.com:8443"),
        ("  https://xn--mnchen-3ya.de ", "https://xn--mnchen-3ya.de"),
    ],
)
def test_origins_are_canonical(value: str, expected: str) -> None:
    assert rules.origin(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "http://example.com",
        "https://*.example.com",
        "https://example.com/contact",
        "https://example.com?x=1",
        "https://user:pass@example.com",  # pragma: allowlist secret
        "javascript:alert(1)",
        "ftp://example.com",
        "https://example",
        "https://localhost",
        "https://exa mple.com",
        "",
    ],
)
def test_anything_but_a_plain_https_origin_is_refused(value: str) -> None:
    with pytest.raises(InvalidValue):
        rules.origin(value)


def test_localhost_only_for_development() -> None:
    assert rules.origin("http://localhost:5173", allow_local=True) == "http://localhost:5173"
    assert rules.origin("http://127.0.0.1:8080", allow_local=True) == "http://127.0.0.1:8080"
    with pytest.raises(InvalidValue):
        rules.origin("http://localhost:5173")


def test_a_website_has_one_to_twenty_distinct_origins() -> None:
    assert rules.origins(["https://a.example", "https://A.example/"]) == ["https://a.example"]
    with pytest.raises(InvalidValue):
        rules.origins([])
    with pytest.raises(InvalidValue):
        rules.origins([f"https://s{i}.example" for i in range(rules.ORIGINS_MAX + 1)])


def test_request_origins_are_read_leniently() -> None:
    assert rules.request_origin("https://www.example.com") == "https://www.example.com"
    assert rules.request_origin("http://localhost:3000") == "http://localhost:3000"
    for header in (None, "", "null", "not an origin", "https://example.com/path"):
        assert rules.request_origin(header) is None


def test_attribution_keeps_short_utm_values_and_own_page_urls_only() -> None:
    kept = rules.attribution(
        {
            "utm_source": " google\n",
            "utm_medium": "x" * 400,
            "utm_campaign": 5,
            "page_url": "https://www.example.com/pricing?plan=pro",
            "referrer": "https://news.example.org/story",
            "unknown_key": "ignored",
        },
        "https://www.example.com",
    )
    assert kept.utm == {"utm_source": "google", "utm_medium": "x" * rules.ATTRIBUTION_MAX}
    assert kept.page_url == "https://www.example.com/pricing?plan=pro"
    assert kept.referrer == "https://news.example.org/story"
    assert "unknown_key" not in kept.as_dict()


def test_attribution_drops_foreign_pages_and_unsafe_urls() -> None:
    dropped = rules.attribution(
        {"page_url": "https://evil.example/x", "referrer": "javascript:alert(1)"},
        "https://www.example.com",
    )
    assert dropped.page_url is None
    assert dropped.referrer is None
    assert rules.attribution("not an object", None).empty
    assert rules.attribution({"page_url": "https://www.example.com/"}, None).page_url is None
