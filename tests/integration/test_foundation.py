"""Phase 1 foundation, end to end against PostgreSQL and Redis.

Covered: both migration histories in order and idempotent; the product
schema and its grants; application startup on the platform's fail-closed
checks, with health and readiness; refusal of an application role that can
bypass Row-Level Security; and the worker starting with its health probe.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import psycopg
import pytest

from tests.support import run_module, run_python

SAAS_OS_MIGRATION_HEAD = "f6a2c8e4b1d9"
PRODUCT_MIGRATION_HEAD = "0008_custom_fields"

_STARTUP_PROBE = (
    "import json\n"
    "from fastapi.testclient import TestClient\n"
    "from crm_app.app import create_app\n"
    "with TestClient(create_app()) as client:\n"
    "    result = {p: client.get(p).status_code for p in ('/healthz', '/readyz', '/auth/me')}\n"
    "print('PROBE ' + json.dumps(result))\n"
)


def _probe_result(stdout: str) -> dict[str, int]:
    lines = [line for line in stdout.splitlines() if line.startswith("PROBE ")]
    assert len(lines) == 1, stdout
    return json.loads(lines[0].removeprefix("PROBE "))


@pytest.mark.usefixtures("migrated")
def test_both_migration_histories_are_at_head(owner_connection: psycopg.Connection) -> None:
    platform = owner_connection.execute(
        "SELECT version_num FROM alembic_version_saas_os"
    ).fetchall()
    product = owner_connection.execute("SELECT version_num FROM alembic_version").fetchall()
    assert platform == [(SAAS_OS_MIGRATION_HEAD,)]
    assert product == [(PRODUCT_MIGRATION_HEAD,)]


@pytest.mark.usefixtures("migrated")
def test_application_role_has_usage_but_cannot_create_in_the_product_schema(
    integration_env: dict[str, str], owner_connection: psycopg.Connection
) -> None:
    role = integration_env["APP_DB_USER"]
    row = owner_connection.execute(
        "SELECT has_schema_privilege(%s, 'crm_app', 'USAGE'),"
        " has_schema_privilege(%s, 'crm_app', 'CREATE'),"
        " has_schema_privilege('public', 'crm_app', 'USAGE')",
        (role, role),
    ).fetchone()
    assert row == (True, False, False)


def test_application_role_is_restricted(
    integration_env: dict[str, str], owner_connection: psycopg.Connection
) -> None:
    row = owner_connection.execute(
        "SELECT rolsuper, rolbypassrls, rolcreaterole, rolcreatedb"
        " FROM pg_roles WHERE rolname = %s",
        (integration_env["APP_DB_USER"],),
    ).fetchone()
    assert row == (False, False, False, False)


@pytest.mark.usefixtures("migrated")
def test_application_starts_and_reports_ready(
    integration_env: dict[str, str], tmp_path: Path
) -> None:
    result = run_python(_STARTUP_PROBE, integration_env, tmp_path)
    assert result.returncode == 0, result.stderr
    assert _probe_result(result.stdout) == {"/healthz": 200, "/readyz": 200, "/auth/me": 401}


@pytest.mark.usefixtures("migrated")
def test_application_refuses_a_role_that_can_bypass_rls(
    integration_env: dict[str, str], unsafe_role_url: str, tmp_path: Path
) -> None:
    env = {**integration_env, "DATABASE_URL": unsafe_role_url}
    result = run_python(_STARTUP_PROBE, env, tmp_path)
    assert result.returncode != 0
    assert "UnsafeDatabaseRoleError" in result.stderr
    assert "PROBE " not in result.stdout


@pytest.mark.usefixtures("migrated")
def test_worker_starts_and_passes_its_health_probe(
    integration_env: dict[str, str], tmp_path: Path
) -> None:
    worker = subprocess.Popen(
        [sys.executable, "-m", "crm_app.worker"],
        env=integration_env,
        cwd=tmp_path,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 60
        while True:
            check = run_module("crm_app.worker", ["--check"], integration_env, tmp_path, timeout=30)
            if check.returncode == 0:
                break
            assert worker.poll() is None, "worker exited early"
            assert time.monotonic() < deadline, f"worker never became healthy:\n{check.stderr}"
            time.sleep(1)
    finally:
        worker.terminate()
        try:
            worker.wait(timeout=30)
        except subprocess.TimeoutExpired:
            worker.kill()
            worker.wait(timeout=30)


def test_worker_health_probe_fails_when_no_worker_runs(
    integration_env: dict[str, str], tmp_path: Path
) -> None:
    """Uses its own Redis database so a worker left by another test cannot
    satisfy the probe."""
    env = {**integration_env, "REDIS_URL": integration_env["REDIS_URL"].rsplit("/", 1)[0] + "/15"}
    result = run_module("crm_app.worker", ["--check"], env, tmp_path, timeout=30)
    assert result.returncode != 0
