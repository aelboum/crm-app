"""The entrypoints validate configuration before SaaS-OS reads it.

Each case runs in a fresh interpreter, because SaaS-OS resolves and caches
configuration per process. No service is contacted: the placeholder
settings point at addresses nothing listens on.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.support import PLACEHOLDER_SETTINGS, clean_environment, run_module, run_python

MARKER = "do-not-leak-91c2"


def test_importing_the_entrypoints_reads_no_configuration(tmp_path: Path) -> None:
    result = run_python(
        "import crm_app.app, crm_app.worker, crm_app.migrate, crm_app.permissions",
        clean_environment(),
        tmp_path,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ("code", "expected_missing"),
    [
        ("from crm_app.app import create_app; create_app()", "OIDC_CLIENT_ID is not set."),
        ("from crm_app.worker import run; run([])", "REDIS_URL is not set."),
        ("from crm_app.migrate import migrate; migrate()", "MIGRATIONS_DATABASE_URL is not set."),
    ],
)
def test_entrypoints_fail_closed_without_leaking_values(
    code: str, expected_missing: str, tmp_path: Path
) -> None:
    env = clean_environment(
        {"ENVIRONMENT": "test", "DATABASE_URL": f"postgresql://{MARKER}:{MARKER}@db/{MARKER}"}
    )
    result = run_python(code, env, tmp_path)
    assert result.returncode != 0
    assert "crm_app.settings.ConfigurationError" in result.stderr
    assert expected_missing in result.stderr
    assert MARKER not in result.stderr
    assert MARKER not in result.stdout


def test_entrypoint_without_environment_names_the_problem(tmp_path: Path) -> None:
    result = run_python(
        "from crm_app.app import create_app; create_app()", clean_environment(), tmp_path
    )
    assert result.returncode != 0
    assert "ENVIRONMENT is not set" in result.stderr


def test_worker_script_fails_closed(tmp_path: Path) -> None:
    result = run_module("crm_app.worker", ["--check"], clean_environment(), tmp_path)
    assert result.returncode != 0
    assert "ConfigurationError" in result.stderr


def test_create_app_builds_on_the_platform_without_contacting_services(tmp_path: Path) -> None:
    code = (
        "import json\n"
        "from crm_app.app import create_app\n"
        "app = create_app()\n"
        "print(json.dumps({'title': app.title, 'paths': sorted(app.openapi()['paths'])}))\n"
    )
    result = run_python(code, clean_environment(PLACEHOLDER_SETTINGS), tmp_path)
    assert result.returncode == 0, result.stderr
    built = json.loads(result.stdout.strip().splitlines()[-1])
    assert built["title"] == "crm-app"
    assert {"/auth/login", "/auth/callback", "/auth/logout", "/auth/me"} <= set(built["paths"])
