# Progress Record

The verified current state of the project. `ROADMAP.md` defines the
destination; this file records what is actually true. Do not record
anything here that was not verified.

**Last updated:** 2026-10-21 (SaaS-OS pin moved to v0.3.0, decision K3.1;
first local commits, decision K2.1; remote, push and first CI run,
decision K2.2; Claude Design inspection, D-DES and K5.1; Phase 2
decisions P2-A to P2-E approved)

## Current phase

- **Phase 0 — Discovery:** evidence complete. Task 0.3 was completed on
  2026-10-21 by a read-only inspection of the owner's file export of the
  Claude Design project; the Claude Design MCP workflow was not used.
  Canonical record: `DESIGN-INSPECTION.md`.
- **Phase 0.5 — Foundational decisions:** K1–K5, D-WS and P-1 to P-6
  approved and recorded in `DECISIONS.md`; K5.1 (global SaaS direction)
  approved 2026-10-21. P-6 defers the frontend framework choice, which
  is still open.
- **Phase 1 — Product foundation:** complete. Locally verified, and CI
  passed on the exact pushed commit `dbb15609cd2531d3c430f06ee9c2e7bbd7f6a1c6`
  (GitHub Actions run 39652641595, 2026-10-21), which meets acceptance
  criterion 9 (decision K2.2). CI also passed on `13d6685` (run
  39653421776).
- **Phase 2 — Identity, workspaces and tenant isolation:** not started.
  Its decisions P2-A to P2-E were approved on 2026-10-21 with conditions
  (`DECISIONS.md`); implementation needs an approved Phase 2 plan.

## Repository state

- **Directory:** `C:\Users\imran\Documents\crm-app`, branch `main`.
- **Commits** on `main` (decisions K2.1 and K2.2):
  - `0bdbfdb4ef382b1b64b28b7589123a425f6b9cf4` — Phase 1 foundation on
    SaaS-OS v0.1.2 (`b0809ee`), 44 files;
  - `35e13e8873ba47ac8a4da752bfa089a6c72ec01f` — SaaS-OS v0.3.0 upgrade
    (decision K3.1), 10 files; installed pin
    `5905156a99a4526e5071ce091a58667c08b0a019`;
  - `df6d810a267095c351659b84cb9d7f728427d36f` — project records for the
    local commits;
  - `dbb15609cd2531d3c430f06ee9c2e7bbd7f6a1c6` — CI keeps a result for
    every commit on `main` (per-commit concurrency group, no
    cancellation on `main`);
  - a documentation-only follow-up recording the remote and CI result.
- **Remote:** `https://github.com/aelboum/crm-app`, default branch
  `main`, created and pushed 2026-10-21 (decision K2.2). Visibility on
  2026-10-22 (`gh repo view`): **public**, by the owner's choice; the
  owner intends to make it private later. Further
  pushes need approval each time; pull requests, merges, tags,
  releases and deployment are not authorized.
