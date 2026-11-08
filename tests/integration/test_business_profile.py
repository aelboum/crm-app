"""The business's contact details (decision P2-BP).

Drives `business_profile_probe` in a fresh interpreter: values are
normalised, refused when malformed, saved only by those who may change
the workspace, cleared with an empty string, and shown on a public
booking page only when the workspace chooses to show them.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from tests.support import REPO_ROOT, run_module

pytestmark = pytest.mark.usefixtures("migrated")

Probe = dict[str, Any]


@pytest.fixture(scope="module")
def probe(integration_env: dict[str, str], tmp_path_factory: pytest.TempPathFactory) -> Probe:
    env = {**integration_env, "PYTHONPATH": str(REPO_ROOT)}
    tmp = tmp_path_factory.mktemp("business-profile")
    result = run_module("tests.integration.business_profile_probe", [], env, tmp, timeout=600)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def test_a_new_workspace_has_no_contact_details_and_hides_them(probe: Probe) -> None:
    assert probe["defaults"] == {
        "business_hours": None,
        "business_phone": None,
        "business_email": None,
        "business_website": None,
        "business_address": None,
        "business_contact_public": False,
    }


def test_details_are_stored_normalised(probe: Probe) -> None:
    status, saved = probe["saved"]
    assert status == 200
    assert saved == {
        "business_phone": "+31 20 123 4567",
        "business_email": "hello@example.test",
        "business_website": "https://www.example.test",
        "business_address": "Keizersgracht 1\n1015 CJ Amsterdam",
    }


def test_only_owners_and_admins_save_and_malformed_values_are_refused(probe: Probe) -> None:
    assert probe["member"] == 403
    assert set(probe["refused"].values()) == {422}


def test_booking_pages_show_them_only_when_chosen(probe: Probe) -> None:
    assert probe["hidden"] is None
    assert probe["shown"] == {
        "phone": "+31 20 123 4567",
        "email": "hello@example.test",
        "website": "https://www.example.test",
        "address": "Keizersgracht 1\n1015 CJ Amsterdam",
    }
    # Shown but nothing left to show: no contact block at all.
    assert probe["all_cleared"] is None


def test_an_empty_string_clears_and_null_keeps(probe: Probe) -> None:
    assert probe["cleared"] == {"business_phone": None, "business_email": "hello@example.test"}
