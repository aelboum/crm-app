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
- `crm_app_automation_run` (decision P8-A): advances one automation run
  (`crm_app.automations.advance`); an unexpected failure is counted on
  the run and raised, so the queue retries it.
- `crm_app_email_send` (decision P6-E): one try at a queued email
  (`crm_app.emails.send`). The payload names the email; a try that may
  pass later raises, so the queue retries it with backoff.

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


async def crm_app_email_send(context: TenantJobContext, payload: TenantJobPayload) -> None:
    from crm_app import emails  # noqa: PLC0415

    email_id = uuid.UUID(str(payload.data["email_id"]))
    await asyncio.to_thread(emails.send, context.tenant_id, email_id)


async def crm_app_automation_run(context: TenantJobContext, payload: TenantJobPayload) -> None:
    from crm_app import automations  # noqa: PLC0415

    run_id = uuid.UUID(str(payload.data["run_id"]))
    try:
        await asyncio.to_thread(automations.advance, context.tenant_id, run_id)
    except Exception as exc:
        await asyncio.to_thread(
            automations.record_failure, context.tenant_id, run_id, type(exc).__name__.lower()
        )
        raise


# arq `Function`s, as SaaS-OS's worker takes them.
JOB_FUNCTIONS: tuple[Any, ...] = (
    register_tenant_job(crm_app_import_commit),
    register_tenant_job(crm_app_email_send),
    register_tenant_job(crm_app_automation_run),
)
