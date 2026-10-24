"""Configuration validation: every problem reported at once, no value leaked."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from pathlib import Path

import pytest
from saas_os.infra.secrets import get_secrets_provider

from crm_app.settings import ConfigurationError, Process, validate_settings
from tests.support import CONFIG_NAMES, PLACEHOLDER_SETTINGS

MARKER = "do-not-leak-7f3a"


def _validate(process: Process, env: Mapping[str, str]) -> None:
    validate_settings(process, environ=env, secret_lookup=env.get)


def _problems(process: Process, env: Mapping[str, str]) -> list[str]:
    with pytest.raises(ConfigurationError) as caught:
        _validate(process, env)
    return caught.value.problems


@pytest.mark.parametrize("process", list(Process))
def test_valid_placeholder_settings_pass(process: Process) -> None:
    _validate(process, PLACEHOLDER_SETTINGS)


def test_missing_environment_is_reported_first() -> None:
    problems = _problems(Process.APP, {})
    assert problems == [
        "ENVIRONMENT is not set; set it to one of ['development', 'production', 'test']."
    ]


def test_unknown_environment_is_refused() -> None:
    problems = _problems(Process.APP, {"ENVIRONMENT": "staging"})
    assert len(problems) == 1
    assert problems[0].startswith("ENVIRONMENT must be one of")


@pytest.mark.parametrize(
    ("process", "expected"),
    [
        (
            Process.APP,
            {"DATABASE_URL", "REDIS_URL", "OIDC_ISSUER_URL", "OIDC_CLIENT_ID", "PUBLIC_APP_ORIGIN"},
        ),
        (Process.WORKER, {"DATABASE_URL", "REDIS_URL"}),
        (Process.MIGRATE, {"DATABASE_URL", "MIGRATIONS_DATABASE_URL", "REDIS_URL"}),
    ],
)
def test_every_missing_setting_is_reported_together(process: Process, expected: set[str]) -> None:
    problems = _problems(process, {"ENVIRONMENT": "test"})
    assert {problem.split(" ")[0] for problem in problems} == expected


def test_an_empty_value_counts_as_missing() -> None:
    problems = _problems(Process.WORKER, {**PLACEHOLDER_SETTINGS, "REDIS_URL": ""})
    assert problems == ["REDIS_URL is not set."]


def test_messages_never_contain_configuration_values() -> None:
    env = {
        "ENVIRONMENT": "production",
        "DATABASE_URL": f"mysql://{MARKER}:{MARKER}@db/{MARKER}",
        "MIGRATIONS_DATABASE_URL": f"postgresql://same:{MARKER}@db/{MARKER}",
        "REDIS_URL": f"memcached://{MARKER}",
        "OIDC_ISSUER_URL": f"http://{MARKER}.example",
        "OIDC_CLIENT_ID": MARKER,
        "PUBLIC_APP_ORIGIN": f"https://{MARKER}.example/path?{MARKER}",
        "APP_DB_USER": f"{MARKER}; DROP",
    }
    with pytest.raises(ConfigurationError) as caught:
        _validate(Process.APP, env)
    assert len(caught.value.problems) >= 5
    assert MARKER not in str(caught.value)


def test_application_role_must_differ_from_migration_role() -> None:
    env = {
        **PLACEHOLDER_SETTINGS,
        "DATABASE_URL": "postgresql+psycopg://owner:a@db:5432/crm",
        "MIGRATIONS_DATABASE_URL": "postgresql+psycopg://owner:b@db:5432/crm",
    }
    problems = _problems(Process.MIGRATE, env)
    assert len(problems) == 1
    assert "different database roles" in problems[0]


@pytest.mark.parametrize("process", [Process.APP, Process.WORKER])
def test_platform_configuration_credential_is_refused_at_runtime(process: Process) -> None:
    env = {**PLACEHOLDER_SETTINGS, "PLATFORM_CONFIG_DATABASE_URL": "postgresql://cfg:x@db/crm"}
    problems = _problems(process, env)
    assert problems == [
        "PLATFORM_CONFIG_DATABASE_URL must not be present in the "
        f"{process} environment (it is the platform-configuration credential)."
    ]


def test_production_requires_https_for_browser_facing_urls() -> None:
    env = {
        **PLACEHOLDER_SETTINGS,
        "ENVIRONMENT": "production",
        "OIDC_ISSUER_URL": "http://identity.example",
        "PUBLIC_APP_ORIGIN": "http://app.example",
    }
    problems = _problems(Process.APP, env)
    assert problems == [
        "OIDC_ISSUER_URL must use https in production.",
        "PUBLIC_APP_ORIGIN must use https in production.",
    ]


def test_development_allows_local_http_urls() -> None:
    env = {
        **PLACEHOLDER_SETTINGS,
        "ENVIRONMENT": "development",
        "OIDC_ISSUER_URL": "http://zitadel.localhost:8081",
        "PUBLIC_APP_ORIGIN": "http://localhost:8000",
    }
    _validate(Process.APP, env)


@pytest.mark.parametrize(
    "origin",
    [
        "https://app.example/path",
        "https://app.example?x=1",
        "https://user@app.example",
        "app.example",
    ],
)
def test_public_app_origin_must_be_an_origin(origin: str) -> None:
    problems = _problems(Process.APP, {**PLACEHOLDER_SETTINGS, "PUBLIC_APP_ORIGIN": origin})
    assert len(problems) == 1
    assert problems[0].startswith("PUBLIC_APP_ORIGIN must be")


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("DATABASE_URL", "mysql://app:x@db/crm"),
        ("DATABASE_URL", "postgresql://"),
        ("REDIS_URL", "http://redis:6379"),
    ],
)
def test_connection_urls_are_checked(name: str, value: str) -> None:
    problems = _problems(Process.WORKER, {**PLACEHOLDER_SETTINGS, name: value})
    assert len(problems) == 1
    assert problems[0].startswith(f"{name} must be")


@pytest.mark.parametrize("name", ["APP_DB_USER", "PLATFORM_CONFIG_DB_USER"])
def test_role_names_must_be_plain_identifiers(name: str) -> None:
    problems = _problems(Process.MIGRATE, {**PLACEHOLDER_SETTINGS, name: 'app"; drop'})
    assert problems == [f"{name} must be a plain SQL identifier."]


@pytest.fixture
def isolated_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """The real process environment, emptied of configuration, with the
    SaaS-OS secrets-provider cache cleared before and after."""
    for name in CONFIG_NAMES:
        monkeypatch.delenv(name, raising=False)
    get_secrets_provider.cache_clear()
    yield
    get_secrets_provider.cache_clear()


@pytest.mark.usefixtures("isolated_environment")
def test_secrets_are_read_through_the_saas_os_provider_in_development(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """In development SaaS-OS reads secrets from a `.env` file; validation
    must see exactly what the platform will see."""
    env_file = tmp_path / "local.env"
    secrets = {
        k: v
        for k, v in PLACEHOLDER_SETTINGS.items()
        if k not in ("ENVIRONMENT", "PUBLIC_APP_ORIGIN")
    }
    env_file.write_text("".join(f"{k}={v}\n" for k, v in secrets.items()), encoding="utf-8")
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("SECRETS_ENV_FILE", str(env_file))
    monkeypatch.setenv("PUBLIC_APP_ORIGIN", "http://localhost:8000")

    validate_settings(Process.APP)


@pytest.mark.usefixtures("isolated_environment")
def test_outside_development_secrets_come_from_the_process_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A `.env` file is ignored outside development, as SaaS-OS ignores it."""
    env_file = tmp_path / "local.env"
    env_file.write_text("DATABASE_URL=postgresql://app:x@db/crm\n", encoding="utf-8")
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("SECRETS_ENV_FILE", str(env_file))
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")

    with pytest.raises(ConfigurationError) as caught:
        validate_settings(Process.WORKER)
    assert caught.value.problems == ["DATABASE_URL is not set."]


