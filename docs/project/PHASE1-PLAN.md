# Phase 1 Plan — Repository and Scaffold

**Status:** Approved by the owner on 2026-10-20, with P-1 to P-6
(`DECISIONS.md`). Implemented and verified locally; acceptance criterion 9
(CI on the evaluated commit) is open. See `PROGRESS.md` for the results.
Approval of this plan does not authorize creating the remote repository,
committing, pushing, releasing, or deploying.

Changes made during implementation, against the text below:

- **§6:** local ZITADEL is v4.19.5, not v4.19.0. See "P-4 verification
  result" in `DECISIONS.md`.
- **§2:** the dependency audit uses a hashed export of `uv.lock` with
  SaaS-OS excluded.
- **§10:** no purge participant is registered yet, because there is no
  tenant table. Its documented module
  (`saas_os.core.tenancy.purge_participants`) is not a package export;
  that is an open question for Phase 2.

Scope follows `ROADMAP.md` §6 (Phase 1 — Product Foundation) and decisions
K1–K5 and D-WS in `DECISIONS.md`.

## 1. Repository

| Item | Plan |
| --- | --- |
| Local directory | `C:\Users\imran\Documents\crm-app` (exists, `git init -b main`, no commits) |
| Remote | Private repository under `aelboum`, proposed name `crm-app`. **Created only on explicit approval** |
| Initial content | `CLAUDE.md`, `ROADMAP.md` (corrected copies), `docs/project/*` |
| History | Fresh. Nothing imported from `sofioco/leadstack-crm` or `aelboum/leadstack` |
| Product licence | No open-source licence; a proprietary notice in `README.md` (P-5) |
| Never committed | `.env`, credentials, dumps, `node_modules`, virtual environments, build output |

## 2. Dependency pin

```toml
dependencies = [
    "saas-os @ git+https://github.com/aelboum/saas-os@b0809eeb3448956a4dc85a5541514823ec9ceae7",
]
```

- Exactly one SaaS-OS requirement, a 40-character SHA, no extras in
  Phase 1. `[stripe]` waits until billing is in scope.
- The URL never carries credentials. SaaS-OS is public, so CI needs no
  token. Verified 2026-10-20; re-check before CI is configured.
- A lockfile records the same commit. A unit test asserts:
  - the manifest pin,
  - the lockfile commit,
  - the installed `direct_url.json` commit,
  - a non-editable install.
- Moving the pin requires a new approved decision (K3).

## 3. Public SaaS-OS surface the product may import

These were verified to import at the pin with placeholder configuration
on 2026-10-20:

- `saas_os.api.platform`, `saas_os.api.dependencies`,
  `saas_os.api.context`, `saas_os.api.errors`, `saas_os.api.worker`,
  `saas_os.api.v1`
- `saas_os.infra.db`, `saas_os.infra.jobs`, `saas_os.infra.secrets`,
  `saas_os.infra.observability`, `saas_os.infra.egress`
- `saas_os.core.identity`, `saas_os.core.tenancy`, `saas_os.core.rbac`,
  `saas_os.core.authority`, `saas_os.core.audit_log`,
  `saas_os.core.idempotency`, `saas_os.core.email`, `saas_os.core.crypto`,
  `saas_os.core.billing`, `saas_os.core.webhooks`, `saas_os.core.usage`,
  `saas_os.core.notifications`
- `saas_os.inference` (Phase 9 only)

**Rule:** only package `__init__` exports, `saas_os.api.*`,
`saas_os.inference`, and `saas_os.contracts`.

**Never import:**
- `saas_os.api.main` or `saas_os.api.server`;
- `saas_os.control_plane.inference.*`;
- any `saas_os.core.*` or `saas_os.infra.*` submodule below its
  `__init__` (for example `...service`, `...queue`).

**Exception:** `saas_os.infra.jobs.queue.system_cron` may be used only
because CONSUMER-GUIDE documents it.

