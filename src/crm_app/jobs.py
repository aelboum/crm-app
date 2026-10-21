"""This product's background jobs, run on SaaS-OS's production worker.

Phase 1 registers none. When jobs are added, each one:

- is registered with `saas_os.infra.jobs.register_tenant_job` (or
  `register_system_job`), whose worker validates the tenant before the
  handler runs;
- has a name prefixed `crm_app_`, because the worker refuses a name that
  collides with a platform job;
- is idempotent, because delivery is at-least-once;
- takes the tenant from the validated job context, never from
  `payload.data`.

Importing a module that registers jobs resolves `REDIS_URL`, so only the
worker entrypoint imports this module, after validation.
"""

from __future__ import annotations

JOB_FUNCTIONS: tuple[()] = ()
