"""Helpers shared by unit and integration tests."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

from crm_app.purge import PURGE_TABLES

REPO_ROOT = Path(__file__).resolve().parent.parent

# Every setting this product or SaaS-OS reads. A child process starts with
# none of them unless a test passes them explicitly.
CONFIG_NAMES = (
    "ENVIRONMENT",
    "SECRETS_ENV_FILE",
    "DATABASE_URL",
    "MIGRATIONS_DATABASE_URL",
    "PLATFORM_CONFIG_DATABASE_URL",
    "APP_DB_USER",
    "PLATFORM_CONFIG_DB_USER",
    "REDIS_URL",
    "OIDC_ISSUER_URL",
    "OIDC_CLIENT_ID",
    "OIDC_CLIENT_SECRET",
    "PUBLIC_APP_ORIGIN",
)

# Syntactically valid settings that point at nothing reachable.
PLACEHOLDER_SETTINGS = {
    "ENVIRONMENT": "test",
    "DATABASE_URL": "postgresql+psycopg://placeholder_app:x@127.0.0.1:1/placeholder",
    "MIGRATIONS_DATABASE_URL": "postgresql+psycopg://placeholder_owner:x@127.0.0.1:1/placeholder",
    "REDIS_URL": "redis://127.0.0.1:1/0",
    "OIDC_ISSUER_URL": "https://identity.invalid",
    "OIDC_CLIENT_ID": "placeholder-client",
    "PUBLIC_APP_ORIGIN": "https://app.invalid",
}


# Tables the product schema `crm_app` may contain, each approved by a
# decision (P3-A: `company`, `contact`; P3-B: `note`, `activity`). The guards
# in `tests/unit/test_schema_guard.py` and
# `tests/integration/test_tenant_table_guard.py` fail if a migration adds a
# table that is not listed here.
PRODUCT_TABLES: frozenset[str] = frozenset({"company", "contact", "note", "activity"})

# Tenant tables the application may only append to and delete from (P3-B D6:
# the record history). The guard requires the runtime role to lack UPDATE on
# them, a stricter rule than for other tables, never a looser one.
APPEND_ONLY_TABLES: frozenset[str] = frozenset({"activity"})

# Product tables that deliberately hold no tenant data and so carry no
# `tenant_id`. Every other product table must be tenant-owned; listing a
# table here is a reviewed decision, never a way past the RLS and purge
# guards.
GLOBAL_TABLES: frozenset[str] = frozenset()

# Tenant-owned tables whose rows a tenant purge removes: the purge
# participant's own manifest (`crm_app.purge.PURGE_TABLES`), so the guard
# checks what the participant actually deletes.
PURGE_COVERED_TABLES: frozenset[str] = frozenset(PURGE_TABLES)


def clean_environment(overrides: Mapping[str, str] | None = None) -> dict[str, str]:
    """The current environment without any configuration, plus `overrides`."""
    env = {key: value for key, value in os.environ.items() if key not in CONFIG_NAMES}
    env.update(overrides or {})
    return env


def run_python(
    code: str,
    env: Mapping[str, str],
    cwd: Path,
    timeout: float = 120,
) -> subprocess.CompletedProcess[str]:
    """Run `code` in a fresh interpreter: SaaS-OS caches configuration per process."""
    return subprocess.run(
        [sys.executable, "-c", code],
        env=dict(env),
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def run_module(
    module: str,
    args: list[str],
    env: Mapping[str, str],
    cwd: Path,
    timeout: float = 300,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", module, *args],
        env=dict(env),
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