**Enforcement:**
- import-linter contracts in this repository;
- a unit test that parses every `saas_os` import and checks it against
  this allowlist.

## 4. Proposed layout

```text
crm-app/
  pyproject.toml          # project, pin, tool config
  uv.lock                 # P-2
  .env.example            # variable names and safe placeholders only
  README.md
  CLAUDE.md, ROADMAP.md
  docs/project/           # decisions, progress, plans, reports
  docs/architecture/      # saas-os-integration.md, tenancy.md (Phase 1–2)
  deploy/local/           # compose file for PostgreSQL, Redis, ZITADEL
  src/crm_app/
    app.py                # create_app(): build_platform_app + routers
    migrate.py            # platform migrations, product migrations, permissions
    worker.py             # saas_os.api.worker.main(extra_functions=...)
    jobs.py
    permissions.py        # resources prefixed "crm_app."
    purge.py              # purge-participant registration
    config.py             # product settings, validated at startup
    migrations/           # product Alembic history, own schema
    domains/              # product modules (empty in Phase 1)
    routes/
  tests/
    unit/                 # pin, import surface, config, architecture
    integration/          # real PostgreSQL + Redis
```

The structure is adapted from `examples/consumer-scaffold/` at the pin.
The scaffold's example `items` table and routes are not kept: Phase 1
ships no business data.

## 5. Tooling

| Concern | Tool | Note |
| --- | --- | --- |
| Python | 3.13 (3.13.14 installed locally) | SaaS-OS requires ≥3.13 |
| Environment and lock | uv (0.12.3 installed) with `uv.lock` | **P-2.** CONSUMER-GUIDE shows `pip install -e .`; uv is an equivalent resolver/installer and gives a reproducible lock |
| Format and lint | ruff | |
| Types | pyright (standard) | |
| Boundaries | import-linter, plus the import-allowlist unit test | |
| Tests | pytest | |
| Dependency audit | pip-audit | SaaS-OS itself is excluded because it is not on an index; review its pin manually |
| Secret scan | detect-secrets with a committed baseline | |

All are development-only dependencies and add no runtime framework.

## 6. Local runtime (development only)

- **PostgreSQL** `postgres:16-alpine` and **Redis** `redis:7-alpine`, the
  versions SaaS-OS uses in its own compose file and CI at the pin.
- **ZITADEL** through `saas-os-local-identity`. The pin references
  `ghcr.io/zitadel/zitadel:v4.19.0`.
- Docker 29.8.2 is installed. Nothing runs against production or any
  shared system.
- Database roles: a migration role (owner of the product schema, with
  `CREATEROLE` or a pre-created `saas_os_platform_config` role) and an
  application role (`NOSUPERUSER NOBYPASSRLS`). SaaS-OS's startup check
  refuses an unsafe application role.

## 7. Configuration and secrets

- `.env.example` lists names only:
  - the SaaS-OS minimum in `PHASE0-DISCOVERY.md` §3;
  - product settings as they are introduced.
- SaaS-OS reads configuration at import time. The product therefore
  validates its own settings in `config.py` before building the
  application and fails closed with a clear message that never echoes a
  value.
- No secret in source, logs, test fixtures, or documentation. Local
  secrets live in an untracked `.env`.

## 8. Observability

- Use SaaS-OS JSON logging with redaction and request correlation.
- Use OpenTelemetry tracing with the console exporter.
- Metrics are not provided at the pin. Record this as a known gap
  (ROADMAP §6, task 1.4).
- Health comes from the platform: `/healthz`, `/readyz`, and the worker's
  `--check`.

## 9. CI (prepared, inactive until a push is approved)

- GitHub Actions, with third-party actions pinned by SHA.
- Jobs:
  - lock check, ruff, pyright, import-linter, unit tests;
  - integration tests with PostgreSQL 16 and Redis 7 service containers;
  - pip-audit and detect-secrets.
- No deploy job, no publish job, no secrets beyond what tests need.

## 10. Security contract compatibility at the pin

