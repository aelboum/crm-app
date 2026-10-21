"""Configuration validation, run before SaaS-OS is imported.

SaaS-OS reads its configuration when its modules are imported, and each
module stops at the first value it is missing. This module checks
everything one process needs, in one pass, before any SaaS-OS module that
reads configuration is imported, and reports every problem at once.

Rules this module keeps:

- Messages name variables and describe the problem. They never contain a
  value, because values here are credentials and connection strings.
- Secrets are read the way SaaS-OS reads them: through
  `saas_os.infra.secrets.get_secrets_provider()` (a `.env` file in
  development, the process environment otherwise). Non-secret settings are
  read from the process environment, as SaaS-OS reads them.
- Validation never contacts a service. Reachability is checked by the
  platform's own startup checks and `/readyz`.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Mapping
from enum import StrEnum
from urllib.parse import SplitResult, urlsplit

ENVIRONMENTS = frozenset({"development", "test", "production"})

# A plain SQL identifier, as SaaS-OS's own migrations require for role names.
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class Process(StrEnum):
    """The processes this product runs. Each needs a different subset."""

    APP = "app"
    WORKER = "worker"
    MIGRATE = "migrate"


# Secrets and connection strings each process needs, read through the
# SaaS-OS secrets provider. MIGRATE needs REDIS_URL because registering
# permissions imports SaaS-OS modules that resolve it at import time.
_REQUIRED_SECRETS: dict[Process, tuple[str, ...]] = {
    Process.APP: ("DATABASE_URL", "REDIS_URL", "OIDC_ISSUER_URL", "OIDC_CLIENT_ID"),
    Process.WORKER: ("DATABASE_URL", "REDIS_URL"),
    Process.MIGRATE: ("DATABASE_URL", "MIGRATIONS_DATABASE_URL", "REDIS_URL"),
}

# Non-secret settings each process needs, read from the process environment.
_REQUIRED_PLAIN: dict[Process, tuple[str, ...]] = {
    Process.APP: ("PUBLIC_APP_ORIGIN",),
    Process.WORKER: (),
    Process.MIGRATE: (),
}

# The platform-configuration credential must never reach the application or
# the worker (SaaS-OS ADR-0056); SaaS-OS refuses to start if it does.
_FORBIDDEN_FOR_RUNTIME = ("PLATFORM_CONFIG_DATABASE_URL",)


class ConfigurationError(RuntimeError):
    """The environment cannot run the requested process.

    `problems` lists one human-readable line per problem. No line contains a
    configuration value.
    """

    def __init__(self, process: Process, problems: list[str]) -> None:
        self.process = process
        self.problems = problems
        lines = "\n".join(f"  - {problem}" for problem in problems)
        super().__init__(f"Configuration is not valid for the {process} process:\n{lines}")


SecretLookup = Callable[[str], "str | None"]


def _platform_secret_lookup() -> SecretLookup:
    # Safe to import before validation: this module reads nothing at import.
    from saas_os.infra.secrets import get_secrets_provider  # noqa: PLC0415

    return get_secrets_provider().get


def validate_settings(
    process: Process,
    *,
    environ: Mapping[str, str] | None = None,
    secret_lookup: SecretLookup | None = None,
) -> None:
    """Raise `ConfigurationError` listing every problem, or return `None`.

    `environ` and `secret_lookup` exist for tests; by default they are the
    process environment and the SaaS-OS secrets provider.
    """
    env = os.environ if environ is None else environ
    problems: list[str] = []

    environment = env.get("ENVIRONMENT")
    if not environment:
        problems.append(f"ENVIRONMENT is not set; set it to one of {sorted(ENVIRONMENTS)}.")
        # The secrets provider cannot be chosen without ENVIRONMENT.
        raise ConfigurationError(process, problems)
    if environment not in ENVIRONMENTS:
        problems.append(f"ENVIRONMENT must be one of {sorted(ENVIRONMENTS)}.")
        raise ConfigurationError(process, problems)

    lookup = secret_lookup if secret_lookup is not None else _platform_secret_lookup()

    values: dict[str, str] = {}
    for name in _REQUIRED_SECRETS[process]:
        value = lookup(name)
        if not value:
            problems.append(f"{name} is not set.")
        else:
            values[name] = value
    for name in _REQUIRED_PLAIN[process]:
        value = env.get(name)
        if not value:
            problems.append(f"{name} is not set.")
        else:
            values[name] = value

    if process in (Process.APP, Process.WORKER):
        problems.extend(
            f"{name} must not be present in the {process} environment "
            "(it is the platform-configuration credential)."
            for name in _FORBIDDEN_FOR_RUNTIME
            if lookup(name) or env.get(name)
        )

    production = environment == "production"
    problems.extend(_check_database_urls(values))
    problems.extend(_check_redis_url(values))
    problems.extend(_check_http_url(values, "OIDC_ISSUER_URL", require_https=production))
    problems.extend(_check_origin(values, require_https=production))
    problems.extend(_check_role_names(env))

    if problems:
        raise ConfigurationError(process, problems)


def _split(value: str) -> SplitResult | None:
    try:
        return urlsplit(value)
    except ValueError:
        return None


def _check_database_urls(values: Mapping[str, str]) -> list[str]:
    problems: list[str] = []
    users: dict[str, str | None] = {}
    for name in ("DATABASE_URL", "MIGRATIONS_DATABASE_URL"):
        if name not in values:
            continue
        parts = _split(values[name])
        if parts is None or not parts.scheme.startswith("postgresql") or not parts.hostname:
            problems.append(f"{name} must be a postgresql:// URL with a host.")
            continue
        users[name] = parts.username
    if (
        "DATABASE_URL" in users
        and "MIGRATIONS_DATABASE_URL" in users
        and users["DATABASE_URL"] == users["MIGRATIONS_DATABASE_URL"]
    ):
        problems.append(
            "DATABASE_URL and MIGRATIONS_DATABASE_URL must use different database roles "
            "(the application role must not be the migration role)."
        )
    return problems


def _check_redis_url(values: Mapping[str, str]) -> list[str]:
    if "REDIS_URL" not in values:
        return []
    parts = _split(values["REDIS_URL"])
    if parts is None or parts.scheme not in ("redis", "rediss") or not parts.hostname:
        return ["REDIS_URL must be a redis:// or rediss:// URL with a host."]
    return []


def _check_http_url(values: Mapping[str, str], name: str, *, require_https: bool) -> list[str]:
    if name not in values:
        return []
    parts = _split(values[name])
    if parts is None or parts.scheme not in ("http", "https") or not parts.hostname:
        return [f"{name} must be an http:// or https:// URL with a host."]
    if require_https and parts.scheme != "https":
        return [f"{name} must use https in production."]
    return []


def _check_origin(values: Mapping[str, str], *, require_https: bool) -> list[str]:
    if "PUBLIC_APP_ORIGIN" not in values:
        return []
    problems = _check_http_url(values, "PUBLIC_APP_ORIGIN", require_https=require_https)
    if problems:
        return problems
    parts = _split(values["PUBLIC_APP_ORIGIN"])
    if parts is not None and (
        parts.path not in ("", "/") or parts.query or parts.fragment or parts.username
    ):
        return ["PUBLIC_APP_ORIGIN must be an origin only (scheme, host and optional port)."]
    return []


def _check_role_names(env: Mapping[str, str]) -> list[str]:
    return [
        f"{name} must be a plain SQL identifier."
        for name in ("APP_DB_USER", "PLATFORM_CONFIG_DB_USER")
        if env.get(name) and not _IDENTIFIER.fullmatch(env[name])
    ]
