# Progress Record

The verified current state of the project. `ROADMAP.md` defines the
destination; this file records what is actually true. Do not record
anything here that was not verified.

**Last updated:** 2026-10-21 (SaaS-OS pin moved to v0.3.0, decision K3.1)

## Current phase

- **Phase 0 — Discovery:** evidence complete except task 0.3 (Claude
  Design import).
- **Phase 0.5 — Foundational decisions:** K1–K5, D-WS and P-1 to P-6
  approved and recorded in `DECISIONS.md`.
- **Phase 1 — Product foundation:** implemented and verified locally.
  **Not complete:** acceptance criterion 9 (CI passing on the exact
  evaluated commit) cannot be met until committing and pushing are
  approved.

## Repository state

- **Directory:** `C:\Users\imran\Documents\crm-app`, branch `main`.
- **Commits and remote:** no commits, no remote. Committing, pushing and
  creating the remote are not authorized.
- **Untracked local files, never committed (covered by `.gitignore`):**
  - `.env` and `.env.test`: local-only random credentials and the local
    OIDC client ID;
  - `.venv/`;
  - `deploy/local/.bootstrap/` (ZITADEL's bootstrap token);
  - tool caches.
- **Local Docker services** (project `crm-app-local`, all bound to
  127.0.0.1): `db` on 55432, `redis` on 56379, `zitadel` on 8081.
  `zitadel-db` publishes no port. They are still running. Stop them with
  `docker compose -f deploy/local/compose.yaml --env-file .env --profile identity down`.
- **Untouched (verified by `git status` on 2026-10-20):**
  - `C:\Users\imran\Documents\leadstack-crm`: 1,466 deletions, `CLAUDE.md`
    modified, 2 untracked; `CLAUDE.md` and `ROADMAP.md` hashes unchanged;
  - `C:\Users\imran\Documents\Leadstack`: `a4422a0`, 72 uncommitted paths;
  - `C:\Users\imran\Documents\saas-os`: `2adf634`, clean. On 2026-10-21
    it was at `5905156` (v0.3.0, advanced by the owner) and clean; it was
    only read for the K3.1 upgrade.

## Phase 1: what was built

| Area | Files |
| --- | --- |
| Manifest, pin, tools | `pyproject.toml`, `uv.lock` (72 packages; Python 3.13.14) |
| Configuration validation | `src/crm_app/settings.py` |
| Entrypoints | `src/crm_app/app.py` (`create_app` factory), `worker.py`, `migrate.py` |
| Product migrations | `src/crm_app/migrations/` (revision `0001_crm_app_schema`: schema `crm_app`, USAGE for the runtime role, PUBLIC revoked) |
| Placeholders for later phases | `jobs.py`, `permissions.py`, `domains/` (all empty) |
| Local services | `deploy/local/compose.yaml`, `deploy/local/init/01-roles.sh`, `.env.example`, `.env.test.example` |
| CI | `.github/workflows/ci.yml` (quality, integration, security) |
| Secret-scan baseline | `.secrets.baseline` (4 audited false positives: placeholder URLs in the env examples, the pin SHA, the migration head) |
| Docs | `README.md` (with the proprietary notice), `docs/architecture/saas-os-integration.md` |
| Tests | `tests/unit` (43), `tests/integration` (7), `tests/identity` (1, opt-in) |

## Phase 1 acceptance criteria (PHASE1-PLAN.md §11)

| # | Criterion | Result | Evidence (2026-10-20) |
| --- | --- | --- | --- |
| 1 | Locked install from a clean clone; installed SaaS-OS = `b0809ee` | **Passed (clean copy)** | Copied the 44 trackable files to a fresh directory with an empty uv cache. `uv lock --check` exit 0; `uv sync --locked` exit 0; installed commit `b0809eeb…`. A true `git clone` needs a commit, which is not yet authorized |
| 2 | ruff, pyright, import-linter, import-allowlist test | **Passed** | `ruff format --check .`: 32 files already formatted. `ruff check .`: all checks passed. `pyright`: 0 errors. `lint-imports`: 2 kept, 0 broken. `tests/unit/test_import_surface.py` passed |
| 3 | Migrations after the platform's, idempotent, permissions registered | **Passed** (no permissions exist yet) | `test_both_migration_histories_are_at_head`: platform `f6a2c8e4b1d9`, product `0001_crm_app_schema` after two runs. Schema grants checked by `test_application_role_has_usage_but_cannot_create_in_the_product_schema` |
| 4 | App starts with a safe role, refuses an unsafe role, health and readiness | **Passed** | `test_application_starts_and_reports_ready` (`/healthz` 200, `/readyz` 200, `/auth/me` 401). `test_application_refuses_a_role_that_can_bypass_rls` (`UnsafeDatabaseRoleError`) |
| 5 | Worker starts with product jobs merged; `--check` passes | **Passed** (no product jobs yet) | `test_worker_starts_and_passes_its_health_probe`; negative case `test_worker_health_probe_fails_when_no_worker_runs` |
| 6 | OIDC login against local ZITADEL; `/auth/me` returns the user ID | **Passed** (ZITADEL v4.19.5) | `CRM_APP_IDENTITY_TEST=1 pytest tests/identity`: 1 passed. Covers login, `/auth/me` = `{user_id}`, cross-origin logout refused (403), logout, and no secrets in the server log |
| 7 | Configuration validation fails closed without printing values | **Passed** | `tests/unit/test_settings.py`, `tests/unit/test_entrypoints.py` (marker strings absent from stdout and stderr) |
| 8 | pip-audit and detect-secrets clean | **Passed** | pip-audit on a hashed export (SaaS-OS excluded): "No known vulnerabilities found". detect-secrets hook exit 0, and exit 1 on a planted credential |
| 9 | CI passes on the exact commit evaluated | **Not met** | No commit or push is authorized. Local stand-in: the CI integration job was dry-run against a fresh PostgreSQL 16 container using the CI credentials and `01-roles.sh` over TCP; 7 passed |
| 10 | SaaS-OS unmodified; other repositories unchanged | **Passed** | `git status` of all three repositories (see above) |

**Totals:** unit 43 passed; integration 7 passed (against local services,
and again in the CI dry run); identity 1 passed. All runs were local on
Windows 11 with Docker Desktop. Linux CI has not run.

## SaaS-OS upgrade to v0.3.0 (decision K3.1, 2026-10-21)

The table above records the evidence at `b0809ee`. On the new pin
`5905156` every check was run again, locally:

| Check | Result |
| --- | --- |
| `uv lock` | Only the saas-os entry changed (0.1.2 → 0.3.0); 72 packages, the other 71 unchanged |
| `uv sync --locked`, `uv lock --check` | Exit 0; installed `saas-os` 0.3.0, `direct_url.json` commit `5905156…`, not editable |
| `ruff format --check .` / `ruff check .` | 32 files already formatted / all checks passed |
| `pyright` / `lint-imports` | 0 errors / 2 kept, 0 broken |
| `pytest tests/unit` | 43 passed (includes the pin test, now asserting `5905156`) |
| `pytest tests/integration` (local services, `.env.test`) | 7 passed; platform migration head still `f6a2c8e4b1d9` |
| `CRM_APP_IDENTITY_TEST=1 pytest tests/identity` | 1 passed |
| `saas-os-local-identity` rerun against the local ZITADEL | Exit 0; existing project and application found, nothing created, client ID unchanged |
| detect-secrets hook | Exit 0, after replacing the audited false-positive hash of the pin SHA in `.secrets.baseline` |
| pip-audit (hashed export, SaaS-OS excluded) | "No known vulnerabilities found" |

| Clean copy (criterion 1): trackable files copied to a fresh temporary directory, empty uv cache | `uv sync --locked` and `uv lock --check` exit 0; installed commit `5905156…`; unit tests 43 passed; directory removed afterwards |

Not run: CI (criterion 9, still blocked on commit approval).

## Security assumptions and unverified behaviour

- **Migration role (development and CI only):** the migration role is the
  PostgreSQL bootstrap superuser. Production needs a dedicated
  schema-owner role with only the rights the migrations need. That design
  is not done.
- **RLS on product tables:** the RLS policy itself is not exercised yet,
  because no tenant table exists. RLS predicate-free and cross-tenant tests
  start with the first table (Phase 2).
- **SUBTREE access:** not tested.
- **Same-origin rule:** verified only for `POST /auth/logout`.
- **ZITADEL v4.19.5:** not the version SaaS-OS was qualified against. It
  was verified only by the local login test.
- **Lifetimes:** session cookie and token lifetimes are SaaS-OS defaults
  and were not reviewed.
- **Development secrets:** read from `.env` in the working directory. In
  production they come from the process environment or `*_FILE` mounts.
  No production secret store is selected.
- **Logging:** SaaS-OS logs carry request IDs. Console tracing prints span
  attributes. The identity test checked that no configured password
  appeared in the server log; broader log-content review is not done.
- **CI workflow:** never executed on GitHub. Linux differences, such as
  `PGHOST` handling and the `psql` client on the runner, are untested.
- **Third-party login pages:** the identity test drives ZITADEL's HTML
  login pages and may break on a ZITADEL upgrade. It is therefore opt-in
  and not part of CI.

## Blockers

| Blocker | Impact | Needed |
| --- | --- | --- |
| No commit or remote authorized | Phase 1 criterion 9; any CI evidence | Owner approval to create the private `aelboum/crm-app` repository, make the first commit, and push |
| Claude Design not accessible (no design MCP server configured) | Frontend work and the P-6 decision | Owner adds the Claude Design MCP server and completes `/design-login`, or exports the project files locally. Standalone Claude Design closes 2026-12-14 |
| ZITADEL v4.19.5 instead of the proposed v4.19.0 | Recorded under P-4 | Owner confirmation |

## Open questions recorded for later phases

- D-WS details (workspace discovery, signup, agency access) are verified
  in Phase 2.
- The purge-participant registry module is documented but not a package
  export. Settle its use before the first tenant table.
- The timing of calendar/booking, campaigns, automation, AI, and
  reporting relative to the K5 MVP.
- The sibling repository's ownership and permission, before any reuse.
- Written terms for SaaS-OS (`UNLICENSED`) before third-party
  involvement.
- A trademark check on the product name before any public use.

## Next authorized action

None beyond reporting. The next roadmap task is Phase 2 (identity,
workspaces, and tenant isolation). It should start only after Phase 1
criterion 9 is resolved or explicitly waived by the owner.