- **Untracked local files, never committed (covered by `.gitignore`):**
  - `.env` and `.env.test`: local-only random credentials and the local
    OIDC client ID;
  - `.venv/`;
  - `deploy/local/.bootstrap/` (ZITADEL's bootstrap token);
  - tool caches.
- **Local Docker services** (project `crm-app-local`, all bound to
  127.0.0.1): `db` on 55432, `redis` on 56379, `zitadel` on 8081.
  `zitadel-db` publishes no port. (Changed 2026-10-22, decision D-IDL: `edge`
  on 8000 fronts the application and ZITADEL; ZITADEL publishes no port.) They are still running. Stop them with
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

CI on GitHub: see "Criterion 9: CI on the pushed commit" below.

## Criterion 9: CI on the pushed commit (2026-10-21)

GitHub Actions run 39652641595 (`push` to `main`), head commit
`dbb15609cd2531d3c430f06ee9c2e7bbd7f6a1c6`, which is the remote `main`
(`git ls-remote origin refs/heads/main`). Conclusion: success.

| Job | Result | Evidence from the run log |
| --- | --- | --- |
| quality | success | 32 files already formatted; ruff: all checks passed; pyright: 0 errors; import-linter: 2 kept, 0 broken; unit: 43 passed |
| integration | success | 7 passed against the PostgreSQL 16 and Redis 7 service containers (`CRM_APP_REQUIRE_INTEGRATION=1`, so missing settings fail instead of skipping) |
| security | success | pip-audit: no known vulnerabilities; detect-secrets hook passed |

This was the first run on Linux. The local integration suite was not
rerun after the CI concurrency commit because Docker Desktop was
stopped; that commit changes only `.github/workflows/ci.yml`.

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
| Frontend framework not chosen (P-6) | Frontend work | Resolved 2026-10-22: React + Vite SPA (`DECISIONS.md` P-6.1) |
| Missing designs (states, a generic CRM version, membership, consent) | Frontend work on MVP screens | Design requests in `DESIGN-INSPECTION.md` §6, before standalone Claude Design closes on 2026-12-14 |
| No email provider configured | Real invitation delivery (P2-C) and the MVP email channel | An approved transactional email provider and credentials; until then nothing may be shown as sent |
| Purge participants outside the approved import surface | Removal of product data on tenant purge, before the first tenant table | Owner decision on a narrowly scoped exception or another supported path (P2-D) |
| ZITADEL v4.19.5 instead of the proposed v4.19.0 | Recorded under P-4 | Owner confirmation |

## Open questions recorded for later phases

- D-WS details: agency access and initial provisioning are now decided
  (P2-B, P2-C); the product-owned workspace index for the switcher is
  designed in the Phase 2 plan.
- Whether `SystemCaller(PROVISIONING)` may seed product roles right
  after the tenant bootstrap, and add permissions to existing workspaces
  later (P2-A open point). Settle in the Phase 2 plan.
- The purge-participant registry module is documented but not a package
  export (P2-D). Settle its use before the first tenant table.
- Multi-region hosting and data residency (K5.1).
- The timing of calendar/booking, campaigns, automation, AI, and
  reporting relative to the K5 MVP.
- The sibling repository's ownership and permission, before any reuse.
- Written terms for SaaS-OS (`UNLICENSED`) before third-party
  involvement.
- A trademark check on the product name before any public use.

## Next authorized action

None beyond reporting. Phase 1 is complete and Phase 0 task 0.3 is
done. Phase 2 is in progress (2026-10-21), following
`PHASE2-PLAN.md`. Owner decisions that day: Q6 approved (role matrix);
Q-purge option (a), upstream first with no internal-import exception;
Q1 approved as a design direction only; S1b and S3 approved within
supported APIs. Done and committed (plan §11.1):
- the permission catalogue and role templates (`src/crm_app/roles.py`);
- registration of the 39 granted permissions in the migration step
  (`crm_app.permissions`), with no role created or granted anywhere;
- structural schema guards that keep tenant-owned tables out until the
  purge gate G1;
- two read-only routes, `GET /v1/workspaces/{id}` and
  `/v1/workspaces/{id}/members`.

All checks pass locally:
- unit tests (77), plus the static, secret and dependency checks;
- integration tests (33), including the tenant-table guards and the
  workspace route tests, run against local services;
- the opt-in identity test (1).

Committed as `a069a6a1675802139e8862d0f639388d521b95c7` on `main` and
pushed; local and remote `main` matched and the working tree was clean.
GitHub Actions run 39675570028 on that commit: **success**.
- quality: 77 unit tests passed; pyright 0 errors; import contracts 2
  kept.
- integration: 33 passed against CI's PostgreSQL and Redis services.
- security: secret scan passed; dependency audit found no known
  vulnerabilities.

No merge, release or deployment.

Not done: tenant tables, the purge participant, the provisioning command,
and any route that changes memberships, roles or Owners (gates G1, G2,
G-LOCK in plan §14). Both upstream requests are drafted and have not been
sent: purge-participant registration (plan Appendix A) and adding
permissions to existing workspaces (plan §7.5, draft in Appendix B).
Tenant isolation is untested, because no tenant-owned table exists.

**Since then (2026-10-21; plan §11.2):**
- **Provisioning command (S6, gate G2):** `python -m crm_app.provision`,
  8 integration tests against `crm_app_test` pass. No real workspace has
  been provisioned.
- **Membership and role routes with last-Owner protection (S7, gate
  G-LOCK):** 8 integration tests pass, including 15 rounds of competing
  Owner removals. In every round the database kept exactly one active
  Owner. The operator rule for paths outside the product is in plan §5.4.
- **Totals:** unit 83, integration 49, static and secret checks pass.
- **Committed** as `19e7dce3f05c90580dcc930fc7e49fde617acda0` on `main`
  and pushed (2026-10-22, owner-approved). GitHub Actions run 39742030028
  on that commit: **success** (quality, integration, security).
- G1 (tenant tables) remains blocked.

Both upstream request drafts are now complete with acceptance criteria
and expected tests (plan Appendices A and B, 2026-10-22); neither has
been sent.

Next: every remaining Phase 2 step waits on an owner decision or an
external dependency (plan §15): sending the upstream requests (G1, G7),
provisioning a real workspace, Q3–Q5 (invitations) and P-6 (frontend).

**2026-10-22, owner decisions:** both upstream requests opened
(aelboum/saas-os#87, #88); P-6 decided as a React + Vite SPA (P-6.1);
Q4 manual invitation link and Q5 two-step role confirmation approved.
Next: frontend scaffold and Phase 2 screens (plan §16, F1). G1 waits on #87.

**F1 (2026-10-22, plan §11.3):** the frontend shell and the member screens,
served by the API under `/app`, plus `GET /v1/workspaces/{id}/access`.
Frontend 15 tests, unit 91 and integration 55 (full suite, `crm_app_test`) pass locally.
Not yet tried in a real browser against ZITADEL (done since; see below).

**Browser validation (2026-10-22, real Chrome, local ZITADEL; plan §11.3):**
- **Setup:** app server started by Claude with the owner's approval,
  against the disposable `crm_app_test` database and the local OIDC client.
  The owner signed in to ZITADEL themselves; no credential passed through
  Claude. A throwaway workspace was seeded in `crm_app_test` only (the
  owner plus fake Owner, Admin, Member and suspended Member). The server
  was stopped afterwards. Compose services were not touched.
- **Verified in the browser:**
  - sign-in redirect (PKCE S256, callback `/auth/callback`) and return
    to `/app`;
  - member list, roles and statuses;
  - suspend and reactivate;
  - remove (Escape cancels and sends nothing; Confirm revokes);
  - removing another Owner's Owner role after confirmation (200);
  - stepping down as the last Owner, refused with the right message
    (409);
  - opening a workspace by ID with the keyboard;
  - an unknown workspace getting the neutral not-found message;
  - sign-out.
- **Page checks:** no application console errors and no CSP violations
  (only a wallet extension's warnings). The self-hosted font loaded. The
  session cookie is not readable from JavaScript.
- **Defects found and fixed (tests added, frontend now 17 tests):**
  - keyboard focus fell to `<body>` when a removed member's row
    disappeared; it now moves to the result message;
  - after sign-out the previous workspace's data stayed on screen; the
    app now returns to the start page.

  Both fixes were rechecked in the browser.
- **Gaps found, not fixed:**
  - Sign-out ends only the app session. The ZITADEL session survives, so
    "Sign in" succeeds again without a password. SaaS-OS's logout does
    not end the provider session; an upstream request is drafted (plan
    Appendix C), not sent.
  - In Git Bash on Windows, `AUTH_POST_LOGIN_PATH=/app` is rewritten
    into a Windows path and sign-in fails with "Authentication is not
    configured"; this is now documented in the README.
  - `HEAD /app` returns 405 (only GET is registered).
- **Not tested in a browser:** the Admin view (actions on Owners hidden),
  automated contrast measurement, screen-reader output, and mobile width.
- **Uncommitted:** the two fixes, their tests, and these documents. The
  owner has not authorized a commit for this cycle.

**Same-origin sign-in (2026-10-22, decision D-IDL):**
- Local ZITADEL now sits behind the `edge` service on
  `http://localhost:8000`, with Login V2.
- **Verified:**
  - live discovery shows issuer `http://localhost:8000`;
  - in Chrome, the whole sign-in stayed on `localhost:8000`, from `/app`
    through `/oauth/v2/authorize` and `/ui/v2/login/...` to
    `/auth/callback` and back to `/app`; the owner entered their own
    credentials;
  - a membership change through the edge succeeded, so the same-origin
    check passes behind the proxy;
  - no application console errors;
  - with a throwaway Caddy and an echo server using the same Caddyfile,
    the app received only `saas_os_session`, never the provider cookies.
- **Observed gaps:**
  - a sign-in left open for more than 10 minutes ends on a raw 400 page
    at `/auth/callback` (SaaS-OS's transaction lifetime; its page);
  - Login V2 offers self-registration and is shown in the browser's
    language;
  - sign-out still leaves the ZITADEL session alive (Appendix C).
- **Uncommitted:** `deploy/local/compose.yaml`, `deploy/local/Caddyfile`,
  `.env.example`, `.env.test.example`, README and docs. The owner's
  `.env` was updated locally (backup `.env.backup-2026-10-22`, untracked);
  `.env.test` still names the old issuer.

**Sign-in settings (2026-10-22, decision D-IDL.1):**
- `deploy/local/configure-zitadel.py` applied the settings to local
  ZITADEL. It printed the resulting values, and a second run changed
  nothing.
- **Checked in the browser:** Login V2 no longer shows a registration
  link.
- **Not yet tried by hand:** lockout and the hidden-unknown-username
  behaviour.
- **Login V2 response headers** (observed through the edge):
  - `frame-ancestors 'none'`, `X-Frame-Options: deny`, `nosniff`, and
    `no-store` caching;
  - its own Content-Security-Policy allows `'unsafe-inline'` and
    `'unsafe-eval'` scripts and names the internal `http://zitadel:8080`
    for images and fonts. That policy belongs to ZITADEL's official
    image; changing it would mean customizing that image (SaaS-OS
    ADR-0025 uses the official one). Because Login V2 shares the app's
    origin, this is the weaker side of the shared-origin trade-off
    ADR-0025 accepted;
  - it also sends HSTS, which browsers ignore over plain HTTP.
- **Commits:** the earlier work is committed as `4e576e7` and `3023ff5`;
  GitHub Actions run 39754775922 succeeded (quality, frontend,
  integration, security). The settings script and these notes are
  committed together, after these notes were written.

**2026-10-22 (later), Phase 3 design, app frame and design fidelity (uncommitted):**
- **Phase 3 design:** a build-ready plan for Contacts and Companies is in
  `PHASE3-PLAN.md`. It is planning only; no table or migration (G1).
  Owner questions are in its §18.
- **App frame, rebuilt to the design** (`frontend/src/shell/`,
  `components/ui/`):
  - the header, the sidebar (232/60 px, collapsible groups) and the
    design's placeholder page for every unbuilt module;
  - Settings › Team & roles in the design's settings layout, with a
    read-only role matrix generated from Q6;
  - shared Button, Badge, Dialog, DataTable, Toast and state components.
  - Unbuilt features are labelled "soon" or "not available yet";
    nothing pretends to work.
- **Design fidelity:**
  - Inventory: every file in the export was inspected from source.
  - Comparison: geometry and styles of the frame and the Team & roles
    page were compared numerically against the prototype, served locally
    at the same viewport.
  - Six material differences were fixed; the remaining deviations are
    listed with reasons.
  - Details: `DESIGN-FIDELITY.md`.
- **Quality:**
  - `HEAD /app` returns 200.
  - Lighthouse accessibility scores 100 with no failed audits on
    Settings and on a placeholder page, colour contrast included.
  - Keyboard order and focus are checked, as is the phone layout at
    390 px (emulated).
  - The Admin view is checked with a test Admin session.
  - A real CSP violation (React Aria's injected stylesheet) is fixed with
    a hash-only allowance, and the favicon 404 is removed.
  - Test sessions were created only in `crm_app_test` and revoked
    afterwards.
- **Tests:** frontend 25; Python unit 92.
- **Not verified:**
  - pixel overlays (no image library);
  - Firefox and Safari;
  - screen reader output;
  - the phone layout in a real window (the Chrome window could not be
    resized; DevTools emulation was used).
- **Committed locally** (owner-authorized, 2026-10-22; **not pushed**):
  backend and tests `dc1b4f7`, frontend `2e722e7`, and these documents in
  the following commit. CI has not run on them.

**Settings › My profile (2026-10-22, uncommitted):**
- Implemented in the design's layout with only what exists: the real role
  line, disabled fields with a note that profiles cannot be stored yet
  (G1), the browser's time zone shown read-only, and "Manage" disabled.
- No storage, endpoint or migration.
- Compared against the design at 1280 px; one mismatch fixed
  (`DESIGN-FIDELITY.md` §4a).
- Frontend tests: 28 passed. Lighthouse accessibility 100 (0 failed) on
  My profile; no console messages; no overflow at 390 px.
- Review fix: the role shown is now the most senior one, not the
  alphabetically first.
- Screens compared so far: the app frame, Team & roles and My profile.
  The other design screens are placeholders or not started.

**My profile committed locally; palette (2026-10-22):**
- **My profile:** commit `02a6129`, local and not pushed. Validated on its
  own in a clean worktree: types, lint, 28 tests and the build pass.
- **Earlier pushes:** commits `dc1b4f7`, `2e722e7` and `3080d20` were
  pushed; GitHub Actions run 39766719219 succeeded (quality, frontend,
  integration, security).
- **⌘K palette:** implemented with page navigation only; it never
  searches records (`DESIGN-FIDELITY.md` §4b). Committed locally with
  owner authorization; not pushed. Frontend tests: 29 passed.
- **Screens compared so far:** the app frame, Team & roles and
  My profile. The palette is checked for behaviour and accessibility but
  not compared geometrically. No other design screen is implemented or
  verified.
- **Outstanding:** Firefox and Safari, and a real screen reader; none is
  available in this environment.

**Pushes, palette comparison and #87 (2026-10-22):**
- **Pushed:** `02a6129` (My profile), as a fast-forward. GitHub Actions
  run 39769519580: **success** (quality, frontend, integration,
  security).
- **Palette:** committed locally as `264c639`; not pushed.
- **Palette comparison against the design** (`DESIGN-FIDELITY.md` §4b),
  1280×609, numeric:
  - the panel, input, rows, header, footer, empty state and backdrop
    match;
  - three differences fixed: input text colour, panel height (it
    overflowed the viewport because of the note row), and placeholder
    contrast;
  - these fixes are uncommitted.
- **#87:** still open with no response; no newer SaaS-OS release. A
  refined technical proposal is in `PURGE-API-PROPOSAL.md`; it is not
  sent. G1 stays closed.

**Later on 2026-10-22:**
- **Pushed:** `264c639`, `c6af3ef` and `3376e37`.
  - GitHub Actions run 39771257565 on `3376e37` **failed** in the quality
    job's format step: `ruff format` also formats Python blocks in
    Markdown, and the proposal's example lacked blank lines.
  - Fixed in `e0fe0fd`; run 39771661933 **succeeded** (quality,
    frontend, integration, security).
- **SaaS-OS #87:** the owner-approved comment was posted
  (issuecomment-6339887993). No reply yet. G1 stays closed.
