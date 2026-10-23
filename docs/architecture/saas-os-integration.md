# SaaS-OS Integration

## Pin

```text
saas-os @ git+https://github.com/aelboum/saas-os@b03d87a5272924d1e413c144dc5c3b41ac430580
```

- **Release:** v0.5.0. The annotated tag object is `1254662`, and the
  remote tag resolved to this commit on 2026-10-23. SaaS-OS CI run
  40002133371 passed on it.
- **Platform migration head:** `f6a2c8e4b1d9` (unchanged since v0.1.2).
- **Approval:** decision K3, moved from v0.1.2 (`b0809ee`) by decision
  K3.1 and from v0.3.0 (`5905156`) by decision K3.2. The pin is fixed
  until a further approved decision.
- **Guard:** `tests/unit/test_dependency_pin.py` checks the manifest, the
  `uv.lock` source, the installed `direct_url.json` commit, that the
  install is non-editable, and that no URL carries credentials.
- **Upgrade path:** `saas-os-update check`, then SaaS-OS CONSUMER-GUIDE
  §14, then a new decision.

## Boundary

| Owned by SaaS-OS (consumed, never modified) | Owned by this product |
| --- | --- |
| Application construction, startup checks, request correlation, `/healthz`, `/readyz` | Router composition in `crm_app.app` |
| OIDC sign-in, sessions, `/auth/*`, same-origin check on cookie mutations | Workspace experience and every product route (Phase 2+) |
| Tenants, memberships, invitations, RBAC, audit log | Product permissions (`crm_app.*`), granted to tenant roles |
| RLS helper `tenant_rls_statements`, `tenant_session_scope` | The `crm_app` schema, tables and migrations, with RLS on every tenant table |
| Worker, retries, dead-lettering, platform jobs | Product jobs (`crm_app_` prefix), idempotent |
| Secrets provider (`.env` in development, the environment otherwise) | Configuration validation before startup (`crm_app.settings`) |
| Local identity bootstrap tool `saas-os-local-identity` | Local Compose services in `deploy/local/` |

## Public interfaces used (Phase 1)

| Interface | Used in | Verified by |
| --- | --- | --- |
| `saas_os.api.platform.build_platform_app(*, title, version)` | `crm_app/app.py` | `tests/unit/test_entrypoints.py`, `tests/integration/test_foundation.py` |
| `saas_os.api.worker.main(argv, *, extra_functions)` | `crm_app/worker.py` | `test_worker_starts_and_passes_its_health_probe` |
| `saas_os.infra.db.run_core_migrations()` | `crm_app/migrate.py` | `test_both_migration_histories_are_at_head` |
| `saas_os.infra.db.get_migrations_database_config()` | `crm_app/migrations/env.py` | same |
| `saas_os.infra.secrets.get_secrets_provider()` | `crm_app/settings.py` | `test_secrets_are_read_through_the_saas_os_provider_in_development` |
| `saas_os.core.rbac.register_permission` | `crm_app/permissions.py` (no permissions yet) | not exercised in Phase 1 |
| `saas-os-local-identity` (console script) | local identity setup | `tests/identity/test_oidc_login.py` (opt-in) |

**Rule:** imports are restricted to package `__init__` exports,
`saas_os.api.*`, `saas_os.inference` and `saas_os.contracts`. This is
enforced by `tests/unit/test_import_surface.py`.

The scaffold's own imports of `saas_os.infra.db.config`,
`saas_os.infra.db.rls` and `saas_os.core.tenancy.purge_participants` were
replaced by the public `saas_os.infra.db` exports. The purge participant is
deferred until the first tenant table exists. Its documented module path
(`saas_os.core.tenancy.purge_participants`) is not a package `__init__`
export. From v0.5.0, `saas_os.core.tenancy` exports
`register_purge_participant`, `registered_purge_participant_names` and
`TenantPurgeParticipant` (SaaS-OS #87, #94); this product does not use
them yet. Registering the participant is gate G1's work (decision
Q-purge), not part of the pin move.

## Observed platform behaviour

**Configuration is read at import time.** For example, importing
`saas_os.api.platform` without `ENVIRONMENT` or `REDIS_URL` raises. The
product therefore validates first and imports SaaS-OS inside its
entrypoints.

**In development**, secrets are read from the process environment first and
then from `.env` in the working directory (`SECRETS_ENV_FILE` overrides the
path). Non-secret settings are read from the process environment only.

**Startup checks:**
- The application refuses a database role that can bypass RLS
  (`UnsafeDatabaseRoleError`). `test_application_refuses_a_role_that_can_bypass_rls`
  proves this.
- `/readyz` checks PostgreSQL and Redis.
- `crm-app-worker --check` succeeds only while a worker is running.

**Sign-in:**
- `/auth/login` redirects to the issuer with PKCE S256 and the
  `openid email` scope. The callback is derived from `PUBLIC_APP_ORIGIN`.
- A cookie-authenticated `POST /auth/logout` with a foreign `Origin` is
  refused with `403`.

**Tracing:** OpenTelemetry spans are printed to the console.

## Known gaps at the pin, relevant to coming phases

- **Tenancy and identity:**
  - No API lists a user's tenants (decision D-WS, open question).
  - Request access requires a direct membership; SUBTREE scope does not
    admit a request.
  - Tenant creation requires an operator or `SystemCaller(PROVISIONING)`.
- **Jobs and events:** no delayed jobs and no job deduplication ID;
  products cannot register outbox consumers.
- **Platform services:**
  - No metrics.
  - No per-tenant secret store.
  - Email is transactional SMTP only.
  - No embeddings or streaming inference.
- **Upstream note:** from v0.2.0, SaaS-OS's Compose files use ZITADEL
  v4.19.5, the version this product already runs locally
  (`deploy/local/compose.yaml`). SaaS-OS's live validation of v4.19.5 did
  not cover browser sign-in through the Login V2 pages; this product's
  identity test covers sign-in through the legacy login UI only.
- **Local identity bootstrap:** from v0.2.0, `saas-os-local-identity`
  reads complete paged listings and stops with `IncompleteListingError`
  on a partial one. Rerun against the local ZITADEL on 2026-10-21, it
  found the existing project and application and created nothing.
