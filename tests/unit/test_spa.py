"""Which file the frontend routes send (`crm_app.api.spa.resolve`)."""

from __future__ import annotations

from pathlib import Path

import pytest

from crm_app.api.spa import IMMUTABLE, REVALIDATE, SECURITY_HEADERS, resolve


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    root = tmp_path / "dist"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text("<!doctype html>", encoding="utf-8")
    (root / "assets" / "index-abc123.js").write_text("", encoding="utf-8")
    (root / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    (root / ".env").write_text("SECRET=1", encoding="utf-8")
    (tmp_path / "outside.txt").write_text("outside", encoding="utf-8")
    return root.resolve()


def test_app_routes_get_the_index_and_are_revalidated(dist: Path) -> None:
    for requested in ("", "w/7d5f/members", "settings"):
        assert resolve(dist, requested) == (dist / "index.html", REVALIDATE)


def test_fingerprinted_assets_are_cached_for_good(dist: Path) -> None:
    assert resolve(dist, "assets/index-abc123.js") == (
        dist / "assets" / "index-abc123.js",
        IMMUTABLE,
    )
    assert resolve(dist, "favicon.svg") == (dist / "favicon.svg", REVALIDATE)


def test_missing_files_with_an_extension_are_not_found(dist: Path) -> None:
    assert resolve(dist, "assets/missing.js") is None


def test_nothing_outside_the_build_or_hidden_is_served(dist: Path) -> None:
    assert resolve(dist, "../outside.txt") is None
    assert resolve(dist, "assets/../../outside.txt") is None
    assert resolve(dist, ".env") is None


def test_without_a_build_nothing_is_served(tmp_path: Path) -> None:
    assert resolve(tmp_path, "") is None


def test_the_policy_allows_only_same_origin_resources() -> None:
    policy = SECURITY_HEADERS["Content-Security-Policy"]
    assert "default-src 'self'" in policy
    assert "frame-ancestors 'none'" in policy
    assert "unsafe" not in policy
