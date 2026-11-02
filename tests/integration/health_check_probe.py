"""Drives `crm_app.health_check` (decision 13-O1) and prints one
`RESULT <json>` line.

Run in a fresh interpreter by `tests/integration/test_health_check.py`. Adds
one overdue `automation_due` row for a made-up run, then removes it. Refuses
to run unless ENVIRONMENT=test.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import uuid
from datetime import UTC, datetime, timedelta

from saas_os.infra.db import delete, session_scope

from crm_app import health_check
from crm_app.models import AutomationDue


def main() -> None:
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("health_check_probe runs only with ENVIRONMENT=test")
    now = datetime.now(UTC)
    long_ago = datetime(2000, 1, 1, tzinfo=UTC)
    before = health_check.overdue(now)
    run_id = uuid.uuid4()
    with session_scope() as session:
        session.add(
            AutomationDue(run_id=run_id, workspace_id=uuid.uuid4(), due_at=now - timedelta(hours=1))
        )
    try:
        after = health_check.overdue(now)
        recent = health_check.overdue(now - timedelta(minutes=50))
    finally:
        with session_scope() as session:
            session.execute(delete(AutomationDue).where(AutomationDue.run_id == run_id))
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        usage = health_check.main(["--now"])
    result = {
        "keys": sorted(before),
        "detected": after["automation_runs"] - before["automation_runs"],
        "not_yet_late": recent["automation_runs"]
        - health_check.overdue(now - timedelta(minutes=50))["automation_runs"],
        "nothing_in_2000": health_check.overdue(long_ago),
        "usage": [usage, "usage:" in out.getvalue()],
    }
    print("RESULT " + json.dumps(result))


if __name__ == "__main__":
    main()
