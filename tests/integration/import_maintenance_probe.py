"""Stages CSV imports in throwaway workspaces, makes some fall due, runs
`crm_app.import_maintenance.maintain`, and prints one `RESULT <json>` line.

Run in a fresh interpreter by `tests/integration/test_import_maintenance.py`.
Refuses to run unless ENVIRONMENT=test.
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Any

from saas_os.core.identity import issue_session
from saas_os.infra.db import session_scope, tenant_session_scope
from sqlalchemy import text

from crm_app import import_commit, imports
from crm_app.import_maintenance import maintain
from crm_app.records import Scope
from tests.integration.workspace_route_probe import _new_workspace

FILE = b"first_name,email\r\nSam,sam@example.test\r\nAnn,ann@example.test\r\n"


def _make_due(import_id: uuid.UUID) -> None:
    with session_scope() as session:
        session.execute(
            text(
                "UPDATE crm_app.import_expiry SET due_at = now() - interval '1 minute'"
                " WHERE import_id = :id"
            ),
            {"id": import_id},
        )


def _state(workspace: uuid.UUID, import_id: uuid.UUID) -> dict[str, Any]:
    with tenant_session_scope(workspace) as session:
        status = session.execute(
            text("SELECT status FROM crm_app.import_job WHERE id = :id"), {"id": import_id}
        ).scalar_one()
        rows = session.execute(
            text("SELECT count(*) FROM crm_app.import_row WHERE import_id = :id"),
            {"id": import_id},
        ).scalar_one()
        contacts = session.execute(
            text("SELECT count(*) FROM crm_app.contact WHERE source = 'import'")
        ).scalar_one()
    with session_scope() as session:
        entry = session.execute(
            text("SELECT due_at > now() FROM crm_app.import_expiry WHERE import_id = :id"),
            {"id": import_id},
        ).scalar_one_or_none()
    return {"status": status, "rows": rows, "imported_contacts": contacts, "entry_later": entry}


def main() -> None:
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("import_maintenance_probe runs only with ENVIRONMENT=test")
    a = _new_workspace("maintenance-a")
    b = _new_workspace("maintenance-b")
    issue_session(a.owner_id)
    scope_a = Scope(workspace=a.id, actor=a.owner_id)
    scope_b = Scope(workspace=b.id, actor=b.owner_id)

    finished = uuid.UUID(str(imports.preview(scope_a, "contact", FILE, None).summary["id"]))
    import_commit.queue(scope_a, finished)
    import_commit.run(scope_a, finished)
    abandoned = uuid.UUID(str(imports.preview(scope_b, "contact", FILE, None).summary["id"]))
    queued = uuid.UUID(
        str(imports.preview(scope_b, "contact", FILE.replace(b"sam", b"sid"), None).summary["id"])
    )
    import_commit.queue(scope_b, queued)
    recent = uuid.UUID(str(imports.preview(scope_a, "contact", FILE, None).summary["id"]))
    orphan = uuid.uuid4()
    with session_scope() as session:
        session.execute(
            text(
                "INSERT INTO crm_app.import_expiry (import_id, workspace_id, due_at)"
                " VALUES (:id, :ws, now() - interval '1 day')"
            ),
            {"id": orphan, "ws": a.id},
        )
    for import_id in (finished, abandoned, queued):
        _make_due(import_id)

    report = maintain()
    again = maintain()
    result = {
        "report": report.__dict__,
        "again": again.__dict__,
        "finished": _state(a.id, finished),
        "abandoned": _state(b.id, abandoned),
        "queued": _state(b.id, queued),
        "recent": _state(a.id, recent),
    }
    print("RESULT " + json.dumps(result))


if __name__ == "__main__":
    main()
