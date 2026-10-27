"""This product's background jobs, run on SaaS-OS's production worker.

Each job:

- is registered with `saas_os.infra.jobs.register_tenant_job` (or
  `register_system_job`), whose worker validates the tenant before the
  handler runs;
- has a name prefixed `crm_app_`, because the worker refuses a name that
  collides with a platform job;
- is idempotent, because delivery is at-least-once;
- takes the tenant from the validated job context, never from
  `payload.data`.

Jobs:

- `crm_app_import_commit` (decision P3-F 5): commits a queued CSV import
  (`crm_app.import_commit.run`). The payload names the import and the
  member who committed it, who is the actor of the records it creates.

Importing a module that registers jobs resolves `REDIS_URL`, so only the
worker entrypoint imports this module, after validation.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from saas_os.infra.jobs import TenantJobContext, TenantJobPayload, register_tenant_job


async def crm_app_import_commit(context: TenantJobContext, payload: TenantJobPayload) -> None:
    from crm_app import import_commit  # noqa: PLC0415
    from crm_app.records import Scope  # noqa: PLC0415

    import_id = uuid.UUID(str(payload.data["import_id"]))
    actor = uuid.UUID(str(payload.data["actor_id"]))
    scope = Scope(workspace=context.tenant_id, actor=actor)
    await asyncio.to_thread(import_commit.run, scope, import_id)


# arq `Function`s, as SaaS-OS's worker takes them.
JOB_FUNCTIONS: tuple[Any, ...] = (register_tenant_job(crm_app_import_commit),)