All of these were verified by reading the source at `b0809ee` and are
compatible with the plan. Phase 2 must prove them with tests.

| Contract | Evidence | Product obligation |
| --- | --- | --- |
| Request tenant resolution | `get_tenant_context`: tenant exists, is accessible, and the caller has a direct membership; otherwise a uniform 404 | Handlers read `context.tenant_id`, never the path or body |
| Authorization | `require_permission(resource, action, *, api_key=False)` runs authentication → tenant → rate limit → `rbac.can()`, and audits denials | Every product route declares exactly one policy (enforced at startup) |
| RLS | `tenant_rls_statements` emits ENABLE + FORCE + `USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)` | Every tenant table uses it. Write a predicate-free read test and cross-tenant insert/update/delete tests |
| Pooled-connection safety | `tenant_session_scope` calls `set_config('app.tenant_id', :id, true)`, which is transaction-local | Never open a tenant data session without it |
| Unsafe role refusal | `validate_application_role` (`saas_os/infra/db/role_guard.py`) | The application role is `NOSUPERUSER NOBYPASSRLS` |
| Route policy | `assert_route_policies` (`saas_os/api/route_policy.py`) | Every route declares a policy |
| Jobs | `register_tenant_job`; the tenant comes from the validated job context; at-least-once delivery | Handlers are idempotent; tenant never read from payload data |
| Tenant creation | `create_tenant(..., caller)` requires an operator or `SystemCaller(PROVISIONING)` | The signup and workspace-creation design waits for Phase 2 verification (D-WS) |

**Gap noted:** Phase 1 has no tenant data table, so the RLS and
cross-tenant tests begin in Phase 2. Phase 1 proves:
- migration ordering;
- the role guard;
- application startup;
- health and readiness.

## 11. Phase 1 acceptance criteria

These come from ROADMAP §6. Each needs evidence: the command and its
actual result.

1. `uv sync --locked` succeeds from a clean clone. The installed SaaS-OS
   commit equals `b0809ee`, checked by the pin test.
2. ruff, pyright, import-linter, and the import-allowlist test pass.
3. Product migrations run after `run_core_migrations()` against a
   disposable local PostgreSQL. Running them twice is a no-op. Product
   permissions are registered.
4. The application starts via `create_app()` with a safe application
   role. Startup is refused with an unsafe role (a negative test).
   `/healthz` and `/readyz` return success with local PostgreSQL and
   Redis.
5. The worker starts with product jobs merged, and `--check` passes.
6. OIDC login completes against local ZITADEL; `/auth/me` returns the
   user ID.
7. Configuration validation fails closed when required variables are
   missing, without printing values.
8. pip-audit and detect-secrets report no unaccepted findings.
9. CI passes on the exact commit evaluated. This applies only after
   commit and push are approved; until then, record local gate results.
10. No SaaS-OS source is modified. Both existing CRM repositories are
    unchanged.

## 12. Excluded from Phase 1

- Any business domain module: workspaces, contacts, and the rest begin in
  Phase 2 or later.
- Frontend work, including choosing the frontend stack (P-6). This waits
  for the Claude Design import.
- Billing, email sending, AI, external providers, deployment, and hosting
  selection.

## 13. Decisions needed before Phase 1 implementation

| ID | Question | Recommendation |
| --- | --- | --- |
| P-1 | Neutral technical name for the repository, directory, and Python package | `crm-app` / `crm_app` |
| P-2 | Use uv with `uv.lock`, or pip as shown in the consumer guide | uv with a committed `uv.lock` |
| P-3 | Development tools listed in §5 | Approve as listed |
| P-4 | PostgreSQL 16, Redis 7, ZITADEL v4.19.0 for local development | Match the pinned SaaS-OS versions |
| P-5 | Product licence | Proprietary notice, no licence file |
| P-6 | Frontend stack | Defer until the Claude Design import |

Also required: approval to begin Phase 1 implementation. Remote
repository creation and the first commit need separate approval when
they are due.
