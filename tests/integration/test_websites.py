"""Website integration (decision P12-W).

Drives `website_probe` in a fresh interpreter: websites are managed by
members who manage forms and read by members who read forms, with plain
https origins only; a published form accepts a browser submission only
from an origin listed for an active website of its own workspace, answers
it with CORS headers for that origin alone, and refuses others (403) and
their preflights; the hosted page and server-side callers keep working;
the submission records the website and its attribution, dropping a page
from another origin; disabling or removing a website stops it, and
removing keeps the submissions without the link.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from tests.support import REPO_ROOT, run_module

pytestmark = pytest.mark.usefixtures("migrated")

Probe = dict[str, Any]
SITE = "https://www.acme-shop.example"


@pytest.fixture(scope="module")
def probe(integration_env: dict[str, str], tmp_path_factory: pytest.TempPathFactory) -> Probe:
    env = {
        **integration_env,
        "PYTHONPATH": str(REPO_ROOT),
        "RATE_LIMIT_REQUESTS_PER_WINDOW": "1000",
    }
    tmp = tmp_path_factory.mktemp("websites")
    result = run_module("tests.integration.website_probe", [], env, tmp, timeout=600)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def test_websites_are_managed_by_form_managers_with_plain_https_origins(probe: Probe) -> None:
    assert probe["created"] == [201, "Acme shop", [SITE, "https://acme-shop.example"]]
    # http, wildcard, none, a member, another workspace's owner
    assert probe["refused"] == [422, 422, 422, 403, 404]
    assert probe["member_reads"] == 1
    assert probe["other_lists"] == 0


def test_only_listed_origins_of_the_forms_own_workspace_may_submit(probe: Probe) -> None:
    assert probe["allowed"] == [201, SITE]
    assert probe["unlisted"] == [403, None]
    assert probe["other_workspace_site"] == [403, None]
    assert probe["preflight"] == [204, SITE, True]
    assert probe["preflight_refused"] == [403, None]


def test_the_hosted_page_and_servers_keep_working(probe: Probe) -> None:
    assert probe["no_origin"] == [201, None]
    assert probe["same_origin"] == [201, None]


def test_submissions_keep_their_website_and_attribution(probe: Probe) -> None:
    first, no_origin, same_origin, foreign = probe["stored"][:4]
    assert first == {
        "website": probe["site_id"],
        "attribution": {
            "utm_source": "newsletter",
            "utm_campaign": "autumn",
            "page_url": f"{SITE}/contact?utm_source=newsletter",
            "referrer": "https://search.example/q",
        },
    }
    assert no_origin == {"website": None, "attribution": None}
    assert same_origin == {"website": None, "attribution": None}
    # A page on another origin than the request's is dropped.
    assert foreign == {"website": probe["site_id"], "attribution": None}


def test_disabling_or_removing_a_website_stops_it(probe: Probe) -> None:
    assert probe["disabled"] == [200, 403]
    assert probe["stale"] == 409
    assert probe["enabled"] == [200, 201]
    # a member, another workspace's owner, the owner, then a submission
    assert probe["removed"] == [403, 404, 204, 403]
    assert probe["kept_submissions"] == 5
    assert probe["unlinked"] == 0
