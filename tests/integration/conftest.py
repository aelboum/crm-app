"""Integration tests run against real PostgreSQL and Redis.

They need the integration settings exported in the process environment
(locally from `.env.test`, see README.md; in CI from the workflow) and are
skipped otherwise, so the unit suite runs anywhere. Each test drives the
product through a fresh interpreter, because SaaS-OS caches its
configuration per process.
"""

from __future__ import annotations

import os
import secrets
from collections.abc import Iterator
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
from psycopg import sql

from tests.support import clean_environment

REQUIRED = (
    "ENVIRONMENT",
    "DATABASE_URL",
    "MIGRATIONS_DATABASE_URL",
    "REDIS_URL",
    "APP_DB_USER",
    "OIDC_ISSUER_URL",
    "OIDC_CLIENT_ID",
    "PUBLIC_APP_ORIGIN",
)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if "tests/integration" in item.nodeid.replace("\\", "/"):
            item.add_marker(pytest.mark.integration)


@pytest.fixture(scope="session")
def integration_env() -> dict[str, str]:
    missing = [name for name in REQUIRED if not os.environ.get(name)]
    if missing:
        message = f"integration settings not exported: {', '.join(missing)}"
        # CI sets this so a misconfigured job fails instead of passing by skipping.
        if os.environ.get("CRM_APP_REQUIRE_INTEGRATION") == "1":
            pytest.fail(message)
        pytest.skip(message)
    if os.environ["ENVIRONMENT"] != "test":
        pytest.fail("integration tests require ENVIRONMENT=test")
    return clean_environment({name: os.environ[name] for name in REQUIRED})


def libpq_url(url: str) -> str:
    """A SQLAlchemy URL (`postgresql+psycopg://`) as a libpq URL."""
    parts = urlsplit(url)
    return urlunsplit(parts._replace(scheme="postgresql"))


@pytest.fixture(scope="session")
def owner_connection(integration_env: dict[str, str]) -> Iterator[psycopg.Connection]:
    with psycopg.connect(
        libpq_url(integration_env["MIGRATIONS_DATABASE_URL"]), autocommit=True
    ) as connection:
        yield connection


@pytest.fixture
def unsafe_role_url(
    integration_env: dict[str, str], owner_connection: psycopg.Connection
) -> Iterator[str]:
    """A login role that can bypass Row-Level Security, for the negative test.
    Created for one test and dropped afterwards."""
    role = f"crm_app_unsafe_probe_{secrets.token_hex(4)}"
    password = secrets.token_urlsafe(16)
    owner_connection.execute(
        sql.SQL("CREATE ROLE {} LOGIN BYPASSRLS PASSWORD {}").format(
            sql.Identifier(role), sql.Literal(password)
        )
    )
    database = urlsplit(integration_env["DATABASE_URL"]).path.lstrip("/")
    owner_connection.execute(
        sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
            sql.Identifier(database), sql.Identifier(role)
        )
    )
    parts = urlsplit(integration_env["DATABASE_URL"])
    netloc = f"{role}:{password}@{parts.hostname}:{parts.port}"
    try:
        yield urlunsplit(parts._replace(netloc=netloc))
    finally:
        owner_connection.execute(
            sql.SQL("REVOKE CONNECT ON DATABASE {} FROM {}").format(
                sql.Identifier(database), sql.Identifier(role)
            )
        )
        owner_connection.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))
