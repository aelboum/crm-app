"""The settings template lists every setting by name, with no secret value
(decision D-STG.4; `deploy/staging/env.template`).

Every setting the product requires (`crm_app.settings`), every setting the
local rehearsal writes for the app, worker and migrations
(`deploy/staging/prepare_local.py`) and every setting a host timer reads is
named in the template; every name marked `[secret]` has no value; every
email switch and signup is off. A new required setting without a line in
the template fails here.
"""

from __future__ import annotations

import importlib.util
import re
from types import ModuleType

from crm_app import settings
from tests.support import REPO_ROOT

STAGING = REPO_ROOT / "deploy" / "staging"
TEMPLATE = STAGING / "env.template"
_LINE = re.compile(r"^([A-Z][A-Z0-9_]+)=([^#]*?)\s*(#.*)?$")
_PASSWORDS = (
    "admin",
    "owner",
    "runtime",
    "redis",
    "zitadel_db",
    "masterkey",
    "login_cookie",
    "zitadel_admin",
    "field_key",
)


def _template() -> dict[str, tuple[str, str]]:
    found: dict[str, tuple[str, str]] = {}
    for line in TEMPLATE.read_text(encoding="utf-8").splitlines():
        match = _LINE.match(line)
        if match:
            found[match.group(1)] = (match.group(2).strip(), match.group(3) or "")
    return found


def _prepare_local() -> ModuleType:
    spec = importlib.util.spec_from_file_location("prepare_local", STAGING / "prepare_local.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _rehearsal_names() -> set[str]:
    files = _prepare_local()._files(dict.fromkeys(_PASSWORDS, "x"))
    names: set[str] = set()
    for name in ("app.env", "migrate.env"):
        names |= {
            line.split("=", 1)[0]
            for line in files[name].splitlines()
            if "=" in line and not line.startswith("#")
        }
    return names


def test_every_required_setting_is_named() -> None:
    required = {
        name
        for group in (settings._REQUIRED_SECRETS, settings._REQUIRED_PLAIN)
        for names in group.values()
        for name in names
    }
    assert required - set(_template()) == set()


def test_every_setting_the_rehearsal_writes_is_named() -> None:
    assert _rehearsal_names() - set(_template()) == set()


def test_the_host_timers_settings_are_named() -> None:
    template = _template()
    for name in ("HEARTBEAT_URL", "BACKUP_ENCRYPTION_RECIPIENT", "ZITADEL_BACKUP_DATABASE_URL"):
        assert name in template, name


def test_no_secret_has_a_value() -> None:
    for name, (value, marks) in _template().items():
        if "[secret]" in marks:
            assert value == "", f"{name} is a secret and must stay empty"


def test_every_email_switch_and_signup_is_off() -> None:
    template = _template()
    switches = [name for name in template if name.startswith("EMAIL_") and "ENABLED" in name]
    assert len(switches) == 5
    assert all(template[name][0] == "false" for name in switches)
    assert template["SIGNUP_ENABLED"][0] == "false"


def test_every_setting_a_host_writes_is_named() -> None:
    """Decision D-STG.5: `prepare_local.py --host` adds log labels and turns
    the stdout trace exporter off; each name is in the template."""
    files = _prepare_local()._files(
        dict.fromkeys(_PASSWORDS, "x"), "https://crm-staging.example.nl", "crm-staging.example.nl"
    )
    names = {
        line.split("=", 1)[0]
        for line in files["app.env"].splitlines()
        if "=" in line and not line.startswith("#")
    }
    assert {"DEPLOYMENT_ID", "OBSERVABILITY_EXPORTER"} <= names
    assert names - set(_template()) == set()
    assert "OBSERVABILITY_EXPORTER=none" in files["app.env"]
