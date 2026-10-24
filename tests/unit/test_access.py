"""`GET /v1/workspaces/{id}/access` when the membership vanishes mid-request
(`PHASE2-SECURITY-REVIEW.md` I2, decision P2-F).

`require_permission` admits the caller, then the membership is removed
before the handler reads it. The handler must answer as for any non-member
(SaaS-OS's 404 "tenant not found."), never with a server error. Run in a
fresh interpreter with placeholder settings, because SaaS-OS resolves
configuration at import time; no database is touched.
"""

from __future__ import annotations

import json
from pathlib import Path

from tests.support import PLACEHOLDER_SETTINGS, clean_environment, run_python

_PROBE = (
    "import json, types, uuid\n"
    "from fastapi import HTTPException\n"
    "import crm_app.api.access as access\n"
    "access.get_membership = lambda tenant_id, user_id: None\n"
    "context = types.SimpleNamespace(tenant_id=uuid.uuid4(), actor_id=uuid.uuid4())\n"
    "try:\n"
    "    access.get_access(context.tenant_id, context)\n"
    "    outcome = ['returned']\n"
    "except HTTPException as exc:\n"
    "    outcome = [exc.status_code, exc.detail]\n"
    "print('OUTCOME ' + json.dumps(outcome))\n"
)


def test_a_membership_removed_mid_request_is_a_404_not_a_500(tmp_path: Path) -> None:
    result = run_python(_PROBE, clean_environment(PLACEHOLDER_SETTINGS), tmp_path)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("OUTCOME "))
    assert json.loads(line.removeprefix("OUTCOME ")) == [404, "tenant not found."]