def test_invitation_delivery_defaults_to_manual_and_accepts_only_known_modes() -> None:
    _validate(Process.APP, PLACEHOLDER_SETTINGS)  # unset: manual (decision Q4)
    _validate(Process.APP, {**PLACEHOLDER_SETTINGS, "INVITATION_DELIVERY": "manual"})
    problems = _problems(Process.APP, {**PLACEHOLDER_SETTINGS, "INVITATION_DELIVERY": "sms"})
    assert problems == ["INVITATION_DELIVERY must be one of ['manual', 'email']."]


def test_email_delivery_needs_a_sender_and_an_explicit_provider() -> None:
    email = {**PLACEHOLDER_SETTINGS, "INVITATION_DELIVERY": "email"}
    assert _problems(Process.APP, email) == [
        "INVITATION_DELIVERY=email needs EMAIL_DEFAULT_SENDER."
    ]
    with_sender = {**email, "EMAIL_DEFAULT_SENDER": "crm@example.test"}
    assert _problems(Process.APP, with_sender) == [
        "INVITATION_DELIVERY=email needs EMAIL_PROVIDER set to smtp or mailpit."
    ]
    _validate(Process.APP, {**with_sender, "EMAIL_PROVIDER": "mailpit"})
    # The worker sends no invitations, so it does not check the setting.
    _validate(Process.WORKER, {**PLACEHOLDER_SETTINGS, "INVITATION_DELIVERY": "sms"})
