"""The staging host's timers match the schedule in OPERATIONS.md (decision
D-STG.3).

Every scheduled command in `docs/project/OPERATIONS.md` has a timer in
`deploy/staging/systemd/`; every timer starts a unit that exists there; the
job template runs the product image's own module; nothing secret is written
in a unit. A new scheduled command without a timer fails here. Running the
commands and the heartbeat is `deploy/staging/schedule_local.py`.
"""

from __future__ import annotations

import re

from tests.support import REPO_ROOT

UNITS = REPO_ROOT / "deploy" / "staging" / "systemd"
OPERATIONS = REPO_ROOT / "docs" / "project" / "OPERATIONS.md"
# SaaS-OS's own host timers (deploy/*.timer at the pinned commit), except
# its backups, which wait for the provider (SaaS-OS gaps 17 and 18).
SAAS_OS_JOBS = {
    "saas_os.api.session_cleanup_trigger",
    "saas_os.api.billing_event_retention_trigger",
}


def _scheduled_in_operations() -> set[str]:
    text = OPERATIONS.read_text(encoding="utf-8")
    section = text.split("## Scheduled commands", 1)[1].split("\n## ", 1)[0]
    return set(re.findall(r"^\| `python -m (crm_app\.\w+)`", section, re.M))


def _timer_targets() -> dict[str, str]:
    targets = {}
    for timer in UNITS.glob("*.timer"):
        unit = re.search(r"^Unit=(\S+)$", timer.read_text(encoding="utf-8"), re.M)
        assert unit, f"{timer.name} names no Unit="
        targets[timer.name] = unit.group(1)
    return targets


def test_every_scheduled_command_has_a_timer() -> None:
    scheduled = _scheduled_in_operations()
    assert scheduled, "no scheduled commands found in OPERATIONS.md"
    jobs = {
        unit.removeprefix("leadstack-job@").removesuffix(".service")
        for unit in _timer_targets().values()
        if unit.startswith("leadstack-job@")
    }
    assert jobs == scheduled | SAAS_OS_JOBS


def test_every_timer_starts_a_unit_that_exists() -> None:
    for timer, unit in _timer_targets().items():
        name = re.sub(r"@.+\.service$", "@.service", unit)
        assert (UNITS / name).exists(), f"{timer} starts {unit}, which has no unit file"


def test_the_heartbeat_has_a_timer_and_its_script() -> None:
    assert "leadstack-heartbeat.service" in _timer_targets().values()
    service = (UNITS / "leadstack-heartbeat.service").read_text(encoding="utf-8")
    assert "heartbeat.sh" in service
    assert (REPO_ROOT / "deploy" / "staging" / "heartbeat.sh").exists()
    # The heartbeat address carries the monitor's token: environment file only.
    assert "HEARTBEAT_URL=" not in service
    assert "EnvironmentFile=" in service


def test_the_job_template_runs_the_named_module_in_the_product_image() -> None:
    template = (UNITS / "leadstack-job@.service").read_text(encoding="utf-8")
    exec_start = re.search(r"^ExecStart=(.+)$", template, re.M)
    assert exec_start
    assert exec_start.group(1).endswith("run --rm --no-deps -T app python -m %i")
    assert "Type=oneshot" in template


def test_no_unit_holds_a_secret() -> None:
    for unit in UNITS.iterdir():
        text = unit.read_text(encoding="utf-8")
        assert not re.search(r"(?i)(password|token|secret|key)\s*=", text), unit.name
        assert "://" not in text, unit.name
