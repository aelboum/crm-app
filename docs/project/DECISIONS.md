# Decision Log

This log records consequential product decisions. Each entry states the
decision, who approved it, the evidence it rests on, and its consequences.
Entries are append-only: a later decision supersedes an earlier one by
referencing it, never by editing it.

Status values: **Approved** (owner decision), **Proposed** (awaiting owner
approval), **Superseded**.

---

## K1 — Product base

- **Status:** Approved by the owner, 2026-10-20.
- **Decision:** Build the product from scratch, starting from the SaaS-OS
  v0.1.2 consumer scaffold (`examples/consumer-scaffold/` at commit
  `b0809eeb3448956a4dc85a5541514823ec9ceae7`). Do not modify SaaS-OS.
- **Reference ZIP:** `leadstack-crm-main.zip` (47,636,561 bytes, SHA-256
  `59b760007fc736c61549dcbea177f4b5f0a49be59647bc26694edd6f1ad24eee`) is
  feature-idea reference material only. Do not copy its code, schemas,
  business rules, text, or assets.
- **Evidence:** The ZIP is a GitHub export of commit `dcc2476` of
  `sofioco/leadstack-crm`, which is the AgentStack CRM template
  (© AgentStack.Dev) under PolyForm Perimeter 1.0.0. That licence includes
  a noncompete clause covering products that compete with the software,
  including ports to other languages or platforms. Nothing in the archive
  ties ownership to the owner. See `PHASE0-DISCOVERY.md`.
- **Sibling repository:** Code from the owner's earlier
  `aelboum/leadstack` repository (`C:\Users\imran\Documents\Leadstack`) is
  not reused until its ownership and permission are confirmed and recorded
  here. Its documentation may be read as requirements input.
- **Consequences:** No inherited code or history. Platform concerns come
  from SaaS-OS public contracts; product concerns are implemented here.

## K2 — Repository strategy

- **Status:** Approved by the owner, 2026-10-20.
- **Decision:** A new, empty, private repository under the `aelboum`
  GitHub account, developed in a new local directory with fresh Git
  history. Do not reuse or rewrite the history of either existing CRM
  repository. Initially carry over only `CLAUDE.md` and `ROADMAP.md`.
- **Local directory:** `C:\Users\imran\Documents\crm-app`, initialized with
  `git init -b main` on 2026-10-20 and holding no commits. The directory
  name is provisional (see P-1 in `PHASE1-PLAN.md`).
- **Not yet authorized:** creating the remote repository, setting its
  visibility, committing, pushing, opening pull requests, releasing, or
  deploying. Each needs explicit owner approval when it is due.
- **Evidence:** `C:\Users\imran\Documents\leadstack-crm` has AgentStack code
  in every commit since `16fdc24` (2026-06-25). Its remote
  `sofioco/leadstack-crm` is public, owned by another GitHub user, and the
  owner's account has pull-only access. `aelboum/leadstack` is public and
  contains a prior product with uncommitted work.
- **Consequences:** Both existing repositories and their working trees
  stay untouched.

## K3 — SaaS-OS pin

- **Status:** Approved by the owner, 2026-10-20. Fixed through Phase 1.
- **Decision:** Exactly one SaaS-OS dependency:
  `saas-os @ git+https://github.com/aelboum/saas-os@b0809eeb3448956a4dc85a5541514823ec9ceae7`
- **Evidence (verified 2026-10-20):**
  - `git ls-remote https://github.com/aelboum/saas-os refs/tags/v0.1.2^{}`
    resolves to `b0809eeb…`; the annotated tag object is `dd398b1`.
  - The GitHub Release `v0.1.2` was published 2026-10-20 with no assets.
  - `main` (`2adf634`) is nine commits ahead of the tag, with no changes
    under `saas_os/` and none to `pyproject.toml`.
  - A clean, non-editable install of the pin into a throwaway Python
    3.13.14 virtual environment reported version `0.1.2`,
    `direct_url.json` commit `b0809eeb…`, a single top-level package
    `saas_os`, and `uv pip check`: all packages compatible.
  - The SaaS-OS migration head is `f6a2c8e4b1d9`.
  - CONSUMER-GUIDE §3 states that no pin older than `4197d2f` is supported;
    `b0809ee` is newer.
- **Consequences:** Imports use only the `saas_os` public surface (see
  `CLAUDE.md` §3). Moving the pin requires a new approved decision and the
  CONSUMER-GUIDE §14 upgrade procedure.

## K4 — Product name

- **Status:** Approved by the owner, 2026-10-20.
- **Decision:** "LeadStack CRM" is an internal, provisional working name
  only. Technical package, import, and repository names are neutral.
  There is no public launch and no investment in public branding until the
  name has been checked.
- **Evidence:** The sibling repository's `CLAUDE.md` describes it as
  inspired by a third-party product at `leadstack.dev`, which indicates a
  possible naming conflict. This has not been independently verified.
- **Consequences:** The neutral technical name is proposed in
  `PHASE1-PLAN.md` (P-1) and needs owner confirmation before the remote
  repository is created.

## K5 — Initial market and scope

- **Status:** Approved by the owner, 2026-10-20.
- **Target users:** Small agencies and SMBs in the Netherlands and the EU.
- **Deployment model:** Hosted, single EU region.
- **UI language:** English, with an internationalization-ready structure.
- **MVP includes:** Workspaces and members; contacts; companies;
  pipelines; deals; tasks; forms; one email channel with consent and
  suppression controls.
- **Deferred:** SMS, WhatsApp, voice, reviews, AI auto-send, funnels,
  and white-labeling.
- **Consequences:** Roadmap phases that mention deferred features do not
  bring them into the MVP. Adding to the MVP requires a new decision.
  Calendar/booking, campaigns, automation, AI assistants, and reporting
  are outside the MVP list above; their timing needs a separate decision.

## D-WS — Workspace and tenant model

- **Status:** Approved by the owner, 2026-10-20. Implementation details
  must be verified against the pinned contracts in Phase 2 before use.
- **Decision:** A product workspace is the user-facing representation of
  a SaaS-OS tenant, not a second security boundary. An agency may
  eventually relate to multiple client workspaces, but every cross-tenant
  access path must be explicitly authorized and enforced. A workspace
  listing or membership index must never bypass SaaS-OS authorization or
  tenant isolation.
- **Contract evidence at the pin (verified by source reading):**
  - `saas_os.api.dependencies.get_tenant_context` admits a request only
    when the tenant exists, `is_accessible_to_principals` holds, and
    `saas_os.core.identity.get_membership(tenant_id, user_id)` returns a
    membership; every other case is the same 404.
  - `saas_os.core.identity` exports `get_membership` and
    `list_tenant_members(tenant_id)` but no function that lists the
    tenants of a user; `/auth/me` returns only `user_id`.
  - `saas_os.core.tenancy.create_tenant(name, *, parent_id=None, caller)`
    accepts only a `UserCaller` holding `platform.tenant:create` or
    `SystemCaller(SystemAuthority.PROVISIONING)`.
  - `saas_os.core.rbac.assign_first_role_for_new_tenant` documents itself
    as reserved for SaaS-OS's own tenant bootstrap.
- **Open questions (to resolve in Phase 2, not assumed here):**
  - How a user discovers their workspaces without a SaaS-OS "my tenants"
    API. Any product-side index may only be a candidate list; each entry
    must be re-checked through `get_membership` and tenant accessibility
    before it is shown or used.
  - Whether self-service signup may create a root tenant and its first
    administrator through supported contracts.
  - How agency staff reach client workspaces. At the pin, request access
    requires a direct membership in the target tenant; SUBTREE role scope
    alone does not admit a request.

## P-1 to P-6 — Phase 1 repository and tooling

- **Status:** Approved by the owner, 2026-10-20, together with Phase 1 itself.
- **P-1:** Repository and project name `crm-app`; Python package and import
  namespace `crm_app`. The customer-facing name stays provisional (K4).
- **P-2:** uv with a committed `uv.lock`. SaaS-OS stays pinned to
  `b0809eeb3448956a4dc85a5541514823ec9ceae7`.
- **P-3:** Ruff, Pyright, import-linter, pytest, pip-audit and
  detect-secrets as development and CI tools. No new runtime framework
  without a documented need and approval.
- **P-4:** PostgreSQL 16 and Redis 7 for local development. ZITADEL's
  version, image tags, configuration and compatibility must be verified
  before they are recorded as fixed. Local services are never exposed
  publicly.
- **P-5:** A proprietary notice, no open-source licence. No publication or
  distribution until the licensing and ownership position is clear.
- **P-6:** The frontend framework decision is deferred until Claude Design
  has been imported and inspected.

## P-4 verification result — local service images

- **Status:** Recorded 2026-10-20 as verification evidence under P-4. The
  ZITADEL patch version below differs from the one proposed in
  `PHASE1-PLAN.md` and is reported to the owner for confirmation.
- **Images** (development only; pinned by tag and digest in
  `deploy/local/compose.yaml`):
  - `postgres:16-alpine@sha256:7218…80ea` (PostgreSQL 16.15)
  - `redis:7-alpine@sha256:858f…3499` (Redis 7.4.11)
  - `busybox:1.36.1@sha256:73aa…1662`
  - `ghcr.io/zitadel/zitadel:v4.19.5@sha256:a586…18d3`
- **Why v4.19.5, not the proposed v4.19.0:** GitHub security advisories
  published by ZITADEL list v4.19.0 inside the affected ranges of:
  - GHSA-x4c7-fpcx-w9q6 and GHSA-jh92-5mrj-p2w2 (high; patched in 4.19.2);
  - GHSA-mchc-246r-6m76, GHSA-84fg-x5h4-w8xv and GHSA-qj3q-235g-qr6w
    (high; patched in 4.19.5).

  v4.19.5 was the latest release on 2026-10-20.
- **Compatibility evidence:**
  - `saas-os-local-identity` from the pinned SaaS-OS created the OIDC
    project and public PKCE application on v4.19.5.
  - `tests/identity/test_oidc_login.py` signed in through ZITADEL's login
    UI, obtained a SaaS-OS session (`/auth/me` 200), and logged out.
  - SaaS-OS itself was qualified against v4.19.0, not v4.19.5. The patch
    version difference is verified only by this local test.

## K3.1 — SaaS-OS pin moved to v0.3.0

- **Status:** Approved by the owner, 2026-10-21 ("upgrade to v0.3.0").
  Supersedes the commit named in K3 (and in P-2); every other part of K3
  stands. The pin stays fixed until a further approved decision.
- **Decision:** Exactly one SaaS-OS dependency:
  `saas-os @ git+https://github.com/aelboum/saas-os@5905156a99a4526e5071ce091a58667c08b0a019`
- **Evidence (verified 2026-10-21):**
  - `git ls-remote https://github.com/aelboum/saas-os refs/tags/v0.3.0^{}`
    resolves to `5905156…`, the merge commit of pull request #86, which
    is also `main`; the annotated tag object is `e01b6a0`.
  - The GitHub Release `v0.3.0` was published 2026-10-21 with no assets.
    The `CI` (run 39628783399) and `Release` (run 39634387373) workflows
    succeeded on `5905156`.
  - Between `b0809ee` (v0.1.2) and `5905156` (39 commits), the only
    library change is `saas_os/infra/local_identity/zitadel_bootstrap.py`
    (complete paged listings, new `IncompleteListingError`). The package
    metadata raises the certifi floor to `2026.10.19`. The changelog
    records no migration (head `f6a2c8e4b1d9`) and no changed public
    signature. The other changes are SaaS-OS's own Compose files,
    `deploy/` units, scripts, CI and documentation, which this product
    does not use.
  - `saas-os-update check` (policy v4) returned `BLOCKED` (exit 30) only
    because the updater does not rewrite `uv.lock` and the working tree is
    untracked; the changed paths were reviewed by hand instead.
  - CONSUMER-GUIDE §14, v0.1.2 → v0.2.0 and v0.2.0 → v0.3.0: the only
    step that applies here is accepting `certifi>=2026.10.19`; `uv.lock`
    already had 2026.10.19. The ZITADEL, `.env.app` and `deploy/` steps
    concern `docker-compose.prod.yml`, which this product does not run.
  - `uv lock` changed only the saas-os entry; the other 71 packages are
    unchanged. Every Phase 1 check passed again on the new pin (see
    `PROGRESS.md`).
- **Rollback:** move the pin, lock entry, `APPROVED_PIN` and the
  `.secrets.baseline` hash back. Both releases share the migration head.

## K3.2 — SaaS-OS pin moved to v0.5.0

- **Status:** Approved by the owner, 2026-10-23 ("Proceed with Project A
  only: the crm-app dependency pin update to SaaS-OS v0.5.0").
  Supersedes the commit named in K3.1; every other part of K3 stands.
  The pin stays fixed until a further approved decision.
- **Decision:** Exactly one SaaS-OS dependency:
  `saas-os @ git+https://github.com/aelboum/saas-os@b03d87a5272924d1e413c144dc5c3b41ac430580`
- **Evidence (verified 2026-10-23):**
  - `git ls-remote https://github.com/aelboum/saas-os refs/tags/v0.5.0^{}`
    resolves to `b03d87a…`, the merge commit of pull request #101, which
    is also `main`; the annotated tag object is `1254662`.
  - The GitHub Release `v0.5.0` was published 2026-10-23. The `CI` (run
    40002133371, 7 of 7 jobs) and `Release` (run 40006170148) workflows
    succeeded on `b03d87a`, and `scripts/release.py verify --tag v0.5.0`
    passed.
  - Between `5905156` (v0.3.0) and `b03d87a` (25 commits): v0.4.0 adds
    deployment-level email provider selection and requires SMTP TLS in
    production; v0.4.1 moves SaaS-OS's own frontend to Next.js 15.5.28 and
    fixes its release tooling; v0.5.0 exports the tenant-purge
    participant API from `saas_os.core.tenancy` (SaaS-OS #87, #94),
    checks participant names against `[a-z0-9][a-z0-9._-]{0,99}`, records
    `product_participants_skipped` in the purge audit (#99) and exports
    `AuthorityNotAuthorizedError` from `saas_os.core.rbac` (#98). No
    migration in any of them (head `f6a2c8e4b1d9`, 52 SaaS-OS migrations
    at both commits).
  - CONSUMER-GUIDE §14, v0.3.0 → v0.4.0, v0.4.0 → v0.4.1 and v0.4.1 →
    v0.5.0: no step applies. This product sends no email through SaaS-OS
    and sets no SMTP or `EMAIL_PROVIDER` setting; it does not build
    SaaS-OS's frontend; it registers no purge participant, does not call
    `purge_tenant()` and does not catch `AuthorityNotAuthorizedError`.
    Every SaaS-OS import is still a public export
    (`tests/unit/test_import_surface.py`).
  - `saas-os-update check` (policy v4) returned `BLOCKED` (exit 30) only
    because the updater does not rewrite `uv.lock`; its review categories
    (architecture, authorization, dependency_toolchain, public_api,
    tenant_rls, unknown) were reviewed by hand against the points above.
  - `uv lock` changed only the saas-os entry; the other 71 packages are
    unchanged. The checks in `PROGRESS.md` passed on the new pin.
- **Not decided here:** registering this product's purge participant
  and creating tenant-owned tables stay with gate G1 (Q-purge) and need
  their own approved work.
- **Rollback:** move the pin, lock entry, `APPROVED_PIN` and the
  `.secrets.baseline` hash back. Both releases share the migration head.

## K3.4 — SaaS-OS pin moved to v0.8.0

- **Status:** Approved by the owner, 2026-11-06 ("Saas-os is updated
  please upgrade crm-app"). Supersedes the commit named in K3.3; every
  other part of K3 stands. The pin stays fixed until a further approved
  decision.
- **Decision:** Exactly one SaaS-OS dependency:
  `saas-os @ git+https://github.com/aelboum/saas-os@140d9dd2e724357cf54e74fb3be9dadb8943a238`
  (v0.8.0, the latest release; v0.7.0 is skipped as an intermediate
  step, and the unreleased commits after v0.8.0 on SaaS-OS `main` are
  not taken).
- **Evidence (verified 2026-11-06):**
  - The tag `v0.8.0` resolves to `140d9dd…`, the merge commit of release
    pull request #219; `git tag -v v0.8.0` reports a good ED25519
    signature by the owner's key.
  - Between `d980e73` (v0.6.0) and `140d9dd`: eight migrations (head
    `b3d5f7a9c2e4` → `f0cc2e656d79` at v0.7.0 → `e2b7c4d9a1f6`), all
    additive; the permission-grant ledger and its operator commands;
    system actor attribution (`SystemActor`,
    `record_system_action_in_transaction`); outbox timing on the
    database clock, ambiguous-outcome classification and started
    markers (off by default); `http://` webhook destinations refused by
    default; stricter single-mailbox address validation; platform audit
    rows about a user store a reference (`user_subject`) instead of the
    raw id. The public API snapshot only grew.
  - CONSUMER-GUIDE §14, v0.6.0 → v0.7.0 and v0.7.0 → v0.8.0, against
    this product:
    1. Migrations: `crm_app.migrate` runs SaaS-OS's first, so local and
       test databases move to `e2b7c4d9a1f6` on the next run;
       `tests/integration/test_foundation.py` expects that head.
    2. New platform permissions: not needed; this product runs none of
       those operator commands.
    3. `http://` webhooks, `OUTBOX_LEASE_SECONDS`, receiver
       de-duplication, outbox consumer timeouts, started markers: this
       product registers no outbox consumer and no webhook subscription,
       and sets neither setting.
    4. Audit initiators: every `record_in_transaction` call passes a
       `UserCaller` and no `initiated_by`, so the new refusal of a user
       initiator does not apply.
    5. Platform audit target shape: this product neither writes nor
       reads `core.platform_audit_log`.
    6. `core.users` rows: this product and its tests never delete them.
    7. Email: `EmailMessage` is built by keyword. The new
       `EmailOutcomeUnknownError` and `EmailNotSentError` subclass
       `EmailProviderError` and are not permanent, so `crm_app.emails`
       keeps its existing retry path for them (unchanged behaviour from
       v0.6.0). The stricter address check is already mapped to a
       permanent `invalid_address` failure.
  - Every SaaS-OS import is still a public export
    (`tests/unit/test_import_surface.py`).
  - `uv lock --upgrade-package saas-os` changed only the saas-os entry.
- **Follow-ups (not done in this move, each needs its own slice):**
  - `crm_app.emails` could stop retrying an `EmailOutcomeUnknownError`
    whose `retry_within` is `None` (SMTP: a retry may deliver twice),
    and bound Resend retries to `retry_within`. Production sending is
    not authorized, so nothing is sent twice today. **Blocked
    (2026-11-06):** the error classes are not exported from
    `saas_os.core.email`, and importing them from the private module or
    reading their attributes would break K3's public-surface rule;
    recorded as gap 14 in `saas-os-gaps.md` and filed, with the owner's
    approval, as aelboum/saas-os#223 (2026-11-06).
  - Gap 11 (`saas-os-gaps.md`): `record_system_action_in_transaction`
    with a `SystemActor` now exists, so worker, public-link and inbound
    actions could get tenant audit entries. **Done** for every path that
    had no entry (K3.5).
  - Gap 10: `saas-os-operator apply-permission-grants` (ADR 0060) is
    the sanctioned way to add a new permission to existing tenants'
    roles and could replace `crm_app.role_upgrade`; adopting it changes
    role semantics and needs owner approval. Design for review:
    `PERMISSION-GRANT-MIGRATIONS-PLAN.md` (2026-11-06).
- **Rollback:** move the pin, lock entry, `APPROVED_PIN`, the expected
  migration head and the `.secrets.baseline` hash back. v0.6.0's
  `saas-os-migrate` cannot run against a database at the new head
  (`Can't locate revision`); recreate local and test databases instead.

## P12-K — Integrations and API keys (2026-11-07)

- **Status:** Approved by the owner ("Follow you recommendations" on
  decisions A, B and D, 2026-11-07; "Approve" on the permission delivery
  below) and built (slice 12K).
- **What:**
  1. An integration is a SaaS-OS service account of the workspace with the
     product role **Member or Read-only, never Admin or Owner** (decision
     B), managed in Settings › Integrations by Owners and Admins
     (`crm_app.integration:manage`; decision A). It has up to 2 live API
     keys, optionally expiring after 30, 90 or 365 days; a key is shown
     once, in an uncached response, and SaaS-OS keeps only its hash.
     Disabling an integration revokes its keys and is final.
  2. A key, sent as `X-API-Key`, reaches exactly the routes pinned in
     `tests/unit/test_routes.py` `API_KEY_ROUTES`: reading, creating and
     updating contacts, companies, deals and tasks, archiving and restoring
     a record, setting a deal's outcome. Never a delete, an export, an
     import, members, roles, keys, automations or any setting; SaaS-OS
     refuses a key on any authority-changing permission (ADR-0047). A
     request with both a key and a session is refused.
  3. The key acts with its role's permissions, in its own workspace only;
     its changes are audited as the service account
     (`ServiceAccountCaller`, `records.audit_caller`,
     `system_audit.record_scoped(service_account=True)`).
- **Permissions:** `crm_app.integration:manage` (an administrative grant
  migration, held back like the others) and SaaS-OS's
  `service_account:create`/`:disable`, `service_account_role:create`,
  `api_key:create`/`:revoke`, `webhook_subscription:create`/`:delete`
  (for P12-H), all on Owner and Admin. SaaS-OS counts the latter as
  authority-changing and refuses them in grant migrations, so they are
  listed in `crm_app.permission_grants.OWNER_GRANTED_ADDITIONS`; the guard
  test checks each one is authority-changing and names its decision, and
  still fails any other template addition without a migration. New
  workspaces get them at provisioning; workspaces created before have no
  way to receive them until an owner-side route exists (none in
  production yet). Their Integrations page answers
  `integrations_unavailable`. `service_account:enable` was left out: no
  route re-enables an integration.
- **Known limits:** a notification or history entry made by an
  integration shows it as an unknown member ("Member 1234abcd"), not by
  name; there is no per-key usage view or last-used time (SaaS-OS keeps
  none).
- **Tests:** `tests/integration/test_integrations.py` (6),
  `tests/unit/test_routes.py` (the pinned key routes, Owner and Admin only),
  `tests/unit/test_permission_grants.py` (the new check),
  `frontend/src/pages/integrationSettings.test.tsx` (4).

## P12-H — Outbound webhooks (approved 2026-11-07; to build)

- **Approved:** Owners and Admins add HTTPS endpoint URLs and see the
  signing secret once (SaaS-OS `core.webhooks`: HMAC with a timestamp,
  delivery only through the worker's egress proxy, private addresses
  refused at every attempt, retries then dead-letter). Events
  `contact.created`, `contact.updated`, `deal.stage_changed`,
  `form.submitted`, `appointment.booked`; the payload carries the record's
  ID, type and a small set of fields (name, email, stage), sent to the
  address the Owner or Admin chose (decision C). Delivery history from
  SaaS-OS's outbox. Every endpoint receives every event until SaaS-OS
  filters per subscription (gap 19, recorded only; decision D).

## P8-N — The automation notify action (2026-11-07)

- **Status:** Done under the autonomous mandate (the owner: "Go" on the
  recommended Phase 8 notify action, 2026-11-07). In-app only: nothing is
  emailed, pushed or sent to the contact.
- **What:**
  1. A new action, `notify_member`: one in-app notification about the
     run's contact, to the contact's owner (the default) or to a named
     member, with a fixed message of 1 to 200 visible characters that the
     automation's author writes. The message is stored as written and never
     filled in from the contact, so no personal data is copied into the
     notification; the list shows the contact's current name only to a
     reader allowed to read contacts (as N-1).
  2. A new notification kind, `automation_notice`, about a contact, with
     the message in a new `note` column that only this kind may carry
     (migration `0040_automation_notice`, a check constraint both ways).
     The automation acted, so no member is named as the actor, and the
     member who activated it is notified like anyone else.
  3. **Once only:** the notification is written in the step's own
     transaction with its `automation_step` row, so a retried or parallel
     run never notifies twice (as every action, P8-A).
  4. **Skips:** a contact without an owner skips the step (`no_owner`); a
     recipient who left or was suspended skips it (`member_gone`). A named
     recipient must be an active member when the automation is activated,
     as for `assign_owner`.
  5. **Screens:** the automation editor offers "Notify a team member" with
     the recipient and the message; the notifications panel shows
     "An automation: <message>" with the contact's name and opens the
     contact.
- **Still not built:** send email or SMS and AI actions (unchanged from
  P8-A 5), round-robin and business-hours waits.
- **Tests:** `tests/integration/test_automation_notify.py` (5),
  `tests/unit/test_automation_rules.py`,
  `frontend/src/records/automations.test.tsx`,
  `frontend/src/shell/AppFrame.test.tsx`.

## D-STG.3 — Scheduled commands and the monitoring heartbeat (2026-11-07)

- **Status:** Done under the autonomous mandate (the owner: "Proceed",
  2026-11-07). Local only; no monitoring account, nothing installed on a
  host.
- **What:** `deploy/staging/systemd/`, host units in the shape of SaaS-OS's
  own (`deploy/*.service` at the pinned commit: host-level, so they keep
  running when the worker does not, and no Docker socket in any container).
  - One template, `leadstack-job@.service`, runs a module once in the
    product image: `docker compose run --rm --no-deps -T app python -m %i`.
  - Its timers: `email_maintenance` every 2 minutes,
    `automation_maintenance` every minute, `signup_maintenance` every 5
    minutes, `import_maintenance` hourly, SaaS-OS's session clean-up
    hourly, and its billing-event retention daily at 03:30 UTC.
  - `leadstack-heartbeat.timer` runs `heartbeat.sh` every 5 minutes. It
    pings `HEARTBEAT_URL`, kept in an environment file and never in a
    unit, only when `crm-app-worker --check` passes (the worker's
    15-second Redis sentinel) and `crm_app.health_check` finds nothing
    overdue. A missed ping is what makes the monitoring service alert.
  - Backup timers are not shipped: on a managed PostgreSQL they wait for
    the provider (SaaS-OS gaps 17 and 18, decision D-STG.2).
  - Paths under `/opt/leadstack` are placeholders until a host is chosen.
- **Verified locally:**
  - `schedule_local.py`, 11 of 11: every command a timer starts, and
    `health_check`, runs in the production image against the stack and
    exits 0. `heartbeat.sh` pings a stand-in monitor while the worker runs;
    with the worker stopped it exits non-zero and sends nothing; with the
    worker back it pings again.
  - `systemd-analyze` (Debian 12, in a throwaway container) accepts every
    unit and every calendar.
  - `tests/unit/test_staging_timers.py`, 5 tests, fails if a scheduled
    command in `OPERATIONS.md` has no timer, a timer starts a missing unit,
    or a unit holds a secret.
- **Not covered:** the monitoring service raising the alert (not chosen;
  brief H section 8, Better Stack recommended); systemd actually firing the
  timers on a host; log shipping for the audit digests (S11).

## D-STG.2 — Backup and restore drill, rehearsed locally (2026-11-07)

- **Status:** Done under the autonomous mandate (the owner chose
  "Proceed: recommended", 2026-11-07). Local only; nothing leaves the
  machine.
- **What:** `deploy/staging/backup_drill.py`. It backs up the app database
  and ZITADEL's with SaaS-OS's own production pipeline
  (`python -m saas_os.infra.db.backup.orchestrator run`, `age`-encrypted,
  checksummed, retention 7), as its host timers would. It starts a separate,
  empty PostgreSQL with TLS from the local CA on its own internal network,
  prepared with the same roles (`init/01-roles.sh`), restores both
  (`orchestrator restore`) and checks the copies. Afterwards it removes the
  drill instance; the backups and the `age` key pair stay in
  `.local/backups/` (git-ignored).
- **Verified locally:** 15 of 15.
  - Both artifacts are age ciphertexts.
  - Both restore into fresh databases.
  - Every table's exact row count matches: app 125 tables and 739 rows,
    ZITADEL 144 tables and 2,150 rows.
  - Both migration versions match.
  - RLS is identical table by table (105 tables force RLS, 58 of them in
    `crm_app`), and SaaS-OS's `verify_restored_database` passes.
  - The app role is still safe.
  - Through the app role over `verify-full`, one workspace's context sees
    its own 4 roles and none of the other workspace's.
  - `saas_os.ops.audit_digest verify --partial` passes against the
    worker's exported `audit_digest` line.
- **Production backups (owner's choice, option 1):** the app database is
  backed up by the managed provider's own backups. Choosing a provider must
  answer whether its admin has BYPASSRLS. If it does, SaaS-OS's encrypted
  `pg_dump` pipeline also runs and gives the off-provider copy; if not, the
  provider's backups must be exportable for that copy.
- **Found:**
  1. A logical backup of the app database needs a superuser or a BYPASSRLS
     role: as the non-superuser migration owner, `pg_dump` fails on the
     first table that forces RLS (SaaS-OS gap 18). ZITADEL's database dumps
     fine as its own owner.
  2. The orchestrator reaches a database only through `docker exec`
     (SaaS-OS gap 17), so it cannot back up a managed PostgreSQL even with
     the right role.
  3. SaaS-OS's decryption expects the identity's key line alone
     (`AGE-SECRET-KEY-1...`), not the file `age-keygen` writes.
- **Not covered:** the off-provider copy (needs a bucket); a second host;
  a restore of a production-sized database (timings are for this small
  one); the app actually serving from the restored copy; RPO and RTO
  measured on real infrastructure. Gaps 17 and 18 are recorded, not filed
  upstream (the owner's choice).

## M-RLS — Data changes in migrations under forced RLS (2026-11-07)

- **Status:** Approved by the owner ("approve the alternative", 2026-11-07)
  in place of the maintenance role first recommended; built and tested.
- **Problem (from D-STG):** every tenant table forces Row-Level Security,
  which applies to the table owner. On a managed PostgreSQL the migration
  owner is no superuser and cannot bypass RLS, so an `UPDATE`,
  `INSERT ... SELECT` or `DELETE` on a tenant table without a tenant
  context silently changes no rows. Local development and CI migrate as a
  superuser and hid it. Affected: the upgrades of `0030` and `0038`, and the
  downgrades of `0016`, `0017`, `0019`, `0022`, `0024`, `0025`, `0026`,
  `0030`, `0031`, `0032`, `0034`, `0038` and `0039` (20 statements). `0003`
  was listed in D-STG by mistake: its back-fill already loops per workspace
  with `app.tenant_id` and works.
- **Rejected: a maintenance role with BYPASSRLS.** Tested on PostgreSQL 16:
  an admin with CREATEROLE but without BYPASSRLS, as managed services
  usually give, cannot create one ("Only roles with the BYPASSRLS attribute
  may create roles with the BYPASSRLS attribute").
- **Decision:** `crm_app.migrations.all_rows.all_rows(*tables)`. Inside the
  block the migration turns `FORCE ROW LEVEL SECURITY` off for the named
  tables and on again afterwards. RLS stays enabled, so it still applies to
  every role that does not own the table, the application included.
  `ALTER TABLE` holds an ACCESS EXCLUSIVE lock to the end of the
  transaction, and all migrations run in one transaction, so nothing else
  touches the tables meanwhile and a failure rolls the setting back. The
  helper refuses a table that does not force RLS, and only the table's
  owner can use it. A per-workspace loop (`0003`) stays a valid alternative.
- **Guards:** `tests/unit/test_migration_data_writes.py` fails on any data
  change in a migration that is not inside `all_rows` for its table, not a
  per-workspace loop, and not on a global table; it reports all 20
  statements on the code before this change. The integration test
  `tests/integration/test_migrations_as_owner.py` creates a database owned
  by a NOSUPERUSER NOBYPASSRLS role and, as that role, applies both
  histories, shows a bare `UPDATE` changing 0 rows and the same one inside
  `all_rows` changing 2 (RLS forced again afterwards), then downgrades the
  product history to its base and applies it again. It runs in CI's
  integration job.
- **Rule for new migrations:** a data change on a tenant table goes inside
  `with all_rows(...)` (or loops per workspace). The unit guard enforces it.
- **Not covered:** the round trip proves every migration runs as the owner,
  but a missing `all_rows` would still pass it silently; that case is
  caught by the unit guard, not by the database.

## D-STG.1 — ZITADEL in the local staging stack (2026-11-07)

- **Status:** Done under the autonomous mandate (the owner: "Keep going",
  2026-11-07). Local only; it does not choose self-hosted ZITADEL over
  ZITADEL Cloud, which stays an owner decision (brief H).
- **What:** `zitadel` (v4.19.5) and `zitadel-login` (Login V2) in
  `deploy/staging/compose.yaml`, on an internal `identity` network with no
  route out and nothing published. The edge serves them on the app's own
  origin with the same routes as `deploy/local/Caddyfile` (SaaS-OS
  ADR-0025), strips provider cookies before the app, and now uses a
  certificate from the local CA. The app reaches its issuer through the
  edge (network alias `leadstack.localhost`) and trusts only the local CA
  for it (`OIDC_CA_BUNDLE`). `identity_local.py` creates the OIDC
  application (`saas-os-local-identity`) and applies the sign-in settings
  (`deploy/local/configure-zitadel.py`, whose local-issuer guard now also
  accepts exactly `https://leadstack.localhost:8443`, with a unit test).
- **Database:** ZITADEL has its own database on the same PostgreSQL over
  `verify-full`, owned by a `zitadel` role that is not a superuser and has
  no CREATEDB or CREATEROLE; the role and database are prepared first, as an
  operator would on a managed service. ZITADEL's `start-from-init`
  completed with that role as its "admin": no superuser credential is
  needed for a managed PostgreSQL.
- **Verified locally:** `verify_local.py` 35 of 35, adding E4 in part and
  E5 (details in `PROGRESS.md`).
- **Not covered:** the browser sign-in, MFA, and sign-out ending ZITADEL's
  session (the rest of E4; a browser cannot trust the local CA without
  installing it); a system-user key instead of bootstrap tokens for Login
  V2 (SaaS-OS ADR-0025 section 7), which belongs to the host's deployment.

## D-STG — Production-shaped staging stack, rehearsed locally (2026-11-07)

- **Status:** Done under the autonomous mandate (the owner: "cant we just
  proceed locally", 2026-11-07). Brief H section 7.1 items 2, 3 and 5 for
  the parts a local run can prove. No provider chosen, no account, nothing
  deployed.
- **What:** `deploy/staging/` (`compose.yaml`, `Caddyfile`,
  `egress/squid.conf`, `egress/unbound.conf`, `init/01-roles.sh`,
  `prepare_local.py`, `verify_local.py`, `README.md`). The product image
  runs with `ENVIRONMENT=production`; PostgreSQL (`verify-full`, hostssl
  only) and Redis (`rediss://`, `noeviction`, AOF) are TLS stand-ins for the
  managed services under the `stateful-local` profile. The configs are
  written for this product to SaaS-OS's documented rules (ADR-0024,
  ADR-0028, ADR-0059), not copied from SaaS-OS.
- **Least privilege:** the migration owner is not a superuser and cannot
  bypass RLS, as on a managed service; the app and worker get only
  `app.env`, never the owner's or the admin's credentials; app containers
  run read-only with no capabilities.
- **Verified locally** (`verify_local.py`, 24 of 24): E1, E2, E3, E6, E7,
  E10 of the brief (details in `PROGRESS.md`).
- **Found on the way:**
  1. SaaS-OS v0.10.0's `docker-compose.prod.yml` checks the egress proxy
     with `CMD-SHELL exec 3<>/dev/tcp/...`; the Squid image's `/bin/sh` is
     dash, which has no `/dev/tcp`, so that check can never pass. This stack
     uses bash. Recorded in `saas-os-gaps.md` (gap 16); not filed upstream.
  2. Python 3.13 verifies certificates strictly: a private CA must carry a
     subject key identifier and its certificates an authority key
     identifier, or Redis TLS fails with "Missing Authority Key
     Identifier". Matters if a managed Redis uses a private CA (brief V3).
  3. **Risk for future data migrations:** every tenant table forces RLS, so
     a back-fill (`UPDATE`/`INSERT ... SELECT`) run by a non-superuser owner
     without a tenant context changes no rows, silently. Local development
     and CI migrate as a superuser and hide this. **Resolved by decision
     M-RLS** (`all_rows`, a unit guard, and a CI test that migrates as a
     non-superuser owner); the list of affected migrations there corrects
     the one first given here.
- **Not covered:** ZITADEL in the stack (sign-in, E4/E5), backups and the
  restore drill (E8), scheduled maintenance commands, monitoring (E9).

## D-IMG — Production container image (2026-11-07)

- **Status:** Done under the autonomous mandate (brief H, section 7.1 item
  1, "can start now"; the owner's "any other independent work that does not
  require hosting"). It selects no host and deploys nothing.
- **What:** `Dockerfile` (multi-stage: frontend build on `node:24-slim`, a
  locked `uv sync --no-dev --no-editable` on `python:3.13-slim`, then a
  runtime with only the virtual environment and `frontend/dist`) and
  `.dockerignore`. One image; the command chooses the API (default,
  `uvicorn crm_app.app:create_app --factory --no-proxy-headers`), the
  worker or the migrations. Base images and the uv binary are pinned by
  digest; the Python digest is SaaS-OS v0.10.0's. Non-root, no git, uv or
  pip, no secret; the healthcheck probes `/readyz`.
- **CI:** a new `image` job builds it and checks the user, the absence of
  build tools, the frontend, and that the installed SaaS-OS commit equals
  the one in `uv.lock`. Nothing is pushed.
- **Verified locally:** the image built (333 MB); from it, `crm-app-migrate`
  ran against the test database; the API became healthy and answered
  `/healthz`, `/readyz` and `/app/` 200 and an unauthenticated API call
  401; a running worker passed `crm-app-worker --check`.
- **Open:** uvicorn reaches the product through SaaS-OS's dependencies, not
  a direct requirement (unchanged from local development). No image scan
  (SaaS-OS uses one; adding a scanner is a new tool to approve). No
  registry, signing or SBOM: they belong to the deployment decision.

## N-2 — Hosts are reminded in the app before their appointments (2026-11-07)

- **Status:** Done under the autonomous mandate (the owner's "Proceed
  with: … In-app appointment reminders", 2026-11-07). It builds the
  "upcoming-appointment reminders" N-1 left out. Nothing is emailed or
  pushed.
- **What:**
  1. A new notification kind, `appointment_upcoming`, about an
     appointment, for its host. No member acted, so the host is notified
     about their own appointments too.
  2. 30 minutes before the start (`member_reminders.LEAD`, fixed; the
     contact email's `reminder_lead_minutes` is a separate setting), for
     appointments that are pending or confirmed, not cancelled, and were
     made before their reminder time. A host who books something less
     than 30 minutes ahead is not reminded of it.
  3. One reminder per appointment and start time:
     `appointment_member_reminder` (tenant-owned, forced RLS,
     append-only) has that primary key and is written in the notification's
     transaction, so a retried or concurrent run notifies once and a
     rescheduled appointment is reminded of again.
  4. The run is part of `crm_app.email_maintenance` (every 1–5 minutes).
     It finds workspaces through the global `member_reminder_workspace`
     (workspace id and the latest known start time), which appointment
     creation, rescheduling and visitor bookings update in their own
     transaction; a row whose time has passed is removed. A workspace
     that fails is left for the next run; the log names its id and the
     error type only.
  5. The purge participant removes a workspace's registry row; the tenant
     table is in `PURGE_TABLES`.
- **Schema:** migration `0039_member_reminders` (the two tables and the
  notification kind check). Run on local and test databases only. No
  back-fill: an appointment made earlier is reminded of once it is made
  or moved again; no deployment has data.
- **Not done:** per-member preferences or lead times (Settings ›
  Notifications stays "soon"); overdue-task reminders; email or push
  delivery.
- **Tests:** `tests/integration/test_member_reminders.py` (registration,
  once within the lead time, short notice and cancelled skipped,
  rescheduled reminded again, two runs at once, nobody else and no other
  workspace, registry cleared and purged); the table guard
  (`tests/support.py` lists); `tests/unit/test_purge.py`.

## E-R1 — An email whose send outcome is unknown is not retried blindly

- **Status:** Done under the autonomous mandate, 2026-11-07 (the owner's
  "Proceed with: The email retry fix"). It closes the K3.4 follow-up that
  gap 14 blocked; SaaS-OS v0.9.0 exports the error classes (K3.9).
  Production sending stays off.
- **Problem:** `crm_app.emails` retried every non-permanent failure up to
  `MAX_ATTEMPTS`. A send that failed after the message may have been handed
  over (SMTP: the connection lost after `DATA`) could reach the recipient
  twice.
- **Decision:**
  1. `EmailOutcomeUnknownError` is caught before its parent
     `EmailProviderError`. With `retry_within` `None` the email ends in a new
     final status, `outcome_unknown`, at once.
  2. With a window (Resend's idempotency key, 24 hours), another try may
     start only before `retry_safe_until` = `first_attempt_at` + window − 15
     minutes (`UNKNOWN_RETRY_MARGIN`, for a late or long try). It is checked
     when the try is planned and again when it is claimed, since the sweeper
     may run late. A later unknown outcome never moves it later.
  3. Once an outcome was unknown, the email never ends `failed` or
     `suppressed` (running out of tries, a late reminder, a new
     suppression): it ends `outcome_unknown`, because it may have arrived.
     A permanent refusal on a repeat still ends `failed`: under the same
     idempotency key the provider answers for the original request.
  4. `EmailNotSentError` (nothing was handed over) keeps the ordinary retry.
  5. `outcome_unknown` has no `sent_at` and no provider id; it is audited as
     `crm_app.email.outcome_unknown` (codes only). The Inbox shows "Delivery
     unknown: may have been sent, not retried" in the risk tone.
- **Schema:** migration `0038_email_outcome_unknown` adds the status to the
  status and sent checks, and the columns `first_attempt_at` (back-filled
  from `created_at` for tried rows, which can only shorten a window) and
  `retry_safe_until`. Run on local and test databases only.
- **Not covered:** a worker that dies mid-try is taken over after
  `RETRY_DELAY` with the same `Message-ID`. Resend de-duplicates that;
  SMTP does not. The provider would have to say that the earlier try
  started, which nothing records yet. No member is told about an
  `outcome_unknown` email beyond its Inbox badge.
- **Tests:** `tests/unit/test_email_rules.py`
  (`test_an_unknown_outcome_is_final_and_retried_only_inside_the_window`);
  `tests/integration/test_emails.py` (four tests: no window, window and
  expiry, never ends as not sent, `EmailNotSentError` retried).

## K3.9 — SaaS-OS pin moved to v0.10.0

- **Status:** Approved by the owner, 2026-11-07 ("saas-os is updated to
  0.10.0 please upgrade"). Supersedes the commit named in K3.4; every
  other part of K3 stands. The pin stays fixed until a further approved
  decision.
- **Decision:** Exactly one SaaS-OS dependency:
  `saas-os @ git+https://github.com/aelboum/saas-os@0f9bf4d67e13aff284af9f30505b7f256ea49801`
  (v0.10.0, the latest release; v0.9.0 `fb08e47` is skipped as an
  intermediate step).
- **Evidence (verified 2026-11-07):**
  - The tag `v0.10.0` resolves to `0f9bf4d…`, the merge commit of release
    pull request #234; `git tag -v v0.10.0` reports a good ED25519
    signature by the owner's key.
  - No migration in either release: the platform head stays
    `e2b7c4d9a1f6`. No new setting. The public API snapshot only grew,
    by five names: `EmailOutcomeUnknownError` and `EmailNotSentError`
    exported (v0.9.0); `StrictEgressClient.get`, four `EmailMessage`
    fields (`list_unsubscribe`, `list_unsubscribe_post`, `in_reply_to`,
    `references`) and `InvalidEmailHeaderError` (v0.10.0).
  - CONSUMER-GUIDE §14, v0.8.0 → v0.9.0 and v0.9.0 → v0.10.0, against
    this product:
    1. Permission grant register audit rows now carry `user_subject_ref`
       instead of `subject_user_id`: this product neither reads nor
       writes `core.platform_audit_log` and nothing reads
       `subject_user_id`.
    2. `EmailMessage` is built by keyword and sets none of the four new
       fields, so SMTP and Resend output is unchanged.
       `InvalidEmailHeaderError` subclasses `InvalidEmailAddressError`,
       which `crm_app.emails` maps to `invalid_address`; it cannot be
       raised while the fields stay unset.
    3. `StrictEgressClient` is constructed as before in
       `crm_app.sending_domains` and `crm_app.custom_domains`; `post` is
       unchanged and `get` is not called.
  - Every SaaS-OS import is still a public export
    (`tests/unit/test_import_surface.py`).
  - `uv lock --upgrade-package saas-os` changed only the saas-os entry.
  - `saas-os-update check` was not run for this move; SaaS-OS records
    `REVIEW_REQUIRED` for both steps in CONSUMER-GUIDE §14, and the
    review is the list above.
- **Follow-ups unblocked upstream (each needs its own slice; none is done
  in this move):**
  - Gap 14: `crm_app.emails` can now catch the public
    `EmailOutcomeUnknownError` before `EmailProviderError` and stop
    retrying when `retry_within` is `None` (the blocked K3.4 follow-up).
  - Gaps 1 and 5: campaign unsubscribe headers and reply threading
    headers. Production sending stays unauthorized.
  - Gap 2: `StrictEgressClient.get` for Resend's receiving API. Inbound
    receiving stays unauthorized. `delete` and the domains interface
    (gap 3) are not shipped.
- **Rollback:** move the pin, lock entry, `APPROVED_PIN` and the
  `.secrets.baseline` hash back to `140d9dd`. There is no schema change
  to undo.

## UI-Q1 — Quick wins on built features (2026-11-06, owner: "Yes")

- **Status:** Done under the autonomous mandate, frontend only. No API,
  schema or permission changed.
- **What:**
  1. A contact's drawer lists its five most recent conversations (open or
     closed), each opening in the Inbox (`/inbox?record=<id>`). "Calls are
     not available yet" stays, because voice is parked.
  2. "+ New" › Appointment and › Conversation open their pages' create
     dialogs (`?create=appointment`, `?create=conversation`). Every item is
     built, so a disabled item now means the role may not create it, and
     the menu no longer says "soon".
  3. The ⌘K palette searches contacts and deals from two characters, five
     of each, with the lists' own server search. A refused or failed search
     shows no records.
  4. The campaign audience adds tag and owner filters to stages. Company
     filters already saved are kept but not edited here (they are stored
     as ids; a name lookup can follow). Filters combine as the server does:
     every kind used must match, any one value within it.
  5. The account menu's "Profile & preferences" opens My profile. The
     avatar shows the member's initials from their display name. The Forms
     scope text no longer says embedding is unavailable.
  6. An email template shows a preview as a sample contact (Ada Lovelace)
     would get it, mirroring the server's placeholder rule.
- **Not done here:**
  - "Start automation" from a form: the Automations page has no
    pre-filled trigger yet.
  - The business profile's phone, email, website and address: they need
    a migration and nothing would use them yet.
  - The campaign screen's company filter.
- **Docs:** stale entries in `DESIGN-FIDELITY.md` corrected (templates,
  report export, signup, workspace switcher, invitations, palette).

## K3.8 — History entries show the page, form or automation that made them

- **Status:** Approved by the owner, 2026-11-06 (option "C"). It extends
  K3.6 from the audit log to the history users see: the Home feed and a
  contact's or company's history.
- **Decision:** A history entry made in a member's scope by a component
  (a booking page, a public form, an automation; a consent link is allowed
  for later use) names no member. Instead it records that component as its
  `source`, with the page's, form's or automation's id. The screens show
  "Booking page: Intro call", "Form: Contact us" or "Automation: Welcome
  series", or just the kind once the page, form or automation is deleted.
  An entry with neither a member nor a source still shows "System".
- **Schema:** migration `0036_activity_source` adds the nullable `source`
  and `source_id` to `crm_app.activity`, with three checks:
  - a known source;
  - a source never names a member;
  - a `source_id` needs a source.

  Additive: existing entries are not rewritten and keep their member.
  `source_id` is a reference, not a foreign key, so history outlives a
  deleted page.
- **API:** history entries gain `source`, `source_id` and `source_name`.
  The name is the current one, looked up in the same workspace. Every
  role that reads history can also read pages, forms and automations.
- **Not changed:** deal events (no component writes them); rows other
  than history, such as a contact's owner or an appointment's host.
- **Tests:**
  - `test_note_activity_tables.py`: refused and accepted sources;
  - `test_booking_page_routes.py`, `test_form_routes.py` and
    `test_automations.py`: each entry's source, and no member;
  - `notes.test.tsx` and `dashboard.test.tsx`: the labels, including a
    deleted automation.

## K3.7 — Permission grant migrations declared and trialled locally

- **Status:** Approved by the owner, 2026-11-06 ("Go" on steps A to C of
  `PERMISSION-GRANT-MIGRATIONS-PLAN.md`). Steps D to F (enrolling a
  production platform operator, then the production runs) are not
  approved; they replace Brief 7 once approved.
- **Decision:** New workspaces' permissions added after Phase 2 reach
  existing workspaces through SaaS-OS's permission grant migrations (ADR
  0060), declared in `crm_app.permission_grants` (standard and
  administrative lists, namespace `crm_app`). The declarations are
  append-only and pinned by digest. A permission added to a role template
  without a migration fails CI. `crm_app.role_upgrade` stays, unused,
  until the first production run succeeds (plan step G); P2-G7 is then
  superseded.
- **Evidence:** the plan's section 7. In a throwaway database, SaaS-OS's
  dry run and apply matched crm-app's report: once only, and a revoked
  grant was not restored. The database was dropped afterwards.

## K3.6 — Visitor actions and automation steps are audited as system actors

- **Status:** Approved by the owner, 2026-11-06 ("Go" on the
  recommendation to re-attribute visitor actions and automation steps,
  and to keep member-queued emails as the member). It amends the audit
  attribution in 13-H1, P5-C 9, P6-E 2, P7-A 8 and P8-A 8; nothing else
  in those decisions changes.
- **Decision:** These actions ran in a member's scope and were audited as
  that member, although the member did not act. Their new entries name a
  system component instead, with the member as `on_behalf_of_user_id` in
  the metadata:

  | Action | Component (kind) | Was audited as |
  | --- | --- | --- |
  | A visitor books (contact created, appointment created, confirmation email queued) | `crm_app.booking_page` (public_link) | the host |
  | A visitor cancels through the link | `crm_app.booking_page` (public_link) | the host |
  | A form submission (contact created, confirmation requested, its email queued) | `crm_app.public_form` (public_link) | the form's contact owner |
  | A person confirms consent through the link | `crm_app.consent_link` (public_link) | the form's contact owner, or nothing when it had none |
  | An automation step (tags, stage, owner, task) | `crm_app.automation_run` (worker_job) | the activating member |

- **What does not change:**
  - Rows keep the member they named before (the host on the appointment
    and the new contact, the form owner as contact owner, the activating
    member's rights for steps), and steps still stop when that member
    leaves (13-H5). Only audit attribution moves.
  - Emails a member queued still name that member (P6-E 5). An email
    queued by a component now has no `created_by_user_id`, so its later
    entries come from the send worker and the email-events processor
    (K3.5).
  - `"by": "visitor"` stays in the booking and consent metadata.
  - Earlier audit rows are not rewritten. Readers that filtered these
    actions by `actor_user_id` must also read `on_behalf_of_user_id`.
- **How:** `Scope` gained an optional `component`. `records`, `tasks`,
  consent confirmations, bookings and email queuing write through
  `crm_app.system_audit.record_scoped`: a member entry without a
  component, the component's system entry with one. `initiated_by` is
  never passed.
- **Not changed (not part of this approval):** automatic appointment
  reminders still queue their email as the host (`crm_app.reminders`).
- **Tests:** `test_booking_page_routes.py`, `test_form_routes.py`,
  `test_booking_emails.py`, `test_automations.py` and
  `test_consent_confirmations.py` assert the system actor, no
  `actor_user_id`, and the member in `on_behalf_of_user_id`. The consent
  probe's disabled audit query (it named a table that does not exist) is
  replaced by a working one.

## K3.5 — System-actor audit entries for actions no member performs

- **Status:** Done under the autonomous mandate, 2026-11-06 (owner:
  "Proceed" on the K3.4 follow-ups). Additive only: no approved
  attribution changed.
- **Decision:** Where crm-app changed workspace data with no member acting
  and wrote no audit entry, it now writes one through SaaS-OS v0.7.0's
  `record_system_action_in_transaction`, inside the same tenant
  transaction. `crm_app.system_audit` is the single writer. It holds a
  fixed list of components, each with its `SystemActorKind`; an unlisted
  name is refused. `initiated_by` is never passed, so SaaS-OS stores
  `"unavailable"` and no member id. Metadata holds ids, codes and counts
  only.

  | Path | Component (kind) | Entries |
  | --- | --- | --- |
  | Campaign unsubscribe link | `crm_app.unsubscribe_link` (public_link) | `crm_app.contact.consent_withdrawn`, `crm_app.suppression.added` |
  | Email send worker, email queued by nobody | `crm_app.email_send` (worker_job) | `crm_app.email.sent` / `.failed` / `.suppressed` |
  | Resend email events, email queued by nobody | `crm_app.email_events` (provider_event_processor) | `crm_app.email.bounced` / `.complained`, `crm_app.suppression.added` (origin `provider`) |
  | Resend domain events | `crm_app.sending_domain_events` (provider_event_processor) | `crm_app.sending_domain.status_changed` (only when the status changes) |
  | Unverified sending-domain claim released | `crm_app.domain_maintenance` (maintenance) | `crm_app.sending_domain.status_changed` (`expired`) |
  | Custom-domain re-check | `crm_app.domain_maintenance` (maintenance) | `crm_app.custom_domain.status_changed` (`lapsed`, `expired`) |
  | Import retention sweep | `crm_app.import_maintenance` (maintenance) | `crm_app.import.expired`, `crm_app.import.rows_cleared` |
  | Inbound email processing | `crm_app.inbound_process` (inbound_processor) | `crm_app.conversation.inbound_received`, `crm_app.conversation.inbound_quarantined` (reason code only), each once per email |
  | Automation run ends | `crm_app.automation_run` (worker_job) | `crm_app.automation_run.completed` / `.failed` / `.cancelled` |

- **Not changed (approved decisions; changing them needs the owner):**
  entries for bookings and visitor cancellations (as the host, `"by":
  "visitor"`, 13-H1), form submissions (as the form's contact owner,
  P7-A 8), consent confirmations, automation steps (as the activating
  member, P8-A 8), and emails a member queued (as that member, P6-E 5).
  Moving them to system actors is a separate owner decision (made in
  K3.6 for all but member-queued emails).
- **Also:** inbound quarantine now reports whether it held the email this
  time, so a reprocessed email is audited once.
- **Tests:** `tests/unit/test_system_audit.py`; integration assertions in
  `test_campaigns.py`, `test_emails.py`, `test_sending_domains.py`,
  `test_custom_domains.py`, `test_import_maintenance.py`,
  `test_inbound_email.py` and `test_automations.py` check the action,
  `actor_type` `system`, no `actor_user_id`, the component name, "exactly
  once", and no address in metadata.
- **Closes:** gap 11 in `saas-os-gaps.md` for these paths.

## K3.3 — SaaS-OS pin moved to v0.6.0

- **Status:** Approved by the owner, 2026-10-31 ("saas-os is ready we can
  upgrade"). Supersedes the commit named in K3.2; every other part of K3
  stands. The pin stays fixed until a further approved decision.
- **Decision:** Exactly one SaaS-OS dependency:
  `saas-os @ git+https://github.com/aelboum/saas-os@d980e73b0313ed63f2a59fd4a991a89f75791c0e`
- **Evidence (verified 2026-10-31):**
  - The tag `v0.6.0` is annotated and signed; it resolves to
    `d980e73…`, the merge commit of release pull request #185. GitHub
    reports the tag signature as verified (`verification.reason: valid`).
    The release notes report SaaS-OS CI run 41200882248 (7 of 7 jobs)
    passed on that commit.
  - Between `b03d87a` (v0.5.0) and `d980e73` (212 commits, pull requests
    #102 to #132 and #134 to #185): one migration, `b3d5f7a9c2e4`, that
    widens the platform-permission check for the new
    `platform.outbox:replay` permission (head was `f6a2c8e4b1d9`); a
    Resend email provider (`EMAIL_PROVIDER=resend`, ADR-0058); worker
    egress through a proxy (ADR-0059); a per-user API key limit; paging
    arguments on `list_tenant_members`, `list_invitations_for_tenant` and
    `list_api_keys` (keyword-only and optional); refusal of control
    characters in stored strings; less detail in errors and logs; PyJWT
    raised to at least 2.15.1.
  - CONSUMER-GUIDE §14, v0.5.0 → v0.6.0, step by step:
    1. Migration: `crm_app.migrate` runs SaaS-OS's migrations before the
       product's, so local and test databases move to `b3d5f7a9c2e4` the
       next time it runs. The migration only widens a check.
    2. `platform.outbox:replay`: not needed; this product does not replay
       outbox events.
    3. Reference stack (ZITADEL master key file, egress proxy, SMTP on
       `internal`): this product does not run SaaS-OS's
       `docker-compose.prod.yml`. Its own deployment must settle worker
       egress before email is sent (Phase 6).
    4. Stripe: this product sets no `STRIPE_API_KEY`.
    5. New refusals: this product creates no API keys, uses no AI
       inference and moves no tenants. The strings it passes to SaaS-OS
       are checked first: workspace names refuse every control character
       (`normalize_workspace_name`), role and permission names are fixed
       in code, and an `InvalidInvitationEmailError` is already mapped
       to a validation error (`crm_app/invitations.py`).
       The provisioning command (`crm_app.provision`) now refuses a
       control character in the name, issuer or subject before it starts,
       instead of meeting SaaS-OS's refusal during the run
       (`tests/unit/test_provision_request.py`).
    6. Optional additions: none adopted in this move.
    7. Tag signature: checked as above.
  - Every SaaS-OS import is still a public export
    (`tests/unit/test_import_surface.py`).
  - `uv lock --upgrade-package saas-os` changed only the saas-os entry;
    the other 71 packages are unchanged (PyJWT was already 2.15.1). The
    checks in `PROGRESS.md` passed on the new pin.
- **Not decided here:** the email channel (Phase 6). v0.6.0 makes
  `saas_os.core.email.send_email` with SMTP or Resend available; choosing
  the provider, the sending domain and the delivery design needs its own
  decision.
- **Rollback:** move the pin, lock entry, `APPROVED_PIN` and the
  `.secrets.baseline` hash back. v0.5.0 runs on the widened check; to
  downgrade the schema too, no `platform.outbox:replay` grant may exist.

## K2.1 — First local commits

- **Status:** Approved by the owner, 2026-10-21, and completed. Extends
  K2: committing locally on `main` is authorized for the two commits
  below and this documentation follow-up only. Everything else K2 lists
  as not yet authorized stays unauthorized: creating the remote,
  setting its visibility, pushing, pull requests, releasing and
  deploying.
- **Commits** (author `aelboum`, branch `main`, no remote):
  1. `0bdbfdb4ef382b1b64b28b7589123a425f6b9cf4` — Phase 1 foundation on
     SaaS-OS v0.1.2 (`b0809eeb3448956a4dc85a5541514823ec9ceae7`), 44
     files. Its tree is the pre-K3.1 project: the 10 files the upgrade
     changed were rebuilt from the pre-upgrade `uv.lock` backup and by
     reversing the recorded upgrade edits, in a separate copy, without
     touching the working tree. On that copy the Phase 1 checks passed
     again (locked install of `b0809ee`, ruff, pyright, import-linter,
     unit 43, integration 7, identity 1, detect-secrets, pip-audit).
  2. `35e13e8873ba47ac8a4da752bfa089a6c72ec01f` — SaaS-OS v0.3.0 upgrade
     (decision K3.1), 10 files, pin
     `5905156a99a4526e5071ce091a58667c08b0a019`.
- **Excluded from both commits:** `.env`, `.env.test`, `.venv/`,
  `deploy/local/.bootstrap/`, `*.egg-info/`, `__pycache__/` and tool
  caches (all covered by `.gitignore`).
- **Consequences:** Phase 1 acceptance criterion 9 (CI passing on the
  exact evaluated commit) is still not met; it needs the remote, a push
  and a passing CI run, each separately approved. Phase 1 status:
  locally verified; remote CI pending.

## K2.2 — Remote repository, first push and first CI run

- **Status:** Approved by the owner, 2026-10-21 ("approve A and B", then
  "approve the docs commit and push"), and completed. Extends K2 and
  K2.1.
- **Approved and done:**
  - Commit `dbb15609cd2531d3c430f06ee9c2e7bbd7f6a1c6`: CI gives each
    commit on `main` its own concurrency group and never cancels on
    `main`; pull requests still cancel superseded runs.
  - Repository `https://github.com/aelboum/crm-app` created with
    `gh repo create --private` as `aelboum`; visibility private, default
    branch `main`.
  - `main` pushed over HTTPS with the GitHub CLI as credential helper for
    that push only (Git configuration unchanged). The remote `main`
    equalled `dbb1560`, with history `dbb1560` ← `df6d810` ← `35e13e8` ←
    `0bdbfdb`.
  - This documentation commit and its push.
- **Evidence:** GitHub Actions run 39652641595 on `dbb1560`: `quality`,
  `integration` and `security` all succeeded (details in `PROGRESS.md`).
  Phase 1 acceptance criterion 9 is met, and Phase 1 is complete.
- **Still not authorized:** further pushes without approval, pull
  requests, merges, tags, releases, publication and deployment, and any
  change to the repository's visibility or settings.

## D-DES — Claude Design prototype recorded as a design reference

- **Status:** Recorded 2026-10-21 on the owner's instruction. Phase 0
  task 0.3 is complete.
- **Decision:** The owner-exported prototype
  (`Design system questionnaire-handoff.zip`, SHA-256
  `128683965341eeace19746a8c8e0b70987bf484f41590036b19b068c030b55d7`) is
  a visual and interaction reference only. It is not production code, a
  binding architecture, or evidence that any functionality exists.
  `support.js` (the design tool's runtime) and `mock-data.js` (sample
  data) are never copied into the product; no export file is in the
  repository.
- **Evidence and limits:** `DESIGN-INSPECTION.md` (the canonical record).
  The bundle does not contain the project ID named in `CLAUDE.md` §2, so
  the link to that project rests on the owner's statement.
- **Consequences:** Frontend work still waits for P-6 and an approved
  Phase 2 plan (the Phase 2 decisions P2-A to P2-E below were approved on
  2026-10-21). The missing-design backlog is in `DESIGN-INSPECTION.md`
  §6.

## K5.1 — Global SaaS direction

- **Status:** Approved by the owner, 2026-10-21. Extends K5; K5's MVP
  feature list and deferrals are unchanged.
- **Decision:**
  - The product is a global SaaS for agencies, small businesses and
    growing companies. The Netherlands and the EU may be the initial
    market, but the architecture must be neither EU-only nor US-specific.
    This supersedes K5's "Netherlands and the EU" as the definition of
    the target users; it remains the likely initial market.
  - English is the initial and only promised UI language. The UI is
    translation-ready from the start; other languages are promised only
    when implemented.
  - Locale, time zone, date and time formats, currency and international
    phone numbers are configurable.
  - Privacy, consent, communication, retention and data-subject handling
    are designed to be jurisdiction-aware. GDPR applies where relevant
    but is not treated as the only regime.
  - Generic CRM terms and entities only; no industry-specific (for
    example dental) concepts.
  - Tenant isolation and permissions are enforced in the backend through
    SaaS-OS and PostgreSQL. Frontend visibility is never an
    authorization boundary.
  - "Global" does not require every language, jurisdiction, payment
    method or channel in the first release.
- **Unchanged:** K4 (the name stays provisional), K5's MVP list and
  deferrals, and K5's deployment model (hosted, single region). Whether
  later customers need other regions or data residency is an open
  question, not part of this decision.

## P2-A to P2-E — Phase 2 decisions

- **Status:** Proposed on 2026-10-21 and **approved by the owner on
  2026-10-21**, each with the conditions recorded under it. None is
  implemented; implementation follows the Phase 2 plan, which still needs
  approval. Evidence is the pinned SaaS-OS v0.3.0 (`5905156`), verified
  by reading the installed package and its documents at the pin; file
  references are to `saas_os/` in the installed package.
- **Common conditions:** no SaaS-OS capability is assumed or invented,
  and its public API is never bypassed. Where an approved decision cannot
  be implemented through supported interfaces, the exact gap is
  documented and work stops before any workaround.
- **Current product state:** `crm_app/permissions.py` registers no
  permissions; `create_app()` mounts only the platform's health and
  `/auth` routes.

### P2-A — Product roles

- **SaaS-OS facts:**
  - No built-in roles. Roles are freely named, tenant-local rows created
    with `create_role(tenant_id, name, *, caller)` (`core/rbac`).
    SaaS-OS itself only ever creates an `owner` role, in its operator
    bootstrap, holding just `tenant:read_status`.
  - Permissions are a global catalogue registered with
    `register_permission(resource, action)`; registering grants nothing.
    `grant_permission` requires the caller to hold the permission already
    (no privilege amplification). `assign_role` accepts only a signed-in
    user and requires the caller to hold every permission of the role.
  - "Administrator" is a capability (an active member holding
    `membership_role:create`), protected by the last-administrator guard
    (ADR-0043).
  - Deny grants override allows; delegations are time-limited.
  - SaaS-OS ships opt-in routes for members and invitations
    (`/v1/tenants/{id}/members`, `/invitations`, acceptance) but none for
    roles, role assignment or permission grants.
- **Recommendation:** four product role templates seeded into every new
  workspace by the product's provisioning code: **Owner** (everything,
  including membership and roles), **Admin** (everything except
  ownership transfer), **Member** (day-to-day CRM work), **Read-only**
  (view only). Product permissions use the `crm_app.` prefix and are
  registered in the migration step. Role changes go through the public
  `assign_role`/`remove_role` functions behind product routes. The
  identity provider (ZITADEL) holds identities only, not roles.
- **Implications:** The exact permission list per role is defined in the
  Phase 2 plan. Owner protection relies on SaaS-OS's last-administrator
  guard. No new SaaS-OS capability is needed.
- **Approved 2026-10-21:** four initial product roles, Owner, Admin,
  Member and Read-only, with these conditions:
  - They are product-level roles; neither SaaS-OS nor ZITADEL supplies
    them. ZITADEL handles identity only; authorization uses SaaS-OS roles
    and permissions.
  - Every protected operation is checked in the backend; hiding a control
    is not authorization. Permissions are tenant-scoped, and access
    requires explicit membership of the workspace.
  - The last Owner cannot be removed or demoted by accident.
  - Tests cover cross-tenant access, privilege escalation, role
    assignment and unauthorized operations.
- **Verification on 2026-10-21 (implementation gap to plan for):**
  - The documented bootstrap gives its `owner` role only
    `("tenant", "read_status")` (`api/tenant_bootstrap.py:147`). A
    bootstrapped owner therefore cannot invite members or manage roles
    until the product grants it permissions.
  - Supported path: `create_role` and `grant_permission` accept
    `SystemCaller(PROVISIONING)` on any open tenant, and provisioning is
    exempt from the no-amplification check (`core/rbac/service.py`). So
    product provisioning code can create the Admin, Member and Read-only
    roles and grant product and capability permissions to the bootstrap
    `owner` role, which then serves as the product Owner. The Owner
    assigns other roles with `assign_role`, which accepts signed-in users
    only.
  - Open point: `core/authority/caller.py` scopes PROVISIONING to
    "creating a tenant's initial authority structure before any principal
    in it could hold authority". Whether seeding roles immediately after
    bootstrap, and adding permissions to existing workspaces later, fall
    within that scope must be settled in the Phase 2 plan before
    implementation. If not, work stops at that gap.

### P2-B — Agency and client workspaces

- **SaaS-OS facts:** `get_tenant_context` admits a request only with a
  direct membership row in that exact tenant; a parent tenant's
  `SUBTREE` role does not reach a child through these routes. No API
  lists a user's tenants (`/auth/me` returns only the user ID).
- **Recommendation:**
  - The business relationship (an agency serves a client) is product
    data; the security boundary is the SaaS-OS tenant. They are kept
    separate.
  - For the MVP, every workspace is an ordinary tenant, and every agency
    staff member who works in a client workspace is an explicit member of
    it with a role there.
  - A product-owned workspace index may list workspaces for the switcher
    and an agency directory, but every entry is re-checked against a live
    membership before it is shown or opened, and listing never grants
    data access.
  - Not in scope without an approved security design and verified
    SaaS-OS support: parent-to-child access, cross-client rollups,
    "open as client" and an agency access matrix (Phase 11).
- **Approved 2026-10-21:** explicit membership for every workspace a
  user accesses, with these conditions:
  - Agency staff are directly authorized members of each client
    workspace they access.
  - An agency directory may list client workspaces; listing never grants
    access to their data, and every request for workspace data is
    authorized independently.
  - Parent/child relationships never imply inherited access.
  - Cross-client rollups, impersonation, "open as client" and any other
    elevated agency access are deferred until a separate security design
    is reviewed and approved.
  - No SaaS-OS hierarchy or "my workspaces" API is added or simulated.

### P2-C — Signup and tenant provisioning

- **SaaS-OS facts:**
  - SaaS-OS has no self-service signup; ADR-0040 assigns it to the
    product. `create_tenant` accepts an operator holding
    `platform.tenant:create` or `SystemCaller(PROVISIONING)`, which
    `core/authority/caller.py` defines as covering "a consumer's own
    provisioning/seed code". Provisioning may create only a root tenant
    or a child of a still-pending tenant.
  - `assign_first_role_for_new_tenant` requires
    `SystemCaller(PROVISIONING)`, and its docstring says it must not be
    called from any path other than tenant bootstrap.
  - `python -m saas_os.api.tenant_bootstrap` is the documented operator
    command that creates and activates a tenant with its first owner.
  - Invitations carry no role: accepting one gives a bare membership, and
    SaaS-OS sends no invitation email.
- **Recommendation (smallest safe MVP):** workspaces are created by an
  operator with the documented bootstrap command, plus a product step
  that seeds the P2-A role templates; members join by invitation through
  the SaaS-OS invitation routes, and the product assigns their role and
  delivers the invitation email. A public "create my workspace" form is
  a later, separately approved feature with its own abuse controls,
  built on `create_tenant` with `PROVISIONING` in product provisioning
  code; it is not assumed for the MVP.
- **Implications:** no bootstrap bypass and no use of
  `assign_first_role_for_new_tenant` outside a brand-new tenant's
  bootstrap. Invitation email needs the transactional email capability
  (SMTP, verified as partial in Phase 0).
- **Approved 2026-10-21:** operator-created workspaces and
  invitation-based membership as the initial MVP provisioning model, with
  these conditions:
  - No public self-service tenant creation in this phase.
  - Workspace creation and role setup use supported mechanisms only;
    bootstrap-only functions are not misused (see the P2-A open point).
  - Invitations are never simulated. Before they are implemented, the
    Phase 2 plan documents their lifecycle: creation, association with a
    verified identity, expiry, revocation, one-time acceptance, safe role
    assignment, and real delivery status.
  - No invitation system or email integration is authorized by this
    decision.
- **Verified 2026-10-21:**
  - `python -m saas_os.api.tenant_bootstrap` exists at the pin with the
    options `--tenant-name`, `--owner-issuer`, `--owner-subject`,
    `--dry-run` and `--confirm-production` (required when
    `ENVIRONMENT=production`); it prints the tenant, owner, membership and
    role IDs. It describes itself as the "first-tenant bootstrap" but is
    idempotent per tenant name and refuses to claim a tenant that already
    has other members, so it can be run once per new workspace. Not yet
    run against this product; the operator procedure is written in the
    Phase 2 plan only after a dry run against the local services.
  - Email: SaaS-OS exports transactional `send_email` with an SMTP
    provider (`core/email`). `crm-app` has no SMTP or email-provider
    configuration. **Invitation delivery is therefore a dependency:** it
    needs an approved email provider and its credentials. Until then no
    screen or API may report an invitation as sent. An accepted SMTP
    handoff is not proof of delivery; the plan defines what "delivered"
    means.

### P2-D — Localisation and compliance foundation

- **SaaS-OS facts:** tenants and users carry no locale, time zone or
  currency; usage reporting is in UTC; billing currency lives in the
  payment provider. SaaS-OS has no consent, suppression, data-export or
  subject-access API; marketing email is a stated non-goal. Tenant purge
  exists (operator only), and products must register purge participants.
- **Recommendation:**
  - *General internationalisation (product-owned, from Phase 2):* store
    timestamps in UTC; workspace defaults and per-user overrides for
    locale and time zone; ISO 4217 currency on every monetary amount;
    E.164 phone numbers; all UI text in message catalogues; locale-aware
    formatting.
  - *Jurisdiction-specific work (later phases, per market):* consent
    model per contact and channel with source, time and wording (Phase 6
    and 7, needed for the MVP email channel); suppression and
    unsubscribe; retention rules; data-subject export and deletion,
    building on SaaS-OS tenant purge and user erasure; legal review per
    market before claims of compliance (Phase 13).
- **Approved 2026-10-21:** the general internationalisation requirements
  above, plus:
  - No hard-coded US-only (or any single-country) assumptions in dates,
    currency, phone numbers or terminology.
  - Consent, suppression, retention, data-subject requests and legal
    review are explicit, market-specific work items. Localisation alone
    is never presented as legal compliance in any jurisdiction.
  - Global use is the direction; the Netherlands/EU may be the initial
    market but not the exclusive target (K5.1).
  - K5's single-region hosting stands. Multi-region hosting and data
    residency outside that region are undecided and need their own
    decision.
- **Unresolved architecture issue (purge participants):** SaaS-OS's
  documented way for a product to have its tenant data removed by a
  tenant purge is to register purge participants in
  `saas_os.core.tenancy.purge_participants`. That submodule is not
  exported from `saas_os.core.tenancy`, so it is outside this product's
  approved import surface (`CLAUDE.md` §3), although the SaaS-OS
  consumer scaffold uses it. No internal import, reflection,
  monkey-patching or other workaround is allowed without a narrowly
  scoped, documented exception approved by the owner. It must be resolved
  before the first tenant table exists, because product rows would
  otherwise survive a tenant purge.

### P2-E — Generic CRM model

- **Recommendation:** generic terms and entities: Workspace, Member,
  Contact, Company (contacts link to companies by ID), Pipeline, Stage,
  Opportunity (with an explicit open, won or lost outcome and
  stage-change history), Task, Activity, Note, Tag, Custom field
  definition and value, Form and Form submission, Email message, Consent
  record. Contact lifecycle stages and pipelines are configurable per
  workspace, with neutral defaults (for example Lead, Prospect,
  Customer). No dental, health or insurance fields, and nothing from
  `mock-data.js`. Industry templates, if any, are a later feature.
- **Implications:** the schema is designed in Phases 2–4 under the
  existing roadmap; every tenant table has RLS and cross-tenant tests.
- **Approved 2026-10-21:** a generic CRM model for the initial product:
  - Generic concepts (contacts, companies, opportunities/deals,
    pipelines, tasks, activities) with stable identifiers for every
    relationship; contacts link to companies by ID, never by name.
  - Configurable pipeline stages within the approved scope; won and lost
    are explicit outcomes, never a hard-coded stand-in for a stage.
  - Stage history where the roadmap requires it (ROADMAP 4.2–4.4).
  - Dates and times as typed values, never display strings.
  - Tenant-scoped records and access paths under the SaaS-OS and
    PostgreSQL security model.
  - Nothing from the prototype: no dental terms, sample data,
    health or insurance fields, mock data, prototype engine or generated
    assets.
  - No schema or migration in this decision; detailed schema decisions
    belong to the implementation plan of each roadmap phase.

### P-6 — Frontend framework

Still open. Selection criteria are recorded in `DESIGN-INSPECTION.md`
§7; no framework is chosen and no package is added.

## Q6 — Product role and permission matrix

- **Status:** Approved by the owner, 2026-10-21. Refines P2-A; the full
  matrix is `PHASE2-PLAN.md` §5.2–5.3, and the code that encodes it is
  `src/crm_app/roles.py` (checked row by row by `tests/unit/test_roles.py`).
- **Decision:**
  - Four roles: Owner, Admin, Member, Read-only. Authorization is
    enforced in the backend through supported SaaS-OS permission
    mechanisms (tenant-local roles and `crm_app.`-prefixed permissions
    checked by `require_permission` / `can()`).
  - All four roles can read the workspace's CRM data.
  - Owner, Admin and Member can create and edit ordinary CRM records.
  - Only Owner and Admin can delete contacts, companies, opportunities and
    notes; Members may delete tasks only.
  - Owner and Admin manage ordinary memberships and invitations, subject
    to the restrictions below.
  - Admins cannot manage Owners or change security-sensitive settings.
  - Owner assignment, transfer and removal require concurrency-safe
    protection and a last-active-Owner safeguard (gate G-LOCK).
  - Workspace deletion and purge are operator-only; no product role can
    start them (SaaS-OS ADR-0040). No role holds `tenant:suspend` or
    `role_permission:*`.
  - Audit access and export are available to Owner and Admin.
- **Scope:** product policy only. It does not authorize implementing every
  route; each route still needs its gate (G1, G2, G-LOCK, G3/G4 in
  `PHASE2-PLAN.md` §14).
- **Amended 2026-10-24 (P3-B D3):** a note's author may edit and
  permanently delete their own note, whatever their role, as long as they
  still hold `crm_app.activity:create` (Owner, Admin, Member). Owners and
  Admins may edit and delete any note. The rest of Q6 is unchanged.

## Q-purge — Purge integration

- **Status:** Approved by the owner, 2026-10-21 (option (a) in
  `PHASE2-PLAN.md` §9.4).
- **Decision:**
  - The product integrates with tenant purge only through a supported,
    public SaaS-OS purge-registration API.
  - No internal SaaS-OS module is imported and no internal-import
    exception is granted (the registry currently lives only in
    `saas_os.core.tenancy.purge_participants`, outside the public surface
    of `CLAUDE.md` §3).
  - No tenant-owned table is created until all of these are in place: the
    supported integration, an approved SaaS-OS pin that provides it, the
    product safeguards (a participant that verifies no rows remain;
    coverage of every tenant table), and the relevant passing tests (gate
    G1, acceptance criteria in `PHASE2-PLAN.md` §9.4).
  - The operator procedure prohibits bypassing product purge participants
    (`saas-os-operator purge-tenant --no-product-participants` is never
    used for this product). This is a procedural rule; no product check
    can stop an operator who bypasses participants explicitly.
  - The upstream request (`PHASE2-PLAN.md` Appendix A) stays unsent
    unless separately authorized.

## G1 — Purge participant registered; gate passed

- **Status:** Passed 2026-10-23. The owner approved the plan ("Go") to
  build the participant on the v0.5.0 public API and to record G1 as
  passed once its tests pass. Implements Q-purge; nothing in Q-purge
  changes.
- **What exists:**
  - `crm_app/purge.py`: one participant, `crm_app.crm_data`, registered
    with `saas_os.core.tenancy.register_purge_participant` (public since
    v0.5.0, decision K3.2). No internal SaaS-OS module is imported.
  - It runs every delete in one `tenant_session_scope(tenant_id)`
    transaction, in manifest order (children first), then re-reads every
    manifest table and raises `PurgeIncompleteError` if a row remains. A
    manifest table that is not mapped also raises, never skips.
  - `register_purge_participants()` registers it and refuses unless the
    process holds exactly `("crm_app.crm_data",)`. It is called by
    `create_app()`, by the worker before it starts, and by the operator
    command through
    `saas-os-operator purge-tenant --setup crm_app.purge:register_purge_participants`.
    SaaS-OS documents that no route or worker job purges a tenant
    (CONSUMER-GUIDE §11); the worker registers anyway, as §9.4 criterion
    3 asks.
  - The manifest `PURGE_TABLES` is empty: no tenant-owned table exists.
    `tests/support.py` derives `PURGE_COVERED_TABLES` from it, so the
    coverage guard fails for any tenant-owned table the participant does
    not delete.
- **Evidence (2026-10-23, local, disposable test database):**
  `tests/integration/test_purge.py`, against PostgreSQL with a probe
  table built like a product table (forced RLS, DML grants), dropped
  afterwards:
  - the installed operator command refuses without `--setup`, and with
    it purges the workspace with `participant_names == ["crm_app.crm_data"]`;
  - a purge deletes the purged workspace's rows and leaves another
    workspace's rows; a second purge reports `already_purged`;
  - a failing participant leaves the workspace `PURGING` with one
    `tenant.purge_failed` (`participant_error`, `participant:<name>`),
    and a re-run completes;
  - rows left behind (a trigger cancelling deletes) and an unmapped
    manifest table each fail the purge with `PurgeIncompleteError`.

  Unit tests cover the name, the manifest, identifier checks,
  idempotent and exact registration, and registration in `create_app()`
  and the worker.
- **Still required for each tenant-owned table** (from Q-purge and
  `PHASE2-PLAN.md` §9.4): a migration with forced RLS and the grants
  rule, a `PURGE_TABLES` entry in deletion order, and its own RLS
  negative tests. The operator rule stands: this product's workspaces are
  never purged with `--no-product-participants`.
- **Not decided here:** which tables come first. `PHASE2-PLAN.md` S5 and
  `PHASE3-PLAN.md` S1 each need their own approval; the open questions in
  `PHASE3-PLAN.md` §18 remain open.

## P3-A — Phase 3 slice 3A approved

- **Status:** Approved by the owner, 2026-10-23: "I approve Phase 3 slice
  3A backend stages 3A.1–3A.3", with the conditions below. Plan:
  `PHASE3-PLAN.md` §19.
- **Decisions:**
  1. Contact stages are fixed for now: Lead, Prospect, Customer, Inactive.
  2. Contact sources are fixed: Manual, Import, Form, Referral, Other. In
     slice 3A users may choose only Manual, Referral or Other; Import and
     Form are reserved for system-created records in later slices.
  3. Duplicate active contact emails and duplicate active company domains
     are rejected through database-enforced uniqueness. Archived records
     are excluded; names may repeat.
  4. A contact must have an email or a phone number.
  5. The slice begins before Phase 2 closes. No outstanding Phase 2 work or
     security review is waived or marked complete.
- **Interpretation recorded with it (from Q6):** archive and restore are
  updates (Owner, Admin, Member); permanent delete is Owner and Admin.
- **Conditions:** route path IDs are never authorization (the SaaS-OS
  `require_permission` pattern, `PHASE3-PLAN.md` §19.3); duplicate
  normalisation, partial unique indexes, conflict handling and 409s are
  consistent (§19.4); cursor parsing, tie-breaking and paging consistency
  are specified (§19.5); the installed operator process loads the product
  tables without API start-up, and the real purge path is tested; each new
  table joins `PURGE_TABLES` in the change that creates it; tests run only
  against the disposable test database.
- **Not approved:** stage 3A.4 (frontend), notes, imports, exports, custom
  fields, tags and other deferred features; provisioning a real
  workspace; commits and pushes (each needs separate approval).

## P-6.1 — Frontend framework chosen

- **Status:** Approved by the owner, 2026-10-22 (recommendation in
  `PHASE2-PLAN.md` §10). Supersedes "Still open" under P-6.
- **Decision:** a React single-page application built with Vite, served
  from the same origin as the API, using TanStack Router and TanStack
  Query, React Aria Components for accessibility, react-intl for
  localisation, and a typed client generated from the FastAPI OpenAPI
  schema. No server-side rendering framework and no Node server at
  runtime; Node is a build-time tool only.
- **Scope:** approves the framework and adding Node build tooling. It does
  not approve any specific screen: each screen still needs its backend
  use case, its gate and the missing design states (gate G6).

## Q4, Q5 — Invitation delivery and role confirmation

- **Status:** Approved by the owner, 2026-10-22 (`PHASE2-PLAN.md` §8.2).
- **Q4:** while no email provider is configured, an Owner or Admin may
  create an invitation in "manual link" mode: the link is shown once to
  the inviter, labelled "not sent — deliver it yourself", and its
  delivery state is `manual`. The product never says it was sent.
- **Q5:** an accepted invitation gives a membership with no role. The new
  member appears as "awaiting role" until an Owner or Admin confirms the
  intended role with one action (no impersonation, no PROVISIONING).
- **Still blocked:** the invitation flow needs the product table
  `invitation_intent`, so it waits on gate G1. Real email delivery still
  needs Q3 (provider and credentials).

## Upstream requests — sent

- **Status:** Sending approved by the owner, 2026-10-22.
- Opened on `aelboum/saas-os` from the drafts in `PHASE2-PLAN.md`:
  - #87 "Export the tenant-purge participant registration through a public
    API" (Appendix A; gate G1);
  - #88 "Document a supported way to grant a newly registered permission
    to existing tenants' roles" (Appendix B; gate G7).
- Neither changes the pin. Adopting a release that resolves them needs a
  separate, owner-approved pin move.

## D-IDL — Local sign-in on the application's own origin

- **Status:** Approved by the owner, 2026-10-22 ("set up same-origin login
  locally"), after the owner noted that the identity provider's hostname
  appeared during sign-in.
- **Context:** SaaS-OS ADR-0023 keeps ZITADEL an invisible implementation
  detail, and ADR-0025 (accepted and implemented) serves ZITADEL's Login V2
  on the product's own domain for fresh deployments. ADR-0026 (a login form
  built inside the product, with credentials passing through SaaS-OS) was
  rejected by the owner on 2026-10-16. The earlier local setup ran ZITADEL
  on its own host (`http://zitadel.localhost:8081`) with the legacy login
  screens.
- **Decision:**
  - Local development follows ADR-0025's "Topology A". A Caddy `edge`
    service on `http://localhost:8000` (`deploy/local/Caddyfile`, started
    from SaaS-OS's `saas-os-edge-config`) serves Login V2 at
    `/ui/v2/login`, ZITADEL's documented routes, and everything else from
    the application on 127.0.0.1:8001.
  - The OIDC issuer equals `PUBLIC_APP_ORIGIN`. ZITADEL publishes no port.
  - Provider cookies are stripped before requests reach the application
    (ADR-0025 §9).
  - The Login V2 service authenticates to ZITADEL with a login-client
    token that ZITADEL writes to the untracked bootstrap directory. This
    follows ZITADEL's own Compose setup and is local only; production
    follows ADR-0025 §7 (a system-user key).
- **Consequences:**
  - The local ZITADEL instance was recreated on a new volume
    (`zitadel-same-origin-data`). The old volume is left unused and was not
    deleted.
  - The OIDC client ID changed, and so did the admin's login-name domain.
  - Users created under the old issuer no longer match.
- **Not decided here:**
  - the production domain and TLS (it waits on the product name, K4);
  - branding of the login screens;
  - turning off self-registration (Login V2 offers "register" by default;
    P2-C);
  - ending the provider session on sign-out (PHASE2-PLAN Appendix C).

## D-IDL.1 — Local sign-in security settings

- **Status:** Approved by the owner, 2026-10-22. Applies to local ZITADEL;
  production equivalents are part of the deployment work.
- **Settings** (`deploy/local/configure-zitadel.py`, instance defaults,
  idempotent):
  - self-registration off;
  - external identity providers off;
  - unknown usernames not revealed;
  - lockout after 5 wrong passwords or one-time codes;
  - two-factor optional.
- **Why:**
  - accounts come from provisioning and invitations, not self-sign-up
    (sign-up waits on P2-C);
  - no external provider is approved;
  - account enumeration and unlimited guessing were possible with
    ZITADEL's defaults.
- **Open:**
  - whether two-factor becomes required, for example for Owners;
  - password length rules (ZITADEL's default is 8 characters with
    complexity);
  - production settings;
  - Login V2's own response headers (see PROGRESS, 2026-10-22).

## P3-B — Phase 3 slice 3B (notes and activity) approved

- **Status:** Approved by the owner, 2026-10-24: "I approve proceeding with
  Phase 3B (Notes and Activity), based on the submitted plan and the
  decisions below." Plan: `PHASE3-PLAN.md` §21.
- **Decisions:**
  - **D1:** notes and activity in the existing contact and company drawers;
    the full record page and its tabs are deferred.
  - **D2:** two tenant-owned tables, `note` and `activity`.
  - **D3:** authors may edit and permanently delete their own notes; Owners
    and Admins may edit and permanently delete any note. This amends Q6
    (see the Q6 amendment).
  - **D4:** note deletion is permanent with no undo. The note text and its
    `note_added` entry are removed; a minimal `note_deleted` entry stays
    while the record exists. The deleted text is never kept in activity or
    audit metadata.
  - **D5:** the event kinds and payload limits of the plan. Ordinary
    updates record field names only; stage changes may record the fixed
    stage values; owner changes may record user IDs; no other field value
    and no note text.
  - **D6:** activity entries cannot be changed by application operations;
    the purge mechanism and parent-record deletion still remove them; no
    purge bypass and no weakening of tenant isolation.
  - **D7:** one `created` entry backfilled per existing contact and company,
    from the original creation time and creator.
  - **D8:** on an archived record, notes and history stay readable; adding
    or editing a note needs the record restored first; deletion follows D3.
  - **D9:** each independently validated increment may be committed and
    pushed without routine approval.
- **Not approved:** tags, custom fields, imports, exports, automation, AI and
  other deferred scope; production deployment or releases; any SaaS-OS pin
  change. Phase 2 stays open.

## P3-E1 — Contacts CSV export (approved 2026-10-26)

- **Status:** Approved by the owner, 2026-10-26, after the 3E audit:
  "I approve the first bounded Phase 3E slice: Contacts CSV export only."
  It amends P3-A's and P3-B's "Not approved: exports" for contacts only.
- **Decisions:**
  1. Route: `GET /v1/workspaces/{id}/contacts/export.csv`, requiring the
     existing `crm_app.crm_data:export` (Owner, Admin; Q6). No new
     permission. `/access` reports it as `export_records`, for display only.
  2. Columns, in order: `id, first_name, last_name, email, phone,
     job_title, city, lifecycle_stage, source, company_id, company_name,
     created_at, updated_at, archived_at`. Owner, tenant, version and
     creator/updater IDs, notes and activity are excluded.
  3. The list's filters and order, without paging. The default is active
     contacts; `archived=true` and `archived=all` behave as on the list.
  4. UTF-8 with a byte-order mark, minimal quoting, CRLF records, ISO 8601
     UTC times, and an ASCII file name `contacts-YYYY-MM-DD.csv`.
  5. Formula protection (a leading `'` for `=`, `+`, `-`, `@`, tab, CR)
     applies to every cell, including phone numbers starting with `+`.
  6. At most 50,000 rows; the 50,001st gives 413 `export_too_large` and no
     file. There is no separate count.
  7. Ten attempts per user per window. Every attempt that reaches the
     export counts, including one refused for size. A limiter failure
     refuses (503). **Recorded deviation:** SaaS-OS's limiter counts in
     fixed one-hour windows, not a rolling hour, so up to 20 exports can
     fall within one hour across a window boundary. A rolling window would
     need new infrastructure, which this slice excludes.
  8. Audit `crm_app.contacts.exported` with the row count and the names of
     the filters used only, in the same transaction as the read. Refused
     exports leave no entry.
- **Not approved:** companies export, import, tags, custom fields, new
  permissions, file storage, SaaS-OS changes, deployment.

## M1 — Continuous autonomous development (approved 2026-10-26)

- **Status:** Approved by the owner, 2026-10-26 ("LeadStack CRM — Continuous
  Autonomous Development Mandate"). Active across sessions until the owner
  changes or revokes it.
- **Decision:** Within the existing roadmap, approved decisions and
  architecture, Claude Code chooses, implements, tests, documents, commits
  and pushes successive slices to `main` without per-feature approval,
  recording each consequential choice in this log. This amends CLAUDE.md
  §9's "commit and push need approval" and Phase 3's per-slice approval
  (G1, `PHASE3-PLAN.md` §20) for roadmap work.
- **Still needs explicit approval:** production deployment, releases or
  production configuration, data or credentials; enabling production
  signup or flags required to stay off; changes to ZITADEL, the identity
  architecture, the `crm-app`/`crm-app-login` split, `crm-app-login` PR #1
  or its image; the SaaS-OS pin; cross-tenant invitation lookups or
  invitation and role semantics; paid services; destructive or
  hard-to-reverse data-model changes; changing an approved decision in
  this log.
- **Safeguards:** migrations run only on local and disposable test
  databases; authorization, tenant isolation, RLS, rate limits, audit and
  validation are never weakened to pass a check; normal pushes only.

## P3-C — Tags (2026-10-26, under M1)

- **Status:** Approved under M1, 2026-10-26. Roadmap Phase 3.1 ("Tags");
  `PHASE3-PLAN.md` §3.2, §6.2, §20 slice 3C.
- **Decisions:**
  1. Tables `tag`, `contact_tag`, `company_tag` (migration `0007_tags`):
     tenant-owned, forced RLS, composite keys into the record and the tag,
     `ON DELETE CASCADE` from both, in `PURGE_TABLES`.
  2. **No colour.** The design shows every tag as the same neutral pill
     (`ScreenContacts.dc.html`, `#F1F2F4` on `#2A303C`); the plan's colour
     palette is dropped until a design asks for it.
  3. **Names:** trimmed, 1-50 characters, no control characters, unique per
     workspace regardless of case. At most 500 tags per workspace and 20
     per record, so a list row and a filter menu stay bounded.
  4. **Who:** every role reads tags (`contact:read`/`company:read`).
     Creating, renaming and deleting tags is workspace configuration and
     needs `crm_app.workspace:update` (Owner, Admin), as §6.2 proposed.
     Putting existing tags on a record is a record update (Owner, Admin,
     Member). No new permission.
  5. **Assignment** replaces a record's tag set (`PUT .../tags`, with
     `If-Match`). A change is a record update: a new version, a history
     entry `updated` naming `tags` (the migration widens that allow-list),
     and the audit entry `crm_app.contact.updated` / `crm_app.company.updated`
     with `fields: ["tags"]`. Tag names are never written to history or
     audit; configuration changes are audited as `crm_app.tag.created`,
     `.renamed`, `.deleted` with the tag ID only.
  6. **Deleting a tag** removes it from every record by cascade. Those
     records keep their version and get no history entry; the audit entry
     counts the assignments removed.
  7. **Lists** filter by `tag_id` (repeatable, any of them), and the CSV
     exports accept the same filter so an export still matches its list.
     The exports' columns stay as approved in P3-E1 and P3-E2: tags are not
     exported yet.
  8. Records in lists and details carry `tags: [{id, name}]`, by name.
- **Migration locking note (after the 3C security review):** Alembic runs
  each migration in one transaction, so `ALTER TABLE` locks last until
  commit. Acceptable while no production data exists; a later change to a
  large table must split its steps across transactions.

## P3-D — Custom fields (2026-10-26, under M1)

- **Status:** Approved under M1, 2026-10-26. Roadmap Phase 3.1 ("Custom
  fields"); `PHASE3-PLAN.md` §3.2, §6.1, §20 slice 3D; the design's
  "Custom fields" card with "Manage" (`ScreenContacts.dc.html`) and
  Settings › Custom fields (`ScreenSettings.dc.html`, "Extra fields on
  contact records").
- **Decisions:**
  1. Table `custom_field_definition` and a column `custom_fields jsonb NOT
     NULL DEFAULT '{}'` on `contact` and `company` (migration
     `0008_custom_fields`, additive). JSON in the record, not an
     entity-attribute-value table, as the plan recommends.
  2. **A definition** is for contacts or companies. Its `key`
     (`^[a-z][a-z0-9_]{0,39}$`) and type never change and are unique per
     workspace and entity for good, so a key never takes another meaning;
     the label (1-60 characters), the options of a select and the position
     can change. Definitions are archived and restored, not deleted; a
     record's values stay stored while their field is archived and show
     again on restore.
  3. **Types:** `text` (one line, at most 500 characters), `number` (a
     finite number, at most 15 significant digits), `date`
     (`YYYY-MM-DD`), `boolean`, `select` (one of 1-50 options of 1-60
     characters, distinct regardless of case). At most 50 active fields
     per entity per workspace; a record's values are at most 32 KB.
  4. **Who:** every role reads the definitions (`contact:read`); creating,
     changing, archiving and restoring them is workspace configuration
     (`workspace:update`, Owner and Admin). Values are part of the record:
     whoever may create or update the record may set them.
  5. **Writes merge:** a record write names only the keys it changes; a
     key set to `null` is cleared. Only active fields of the record's
     entity are accepted, each value checked against its type. Records
     show only active fields' values.
  6. **History and audit:** a value change is an `updated` entry naming
     `custom_fields`; the record's audit entry lists `custom_fields` and
     the changed keys, never values. Definition changes are audited as
     `crm_app.custom_field.created`, `.updated`, `.archived`, `.restored`
     with the entity, key and type.
  7. **Not yet:** filtering or sorting by custom fields, and custom fields
     in the CSV exports (P3-E1 and P3-E2 fix their columns). Removing a
     select option leaves stored values as they are.

## P4 — Sales pipeline, deals and tasks (2026-10-27, under M1)

- **Status:** Approved under M1; the owner confirmed one pipeline per
  workspace ("go", 2026-10-27). Roadmap Phase 4 (4.1 tasks, 4.2
  opportunities, 4.3 pipelines); P2-E (won and lost are outcomes, stage
  history); the design's `ScreenPipeline.dc.html` (board, table, drawer,
  "New opportunity") and `ScreenTasks.dc.html`. Built in slices 4A
  (pipeline and stages), 4B (deals), 4C (tasks).
- **Design audit:** the design has a pipeline switcher, a probability per
  stage (20/40/60/75/100), a "Won" column that is the last stage, a
  "Lost" stage hidden from the board, a per-deal probability overwritten
  on every move, colours by column position, dollar values and close dates
  as display strings. Kept: board and table, stage totals and
  probabilities, idle days, owner filter, drawer with stage stepper, Mark
  won and Mark lost. Changed: won and lost become the deal's outcome, not
  stages (P2-E); one probability per stage, no per-deal override; values
  in the workspace's currency; real dates.
- **4A decisions (pipeline and stages):**
  1. Tables `pipeline` and `pipeline_stage` (migration `0010_pipelines`):
     tenant-owned, forced RLS, composite keys, in `PURGE_TABLES`. The
     schema allows several pipelines; the product offers **one per
     workspace** for now, so the design's pipeline switcher is not shown.
  2. **The default pipeline** "Sales" with stages Qualified (20 %),
     Meeting (40 %), Proposal (60 %), Negotiation (75 %) is created the
     first time a workspace's pipeline is read, under SaaS-OS's tenant
     advisory lock, so concurrent first reads create it once. No backfill
     or provisioning step is needed, and workspaces created before Phase 4
     get it too. Creating it is not a user action and is not audited.
  3. **Stages** are open stages only: name trimmed, 1-40 characters, no
     control characters, unique per pipeline regardless of case;
     probability a whole number 0-100; 1-15 stages; order is a position.
     No stored colour: the board shades columns by position, as the design
     does. Won and lost are not stages.
  4. **Who:** every role reads the pipeline (`pipeline:read`); renaming
     it and adding, changing, reordering or removing stages needs
     `pipeline:manage` (Owner, Admin). `/access` gains `manage_pipeline`.
  5. **Concurrency:** the pipeline carries one version for its whole
     configuration; every change sends `If-Match` with it and bumps it.
  6. **Removing a stage** is refused for the last stage. From 4B, a stage
     that holds deals can only be removed by naming another stage of the
     same pipeline to move them to; each moved deal gets a stage-change
     history entry.
  7. **Audit:** `crm_app.pipeline.updated` (rename),
     `.stage_created`, `.stage_updated`, `.stage_deleted`,
     `.stages_reordered`, naming IDs and the changed field names, never
     names.
- **4B and 4C direction (detailed in their slices):** a deal (table
  `opportunity`) has a title, a value as a decimal amount in the
  workspace's currency, a stage, an owner, an expected close date, links
  to one contact and one company, and an outcome `open`, `won` or `lost`
  (with a reason for lost); its weighted value is value times its stage's
  probability while open. Stage changes and outcomes are history entries.
  Tasks have a title, an assignee, a due date and time, completion, and
  an optional link to a contact, company or deal; Members may delete
  tasks (Q6).

## P4-B — Deals (2026-10-27, under M1)

- **Status:** Approved under M1 (owner instruction of 2026-10-27, "Implement
  Phase 4B — Deals end to end"). Refines P4's 4B direction; slice 4B.
- **Decisions:**
  1. Tables `opportunity` and `opportunity_event` (migration
     `0011_opportunities`): tenant-owned, forced RLS, composite keys, in
     `PURGE_TABLES`.
  2. **Money.** `amount` is optional, `numeric(15,3)`, never negative, sent
     and returned as a decimal string (`"12500.50"`), never a JSON number,
     so no client or server step uses floating point. It may have at most
     the currency's ISO 4217 minor digits (0 for JPY and the like, 3 for
     BHD and the like, otherwise 2) and at most 12 whole digits; anything
     else is refused, never rounded. `currency` is the workspace's currency
     when the deal is created, set by the server and never by the client;
     there is no per-deal override. Changing the workspace's currency later
     does not rewrite existing deals: each keeps the currency its amount
     was entered in, and totals are summed per currency in exact decimals.
  3. **Stage.** A deal references a stage of the workspace's pipeline
     through `(tenant_id, pipeline_id, stage_id)`, `ON DELETE RESTRICT`. A
     new deal starts in the first stage unless another is given.
     `stage_entered_at` dates the current stage, for "idle" (7 days or
     more in the stage while open, as the design's filter).
  4. **Links.** Contact, company and owner are optional. A contact or
     company must be an active (not archived) record of the same workspace
     when linked; composite keys with `ON DELETE SET NULL` of the link
     column keep the deal if the record is later deleted. The owner must
     be an active member (as for contacts).
  5. **Outcomes.** `open`, `won`, `lost`. Allowed: open to won or lost,
     won or lost back to open ("reopen"); won to lost and lost to won go
     through open. Lost needs a reason (trimmed, 1-500 characters); reopening
     clears it. `closed_at` is set while won or lost. A closed deal's stage
     cannot change (`deal_closed`); its other fields can.
  6. **Who** (Q6): every role reads; Owner, Admin and Member create and
     update, which includes stage changes and outcomes; only Owner and
     Admin delete.
  7. **History** (`opportunity_event`): append-only for the application:
     the runtime role has SELECT, INSERT and DELETE (purge and the cascade
     from a deleted deal) but not UPDATE, and no application code deletes
     an entry. A sequence number orders entries within one transaction.
     Kinds: `created`, `updated` (changed field names from an allow-list),
     `stage_changed` (stage IDs with their names at the time, and whether
     it was a move or a stage removal), `owner_changed`, `outcome_changed`.
     Never amounts, titles or the lost reason.
  8. **Removing a stage that holds deals** needs `move_to`, another stage of
     the same pipeline; the deals move, each with a `stage_changed` entry,
     in the transaction that removes the stage. Without `move_to` the
     refusal is `stage_in_use` with the number of deals.
  9. **Concurrency.** Every deal write takes a share lock on its pipeline's
     row; pipeline changes take the row lock, so a stage removal and a deal
     write never interleave. Deal updates and outcomes need `If-Match`;
     create accepts `Idempotency-Key` (scoped to the member).
  10. **Lists.** `GET /opportunities` filters by text in the title, outcome,
     stage, owner, contact, company and idle, orders by updated, created,
     title, amount or expected close date with cursor paging;
     `GET /opportunities/summary` returns, for the same filters, each
     stage's open-deal count and per-currency total and weighted total. The
     board and the table use the same filters, so they agree.
  11. **Audit:** `crm_app.opportunity.created`, `.updated`,
     `.outcome_changed`, `.deleted` with IDs and field names only; a stage
     removal's audit entry counts the deals moved.
  12. **Not in 4B:** custom fields and tags on deals, deal import and export,
     several pipelines, per-deal probability, card order within a column
     (cards are ordered by last update).

## P4-C — Tasks (2026-10-27, under M1)

- **Status:** Approved under M1 (owner instruction of 2026-10-27, "proceed
  autonomously"). Roadmap 4.1; the design's `ScreenTasks.dc.html`; Q6
  (Members may delete tasks); slice 4C.
- **Design audit:** tabs Open, Assigned to me, Overdue and Completed with
  counts; an assignee filter ("Everyone" or a person); a quick-add row
  (title, assignee, due, priority); groups Overdue, Today and Upcoming;
  a complete toggle, the linked contact and Delete on each row. The
  prototype's due dates are display strings ("Today, 5:00 PM") and
  "overdue" is a stored flag; here both are computed from a real time.
- **Decisions:**
  1. Table `task` (migration `0012_tasks`): tenant-owned, forced RLS, in
     `PURGE_TABLES`. Title trimmed, 1-200 characters, no control
     characters; priority `high`, `medium` (default) or `low`; `due_at`
     an optional timestamp with time zone; `assignee_user_id` an optional
     active member; `completed_at` and `completed_by_user_id` set together
     while done; a version for optimistic concurrency.
  2. **Links:** optional contact, company and deal, each by a composite key
     `ON DELETE SET NULL` of the link column, so a task outlives its
     record. Linked records must be of the same workspace, and a contact or
     company active when linked.
  3. **Who** (Q6): every role reads; Owner, Admin and Member create,
     update, complete, reopen and delete. `/access` gains `create_task`,
     `update_task`, `delete_task`.
  4. **Time:** stored in UTC; "overdue" is an open task due before now on
     the server. "Today" and "Upcoming" are the viewer's local day, so the
     list takes `due_from`/`due_to` bounds the browser computes.
  5. **Lists:** filters open or done, assignee (`me`), overdue, due
     bounds, contact, company and deal; orders by due date (nulls last),
     completion time, creation or last update, with cursor paging;
     `GET /tasks/counts` gives the four tabs' counts for the assignee
     filter. Create accepts `Idempotency-Key`; every change needs
     `If-Match`, including completing and reopening.
  6. **Audit:** `crm_app.task.created`, `.updated` (field names),
     `.completed`, `.reopened`, `.deleted`, never titles. No user-visible
     history: the design shows none.
  7. **Record drawers:** contacts, companies and deals show their open
     tasks and can add one linked to them.
  8. **Not in 4C:** reminders and notifications, recurring tasks, task
     descriptions, bulk actions.

## P4-D — Home dashboard foundations (2026-10-29, under M1)

- **Status:** Decided under M1 after the owner's "proceed" (2026-10-29),
  following the proposal of the Home dashboard as the next unblocked
  slice. Roadmap 4.4 "Dashboard foundations" (total contacts, active
  opportunities, pipeline value, tasks due, recent activity; "only show
  metrics whose definitions are documented"); DESIGN-INSPECTION.md lists
  the Home dashboard as "foundations only".
- **Design audit (`ScreenDashboard.dc.html`):** an agency view across
  client workspaces; for a client workspace a "Business overview" and a
  "My day" lens, a setup checklist, a "Needs attention" strip (unread
  conversations, conversations without an owner, overdue tasks, deals idle
  7+ days), four KPIs with deltas against an earlier period, a 12-week
  lead trend, lead sources, pipeline by stage with a weighted forecast,
  today's appointments, tasks due today with a checkbox, recent
  conversations, campaign performance, AI assistants and recent activity.
  Every number in it is illustrative.
- **Decisions:**
  1. **Built now (slice 4D):** the workspace's Home page with
     - KPIs: **Contacts**, **Open deals**, **Pipeline value** (with its
       weighted value) and **Open tasks** (with the overdue count);
     - **Needs attention:** overdue tasks and deals idle 7+ days, each
       opening the matching filtered list;
     - **Pipeline by stage:** each stage's open deals and value, and the
       weighted forecast;
     - **Today's appointments** in the workspace;
     - **Tasks due today or overdue**, with completing a task in place for
       members who may update tasks;
     - **Recent activity** on contacts and companies.
  2. **Not now:** the agency view (Phase 11, P2-B), the "My day" lens and
     "Customize", the setup checklist, deltas against an earlier period, the
     lead trend, lead sources and conversion rate (no defined lead or
     conversion event yet), and the conversations, campaigns and AI cards
     (their modules are not built). Nothing on the page is a placeholder
     number.
  3. **Definitions:**
     - *Contacts:* contacts not archived, as the Contacts list counts them;
       above 10,000 shown as "10,000+".
     - *Open deals:* deals of the workspace's pipeline whose outcome is
       open. *Pipeline value:* the sum of their amounts in the workspace's
       currency (a deal without an amount counts but adds nothing);
       *weighted:* each amount times its stage's probability (P4-B).
     - *Open tasks* and *overdue:* open tasks of every assignee; overdue
       means due before now (P4-C).
     - *Idle deals:* open deals that have stayed in their stage at least 7
       days (P4-B).
     - *Today:* the viewer's own calendar day in the browser's time zone.
       Tasks shown are open ones due before the end of today, earliest
       first, at most 8; appointments are those starting today and not
       cancelled, at most 8.
     - *Recent activity:* the 10 newest history entries of contacts and
       companies (P3-B), with the record's name.
  4. **Data:** the page reads the existing list, summary, count and range
     endpoints, so each card keeps its own permission check, loads and
     fails on its own, and agrees with the page it links to. One new
     route, `GET /v1/workspaces/{tenant_id}/activity` (`crm_app.activity:
     read`, every role), returns the newest entries across contacts and
     companies (limit 1-20, default 10, no paging) with the record's kind,
     ID and display name. It carries what the record history already
     shows, minus note text: field names, never values.
  5. **Navigation:** Home is no longer "soon" and is where a workspace
     opens (it opened on Settings before).

## P4-E — A record's deals in its drawer (2026-10-31, under M1)

- **Status:** Decided under M1 after the owner's instruction of
  2026-10-31 to continue with the next approved roadmap work. Roadmap
  3.3 lists "Associated opportunities" on a contact's details; the
  contact and company drawers showed tasks, appointments and notes but
  not deals.
- **Decisions:**
  1. **Scope:** an "Opportunities" section in the contact and company
     drawers. Frontend only: `GET /opportunities` already filters by
     `contact_id` and `company_id` under `crm_app.opportunity:read`
     (P4-B), so every role that may read deals sees them.
  2. **What it lists:** the record's deals of every outcome, most
     recently changed first, at most 10, with stage, a Won or Lost tag
     and the value in the deal's own currency. The heading counts all of
     them; when there are more than 10 a line says so. A row opens the
     deal on the Opportunities page.
  3. **New deal from the drawer:** "New opportunity" (only with
     `create_opportunity`) opens the existing deal dialog with the
     contact, and the contact's company, or the company filled in; both
     stay changeable. The server checks the links as for any deal.
  4. **Not built:** totals per record, filtering the Opportunities page
     by record, and showing deals on the deal's contact through its
     company only (a company's section lists deals linked to the company
     itself).
  5. **Stale notes corrected:** the company drawer no longer says
     opportunities and pipeline are unavailable; the contact drawer's
     note names only messages and calls; the contact dialog's hint no
     longer says tags, notes and custom fields are unavailable.
- **Tests:** `frontend/src/records/recordDeals.test.tsx`.

## P5-A — Calendar and appointments (2026-10-28, owner approval)

- **Status:** Approved by the owner on 2026-10-28. Asked "Should Calendar
  and booking (Phase 5, outside the approved MVP) start now, or wait until
  after email?", the owner answered "Yes": start now. This is the separate
  timing decision K5 requires. It brings Phase 5 forward; it does not add
  calendar or booking to the K5 MVP list. Roadmap 5; the design's
  `ScreenCalendar.dc.html`; slice 5A.
- **Design audit:** a Calendar page with Day, Week and Month views,
  previous/Today/next, a range label and "New appointment". A side panel
  (wide screens only) shows "Team availability" (a toggle per person with
  a status line and today's load), "Up next" and a status legend
  (Confirmed, Pending, Completed, No-show). Week view has a column per
  day; Day view a column per team member. Overlapping appointments share
  a column in lanes; clicking a free slot books at that time; working
  hours and lunch are shaded. Month view shows up to three chips a day
  and "+N more". A drawer shows the appointment: status buttons, With,
  type and location, reminders, source, the contact, "Send reminder",
  "Reschedule" and "Cancel appointment". The New appointment dialog has
  title, contact, With, day, start, length (30 min to 2 h), type (In
  person, Video, Phone) and a live conflict or "available" message. In
  the prototype times are hours on a fixed sample week, cancel deletes the
  appointment without confirmation, reminders and "Send reminder" are
  visual only, and the availability lines are invented.
- **Decisions:**
  1. **Scope of 5A:** appointments; Day, Week and Month views; create,
     edit and reschedule; status; cancel; conflict detection; time zones;
     an Appointments section in the contact drawer. **Later slices:**
     working hours and availability (5B, also the "outside working hours"
     warning and the shading); a public booking page (after 5B);
     reminders and notifications (need a delivery channel; the email
     channel waits for SaaS-OS, Phase 6). **Not planned now:** external
     calendar sync (roadmap: evaluate first), recurring appointments,
     rooms and resources, several hosts per appointment.
  2. **Table `appointment`** (migration `0014_appointments`):
     tenant-owned, forced RLS, in `PURGE_TABLES`. Title trimmed, 1-200
     characters, no control characters; `starts_at` and `ends_at`
     timestamps with time zone, at least 5 minutes and at most 24 hours
     apart; kind `in_person`, `video` or `phone`; an optional location of
     up to 300 characters (an address, a phone number or a meeting link,
     stored as text, never fetched); an optional note of up to 2,000
     characters; a host, required, who must be an active member when set;
     an optional contact by a composite key `ON DELETE SET NULL
     (contact_id)`, active when linked; a version.
  3. **Status:** `pending`, `confirmed` (the default), `completed`,
     `no_show` or `cancelled`. The design books as Pending because it
     simulates a confirmation SMS; nothing here sends one, so nothing
     would ever move an appointment out of Pending. A member may still
     choose Pending. **Cancel is a status, not a delete:** `cancelled_at`
     and `cancelled_by_user_id` are set together exactly while cancelled;
     a cancelled appointment cannot be changed or reopened (book a new
     one). Cancelling asks for confirmation.
  4. **Conflicts:** two appointments conflict when they have the same
     host, neither is cancelled, and their half-open intervals
     `[starts_at, ends_at)` overlap. Creating an appointment, or moving
     one to another time or host, is refused with 409
     `appointment_conflict` and the conflicting appointments (ID, title
     and times; every member may read them) unless the request sets
     `allow_conflict: true`; the UI shows the conflict and offers "Book
     anyway". A per-host advisory lock serialises the check and the write.
     `GET /appointments/conflicts` gives the dialog its live check.
  5. **Time:** stored in UTC. The calendar shows the viewer's browser
     time zone and names it. The list takes a `from`/`to` range of at most
     42 days and returns every appointment overlapping it, at most 500,
     ordered by start, with a `truncated` flag; cancelled ones only when
     asked.
  6. **Who:** permissions `crm_app.appointment` read (every role), create
     and update (Owner, Admin, Member), delete (Owner, Admin; for
     mistakes, since cancelling keeps the record). Gate G7 applies to
     existing workspaces. `/access` gains `create_appointment`,
     `update_appointment` and `delete_appointment`. Every member sees
     every appointment of the workspace, as with tasks.
  7. **Writes:** create accepts `Idempotency-Key`; every change needs
     `If-Match`.
  8. **Audit:** `crm_app.appointment.created`, `.updated` (field names),
     `.status_changed` (old and new status), `.cancelled`, `.deleted`;
     never titles, locations or notes.
  9. **Screens:** the design's three views, toolbar and side panel (team
     filter with today's count, Up next, legend); clicking a free slot
     books at that time; the drawer with status buttons, details, the
     contact, Edit (reschedule) and Cancel; the dialog with a live
     conflict check. Differences: no "Send reminder", reminders row,
     source row or availability lines (no channel, no working hours yet);
     the Day view's columns are the members chosen in the team filter;
     the grid shows the whole day and opens at 07:00; on narrow screens
     the grid scrolls inside its own frame.

## P5-B — Business hours and availability (2026-10-28, under M1)

- **Status:** Decided under M1, inside the scope the owner approved with
  P5-A ("working hours and availability (5B, also the "outside working
  hours" warning and the shading)"). Roadmap 5 "Availability
  management"; the design's `ScreenSettings.dc.html` (Business profile ›
  Business hours) and `ScreenCalendar.dc.html`; slice 5B.
- **Design audit:** Settings › Business profile has "Business hours": a
  row per weekday with an on/off switch and one time range ("08:00 –
  18:00", "Closed"), saved with the rest of the profile, next to the time
  zone. The calendar hatches the time outside working hours ("Outside
  working hours"), tints a lunch hour ("Lunch block"), and the booking
  dialog says "Outside working hours for this team member." The side
  panel gives each person a status line ("Available now", "In appointment
  until 11:00", "Away · back 1:00 PM"). In the prototype the hours are
  fixed in code, the switches change nothing else, and the status lines
  are invented.
- **Decisions:**
  1. **One set of business hours per workspace**, as the design's
     Settings page has it. Hours per member, holidays and days off are
     not built now; every host shares the workspace's hours. The design's
     "for this team member" becomes "outside business hours".
  2. **Shape:** seven days, Monday first; each day closed or one range
     `opens`–`closes` in `HH:MM` (24-hour, whole minutes, `opens` before
     `closes`, both within the day). One range a day: the design's lunch
     block is not modelled (a break can be booked as an appointment).
  3. **Not set until saved.** A workspace without hours has no shading
     and no warning; nothing is invented. Settings offers Monday to Friday
     09:00–17:00 as a starting point that only applies once saved. Hours
     can be cleared again.
  4. **Time zone:** the hours are wall-clock times in the workspace's time
     zone (setting P2-F 1). The server turns them into UTC intervals with
     the IANA rules, so daylight-saving changes are handled in one place;
     the calendar shows them in the viewer's time zone.
  5. **Storage:** a nullable `business_hours` column on
     `workspace_settings` (migration `0015_business_hours`), saved by the
     existing settings `PATCH` with its version, `If-Match` and audit
     (field names only). The table `CHECK` requires a seven-item JSON
     array; the API checks every day. Owner and Admin change them
     (`crm_app.workspace:update`); every role reads them.
  6. **Availability:** `GET /appointments/availability?start&end` (any
     range of at most 42 days; `crm_app.appointment:read`) returns
     whether hours are set, the workspace time zone and the open
     intervals in UTC. The live conflict check also says whether the time
     is outside business hours.
  7. **Outside hours is a warning, not a refusal.** Staff may book
     outside hours (a late call, an exception); the dialog says so before
     booking. Enforcing hours belongs to the later public booking page.
  8. **Screens:** a Business hours section in Settings › Business profile
     (a switch and two times per day; read-only for other roles); the
     calendar shades closed time and labels it; the booking dialog warns;
     the side panel's status line per member is computed from the hours
     and the appointments shown ("Available now", "In an appointment
     until …", "Outside business hours"). The design's "Away" is not
     shown: there is no presence data.

## P5-D — Appointment reminder emails (2026-11-02, under M1)

- **Status:** Decided and built under M1 (owner, 2026-11-01: "proceed" with
  the recommended order, reminders second). Slice 5D. Uses the email
  channel of P6-E; nothing reaches a provider while sending is off, and
  production sending stays unauthorized.
- **Decisions:**
  1. **Setting:** Settings › Business profile › "Appointment reminders":
     off (default), 1 hour, 2 hours, 1 day or 2 days before
     (`workspace_settings.reminder_lead_minutes`, migration
     `0031_appointment_reminders`). Owners and Admins change it, as every
     workspace setting.
  2. **Who and when:** the appointment's contact, by email, once per
     start time, while the appointment is pending or confirmed and has not
     started, and only if it was made before the reminder time (an
     appointment booked inside the window already had its confirmation).
     A rescheduled appointment is reminded again for its new time.
  3. **Run:** the email maintenance run (`crm_app.email_maintenance`)
     finds the workspaces with reminders on through the global
     `reminder_workspace`, re-reads each one's setting under its own
     Row-Level Security, and queues the due reminders before handing
     queued email to the worker. The unique automatic row (appointment and
     start time) means a retried or concurrent run never reminds twice.
  4. **Skipped, with the reason:** no contact, an archived contact, no
     email address, an address the email rules refuse. Suppressed
     addresses are queued but never sent (P7-B).
  5. **Content:** transactional stream (`appointment_reminder`); subject
     "Reminder: title, day"; the contact's first name, the title, the
     time in the workspace's time zone (named), and the kind and location.
     No link and never the appointment's internal note. It acts as the
     host, as a booking confirmation does (P5-C 9).
  6. **"Send reminder":** members who may update appointments
     (`crm_app.appointment:update`) send one now, at most once an hour per
     appointment; refused for a cancelled, completed or started
     appointment and for a contact without a usable address. Every role
     sees the reminder status and the latest ten reminders in the drawer.
  7. **Not in 5D:** reminders for team members (needs a notification
     channel), SMS, several reminders per appointment, per-page settings.
- **Tests:** `tests/integration/test_reminders.py`,
  `tests/unit/test_reminder_rules.py`, `frontend/src/records/calendar.test.tsx`,
  `frontend/src/pages/BusinessSettings.test.tsx`.

## P5-C — Public booking pages (2026-10-28, under M1)

- **Status:** Decided under M1, inside the scope the owner approved with
  P5-A ("a public booking page (after 5B)"). Roadmap 5 "Appointment
  booking"; discovery's recommendation "Phase 3–5: single-user booking";
  slice 5C.
- **Design audit:** the Claude Design project has no booking page. The
  calendar's drawer has a "Source" row ("Booked online", "Added by …"),
  simulated in the prototype. The reference ZIP books publicly with
  reschedule and cancel tokens (an idea only, decision K1). Without a
  delivery channel nothing can be emailed to the visitor (Phase 6).
- **Decisions:**
  1. **Scope of 5C:** booking pages. Each page has one host and offers
     that host's free times inside the workspace's business hours. A
     visitor picks a time, gives a name and an email (and optionally a
     phone and a message) and books. The confirmation shows a private
     link to view and cancel the booking. **Not now:** emails or reminders
     to the visitor or the host (need a delivery channel), the visitor
     rescheduling (cancel and book again), several hosts or round robin,
     buffers between appointments, custom questions, payments, an embed
     script (the CSP forbids framing), CAPTCHA (decision S-1, Phase 13)
     and per-member hours (P5-B 1).
  2. **Tables** (migration `0016_booking_pages`), tenant-owned, forced
     RLS, in `PURGE_TABLES`:
     - `booking_page`: name (1-120), an optional description (up to 1,000
       characters), status `draft` or `published`, a random public key,
       the host (an active member when saved or published), the length
       (15, 30, 45, 60, 90 or 120 minutes), the step between start times
       (15, 30 or 60 minutes), the kind and an optional location (as on
       an appointment), the minimum notice (0 to 7 days, in minutes;
       default 4 hours), how far ahead (1 to 90 days; default 30), a
       booking count, the last booking time and a version. At most 50 a
       workspace.
     - `booking`: the page (`ON DELETE SET NULL`), the appointment (`ON
       DELETE CASCADE`, one booking each), the contact (`ON DELETE SET
       NULL`), the outcome (`created` or `matched`), the SHA-256 of the
       visitor's link token (unique), when the visitor cancelled, and the
       time.
     - The contact `source` gains `booking`; an appointment cancelled by
       the visitor has `cancelled_at` without `cancelled_by_user_id`.
  3. **Publishing** needs the workspace's business hours (P5-B 7: hours
     are enforced here) and an active host. A page whose host has left
     answers like an unpublished one.
  4. **Free times:** on the step grid from each day's opening time; the
     whole appointment inside one open interval; not before now plus the
     notice; not after the horizon; and free of the host's appointments
     that are not cancelled (any appointment, booked online or not). The
     public answer lists start times only, never other appointments, for
     at most 14 days at a time.
  5. **Public routes** under `/v1/public/booking-pages/{workspace}/{key}`
     (`GET` the page, `GET .../times`, `POST` a booking) and
     `/v1/public/bookings/{workspace}` (`POST .../view`, `POST
     .../cancel`, the token in the body, never in an address or a log),
     all SaaS-OS `public_route`, limited per address, the booking also
     per page, failing closed (503). An unknown workspace or key, a draft
     page and a closed or suspended workspace answer the same 404; an
     unknown token too. A booking needs an `Idempotency-Key`, is at most
     8 KiB, and a filled honeypot field is answered like a time that is no
     longer free (409), storing nothing.
  6. **What a booking does**, in one transaction under the host's lock
     (P5-A 4): it checks the time again (`409 time_unavailable` when it is
     no longer free), matches the active contact with the same email or
     creates one (stage Lead, source Booking, owned by the host); a
     matched contact is never changed (as P7-A 6). It refuses a fourth
     upcoming booking of the same contact on the same page (`409
     booking_limit`). It creates a `confirmed` appointment titled "page
     name — visitor's name", with the page's kind and location and the
     visitor's message as its note, hosted by the page's host, and the
     `booking` with the token's hash. The token is returned once.
  7. **The visitor's link** shows the time, the page's name, kind and
     location and whether it is cancelled, and cancels until the
     appointment starts. It works while the booking exists.
  8. **Who:** new catalogue permissions `crm_app.booking_page:read` (every
     role) and `crm_app.booking_page:manage` (Owner and Admin), as forms
     (P7-A 4): a published page lets anyone create contacts and
     appointments. `/access` reports `read_booking_pages` and
     `manage_booking_pages`. Gate G7 applies.
  9. **Audit:** `crm_app.booking_page.created`, `.updated` (field
     names), `.published`, `.unpublished`, `.deleted`. A booking's
     appointment `created` entry and the contact's `created` entry name
     the page and act as the host; a visitor's cancellation is the
     appointment's `cancelled` entry with `by: visitor`. SaaS-OS has no
     caller for an anonymous visitor (as P7-A 8).
  10. **Screens:** Calendar › Booking pages (a list and an editor: name,
      description, host, length, step, kind, location, notice, horizon;
      publish, copy link, delete). The hosted page `/app/b/{workspace}/{key}`
      without the app frame: days with free times, times in the visitor's
      time zone (named), the form, the confirmation with the private link
      `/app/b/{workspace}/manage#{token}`. The appointment drawer's
      "Source" row: "Booked online · page name", and "Cancelled by the
      visitor".

## P7-A — Forms and lead capture (2026-10-28, under M1)

- **Status:** Decided under M1. The owner's instructions of 2026-10-27
  ("continue automatically through the remaining approved roadmap") and
  2026-10-28 (the email channel waits for a SaaS-OS release with an email
  provider, so forms come first). Forms are in the K5 MVP; roadmap 7.3;
  the design's `ScreenForms.dc.html`; slice 7A.
- **Design audit:** a "Forms & pages" list with Forms and Landing pages
  tabs; cards with name, status, field count and views, leads and
  conversion; an editor with a field list (move up, move down, remove),
  an "Add" palette (Text, Email, Phone, Dropdown, Date, Message,
  Checkbox), a live preview, Publish/Unpublish, Copy link, and "After
  someone submits": create or update the contact matched by email or
  phone, add a tag, start an automation, a thank-you message and an embed
  script. Publishing, copying, the test submission and every metric are
  simulated in the prototype.
- **Decisions:**
  1. **Scope of 7A:** forms only. Landing pages (roadmap 7.4) are
     deferred: a page builder needs its own business case. Also deferred:
     the embed script (the app's CSP forbids framing and third-party
     origins), view counts and conversion (an unauthenticated view counter
     can be inflated by anyone), "Start automation" (Phase 8), CAPTCHA
     (evaluated with edge protection in Phase 13, decision S-1), double
     opt-in (needs the email channel), file uploads and custom-field
     targets.
  2. **Tables** (migration `0013_forms`), tenant-owned, forced RLS, in
     `PURGE_TABLES`:
     - `form`: name (1-120), status `draft` or `published`, a random
       public key, the fields, an optional tag (`ON DELETE SET NULL`), a
       thank-you message, optional consent wording, the owner of new
       contacts, a submission count and the last submission time, and a
       version.
     - `form_submission`: the form (`ON DELETE CASCADE`), the contact
       (`ON DELETE SET NULL`), the answers, the outcome (`created` or
       `matched`), whether consent was given, and the time.
     - `consent_record`: append-only (the runtime role has no UPDATE):
       contact (`ON DELETE CASCADE`), channel `email`, status `granted`,
       method `web_form`, the wording shown, the form and submission
       (`ON DELETE SET NULL`), and the time.
  3. **Fields:** 1-20, each with a stable key, a type (`text`, `email`,
     `phone`, `textarea`, `select`, `date`, `checkbox`), a label, required
     or not, options for a select (1-20), and an optional contact target
     (`first_name`, `last_name`, `email`, `phone`, `job_title`, `city`),
     each target at most once and matching the type. A form can be
     published only with a required first-name field and an email or
     phone field.
  4. **Who:** new catalogue permissions `crm_app.form:read` (every role)
     and `crm_app.form:manage` (Owner and Admin): a published form opens
     an unauthenticated path into the CRM. `/access` reports `read_forms`
     and `manage_forms`. As in P3-F, workspaces created before this change
     do not receive them (gate G7).
  5. **Public routes** `GET` and `POST /v1/public/forms/{workspace}/{key}`
     (SaaS-OS `public_route`):
     - an unknown workspace or key, a draft form and a closed workspace
       all answer the same 404;
     - per-address and per-form limits use the SaaS-OS limiter and fail
       closed (503); the body is at most 16 KiB; `Idempotency-Key` is
       required;
     - a filled honeypot field is answered like a success and nothing is
       stored;
     - answers are checked against the form's current fields; unknown
       keys are refused; errors name field keys, never values.
  6. **What a submission does**, in one transaction:
     - the active contact with the same (normalised) email is matched;
       phone numbers are stored as typed, so they are not matched;
     - otherwise a contact is created: stage Lead, source Form, owned by
       the form's contact owner while they are an active member;
     - **a matched contact is never changed by an anonymous visitor**:
       only the form's tag is added (skipped at the tag limit), the
       submission is linked and consent may be recorded;
     - the submission is stored and the form's count increases.
  7. **Consent:** when the form has consent wording, the visitor ticks the
     box and gives an email, a `consent_record` keeps the exact wording,
     the form, the submission and the time. It is single opt-in and
     unverified; nothing here is a claim of legal compliance (P2-D).
  8. **Audit:** `crm_app.form.created`, `.updated` (field names),
     `.published`, `.unpublished`, `.deleted`. A created contact's audit
     entry, and a matched contact's tag change, name the form and act as
     the form's contact owner, as an import's entries name the import
     (P3-F 8). Every form therefore has a contact owner (by default its
     creator), who must be an active member when the form is saved. SaaS-OS has no caller for an
     anonymous visitor, so matched submissions are recorded in
     `form_submission` only.
  9. **Retention:** submissions are kept while their form exists; deleting
     a form deletes its submissions but not the contacts or consent
     records. A retention period for submissions is a later,
     market-specific decision (P2-D).
  10. **Screens:** the Forms list (no Landing pages tab), the editor
      (fields, preview, settings, publish, copy link), the submissions
      list, a contact's consent in its drawer, and the hosted form page
      `/app/f/{workspace}/{key}` without the app frame or sign-in.

## 13-H1 — Security review of the public routes (2026-10-29, under M1)

- **Status:** Decided under M1 after the owner's "go" (2026-10-29) to the
  proposal "hardening: a security review of the public routes". Roadmap
  Phase 13 work brought forward; nothing here changes SaaS-OS, its pin,
  identity or invitation semantics.
- **Review:** a read-only review of every `public_route` (hosted booking
  pages and visitor bookings, hosted forms, signup status, sign-out
  address) and the three public pages. No critical findings. Sound:
  tenant scope taken from the looked-up row under forced RLS, one
  indistinguishable 404, 256-bit visitor tokens stored as hashes and sent
  in bodies, limits before any database access, no input echoed in
  errors, no mass assignment, React text rendering only, CSP and
  `Referrer-Policy: same-origin`.
- **Decisions:**
  1. **Fixed now:**
     - A deeply nested JSON body raised `RecursionError` (a 500); an
       extreme time (year 1 or 9999 with an offset) raised `OverflowError`
       (a 500). `crm_app.api.inputs` now reads small JSON bodies with the
       size checked against `Content-Length` and while streaming, treats
       nesting too deep to parse as "not JSON" (422), and offers `Instant`,
       an aware time between 1900 and 2999, used for every time a client
       sends (bookings, free times, appointments, tasks).
     - The audit entry for an appointment made on a booking page now
       carries `"by": "visitor"`, as its cancellation already did; the host
       remains the actor because SaaS-OS records a user caller.
  2. **Already contained (finding F1):** a public form submission can
     record `granted` for an existing contact whose consent a member
     withdrew. Withdrawing suppresses the address (P7-B 5) and
     `may_send` refuses a suppressed address whatever the consent says,
     so no email follows. Recording new consent for a contact who never
     withdrew remains the documented single opt-in (P7-A 7): **double
     opt-in is a precondition for campaigns** and is built with the email
     channel.
  3. **Launch gate (F2):** per-visitor limits on public routes key on the
     client address, so production must run with
     `TRUST_PROXY_HEADERS=true` behind an edge that overwrites
     `X-Forwarded-For`, and the application must not be reachable around
     the edge. The production topology is decided in Phase 13/14; this is
     recorded there rather than enforced at start-up now. The edge's own
     request-size cap is part of the same gate.
  4. **Accepted for now, revisit with the email channel or Phase 13:** a
     limiter key is created for a well-formed but unknown page before the
     lookup (bounded by the per-address limit); the per-page limit is
     shared by every visitor of that page; a visitor's booking token works
     while the booking exists (P5-C 7), so a leaked link shows the
     booking's time and location; rotating email addresses avoids the
     per-contact cap of upcoming bookings, leaving only the rate limits
     (no CAPTCHA or workspace contact cap yet).

## P6-E — Transactional email on Resend through SaaS-OS (2026-11-01)

- **Status:** The provider is the owner's decision of 2026-11-01: "LeadStack
  will use Resend for email. SaaS-OS v0.6.0 already provides Resend
  integration. Reuse the existing SaaS-OS implementation instead of building
  a competing email provider integration." The design below is decided
  under M1 within that authorisation; nothing sends in production until
  the open decisions are made. Slice 6E.1 (infrastructure).
- **What SaaS-OS v0.6.0 provides (ADR-0058, verified in the pinned
  source):** `EMAIL_PROVIDER=resend` selects `ResendEmailProvider` with
  `RESEND_API_KEY` from the secrets provider; `send_email(message)` posts
  one email over the strict egress client and never retries itself; an
  `EmailMessage.message_id` becomes Resend's `Idempotency-Key`, so a retry
  within 24 hours is not a second email; `400`/`422` are permanent, the
  rest (including `401`, `429` with a retry hint, `5xx`, timeouts)
  transient; nothing about recipients or bodies is logged. It does **not**
  consume Resend's delivery webhooks.
- **Decisions:**
  1. **One adapter, SaaS-OS's.** The product calls `send_email` only; it
     builds no Resend client. The deployment chooses the provider
     (`EMAIL_PROVIDER`), so tests and local use `mailpit` or an injected
     provider, and the product's tables name the provider only as a label.
  2. **Records:** `email_message` per email (purpose, recipient, subject,
     plain text, status, provider id, attempts, last error code),
     `email_event` per provider event (append-only, unique per provider
     event id), and the global `email_index` (ids and retry times) for the
     webhook's lookup and the sweeper. Migration `0019_email`.
  3. **Sending** (`crm_app.emails.send`, job `crm_app_email_send`): only
     while `EMAIL_SENDING_ENABLED=true` (off by default; refused in
     production; needs `EMAIL_DEFAULT_SENDER`). The email is claimed under
     a row lock, so two jobs never send it twice; every try has the
     `Message-ID` `<email id@sender's domain>`. An address on the
     workspace's suppression list is never sent to (also for
     transactional mail). Permanent refusals fail the email; anything else
     returns it to the queue, at most 5 tries. `python -m
     crm_app.email_maintenance` re-enqueues emails whose job was lost and
     drops index rows of emails that never committed.
  4. **Delivery tracking:** `POST /v1/public/email/resend/events`, public,
     404 until `RESEND_WEBHOOK_SECRET` is set, per-address limited, 64 KiB,
     Svix signature checked in constant time with a 5-minute window before
     the body is parsed. `sent`, `delivered`, `delivery_delayed`, `bounced`
     and `complained` are recorded once each and only move the status
     forward; a bounce or complaint suppresses the address with origin
     `provider`. Opens and clicks are not tracked.
  5. **Audit:** `crm_app.email.queued`, `.sent`, `.failed`,
     `.suppressed`, `.bounced`, `.complained`, by email id with purpose
     and codes only, acting as the member whose action queued the email
     (SaaS-OS has no system caller for this); a provider suppression is
     also a `crm_app.suppression.added` entry with `origin: provider`.
  6. **Consumers:** none yet. The purposes are `booking_confirmation`
     (next slice) and `test`. Campaign (marketing) mail also needs
     consent (`may_send(..., marketing=True)`) and double opt-in (13-H1 2).
- **Open decisions (the owner's; not invented here):**
  1. The sending domain and its DNS (SPF, DKIM, DMARC, return path).
  2. One platform-wide sending domain, workspace-specific domains, or
     both, and who verifies a workspace's domain in Resend.
  3. The production sender identity policy: the `From` name and address,
     `Reply-To`, and whether a workspace may send as itself.
  4. Incoming email (replies into conversations): Resend inbound or
     another route.
  5. The worker's outbound route to `api.resend.com` in production
     (SaaS-OS ADR-0059 egress proxy) and the Resend account and plan.
- **Tests:** `tests/unit/test_email_rules.py`,
  `tests/integration/test_emails.py`, settings tests.

## P6-C — Conversations foundation (2026-11-01, under M1)

- **Status:** Implemented under the owner's mission of 2026-10-31 (fifth
  priority, "6.1 Conversations": provider-neutral, no email sending or
  receiving assumptions in the core model).
- **Model (migration `0022_conversations`):** `conversation` (one thread
  with one contact on the `email` channel or `other`, a subject, `open` or
  `closed`, an assignee, the time of the last message), append-only
  `conversation_message` (`inbound`, `outbound` or `note`, plain text up to
  20,000 characters, the author, and for an email reply the
  `email_message` it queued) and `conversation_read` (when each member last
  read a thread). Forced Row-Level Security; in the purge. No column names
  a provider.
- **Behaviour:**
  1. Inbound messages are logged by a member: no provider delivers inbound
     email yet (inbound email remains an open owner decision, P6-E).
  2. An `outbound` message is allowed only on an email thread and queues
     one email through `crm_app.emails` (purpose `conversation_reply`) to
     the contact's address; the message's delivery state is that email's
     status. While `EMAIL_SENDING_ENABLED` is off nothing leaves and the
     screen says "Not sent yet"; nothing ever shows a queued message as
     sent. Suppression is enforced when the email is sent (P6-E).
  3. Creating a thread and adding a message accept an `Idempotency-Key`
     (per member), so a retried request never queues a second email.
  4. A new inbound or outbound message reopens a closed thread; a note
     does not. Unread means a non-note message by someone else after the
     member last opened the thread.
  5. Assignment is to an active member of the workspace; assign, close and
     reopen need `If-Match`. Deleting the contact keeps the thread
     without its contact.
- **Permissions:** new `crm_app.conversation:read` (every role) and
  `crm_app.conversation:reply` (Owner, Admin, Member). As with every new
  permission, workspaces created before this change lack the grants
  until their roles are updated (gate G7).
  Audit entries name ids, kinds and fields, never message text.
- **Screen:** the Inbox (`/inbox`, `ScreenConversations`): list by status
  and assignment with unread marks, the thread with the contact link,
  assignee and close/reopen, a composer for an email reply, a logged
  message or an internal note, and a new-conversation dialog. Phones show
  the list or the thread.
- **Not built:** text search across threads (since built: P6-C1); SMS, WhatsApp and voice
  (deferred, K5); inbound email; attachments; the design's suggested
  reply (Phase 9, blocked by P9-0); bulk actions.

## P6-D — Customer-owned sending domains and sender identities (2026-11-01)

- **Status:** Implemented under the owner's requirement of 2026-11-01
  ("Customer-owned outbound email: a workspace must be able to send through
  Resend using its own verified business email identities ... Never permit
  a workspace to impersonate an unverified or another workspace's domain.
  Do not assume domain ownership or create DNS records"). No domain is
  created at Resend unless `EMAIL_CUSTOMER_DOMAINS_ENABLED` is on, which is
  refused in production.
- **Domains:** Owners and Admins (`crm_app.workspace:update`) register a
  domain (at most 10); every role sees them. A plain, non-reserved domain,
  never LeadStack's own email parent domain or a name under it. A domain
  belongs to at most one workspace on the platform (global
  `sending_domain_index`, migration `0029_sending_domains`); removal frees
  it at once.
- **Records come from Resend only:** with the provider on, registering calls
  Resend's `POST /domains` (sending only) and stores exactly the records it
  returns; "Verify" calls `POST /domains/{id}/verify`; the result arrives as
  Resend's signed `domain.created|updated|deleted` events on the existing
  delivery webhook, checked like every event. Without a provider the
  domain is kept `not_registered` with `provider_unavailable`, and nothing
  is invented. The adapter uses SaaS-OS's egress client (POST only), so the
  product cannot read or delete a Resend domain: a removed domain is left at
  Resend for an operator (`saas-os-gaps.md`, items 2 and 3).
- **Sender identities:** addresses on the workspace's own domains (no `+`,
  no display name), allowed for conversation mail, campaign mail or both,
  one default per stream. An identity is usable only while it is active
  and its domain's provider state is `verified`.
- **Sending:** a conversation or campaign email is queued with the
  workspace's default identity for its stream when that identity is usable,
  otherwise with none (LeadStack's stream sender). An email queued with an
  identity is sent only from that address and only while it is still
  usable; otherwise it waits (`sender_unverified`) and is never sent from
  another address. Transactional email always uses the platform's sender.
- **Verification expiry:** a domain the provider later reports as failed
  (or deleted) stops its identities at once.
- **Not built:** reply-to per identity (replies route through the
  conversation's routing address), display names (SaaS-OS), periodic
  re-checks without webhooks (no GET in the egress client).
- **Verified:** `tests/integration/test_sending_domains.py`,
  `tests/unit/test_sending_domain_rules.py` (including the Resend adapter
  against a test egress client), `frontend/src/pages/sendingDomainSettings.test.tsx`.

## P12-D — Custom domains for hosted pages: ownership and mapping (2026-11-01)

- **Status:** Implemented under the owner's requirement of 2026-11-01
  ("Custom domains for LeadStack-hosted pages: prepare support for
  customer-owned custom domains ... Domain ownership verification. Secure
  tenant-specific domain mapping. Automatic HTTPS/TLS where supported.
  Host-header validation. Protection against domain takeover. Safe removal
  and reassignment. Clear DNS setup instructions. Keep this separate from
  email-domain verification").
- **Claims:** members with `crm_app.workspace:update` add hostnames (at most
  20 per workspace): ASCII (punycode for international names), at least
  two labels, no wildcard, port, path or address, not a reserved or local
  name, and not the app's own domain or a name under it. Every role reads
  them. A claim is `pending` for at most seven days with a random 128-bit
  token; then it must be added again for a new token.
- **Ownership proof:** a DNS TXT record at
  `_leadstack-challenge.<hostname>` holding exactly
  `leadstack-verification=<token>` (compared in constant time). Separate
  from email-domain records, which Resend supplies.
- **Mapping:** only verified hostnames are mapped (global
  `custom_domain_index`, migration `0028_custom_domains`), and a partial
  unique index lets one workspace hold a hostname verified at a time;
  another workspace's pending claim never blocks the owner and shows
  `claimed_elsewhere`. `GET /v1/public/domains/resolve` answers which
  workspace the request's `Host` belongs to (port and case ignored), 404
  for anything not verified.
- **Takeover protection:** the maintenance command re-checks verified
  domains daily; a domain whose record is gone becomes `lapsed` and stops
  mapping, so a domain that changed hands is never served for its old
  workspace, and the new owner can then verify. A lookup that fails never
  lapses a domain. Removing a claim deletes its mapping at once; expired
  claims are removed.
- **Open decisions (owner):**
  1. *DNS lookups.* The product has no DNS client: either add the
     `dnspython` dependency or use an external DNS-over-HTTPS service
     (which SaaS-OS's egress client could reach with POST, RFC 8484). Until
     one is approved, a check records `resolver_unavailable` and nothing is
     verified; tests use a test double (`crm_app.custom_domains.TxtResolver`).
  2. *Serving and TLS.* Pages on a verified domain need the deployment's
     edge (Caddy) to accept the hostname and obtain a certificate (Caddy's
     on-demand TLS can ask `/v1/public/domains/resolve` before issuing); the
     single-page app must then open hosted pages by host. Both are
     deployment changes not made here; the Settings screen says pages keep
     their LeadStack address until then.
- **Verified:** `tests/integration/test_custom_domains.py`,
  `tests/unit/test_custom_domain_rules.py`,
  `frontend/src/pages/domainSettings.test.tsx`.

## P12-W — Website integration: embeddable forms and allowed origins (2026-11-01)

- **Status:** Implemented under the owner's requirement of 2026-11-01
  ("Customer website integration: support websites hosted outside
  LeadStack, including WordPress, Shopify, Webflow, Wix and custom
  websites ... Do not require customers to move their websites to
  LeadStack").
- **Built on forms (P7-A):** an external site embeds a published form; the
  lead capture is the existing public form API with its validation,
  honeypot, per-address and per-form limits, `Idempotency-Key`, 16 KiB
  bodies, contact matching and consent records. No second capture path.
- **Websites:** a workspace lists its external sites, each a name and 1 to
  20 allowed origins: `https://host[:port]`, no paths, wildcards or
  credentials; `http://localhost` only in development and test. At most
  50 per workspace. Managed with `crm_app.form:manage`, read with
  `crm_app.form:read` (no new permission). Disabling or removing a site
  stops it at once; removing keeps its submissions without the link.
- **Origin enforcement:** a browser submission from another origin than
  the app's own is accepted only when that origin belongs to an active
  website of the form's own workspace; it is answered with CORS headers
  naming that origin alone (no wildcard, no credentials) and a CORS
  preflight (`OPTIONS`) is answered the same way; any other origin gets
  403 `origin_not_allowed` before the body is read. Requests without an
  `Origin` (servers, for instance a site's own backend) behave as before.
  Listing an origin needs no proof of ownership: it only lets that site
  put leads into this workspace, and only if the site embeds this
  workspace's form.
- **Attribution:** a submission may carry UTM parameters, the page address
  and the referrer; values are cut to 300 characters, URLs must be http or
  https, and a page address on another origin than the request's is
  dropped. Stored on `form_submission.attribution` with the website
  (`website_id`, migration `0027_websites`), and returned with the
  submissions.
- **Embed code:** the form editor offers "Embed on a website": a plain HTML
  form and a short script (no external file) that posts with an
  `Idempotency-Key`, the honeypot, consent and attribution; every label,
  option and consent text is escaped.
- **Not built:** a tracking script (no page-view tracking, so nothing to
  consent to; it would need an owner decision on cookies and consent
  banners); a JavaScript widget served from LeadStack; booking-page embed
  code (the public booking link already works from any site); per-site
  secret keys for server-side posting.
- **Verified:** `tests/integration/test_websites.py`,
  `tests/unit/test_website_rules.py`,
  `frontend/src/records/embedSnippet.test.ts`, `forms.test.tsx`.

## P7-T — Email templates (2026-11-02, under M1)

- **Status:** Decided and built under M1 (owner, 2026-11-01: "proceed" with
  the recommended order, email templates fifth). Slice 7T. Roadmap 7.1
  "message templates"; `ScreenTemplates.dc.html` is an empty stub, so the
  list lives under Campaigns.
- **Decisions:**
  1. **Shape:** a name (unique per workspace), a one-line subject and a
     plain-text body, with exactly the campaign rules: the placeholders
     `{{first_name}}` and `{{last_name}}`, nothing evaluated, no HTML.
     Table `email_template` (migration `0033_email_templates`), at most
     100 per workspace, versioned writes (If-Match), audited without text.
  2. **Permissions:** the existing campaign ones (every role reads; Owners,
     Admins and Members manage); no new permission, so gate G7 is not
     touched. Filling a template in for a contact takes the permission to
     reply (`crm_app.conversation:reply`) and only for the workspace's own
     contacts; values are inserted literally and never expanded again.
  3. **Use:** the campaign editor copies a template's subject and text into
     the draft (the campaign then needs its own approval, P7-C); the reply
     composer fills in a template's text for the conversation's contact.
     A template never sends anything.
  4. **Not in 7T:** HTML, attachments, more placeholders, shared or
     agency-wide templates (Phase 11), template use statistics.
- **Tests:** `tests/integration/test_email_templates.py`,
  `frontend/src/records/emailTemplates.test.tsx`.

## P7-C — Campaign drafts, audiences and approval (2026-11-01)

- **Status:** Implemented under the owner's email mission of 2026-11-01
  ("Campaign sending: Explicit approval required before each campaign ...
  Implement campaign preparation and approval ... A campaign must never
  send automatically merely because it is saved, validated or scheduled").
  K5 had left campaigns outside the MVP; this instruction brings their
  preparation into scope. Sending stays unavailable.
- **Workflow:** `draft → validated → awaiting_approval → approved → queued
  → processing → completed`, or `partially_completed`, `failed`,
  `rejected` (back to editable, with the approver's note) and `cancelled`.
  Steps need `If-Match`; a step from the wrong state is 409
  `campaign_state`.
- **Approval binds content:** each campaign stores the SHA-256 of its exact
  name, subject, body and audience (`content_hash`); approval records it
  (`approved_hash`), and any edit returns the campaign to draft and clears
  the approval, estimate and submission. Queuing and processing check the
  approved hash again (409 `approval_outdated`).
- **Audience:** a segment of the workspace's contacts by lifecycle stage,
  tag, owner and company (at most 50 of each); an empty segment must say
  `all_contacts`, so a send to everyone is never an accident; at most
  50,000 contacts. Validation counts eligible contacts and the excluded
  ones by reason (no address, duplicate address, suppressed, no marketing
  consent) and needs at least one eligible.
- **Content:** plain text, subject one line; placeholders
  `{{first_name}}` and `{{last_name}}` only, replaced literally (nothing is
  evaluated); every email gets a footer with the workspace name and an
  unsubscribe link.
- **Permissions (new):** `crm_app.campaign:read` (every role),
  `crm_app.campaign:manage` (Owner, Admin, Member: draft, edit, validate,
  submit, cancel), `crm_app.campaign:approve` (Owner, Admin, administrative:
  approve, reject, queue). Existing workspaces get them with
  `crm_app.role_upgrade` (P2-G7); `approve` is held back there unless
  `--include-administrative`.
- **Sending:** `queue` is refused (409 `campaign_sending_unavailable`)
  unless `crm_app.campaigns.SENDING_AVAILABLE` (false: SaaS-OS v0.6.0
  cannot set `List-Unsubscribe` headers; `saas-os-gaps.md` item 1), the
  campaign stream is switched on and the environment is not production.
  When available, `process` adds each eligible contact once (unique per
  campaign and contact) and queues one email each on the campaign stream,
  where suppression and consent are checked again at send time.
- **Unsubscribe:** `POST /v1/public/unsubscribe/{workspace}/{token}`, one
  click, rate-limited, always 204; a known token suppresses the address
  (reason `unsubscribed`) and records consent `withdrawn` (method
  `unsubscribe_link`). Tokens are random per recipient and stored hashed.
- **Audit:** every step, with ids, states and hashes; never content.
- **Not built:** scheduling, templates, HTML email, campaign metrics, the
  unsubscribe landing page (the link's page is built with sending), tag,
  owner and company filters in the screen (the API takes them).
- **Verified:** `tests/integration/test_campaigns.py`,
  `tests/unit/test_campaign_rules.py`, `frontend/src/records/campaigns.test.tsx`.

## P6-I — Inbound email: recording, routing, quarantine (2026-11-01)

- **Status:** Implemented under the owner's email mission of 2026-11-01
  ("Incoming email: Yes ... Implement a provider adapter around Resend
  inbound receiving ... Do not activate production inbound receiving").
  Off by default, refused in production, and without a real receiving
  client (below), so no real email is received or processed.
- **Pipeline:**
  1. `POST /v1/public/email/resend/inbound`: its own secret
     (`RESEND_INBOUND_WEBHOOK_SECRET`), 404 unless that is set and
     `EMAIL_INBOUND_ENABLED` is on outside production; per-address limit,
     64 KiB, Svix signature checked before parsing. Each `email.received`
     event is stored once in the global `inbound_email` (unique by event id
     and by provider email id) before any processing; other event types
     are acknowledged and ignored; a malformed received event is refused
     (400) so it stays visible in Resend's delivery log.
  2. The system job `crm_app_inbound_process` and the sweeper
     (`crm_app.email_maintenance`) claim due rows with `FOR UPDATE SKIP
     LOCKED`; a row left `processing` by a dead worker is taken again after
     ten minutes. Transient fetch failures wait with backoff, jitter and
     `Retry-After`; permanent ones and eight tries end as `failed`.
  3. Routing uses server-side data only. Each conversation gets a random
     128-bit routing token when its first email reply is queued
     (`conversation_route`, tenant-owned); its SHA-256 is in the global
     `conversation_route_index`. A received email is routed only when
     exactly one recipient is `reply+<token>@inbound.<parent>` and the
     workspace's own route row holds the same token; nothing else in the
     email (headers, names, addresses) can choose a workspace.
  4. Routed mail from the conversation's contact with a passing or absent
     DMARC result becomes an inbound message (at most once per email: a
     unique key on `conversation_message.inbound_email_id`) and reopens the
     thread. Mail from anyone else, failing DMARC, without text, or on a
     thread without a contact goes to the workspace's review list
     (`inbound_quarantine`). Mail that names no workspace stays `unmatched`
     with a reason and only the sender's domain, for an operator; it is
     never deleted silently.
  5. Text is preferred; HTML is reduced to its visible text (scripts,
     styles and markup dropped; never rendered); 20,000 characters at most.
     Attachments are listed by sanitised name, type and size and are not
     downloaded (no approved malware scanner).
- **Reply-To:** an email reply carries its conversation's routing address
  only while inbound email is on and a parent domain is set.
- **Review:** `GET /conversation-reviews` and `POST
  /conversation-reviews/{id}/accept|discard` (`If-Match`), for members
  with `crm_app.conversation:reply` (no new permission); accepting adds the
  email to its conversation once; both are audited with ids and the reason
  code. The Inbox shows a "Needs review" panel to those members.
- **Gap and open decision:** SaaS-OS v0.6.0's egress client sends only
  POST; Resend's receiving API (`GET /emails/receiving/{id}`) needs GET.
  `crm_app.inbound.configured_client()` therefore returns none, and
  received emails wait as `received` until one is approved. Options for
  the owner: (a) a SaaS-OS release whose egress client supports GET (an
  upstream request, then a pin move); (b) approve a product adapter on
  SaaS-OS's `saas_os.infra.outbound_http` client (not yet on this
  product's import surface); (c) another approved HTTP client.
- **Retention:** unmatched and failed rows keep ids, codes and a domain;
  a retention period for them is to be set with the production activation.
- **Verified:** `tests/integration/test_inbound_email.py`,
  `tests/unit/test_inbound_rules.py`, `frontend/src/records/inbox.test.tsx`.

## P6-S — Email streams, sender identities and retry timing (2026-11-01)

- **Status:** Implemented under the owner's "Final Email Architecture and
  Resend Implementation Mission" (2026-11-01): "Sending-domain
  architecture: Separate subdomains ... notify.<PARENT_DOMAIN> —
  transactional messages; mail.<PARENT_DOMAIN> — one-to-one CRM
  conversations; campaigns.<PARENT_DOMAIN> — marketing campaigns;
  inbound.<PARENT_DOMAIN> — inbound email receiving ... Keep
  transactional, conversation and campaign sending streams logically
  isolated". Production sending and inbound are not authorized.
- **Supersedes** the open items of P6-E (sending domain, domain model,
  sender policy, inbound email): decided as above, except the domain
  itself, which the owner has not supplied.
- **Decisions:**
  1. Three streams (`crm_app.domains.email_streams`); every email purpose
     maps to exactly one. Senders are bare addresses on the stream's
     subdomain of `EMAIL_PARENT_DOMAIN` (SaaS-OS v0.6.0 refuses display
     names), with configurable local parts; without a parent domain only
     transactional mail may use `EMAIL_DEFAULT_SENDER`.
  2. Switches: `EMAIL_SENDING_ENABLED` plus
     `EMAIL_CONVERSATION_SENDING_ENABLED` and
     `EMAIL_CAMPAIGN_SENDING_ENABLED`; `EMAIL_INBOUND_ENABLED` for
     receiving. All off by default; each is refused in production at
     start-up, and the send path refuses production on its own.
  3. Rate limits per stream, per workspace and globally (Redis, one-minute
     windows, configurable). A limit reached or a limiter outage makes the
     email wait; nothing is sent past a limit.
  4. Retry timing: `email_message.next_attempt_at` (migration
     `0024_email_streams`), exponential backoff from 30 s to one hour with
     up to 25 % jitter, never sooner than the provider's `Retry-After`.
     Early jobs only record the wait; the sweeper enqueues when due.
  5. Provider events `email.failed` and `email.suppressed` after
     acceptance set the new final status `rejected`; `failed` keeps its
     meaning (never accepted).
- **Gaps recorded** (`EMAIL-ARCHITECTURE.md` §1): no display names, no
  custom headers (so no `List-Unsubscribe`, no `In-Reply-To`), no
  attachments, no Domains or inbound API in SaaS-OS v0.6.0. The pin does
  not change; the product builds its own adapters over SaaS-OS's public
  egress client where approved (inbound, domains).
- **Verified:** `tests/unit/test_email_streams.py`,
  `tests/unit/test_settings.py` (stream switches, senders, limits,
  validation, production refusals), `tests/unit/test_email_rules.py`
  (rejections, backoff), `tests/integration/test_emails.py` (backoff
  wait, `Retry-After`, per-workspace rate limit, conversation stream
  switch and sender, production lock, provider rejection).

## P2-G7 — Upgrading existing workspaces' roles (2026-11-01, under M1)

- **Status:** Implemented under the owner's instruction of 2026-11-01
  ("Existing workspace permissions: investigate why existing workspaces do
  not automatically receive conversation permissions. Design and implement
  a safe, idempotent migration or permission-provisioning mechanism.
  Preserve existing custom permissions ... Do not silently grant excessive
  privileges").
- **Why it happened:** a role template (`crm_app.roles.ROLE_TEMPLATES`) is
  applied once, by `crm_app.provision` while no member holds authority.
  SaaS-OS `grant_permission` lets a member grant only what they already
  hold (anti-amplification), so no Owner can grant a permission introduced
  later, and SaaS-OS v0.6.0 documents no upgrade operation (saas-os #88,
  still open). Every slice that added a permission (import, booking
  pages, suppressions, automations, conversations, …) left older
  workspaces without it.
- **Mechanism:** the operator command `python -m crm_app.role_upgrade`
  (`--workspace <id>` repeatable, or `--all`). It reports by default and
  changes only with `--apply`. Per workspace it compares the four product
  roles, found by exact name, with their templates and grants only what is
  missing: never a revoke, never a new or renamed role, never a membership
  change, never a permission outside the role's own template. Grants
  outside the template are kept and counted in the report.
- **Safeguards:** administrative and safeguarded permissions (the matrix's
  `ADMINISTRATIVE` kind or a named safeguard: import, export, audit,
  owner, security, pipeline, form, booking-page, suppression and
  automation management, membership and invitation control) are held back
  and listed unless `--include-administrative` is given. A workspace that
  is not active, or lacks one of the four product roles, is skipped.
  `ENVIRONMENT=production` needs `--confirm-production`. Each grant is
  SaaS-OS's own audited `role_permission.grant`, one transaction each; a
  duplicate is skipped, so an interrupted or repeated run is safe.
- **Caller:** `SystemCaller(PROVISIONING)`, the only caller
  `grant_permission` accepts for a permission no member holds. SaaS-OS
  documents that caller for "a tenant's initial authority structure ... a
  consumer's own provisioning/seed code"; bringing a workspace up to the
  approved template extends that use, and is recorded here as the
  product's interpretation until saas-os #88 provides a sanctioned
  operation. No SaaS-OS code or pin changes.
- **New workspaces:** unchanged; `crm_app.provision` still applies the
  whole template, and the command reports nothing missing for them.
- **Running it on a real workspace** is an operator action like
  provisioning: it needs the owner's authorization for that environment.
  It was run only against disposable test workspaces.

## P6-C1 — Inbox search and paging (2026-11-01, under M1)

- **Status:** Implemented under the owner's instruction of 2026-11-01
  ("Conversation search: search message content and relevant conversation
  metadata ... Handle pagination, indexing and query limits").
- **What is searched:** a thread's subject and the text of every message in
  it (inbound, outbound and internal notes: every member who can read the
  thread already sees its notes), plus the contact's first name, last name
  and email. A thread matches when its subject or one of its messages
  contains every word of the search as the start of a word (case-insensitive,
  any order), or when the contact's name or email starts with the whole
  search. The status filter still applies; a new `all` status searches open
  and closed threads together.
- **Input:** at most 100 characters, no NUL. Words are runs of letters and
  digits (`crm_app.domains.conversations.search_terms`), at most 8 of at
  most 64 characters; everything else separates words. So `%`, `_`, quotes,
  backslashes and full-text operators are never interpreted: a search with
  no letters or digits matches only a contact whose name or email literally
  starts with it.
- **Index:** PostgreSQL built-in full-text search, `simple` configuration
  (no stemming, no stop words, no extension). Migration
  `0023_conversation_search` adds a stored generated `search_vector` to
  `conversation` and `conversation_message`, each with a GIN index, and the
  operator `crm_app.@@` (`tsvector @@ varchar`): product code reaches SQL
  only through `saas_os.infra.db`, which binds text as `varchar` and exposes
  no function constructor or cast. The operator's SQL function is inlined
  by PostgreSQL into `vector @@ to_tsquery('simple', terms)`; `EXPLAIN`
  shows a bitmap index scan on the GIN index.
- **Paging:** the list is keyset-paged, latest message first, with a cursor
  bound to the filters (`limit` 1 to 100, default 50). A cursor issued for
  other filters, or a damaged one, is refused with 400 `invalid_cursor`.
- **Isolation:** every subquery names the workspace and runs under its
  Row-Level Security; members of other workspaces get 404, as before.
- **Not built:** relevance ranking (results stay in time order); accent
  folding (`cafe` does not find `café`); searching attachments, which do
  not exist yet.

## P9-0 — AI: what SaaS-OS provides and the decisions it waits for (2026-11-01)

- **Status:** Analysis recorded under M1; implementation is blocked on the
  owner decisions below. The owner's mission of 2026-10-31 makes Phase 9 the
  fourth priority with "do not activate paid external services or incur
  material external costs without authorization" and "provider-independent
  architecture where practical". Work continues with 6.1 conversations.
- **What SaaS-OS v0.6.0 provides (verified in the pinned source,
  CONSUMER-GUIDE section 12a, ADR-0054 and ADR-0055):** governed,
  non-streaming inference through `saas_os.inference.run_inference` only:
  a product registers a `UseCase` once (a ceiling, authorising nothing),
  then calls with a user or service-account caller, an operator-configured
  model alias and a classification on every content part (`none`,
  `tenant_data`, `sensitive`). Every refusal is a typed `InferenceError`
  without content; each attempt is recorded before it is sent; usage and a
  cost estimate come back on the result; per-tenant and installation-wide
  concurrency limits; an optional soft monthly `ai.tokens` quota. No
  embeddings or retrieval API is in the public surface, so knowledge
  retrieval (9.3) would be product-side over plain text.
- **What must be true before any request is sent, and whose decision it
  is:**
  1. **Provider and account (owner):** which provider (OpenAI-compatible
     endpoints are what SaaS-OS's adapters speak), the account and its
     cost; the credential is provisioned as a secret and listed in
     `AI_PROVIDER_CREDENTIALS`.
  2. **Operator setup (platform operator):** provider, model, alias and
     the installation's destination policy per classification
     (`saas-os-operator ai-*`), qualified per
     `AI-PROVIDER-QUALIFICATION.md` section 3.
  3. **Plans (owner):** which plans grant the `ai.inference` entitlement and
     what monthly `ai.tokens` limit; whether `AI_INFERENCE_TOKEN_QUOTA_REQUIRED`
     is on.
  4. **Data policy (owner):** which CRM data may be sent (contact fields,
     notes, activity, deal values) and at which classification; whether
     `sensitive` is ever allowed; residency and retention preferences.
  5. **Tenant controls (product, after 1-4):** enabling a workspace's AI
     policy and granting use cases needs `ai.policy:manage`; whether the
     product shows those controls or the operator sets them.
- **Planned first slice once decided (9A):** one measurable use case,
  "contact brief": a member asks for a summary of a contact and suggested
  next steps from the contact's fields, notes and open tasks
  (`tenant_data`); suggestions are shown, never acted on, and a member may
  turn one into a task. No auto-send (K5). Tests run against SaaS-OS's
  fake provider; nothing is sent to a real provider before the decisions
  above.
- **Not decided here:** assistants with tools, knowledge ingestion and
  retrieval, conversation summaries (they wait for 6.1).

## P8-B — More automation triggers and actions (2026-11-02, under M1)

- **Status:** Decided and built under M1 (owner, 2026-11-01: "proceed" with
  the recommended order, automation triggers and actions third). Slice 8B.
- **Decisions:**
  1. **Triggers added:** a tag added to a contact (one tag, required); a
     form submitted (one form, or any); an appointment booked on a booking
     page (one page, or any); a deal moved into a stage (one stage,
     required; the deal's contact). They fire in the transaction of the
     event: setting a contact's tags, a form submission (its tag too), an
     online booking, a member's deal move. Not triggered: a deal created in
     a stage, deals moved by removing a stage, tags or deals changed by an
     import.
  2. **Once per contact:** every automation still runs at most once per
     contact, whatever the trigger (the unique run key of P8-A), so
     automations that start one another always stop. A second event for
     the same contact starts nothing; a concurrent one is absorbed by a
     savepoint and never fails the member's change.
  3. **Actions added:** remove a tag; set the lifecycle stage. Both are
     recorded like a member's change (history and audit, acting as the
     member who activated the automation). A tag added by an automation
     can start another automation (bounded by 2).
  4. **Checks:** the definition names its tag or stage; activation checks
     that the named tag, form, booking page or stage still exists.
     Migration `0032_automation_triggers` widens the trigger and action
     checks.
  5. **Still not built:** send email or SMS, notify team, AI actions
     (unchanged from P8-A 5), round-robin and business-hours waits.
- **Tests:** `tests/integration/test_automation_triggers.py`,
  `tests/unit/test_automation_rules.py`,
  `frontend/src/records/automations.test.tsx`.

## P8-A — Automation engine foundation (2026-11-01, under M1)

- **Status:** Decided under M1. The owner's mission of 2026-10-31 makes
  Phase 8 the third priority: triggers, conditions, actions, reliable
  background execution, idempotency, retries, failure handling,
  observability, tenant isolation, permissions, execution history and
  limits, "never execute an automation twice merely because a worker
  retries a job" and no arbitrary code or expression evaluation. Slice 8A
  (8A.1 engine and API; 8A.2 the screen). Phase 8 is outside the K5 MVP
  list; this mission is the owner's authorisation for it.
- **Design audit:** `ScreenAutomation.dc.html` shows one workflow: a
  trigger ("New lead created" with sources, "once" per contact), one
  condition and two branches (yes, no) of actions from a catalogue
  (assign owner, create task, send SMS, send email, wait, add tag, notify
  team, hand to an AI assistant), saved as a draft and switched on.
- **Decisions:**
  1. **Shape:** exactly that: one trigger, an optional condition, two
     branches of at most 10 actions. Definitions are JSON data checked by
     `crm_app.domains.automations`; nothing is evaluated as code or as an
     expression, and unknown fields are refused.
  2. **Trigger:** `contact_created`, optionally limited to sources
     (manual, form, booking, referral, other). It fires in the
     transaction that creates the contact (`records.insert_record`), at
     most once per automation and contact (a unique key).
  3. **Imports never trigger**, so a 10,000-row import cannot start
     10,000 runs. At most 20 automations per workspace.
  4. **Conditions:** source or lifecycle stage in or not in a list, email
     present or absent, holds or lacks one of listed tags; read when the
     run starts.
  5. **Actions in 8A:** add a tag, assign an owner, create a task (title,
     priority, due in N minutes, assignee: the contact's owner, nobody or
     a member), wait N minutes (at most 30 days). Not built: send email
     (needs the email decisions of P6-E and consent for marketing), SMS
     and AI (deferred by K5), notify team, round-robin assignment and
     business-hours waits.
  6. **Versions:** the editable draft is frozen as an immutable
     `automation_version` on activation; a running automation's
     definition cannot change (pause it first); runs keep the version
     they began with.
  7. **Execution:** job `crm_app_automation_run` advances a run under a
     row lock, one step per transaction, writing the step's effect and
     its `automation_step` row together, so a retried or parallel job
     finds the step done and never acts twice. A wait parks the run
     until its time in the global `automation_due`;
     `python -m crm_app.automation_maintenance` (every minute) enqueues
     due runs. A missing tag or departed member skips the step with a
     code; a deleted contact cancels the run; unexpected errors are
     counted and retried, failing the run after 5 tries.
  8. **Who:** new permissions `crm_app.automation:read` (every role) and
     `:manage` (Owner, Admin). Steps act as the member who activated the
     automation (SaaS-OS has no system caller), so their history and
     audit entries name that member; task audit entries carry
     `automation_id`. Gate G7 applies: workspaces created before this
     change do not hold the new permissions.
  9. **History:** `GET .../automations/{id}/runs` lists the latest 50
     runs with their steps, outcomes and error codes.
- **Tests:** `tests/unit/test_automation_rules.py`,
  `tests/integration/test_automations.py`.

## P6-E2 — Booking confirmation emails (2026-11-01, under M1)

- **Status:** Decided under M1 as the first consumer of P6-E. Slice 6E.2.
- **Decisions:**
  1. **When:** a booking on a published page queues one transactional
     email to the visitor, in the same transaction as the booking, when
     the page's `confirmation_email` is on (migration
     `0020_booking_confirmation`, default on; Calendar › Booking pages
     editor "Email a confirmation to the visitor"). A replay queues
     nothing more; the honeypot and refusals queue nothing. Nothing is
     handed to a provider while `EMAIL_SENDING_ENABLED` is off (P6-E 3).
  2. **Content:** subject "Booked: page name, day"; plain text with the
     visitor's first name, the page's name, the day and time in the
     workspace's time zone (named), and the kind and location. It acts as
     the host, as the booking does (P5-C 9), and links to the contact.
  3. **No private link in the email:** the visitor's link token is kept
     only as a hash (P5-C 6); putting the link in the email would store
     the token in the email's text. The email says to use the link shown
     when booking. **Open decision for the owner:** whether to email the
     link anyway (the stored copy would then need redacting once sent, or
     the token a separate, expiring email-only form).
  4. **Abuse:** a visitor can make the workspace email any address they
     type. The per-visitor and daily limits (13-H2), the per-contact cap
     (P5-C 6), the suppression list, and the absence of any link or
     visitor-supplied text other than the first name bound it.
  5. The suppression list shows provider-made entries as "Reported by the
     email provider".
- **Tests:** `tests/integration/test_booking_emails.py`,
  `tests/unit/test_booking_page_rules.py`,
  `frontend/src/records/bookingPages.test.tsx`, `consent.test.tsx`.

## P10-B — Reports as CSV (2026-11-02, under M1)

- **Status:** Decided and built under M1 (owner, 2026-11-01: "proceed" with
  the recommended order, report export fourth). Slice 10B.
- **Decisions:**
  1. Each report card has a "CSV" download of the same figures for the
     same period: `GET .../reports/<name>/export.csv` with the report's own
     read permission and period rules (P10-A).
  2. **Contents:** rows of `section, item, value, previous`: the period,
     each total with its comparison value, and each breakdown (sources,
     statuses, amounts per currency, members by id). Only counts, rates,
     amounts and member ids, never a record's contents, so no new
     permission or rate limit is needed (unlike record exports, P3-E1).
  3. Cells pass the spreadsheet-formula protection of P3-E1; UTF-8 with a
     byte-order mark; a fixed file name `report-<name>-<date>.csv`;
     `Cache-Control: no-store`.
  4. **Not in 10B:** member names in the file (ids only), scheduled or
     emailed reports, the team card's merged table.
- **Tests:** `tests/integration/test_reports.py`,
  `tests/unit/test_report_csv.py`, `frontend/src/records/reports.test.tsx`.

## P10-A — Reports over stored CRM data (2026-11-01, under M1)

- **Status:** Decided under M1. The owner's mission of 2026-10-31 makes
  "Phase 10 — Reports" the second priority: deals, tasks, date ranges,
  permissions, states and tests, and "do not invent metrics that cannot
  be derived reliably from stored data". Roadmap 10 asks that each metric
  be defined before it is shown. Slice 10A.
- **Design audit:** `ScreenReports.dc.html` shows a 7/30/90-day switch,
  KPI tiles with a comparison, leads by source with cost per lead, a
  conversion funnel, appointment utilisation with a no-show rate, and
  team performance with conversations, first reply, won and revenue; the
  agency view compares clients. Cost per lead, first reply,
  conversations, AI and reviews have no stored data; the funnel needs
  lead-to-deal attribution the data does not hold; the agency view waits
  for Phase 11.
- **Decisions:**
  1. **Period:** whole calendar days in the workspace's time zone, both
     ends included, at most 366 days, between the years 1900 and 2999.
     Each figure is compared with the same number of days immediately
     before. Presets: the last 7, 30 and 90 days ending today in the
     workspace's zone, and a custom period.
  2. **Definitions** (shown next to each figure):
     - *New contacts:* contacts created in the period, archived ones
       included, by source.
     - *Deals created:* by creation time. *Won* and *lost:* deals whose
       current outcome is won or lost and whose close time is in the
       period; a reopened deal counts as neither. *Win rate:* won out of
       won and lost, rounded; none when nothing closed. Values are summed
       per currency, exactly, never converted.
     - *Tasks created* and *completed* by their times; a completed task
       is *on time* when completed by its due time, *late* after it, or
       has no due time. *Overdue now:* open tasks past their due time at
       the moment of reading, whatever the period.
     - *Appointments:* those starting in the period, by status; *held*
       means not cancelled. *No-show rate:* no-shows out of appointments
       marked completed or no-show.
     - *Team:* deals won by owner, tasks completed by who completed them,
       appointments held by host.
     Deleted records are gone and not counted.
  3. **API:** `GET /v1/workspaces/{id}/reports/{contacts,deals,tasks,
     appointments}?start=&end=`, each guarded by the read permission of
     the records it counts (`crm_app.contact`, `.opportunity`, `.task`,
     `.appointment`), so no new permission and gate G7 does not apply;
     a card the member may not read fails alone. Read-only, no audit.
  4. **Bounded work:** SaaS-OS's public database surface has no `count`
     or `group by`, so rows are read and counted in Python: at most
     20,000 rows per read, with `capped: true` and a notice when that
     limit is reached, under a 5-second statement timeout (`503
     report_timeout`). Migration `0018_report_indexes` adds indexes on
     deals' creation and close times and tasks' creation time.
  5. **Screen:** Insights › Reports: the period switch and custom dates,
     five headline figures with their comparison, cards for contacts by
     source, deal outcomes, tasks, appointments and the team, each with
     its definition, loading, empty and error states.
  6. **Not built:** export (roadmap "export controls"; a later slice),
     the funnel, lead-source costs, conversation and review figures,
     charts over time, and the agency comparison.
- **Tests:** `tests/integration/test_reports.py` (a known dataset: the
  period's edges in Amsterdam, comparisons, per-currency values, every
  definition, another workspace, roles and outsiders, refused periods),
  `frontend/src/records/reports.test.tsx`.

## 13-H3 — Security review of the email, domain and website surface (2026-11-01, under M1)

- **Status:** Done. A read-only review of every public and webhook route
  added in Phases 6, 7 and 12 (Resend delivery and inbound webhooks,
  one-click unsubscribe, custom-domain lookup, cross-site form posting,
  sending domains and their events, sender selection) and migrations
  0024-0029. No critical or high findings. Fixed (migration
  `0030_domain_claims`):
  1. **Inbound mail without a DMARC pass (medium, dormant until a receiving
     client exists):** only an explicit DMARC `pass` may join a thread
     unreviewed; a missing, `none`, `softfail` or `temperror` verdict goes
     to review as `dmarc_unverified`. A forged sender who learned a
     routing address can no longer post into a thread.
  2. **Sending-domain squatting (medium):** a domain never verified holds
     its name for 7 days (`CLAIM_DAYS`); then the daily email maintenance
     releases the name, and the workspace's row becomes `expired` (it can
     be removed and registered again). A domain that was ever verified is
     never released. Settings shows the deadline. The provider-side domain
     of an expired claim, if one was created, is left for an operator
     (SaaS-OS has no DELETE, `saas-os-gaps.md` items 2-3).
  3. **Webhook timestamp (low):** the Svix timestamp must be 1-12 ASCII
     digits; Unicode digits or a huge number answered 500 before.
  4. **Domain events (low, defense in depth):** an event naming another
     domain is ignored, and one older than the newest applied
     (`sending_domain.event_at`) changes nothing.
  5. **Custom-domain lookup:** a suspended, deleted or closed workspace's
     domain resolves to nothing.
- **Recorded, not changed:** the unsubscribe route is POST only; a GET
  confirmation page and `List-Unsubscribe-Post` are required before
  campaign sending (already blocked, `saas-os-gaps.md` item 1). The
  per-form submission limit is keyed on public data, so one visitor can
  exhaust a form's bucket (accepted trade-off; per-address limits also
  apply). The webhook rate limit must be sized for Resend's bursts before
  production. Registering and verifying call Resend inside the workspace
  transaction, so a failed commit can leave an orphan domain at Resend
  (operational).
- **Checked and sound:** Svix verification (HMAC over id, timestamp and
  body, constant-time compare, 5-minute window both ways, 64 KiB cap,
  signature before parsing, fail closed without a secret); workspace
  routing only from global indexes keyed on provider ids or hashed tokens;
  production locks for every email switch; CORS reflects only a
  workspace's active websites, without credentials; unsubscribe tokens
  hashed, always 204; sender identities re-checked at send time; the only
  outbound host is the fixed Resend API.
- **Tests:** `tests/unit/test_email_rules.py`, `test_inbound_rules.py`,
  `test_sending_domain_rules.py`; `tests/integration/test_sending_domains.py`,
  `test_custom_domains.py`; `frontend/src/pages/sendingDomainSettings.test.tsx`.

## 13-H2 — Public booking limits and link expiry (2026-11-01, under M1)

- **Status:** Decided under M1. The owner's mission of 2026-10-31 puts
  "13-H1 — Public booking security" first: expiring visitor links,
  limits per visitor instead of one shared per page, abuse and resource
  limits, with tests for expiry, replay, brute force, concurrency and
  tenant boundaries. It supersedes P5-C 5 ("the booking also per page")
  and P5-C 7 ("it works while the booking exists"), and settles the
  items 13-H1 4 accepted for now.
- **Decisions:**
  1. **Link expiry:** a visitor's link works until 7 days after its
     appointment ends (the appointment's current end, so a host's
     rescheduling moves it). After that, view and cancel answer the same
     404 as an unknown token, and the visitor page says links stop
     working a week after the appointment. No migration: the expiry is
     derived from the appointment, and only the token's SHA-256 is kept
     (P5-C 6).
  2. **Per-visitor limits:** besides the general per-address limit on
     every public route, a booking counts against the visitor's own
     hourly budget for that page (`BOOKING_REQUESTS_PER_VISITOR_PER_HOUR`,
     default 10), and a link view or cancellation against the visitor's
     own hourly budget (`BOOKING_LOOKUPS_PER_VISITOR_PER_HOUR`, default
     30), which keeps guessing a 256-bit token slow even within the
     general limit. The page-wide budget, which one visitor could spend
     for everyone, is gone. A visitor is a client address, so these hold
     in production only with the F2 launch gate (13-H1 3).
  3. **Workspace capacity:** a workspace takes at most
     `BOOKINGS_PER_WORKSPACE_PER_24H` (default 200) online bookings in any
     rolling 24 hours; the next answers `429 booking_capacity` and stores
     nothing. Counted from stored bookings under a workspace lock, so
     refused requests never use it up and two visitors cannot both take
     the last place. It bounds the contacts and appointments a flood
     can create, including one that rotates email addresses past the
     per-contact cap (13-H1 4); a flood can therefore close a workspace's
     online booking for the rest of the day, a trade accepted over
     unbounded data.
  4. **Tokens** stay as they were: 256-bit `secrets.token_urlsafe(32)`,
     returned once, kept only as SHA-256, sent in request bodies, looked
     up within the workspace's row security.
  5. **Still accepted:** a limiter key is created for a well-formed but
     unknown page before the lookup (bounded by the per-address limit).
     No CAPTCHA.
  6. **Settings** are validated at start-up like the signup limits
     (whole numbers of at least 1) and listed in `.env.example`.
- **Tests:** `tests/integration/test_booking_limits.py` (per-visitor
  budgets, capacity and a race for the last place, token guessing,
  expiry, two cancellations at once, another workspace),
  `tests/unit/test_settings.py`, `tests/unit/test_booking_page_rules.py`,
  `frontend/src/records/bookingPages.test.tsx`.

## 13-A1 — Dated exceptions in the frontend dependency audit (2026-10-31)

- **Status:** Approved by the owner, 2026-10-31 ("Narrow exception
  (Recommended)"), after CI run 41244189716 failed only at `npm audit
  --audit-level=low`.
- **Cause:** advisory GHSA-g3hv-75wg-m249 (minimatch below 11.0.1,
  moderate, denial of service through crafted glob patterns), published
  2026-10-30. Only development tooling depends on minimatch: eslint 9 and
  eslint-plugin-jsx-a11y 6.10.2 (3.x), openapi-typescript through
  `@redocly/openapi-core` (5.x) and typescript-eslint (10.x). No patched
  3.x, 5.x or 10.x exists. Forcing 11.x breaks eslint-plugin-jsx-a11y,
  which calls the old default export, and redocly, which calls the module
  as a function. The production bundle contains none of these packages,
  and the glob patterns they match come from this repository's own
  configuration.
- **Decision:**
  1. typescript-eslint's copy is moved to minimatch 11.0.3 with an npm
     override (`frontend/package.json`); its API is unchanged and lint
     passes.
  2. The CI audit step runs `npm run audit` (`frontend/scripts/audit.mjs`)
     instead of `npm audit --audit-level=low`. It fails on every advisory
     of every severity unless the advisory is listed in
     `frontend/audit-exceptions.json`, and only until that entry's expiry
     date. It also fails when a listed advisory is no longer reported, so
     the list cannot go stale, and the production tree
     (`npm audit --omit=dev`) gets no exceptions at all.
  3. The only exception is GHSA-g3hv-75wg-m249, until 2026-11-30. Before
     then, move to fixed releases of eslint, eslint-plugin-jsx-a11y and
     openapi-typescript when they exist, or decide again.
- **Verified:** the gate passes with the exception, fails with it expired,
  and fails for an unlisted advisory and a stale entry.

## 13-A2 — Review of the minimatch audit exception (2026-11-01, under M1)

- **Status:** Reviewed under the owner's instruction of 2026-11-01
  ("Dependency audit: review the exception expiring on 2026-11-30.
  Remediate safely where possible and document any residual risk").
- **What was checked (npm registry, 2026-11-01):** GHSA-g3hv-75wg-m249
  still covers every minimatch below 11.0.1; no fixed 3.x, 5.x or 10.x
  exists.
  - `eslint-plugin-jsx-a11y` 6.10.2 is still its latest release (2024) and
    calls minimatch's default export, which 11.x removed; its peer range
    ends at eslint 9.
  - eslint 10.14.0 exists but depends on minimatch ^10.2.6, still in the
    advisory's range, and the plugin above does not support it.
  - `openapi-typescript` 7.13.0 (latest) needs `@redocly/openapi-core`
    ^1.34 (latest 1.34.22, minimatch 5.1.9). Redocly 2.72.1 no longer
    uses minimatch, but forcing it under openapi-typescript fails
    (`ERR_PACKAGE_PATH_NOT_EXPORTED`): tried and reverted.
- **Remediated:** nothing further could be fixed without breaking tooling;
  typescript-eslint stays on minimatch 11.0.3 (13-A1).
- **Residual risk (unchanged, low):** a denial of service through crafted
  glob patterns, in development tools only (lint and API type
  generation). The production bundle contains none of these packages and
  the production audit (`npm audit --omit=dev`) has no exception. The
  patterns these tools match come from this repository's own
  configuration; an attacker would need to commit a hostile pattern,
  which review and branch protection already gate, and the worst outcome
  is a slow or hung lint run.
- **Decision:** the exception is renewed, visibly, until 2026-12-31
  (`frontend/audit-exceptions.json`, decision 13-A2). The gate still fails
  the day it expires, for any new advisory and for a stale entry. Before
  2026-12-31: check for a jsx-a11y release that supports minimatch 11 or
  eslint 10, an openapi-typescript release on redocly 2, or replace
  either tool; otherwise the owner decides again.

## M-P1 — Member display names (2026-11-03)

- **Status:** Built under the standing autonomous mandate (M1, unfinished
  features first), after the owner set voice aside on 2026-11-03 ("put the
  ai voice for now asside we proceed further"). It implements the approved
  Phase 2 plan, `PHASE2-PLAN.md` §6.5 (gate G1 passed long ago).
- **Problem:** SaaS-OS's `core.users` stores no name, so every owner,
  assignee, host, author and team row showed "Member <id>".
- **Decision:**
  1. Table `crm_app.member_profile` (migration `0035_member_profiles`):
     tenant-owned, forced RLS, one display name per member and workspace,
     1–80 visible characters (no control, format or separator characters;
     inner spaces collapsed). There is no foreign key to
     `core.tenant_memberships`, because the product purge runs before the
     platform's. The table is in `PURGE_TABLES`.
  2. A member sets or clears **only their own** name:
     `GET`/`PUT /v1/workspaces/{ws}/me/profile`. The route needs
     `crm_app.member_profile:read`, which every role holds and which proves
     an active membership; it reads and writes only the caller's row.
     Nobody sets another member's name.
  3. `Member` responses (`GET /members` and the membership changes) carry
     `display_name`, so names follow the member list's existing visibility
     rules; no new visibility is added.
  4. Audited as `crm_app.member_profile.updated` or `.cleared`, without the
     name in the metadata. The name is personal data: kept with the
     workspace and removed by the purge.
  5. Frontend:
     - a member-names context fed by the member list's first page (50);
     - `ownerLabel` and the owner dots show the name when there is one;
     - "You" stays "You";
     - a member without a name still shows by ID;
     - My profile's display-name field now saves (the time zone still
       cannot, and says so).
- **Not done:** names beyond the first 50 members fall back to the ID; time
  zone and other profile preferences; an erasure path for a former member's
  name inside a workspace (it goes with the workspace purge).
- **Tests:** `tests/integration/test_member_profiles.py`;
  `tests/unit/test_routes.py` (the own-profile write is the one named
  exception to "changes are Owner and Admin only"); `AppFrame.test.tsx`
  (profile saves); `reports.test.tsx` (a member shown by name).
## N-1 — In-app notifications in a product-owned inbox (2026-11-06)

- **Status:** Owner decision, 2026-11-06: "Product inbox (Recommended)",
  chosen over using SaaS-OS's channel as it is or waiting for an upstream
  change.
- **Problem:** the header bell showed only an empty panel, and nothing
  told a member when a task, conversation or appointment was put on them or
  a visitor booked them. SaaS-OS v0.8.0's `saas_os.core.notifications`
  `in_app` channel was checked first. It records a delivery outcome, not an
  inbox:
  - rows carry only subject and body text: no type and no link to a record;
  - there is no read state (its own docstring leaves that to the product);
  - `list_notifications()` returns all of a user's rows, unordered and
    unpaged;
  - no row records the outbox event that made it, so the product cannot
    attach its own data to one.
- **Decision:**
  1. Table `crm_app.member_notification` (migration
     `0037_member_notifications`): tenant-owned, forced RLS, in
     `PURGE_TABLES`. Each row holds the recipient, a `kind`, the record by
     type and ID, the acting member (none for a visitor or an automation),
     `created_at` and `read_at`. A CHECK ties each kind to its record type
     and forbids a member being the actor of their own notification. It has
     no foreign key to the record, so a notification outlives a deleted
     record, and none to `core.tenant_memberships` (same reason as M-P1).
  2. Five kinds, each written by `crm_app.notifications.notify()` in the
     same transaction as the change it reports: a rollback notifies nobody,
     and an idempotent replay (which skips the business function) notifies
     nobody twice.
     - `task_assigned`: a task created with, or changed to, an assignee. An
       automation's task step counts too, with no actor.
     - `conversation_assigned`
     - `appointment_assigned`: a host set or changed on an appointment that
       is not cancelled.
     - `booking_received` and `booking_cancelled`: a visitor's booking or
       cancellation, sent to the host.
     Nobody is notified about their own action.
  3. Routes: `GET /v1/workspaces/{ws}/me/notifications` (newest first,
     cursor-paged, at most 50 a page, `unread` filter, unread count capped at
     99), `POST …/me/notifications/{id}/read` and `POST …/read-all`. All
     need `crm_app.workspace:read`, which every role holds, so no new
     permission and no grant migration is needed. The recipient is always
     the caller: no route takes a member ID, and another member's or another
     workspace's notification is 404. Marking read is routine and not
     audited.
  4. No record content is copied. The list reads each record's current
     name, only when the reader holds that record type's read permission. A
     deleted record shows as "No longer available".
  5. Retention: rows older than 90 days are deleted for a recipient whenever
     a new one is written for them. This needs no scheduled job, but an
     inactive recipient keeps their last rows until the workspace purge.
  6. Frontend: the bell shows the design's dot only while something is
     unread, and its label says how many. The panel lists the notifications
     with loading, error, empty and "load more" states and a "Mark all read"
     button. Opening one marks it read and goes to the task (the Tasks page
     now opens `?record=`), the conversation or the appointment. The list
     refreshes every 60 seconds and when the window regains focus; there is
     no push channel.
  7. SaaS-OS stays the path for notification email once sending is
     authorised. The gaps above are recorded in `saas-os-gaps.md` (gap 15,
     filed as aelboum/saas-os#230) so the
     inbox can move to SaaS-OS if it gains them.
- **Not done:** overdue-task and upcoming-appointment reminders (they need a
  scheduled scan); notifications for form submissions, deal or contact
  owner changes and automation failures; per-member notification
  preferences (Settings › Notifications stays "soon"); email or push
  delivery; real-time updates.
- **Tests:** `tests/integration/test_notifications.py`, with booking
  notifications in `test_booking_page_routes.py`;
  `tests/unit/test_routes.py` (marking one's own notifications read is the
  second named exception to "changes are Owner and Admin only");
  `AppFrame.test.tsx` (dot, list, open, mark all, error);
  `tasks.test.tsx` (a linked task opens; a deleted one says so).

## M-P2 — Times use the device's time zone (2026-11-04)

- **Status:** Owner decision, 2026-11-04 ("Device zone, honest field").
- **Problem:** My profile showed a disabled time-zone picker. Every screen
  formats times, and the calendar, task and appointment dialogs, booking
  page and dashboard compute days and times, in the device's zone (about
  50 places). A stored zone applied only to how times are displayed would
  make the edit dialogs disagree with the lists and risk wrong appointment
  times.
- **Decision:**
  1. No stored member time zone. My profile states the device's zone
     read-only and says that changing the device's zone changes it.
  2. When the workspace's business time zone (business hours, booking
     pages, reports) differs, My profile says so.
- **Not done:** a member time-zone preference applied everywhere. It needs
  zone-aware date handling across those screens; revisit if members work
  across zones from wrongly set devices.
- **Tests:** `frontend/src/shell/AppFrame.test.tsx` (My profile).

## P15-V2 — Voice implementation-readiness specification (2026-11-03)

- **Status:** Prepared under the owner's instruction of 2026-11-03 to
  continue voice preparation autonomously without building it.
  Documentation only. K5 unchanged, recording off by default, no provider
  activated, nothing bought.
- **Records:**
  - `VOICE-SPEC.md`: product requirements with ids and acceptance; an
    architecture with SaaS-OS capabilities marked Exists or Proposed; the
    data model; the call state machine; provider-neutral interfaces;
    streaming and interruption; tools and context limits; idempotency;
    failure recovery; metering; security and permissions.
  - `VOICE-UX-SPEC.md`: screens S1–S8 on the existing design system and the
    design's Assistants screen.
  - `VOICE-SLICES.md`: V0–V6 with scope, dependencies, database, API,
    screens, security, tests, acceptance, rollback and approval gates, plus
    test specifications for V1.
  - Second provider research pass in `VOICE-PROVIDER-COMPARISON.md` §5b.
  - Further legal requirements in `VOICE-LEGAL-REVIEW.md` §2a.
- **Findings from the code that V1 must address:**
  - contact phones are stored as entered, with no E.164 normalisation;
  - `consent_record.channel` allows only `email`;
  - `suppression` is keyed by email only;
  - `conversation.channel` allows only `email` and `other`;
  - the product does not yet use SaaS-OS feature flags.
- **Bake-off shortlist (no selection):**
  1. Deepgram Voice Agent with Twilio IE1 (`mip_opt_out` and the EU endpoint
     mandatory);
  2. Vapi;
  3. Twilio ConversationRelay as the do-it-yourself baseline.
  - Alternates: ElevenLabs and Telnyx.
- **Upstream:** aelboum/saas-os#205 and #206 open, no maintainer response
  as of 2026-11-03.
- **Not authorised:** any slice V1–V6; each needs its own approval gate
  (`VOICE-SLICES.md`).
## S-UP1 — Two SaaS-OS proposals submitted upstream (2026-11-03)

- **Status:** Authorised by the owner on 2026-11-03 for submission and
  discussion only, and done the same day:
  - aelboum/saas-os#205, GET (and optionally DELETE) on
    `StrictEgressClient`, needed for inbound email content
    (`SAAS-OS-GET-PROPOSAL.md`);
  - aelboum/saas-os#206, enabling `stream_inference` with a voice
    first-event deadline, plus optional governed audio and media ingress,
    needed for the future voice workstream 15V
    (`SAAS-OS-REALTIME-PROPOSAL.md`).
- Kept separate so they can be reviewed and implemented independently.
  Each states the business rationale, security and compatibility
  requirements, the tests expected upstream and release criteria.
- **Not authorised:** implementing either feature in SaaS-OS, merging
  upstream changes, creating a SaaS-OS release, changing LeadStack's pin,
  or building or enabling voice.
- **Other decisions of the same date:** no paid vendor sandbox accounts;
  legal counsel not commissioned yet; a cost estimate for both
  (`VOICE-ACTIVITY-COSTS.md`); provider research continues from public
  documentation; voice recording stays disabled by default; K5 and the MVP
  scope unchanged.
## P15-V — AI voice agents are an intended capability, with workstream 15V (2026-11-03)

- **Status:** **Approved by the owner on 2026-11-03** (direction and
  workstream 15V), with these eight decisions, quoted in substance:
  1. **Voice direction: approved.** Phase 15V stays in the roadmap as a
     planned post-launch capability. The question whether voice belongs in
     the long-term product is not reopened.
  2. **K5: unchanged.** Voice stays outside the MVP; no silent expansion.
  3. **Providers: deferred.** A comparison is prepared
     (`VOICE-PROVIDER-COMPARISON.md`); no accounts, no purchases.
  4. **Legal review: required** before production implementation or
     activation. DPIA requirements and questions for counsel prepared
     (`VOICE-LEGAL-REVIEW.md`); the legal summary in the brief is not a
     final legal determination.
  5. **Pricing and plan limits:** a cost model only (`VOICE-COST-MODEL.md`);
     no commercial prices.
  6. **SaaS-OS:** a technical proposal for streaming and real-time
     interaction (`SAAS-OS-REALTIME-PROPOSAL.md`); no change to SaaS-OS, its
     release or LeadStack's pin.
  7. **Recording and retention:** no recording is the design default until
     an approved recording policy and legal review exist; transcript and
     metadata retention documented separately (`VOICE-LEGAL-REVIEW.md` §3).
  8. **Outbound consent:** explicit, demonstrable consent for AI outbound
     calls is the initial product policy; no outbound calling until the
     legal interpretation and operational controls are reviewed.
- **Product requirements (owner, 2026-11-03):** inbound and outbound agents
  integrate with contacts, companies, deals, appointments, conversations,
  automations, knowledge and reporting, with human handoff, selectable
  voices, agent configuration, call summaries, transcripts where permitted,
  outcome classification, usage metering, tenant isolation, campaign
  approval, opt-outs, rate limits, budget limits and emergency stop
  controls. Threat model and diagrams: `VOICE-THREAT-MODEL.md`.
- **Still not authorised:** building the voice platform, activating
  providers, creating phone numbers, purchasing services, changing K5,
  changing SaaS-OS, or enabling production calls.
- **Correction:** on 2026-11-03 the owner was told that AI call agents were
  not a planned part of the roadmap. That was an incorrect interpretation:
  the product vision combines the reference LeadStack template and
  GoHighLevel, and both include inbound and outbound AI voice agents.
  `PHASE0-DISCOVERY.md` §2 had omitted the template's voice module; it is
  corrected there.
- **Direction:** inbound and outbound AI calling, with agent configuration,
  selectable voices, business knowledge, call transfers, transcripts,
  summaries, call outcomes, usage limits and human review, integrated with
  contacts and companies, deals, appointments, conversations, automations,
  knowledge and reporting. Roadmap workstream 15V, slices V0 to V6.
- **Architecture boundary:** built on SaaS-OS public contracts, PostgreSQL
  with RLS and ZITADEL; no Firebase; the references' features inform the
  product, their architecture is not copied (K1). The recommended first
  path is a hosted voice platform behind a product adapter, with every LLM
  turn through `saas_os.inference` (option A in the brief).
- **Known SaaS-OS gaps (v0.6.0):** no streaming inference
  (`streaming_not_enabled`), no audio capability, egress POST only, no
  WebSocket egress, no object storage in the public surface. Any change is
  requested upstream; the pin is not moved here.
- **Boundaries kept:** no telephony or AI service purchased, no provider
  account created, no phone number configured, no call enabled, nothing
  implemented, SaaS-OS and its pin unchanged.

## P7-V — Public submissions that match an existing contact are unverified (2026-11-02)

- **Status:** Approved by the owner on 2026-11-02 (brief 8): "Treat an email
  address submitted through a public form or booking as an unverified
  identity claim. Record the submission and booking, but do not
  automatically modify an existing contact's tags, marketing consent or
  automation state based only on an email match." Supersedes P7-A 6 (a
  matched contact gets the form's tag) and the matched-contact part of P7-B
  and P8-B.
- **Forms:** when the email matches an existing contact, the submission is
  still stored (outcome `matched`, the visitor's answers and consent box
  kept) and audited, but:
  - the form's tag is not added;
  - no consent record is written; if the visitor ticked the consent box, a
    confirmation email is queued to the contact's address instead;
  - no form or tag automation starts.
- **Bookings:** a booking for a matched contact is kept and attached to that
  contact (the host must see it), but no `appointment_booked` automation
  starts.
- **Confirmation links:** table `consent_confirmation` (migration 0034,
  tenant RLS). The link is `/app/c/<workspace>#<token>`; the token is in the
  fragment, so it never reaches a server log, and only its SHA-256 hash is
  stored. A link works for 7 days, confirms only in its own workspace, and
  is idempotent: a second confirmation answers the same and records
  nothing more. While a confirmation for the same contact and form is
  pending and less than a day old, a repeat submission queues no new email,
  so a stranger cannot flood the address. Confirming writes one consent record, `granted`, method
  `email_confirmation`, with the form's wording, and is audited. The page
  confirms only when the person presses the button, so a mail scanner that
  opens the link confirms nothing. The route
  `POST /v1/public/consent/{workspace_id}/confirm` answers 204 or 404 (an
  unknown, foreign and expired token look the same) and is rate limited per
  client address.
- **Email:** the confirmation is purpose `consent_confirmation`, on the
  transactional stream, and is never sent after its link expires. Sending
  stays off (production email not authorised), so today the email is only
  queued.
- **Unchanged:** a submission or booking that creates a new contact behaves
  as before (tag, `web_form` consent, automations); there is no
  cross-workspace lookup.
- **Tests:** `tests/integration/test_consent_confirmations.py`,
  `frontend/src/pages/consentConfirm.test.tsx`.
## 13-O1 — One operations page, and the improvements that need no decision (2026-11-02)

- **Status:** Done under the owner's instruction of 2026-11-02 ("Identify
  any further security, reliability, performance or accessibility
  improvements that do not require new product decisions").
- **Done:** `docs/project/OPERATIONS.md` lists every process, deployment
  step, scheduled command (with its cadence and what stops if it stops),
  operator command and the health signals to watch. Until now, the
  schedules were only in the modules' own docstrings.
- **Identified, not yet done (no product decision needed):**
  1. **Reliability — done:** `python -m crm_app.health_check` counts email
     retries and automation runs overdue by more than 15 minutes and import
     clean-ups overdue by more than 3 hours, read-only, counts only; exits
     1 when any is overdue (`tests/integration/test_health_check.py`).
  2. **Performance:** a seeded local load test (about 50,000 contacts) of
     the contact list and search, the reports and the reminder run, to set
     a baseline before production. Planned, not run:
     `LOAD-TEST-PLAN.md` (2026-11-02).
  3. **Accessibility:** the human screen-reader pass
     (`SCREEN-READER-CHECKLIST.md`).
  4. **Security:** size the email webhook's rate limit from Resend's real
     delivery bursts when sending is activated (brief 6); review again the
     per-form submission budget then.

## 13-D1 — Decision briefs, the decision register and the screen-reader checklist (2026-11-02)

- **Status:** Prepared under the owner's instruction of 2026-11-02
  (decision briefs with "the exact decision, available alternatives,
  recommendation, cost implications, security implications and
  reversibility"; a screen-reader checklist; a review of public
  submissions that match an existing contact).
- **Records:** `docs/project/DECISION-BRIEFS.md` (eight briefs and the
  prioritised register), `docs/project/SCREEN-READER-CHECKLIST.md`.
- **Finding:** a public form or booking that matches an existing contact by
  the email typed can tag the contact, record marketing consent for them
  and start their public-trigger automations, all without proof that the
  visitor owns the address. It is bounded today: campaigns cannot send and
  need double opt-in (13-H1 2), and each automation runs once per contact.
  Recommended: treat matched submissions as unverified claims (brief 8);
  it changes accepted behaviour, so it awaits the owner.

## 12D.2 — Custom-domain DNS lookups and the edge's TLS check, built and off (2026-11-02, under the hardening mandate)

- **Status:** Built under the owner's instruction of 2026-11-02 ("Custom
  domains: prepare DNS ownership verification and edge TLS architecture. Do
  not perform DNS changes or issue production certificates."). Nothing
  external is contacted unless the owner sets the resolver; no DNS record is
  changed and no certificate is issued.
- **Decisions:**
  1. TXT ownership lookups use DNS-over-HTTPS (RFC 8484 POST) through
     SaaS-OS's egress client, which already supports POST: no new dependency
     and no pin move. `crm_app.domains.dns_wire` builds the query and reads
     the reply defensively; `custom_domains.DohTxtResolver` sends it.
  2. `configured_resolver()` uses it only when `CUSTOM_DOMAIN_DOH_URL` is an
     https URL; otherwise there is no resolver, as before.
  3. `GET /v1/public/domains/allowed?domain=<host>` is the edge's on-demand
     TLS check: 204 only for a verified host of an open workspace, 404
     otherwise, limited per client address, never naming the workspace.
  4. The edge configuration (Caddy on-demand TLS) and certificate storage
     stay owner decisions (`BLOCKED-WORK-PREPARATION.md` §4).
- **Tests:** `tests/unit/test_dns_txt.py` (query, answer parsing, refusals,
  the resolver against a test egress client, off unless configured),
  `tests/integration/test_custom_domains.py` (the TLS check).

## 13-P1 — Preparation of the blocked work (2026-11-02, under the hardening mandate)

- **Status:** Prepared, nothing built or switched on, under the owner's
  instruction of 2026-11-02 ("Prepare blocked roadmap work … Do not connect
  paid providers or send CRM data externally … Do not activate billing or
  change production Stripe configuration … Do not change the SaaS-OS pin …
  Do not perform DNS changes or issue production certificates … Do not
  activate tracking before the consent decision is approved.").
- **Record:** `docs/project/BLOCKED-WORK-PREPARATION.md`, with what
  SaaS-OS v0.6.0 provides (read from the installed package), the proposed
  architecture, and the owner's decisions for each item:
  1. AI (Phase 9): a provider-neutral `crm_app.ai` on SaaS-OS's governed
     inference, a per-use-case data allowlist, an off switch, an
     entitlement, a token quota, and an audit without prompt text.
  2. Agency, white label and billing (Phase 11): options A, B or C;
     recommended B (an agency parent tenant with client child tenants on
     SaaS-OS's hierarchy and hierarchy-aware billing, with access only by
     explicit membership), billing wholly in SaaS-OS.
  3. Inbound email: SaaS-OS adds `get` to `StrictEgressClient`, the
     smallest safe change; no product-owned HTTP client.
  4. Custom domains: a DNS-over-HTTPS TXT resolver through the existing
     egress POST (no pin move) and Caddy on-demand TLS gated by an `ask`
     endpoint for verified hosts.
  5. Website tracking: off by default, nothing without consent, consent in
     the existing consent records, GPC and DNT respected, short retention.
  6. Role upgrades: 13-R1.

## 13-R1 — An auditable, bound role upgrade (2026-11-02, under the hardening mandate)

- **Status:** Prepared under the owner's instruction of 2026-11-02 ("Prepare
  a safe, auditable role_upgrade migration and dry-run mechanism. Do not
  execute it against real workspaces or change customer permissions.").
  Not run against any real workspace.
- **Decisions:**
  1. The dry run prints a fingerprint of exactly what it would grant
     (workspaces, roles, permissions; a SHA-256 prefix of the canonical
     plan), and `--json` prints the whole report as data for the change
     record.
  2. `--apply --expect <fingerprint>` grants only if the current plan still
     has that fingerprint; anything that changed since the review refuses
     the run (exit 2, nothing granted).
  3. In production, `--apply` needs `--expect` as well as
     `--confirm-production`.
  4. The procedure, review and rollback are in
     `docs/project/ROLE-UPGRADE-RUNBOOK.md`.
- **Tests:** `tests/integration/test_role_upgrade.py` (fingerprint, JSON
  report, a wrong fingerprint refused and granting nothing, production
  needing `--expect`, the matching fingerprint applying).

## 13-H5 — Security review of reminders, automation triggers, templates, booking and the worker (2026-11-02, under the hardening mandate)

- **Status:** Done under the owner's instruction of 2026-11-02 (focused
  review of 5D, 8B, 7T, public booking pages, and background worker
  execution and retries: authorization, tenant isolation, RLS, input
  validation, concurrency, idempotency, rate limiting, secrets, audit
  logging and abuse). Read-only review of the code, then fixes. No critical
  or high findings; the booking controls of 13-H1 and 13-H2 still hold
  with the new automation hook inside the booking transaction.
- **Fixed:**
  1. **Late timely mail (medium):** booking confirmations and reminders
     queued while sending is off would all go out once it is switched on,
     even for past or cancelled appointments. Now, at send time, such mail
     older than a day fails `expired`, and a reminder whose appointment was
     cancelled, closed or has started fails `no_longer_due`
     (`emails.TIMELY_FOR`, `_no_longer_due`).
  2. **Reminder starvation (medium):** the per-run limit of 200 was applied
     before leaving out appointments already reminded, so more than 200 in
     the window could stop later ones being reminded. Already-reminded
     appointments are now left out in SQL before the limit.
  3. **One workspace stopping all email maintenance (medium):** any
     unexpected error in one workspace's reminders ended the maintenance
     run for every workspace. Each workspace is now isolated (logged by id
     and error type only), and the reminder step can never stop delivery.
  4. **Automations acting for a departed member (low-medium):** a run kept
     acting, and being recorded, in the name of the member who activated it
     after they left or were suspended. It is now cancelled `not_active`.
  5. **Failure count (low):** a run's failed tries now reset after every
     successful step, so unrelated transient errors over a long run do not
     fail it.
  6. **A stored definition that no longer parses (low):** it now matches
     nothing instead of failing the contact create, form submission or
     booking that raised the event.
  7. **Limits (low):** template creation takes the workspace's advisory
     lock, so concurrent creations cannot pass 100; a contact is not sent an
     automatic reminder within an hour of the previous one (an appointment
     rescheduled again and again).
- **Superseded by brief 8 of 13-D1:** the review below understated it. A
  matched submission can also record marketing consent for the contact, so
  the recommended fix (`DECISION-BRIEFS.md`, brief 8) awaits the owner.
- **Accepted and documented (low, by design):** a visitor who submits a
  public form or booking with an existing contact's email starts that
  contact's `form_submitted`, `appointment_booked` or form-tag automations
  (at most once per automation and contact, and still bounded by the
  booking limits). Owners should not build automations that demote or
  reassign a contact on these public triggers; a per-automation opt-in for
  matched contacts is a possible later refinement.
- **Checked and sound:** every query names the workspace inside its RLS
  session; global tables hold ids and times only; ids named in definitions
  are re-checked at activation and at run time; one run per automation and
  contact (unique key, savepoint) so no loops; no email action in
  automations; steps commit with their effect under a row lock; reminders
  are unique per appointment and start time; the reminder text excludes
  the note; template placeholders are a closed list replaced literally;
  booking limits fail closed, tokens are hashed and expire; claims use
  `SKIP LOCKED`, a `sending` state and capped attempts; suppression is
  checked at send time; production sending is locked twice.
- **Tests:** `tests/integration/test_reminders.py` (no repeat within the
  hour; late and no-longer-due mail never sent),
  `tests/integration/test_automation_triggers.py` (a departed activator's
  run is cancelled), and the existing suites.

## 13-H4 — Accessibility and responsive audit of the new screens (2026-11-02, under the hardening mandate)

- **Status:** Done under the owner's instruction of 2026-11-02 ("Audit all
  newly implemented screens. Check keyboard navigation, focus management,
  labels, contrast and screen-reader accessibility. Test desktop and phone
  widths, especially 390px. Fix layout defects and accessibility issues.
  Add regression tests where practical.").
- **How:** the built app ran locally against the test database with a
  throwaway workspace and session (the token stayed in a local file, never
  in logs, and was deleted afterwards). In Chrome at 390 × 844 (mobile,
  touch) and 1280 × 800: Home, Calendar and the appointment drawer,
  Automations and its editor, Campaigns with templates, Inbox, Reports,
  Forms, Settings › Business profile, Domains and Sending domains. Per
  screen: horizontal overflow, form controls without a label, buttons and
  links without an accessible name, and the WCAG AA text contrast of every
  text node (4.5:1, or 3:1 for large text). Axe runs in the screens'
  component tests (`accessibilityViolations`).
- **Found and fixed:**
  1. The email-template panel had no styles at 390 px: list bullets, name
     and subject run together, no padding. Now a padded card with a
     two-line item and its actions beside it.
  2. A campaign's status badge stretched across the whole item.
  3. Sending domains: the claim deadline used the browser's numeric date
     (09/11/2026, ambiguous); now the month is written out. The
     "Conversations" and "Campaigns" choices are a fieldset with the
     legend "Use this address for" (regression test).
  4. Automations: the trigger section was still labelled "When a contact
     is created from" whatever the trigger, and the page introduction named
     only that trigger; both now describe every trigger.
  5. The appointment drawer now says when no automatic reminder is
     planned, instead of saying nothing.
- **Checked and sound:** no page scrolls sideways at 390 or 1280 px (the
  contact table and view tabs scroll inside their own regions by design);
  every control has a label; every button and link has a name; no text
  falls below AA contrast (the only flag, the active settings item, is a
  measuring artefact of its translucent background and reads 4.5:1 or
  better on screen); dialogs and drawers keep focus through the shared
  react-aria `Dialog` and `Drawer` components; a skip link leads to `main`.
- **Human check:** `docs/project/SCREEN-READER-CHECKLIST.md` (NVDA and
  VoiceOver, every main workflow, 390 px on iOS), prepared under 13-D1.
- **Not covered:** a full screen-reader session (VoiceOver or NVDA), which
  needs a person; the public booking and form pages were audited in 13-H1.

## 13-A3 — Dependency audit review (2026-11-02, under the hardening mandate)

- **Status:** Reviewed under the owner's instruction of 2026-11-02 ("Review
  every exception. Verify current vulnerability status. Upgrade or
  remediate safely where possible. Remove resolved exceptions. Document
  any remaining exception with justification, owner, expiry and
  remediation plan. Do not silently extend exceptions.").
- **Python:** `pip-audit --strict` over the locked tree (as CI runs it, all
  groups, SaaS-OS excluded by K3): no known vulnerabilities; no exceptions
  exist.
- **npm, production tree** (`npm audit --omit=dev`): clean; it never gets
  an exception.
- **npm, the only exception, GHSA-g3hv-75wg-m249 (minimatch, moderate):**
  re-checked 2026-11-02; unchanged since 13-A2. `eslint-plugin-jsx-a11y`
  6.10.2 is still the latest release, pins minimatch ^3.1.2 and caps its
  eslint peer at 9; eslint 10.14.0 uses minimatch ^10.2.6 (still in the
  advisory's range below 11.0.1); `openapi-typescript` 7.13.0 is still the
  latest and needs `@redocly/openapi-core` 1.x (minimatch 5.1.9). Forcing
  minimatch 11 is unsafe: eslint, `@eslint/config-array`,
  `@eslint/eslintrc`, jsx-a11y and redocly call minimatch 3's default
  function export, which 11.x removed.
- **Decision:** the exception keeps its expiry, 2026-12-31 (not extended),
  and now records its owner and remediation plan
  (`frontend/audit-exceptions.json`). The audit gate
  (`frontend/scripts/audit.mjs`) now fails any exception missing its
  decision, owner, reason, plan or a dated expiry, besides failing on
  expiry, on any new advisory and on a stale entry.
- **Re-checked 2026-11-02 (later, 13-D1):** unchanged. jsx-a11y 6.10.2 is
  still the latest (October 2024), openapi-typescript 7.13.0 still needs
  `@redocly/openapi-core` 1.x (now 1.34.23, minimatch 5), and eslint 10.14.0
  still uses minimatch ^10.2.6. The expiry stays 2026-12-31.

## 13-A4 — The minimatch audit exception is removed (2026-11-06)

- **Status:** Done under the hardening mandate (dependency audit: "remove
  resolved ones").
- **Cause:** CI run 42203444021 failed the frontend audit gate with
  "GHSA-g3hv-75wg-m249: no longer reported; remove its exception". The
  advisory was updated on 2026-11-04 (not withdrawn): its affected range
  is now minimatch `>= 7.0.0, < 11.0.1` (first patched 11.0.1). The
  installed copies are 3.1.5 (four), 5.1.9 and 11.0.3, all outside that
  range; no package was changed.
- **Verified:** `npm audit` reports 0 vulnerabilities of any severity;
  `npm run audit` passes with `frontend/audit-exceptions.json` emptied
  to `[]`.
- **Decision:** the exception is removed. The gate keeps failing on any
  new advisory, so a future range change that covers these versions
  again fails CI instead of passing silently.

## P7-B — Consent and suppression (2026-10-28, under M1)

- **Status:** Decided under M1 after the owner's "Go" (2026-10-28) to the
  proposal "suppression and consent controls". K5's MVP includes "one email
  channel with consent and suppression controls"; P2-D lists consent per
  contact and channel, suppression and unsubscribe as Phase 6 and 7 work.
  Roadmap 7.5 "Consent and suppression management"; slice 7B. Sending
  still waits for the email channel (SaaS-OS release and a pin the owner
  authorises).
- **Design audit:** the design shows consent only as a form option
  ("Email consent") and has no suppression list or unsubscribe screen.
  Slice 7A records consent from forms (`consent_record`, append-only,
  status `granted`, method `web_form`). SaaS-OS has no consent or
  suppression API (P2-D).
- **Decisions:**
  1. **Scope of 7B:** a suppression list per workspace; recording and
     withdrawing a contact's email consent by hand; a contact's email
     status (suppressed or not, consent given, withdrawn or none); and one
     service check every future send must pass. **Not now:** the public
     unsubscribe page and its tokens (they only make sense in a sent
     message, so they come with the email channel), bounce and complaint
     handling (need provider events), CSV import of suppressions (a pasted
     list instead), double opt-in, and channels other than email.
  2. **Suppression** (migration `0017_suppression`, table `suppression`,
     tenant-owned, forced RLS, in `PURGE_TABLES`): one row per email
     address in the workspace, stored lower-cased and unique; a reason
     (`unsubscribed`, `bounced`, `complained` or `manual`); how it was
     added (`manual` or `consent_withdrawn`); an optional note of up to 500
     characters; who and when. It has no link to a contact, so deleting or
     changing a contact never lifts it. Removing an address is a delete.
     At most 100,000 addresses a workspace; at most 1,000 added at once.
  3. **Consent history** stays append-only. `consent_record` gains status
     `withdrawn` and method `manual`; the member who recorded it is kept;
     wording stays required for `granted` and becomes an optional note for
     `withdrawn`. A contact's current email consent is its latest record:
     `granted`, `withdrawn` or none.
  4. **Recording consent by hand** needs the exact wording the person
     agreed to (1-500 characters) and a contact with an email address;
     the record says it was recorded by a member, not given on a form.
  5. **Withdrawing consent** adds a `withdrawn` record and suppresses the
     contact's email address (reason `unsubscribed`, added by
     `consent_withdrawn`) in the same transaction; an address already
     suppressed keeps its first reason. Granting consent again never
     lifts a suppression: only removing the address does.
  6. **The send check** (`crm_app.suppression.email_status`): an address
     that is suppressed may not be sent to; a marketing send also needs
     consent `granted`. No send exists yet; the email channel must call it.
  7. **Who:** new catalogue permissions `crm_app.suppression:read` (Owner,
     Admin, Member) and `crm_app.suppression:manage` (Owner, Admin) for
     the list, adding and removing; Read-only does not see the list.
     Recording and withdrawing consent need `crm_app.contact:update`
     (Members honour opt-outs). A contact's email status is part of the
     contact (`crm_app.contact:read`). `/access` reports
     `read_suppressions` and `manage_suppressions`. Gate G7 applies.
  8. **Audit:** `crm_app.suppression.added` (count, reason),
     `.removed`; `crm_app.contact.consent_recorded` and
     `.consent_withdrawn` (the contact and channel). Addresses, wording and
     notes are never in audit entries.
  9. **Retention:** a suppression is kept until a member removes it,
     because forgetting it would allow mail the person refused. Whether
     a data-subject erasure should keep a suppression (and in what form)
     is a market-specific decision for Phase 13 (P2-D).
  10. **Screens:** Settings › Suppression list (search, add by pasting
      addresses with a reason and note, remove with confirmation); the
      contact drawer's Consent section shows the email status, the full
      history (form, recorded by a member, withdrawn) and "Record consent"
      and "Withdraw consent".

## P3-F — CSV import (2026-10-26)

- **Status:** The owner decided the two open questions on 2026-10-26
  (`PHASE3-PLAN.md` §18 Q4, Q5): "Import permission: Owner and Admin only,
  enforced server-side" and "Retention: Seven days for import staging data
  and temporary artifacts … Do not delete successfully imported CRM
  records after seven days." The rest is decided under M1 from
  `PHASE3-PLAN.md` §9.
- **Decisions:**
  1. **Permission:** a new catalogue permission `crm_app.crm_data:import`
     (administrative) in the Owner and Admin role templates (§9.5 option
     (a)); `/access` reports it as `import_records`. Workspaces created
     from now on receive it. Roles of workspaces created before this change
     do not: SaaS-OS has no supported way to grant a new permission to
     existing roles (gate G7, saas-os #88). No real workspace exists yet;
     local test workspaces are affected, and a test workspace must be
     created afresh to import.
  2. **What:** contacts or companies, one kind per import. Contacts:
     first name, last name, email, phone, job title, city, stage (source is
     set to `import`). Companies: name, domain, website, phone, industry,
     city, country code. Owners, tags, custom fields and company links are
     not imported in this slice.
  3. **Upload:** the request body is the CSV itself (`text/csv`), at most
     5 MB, read with that limit and refused beyond it; at most 10,000 data
     rows; UTF-8 (a byte-order mark is allowed), else Windows-1252; a header
     row; the mapping is proposed from header names or given explicitly.
     No new dependency (no multipart parser), no file stored: only the
     normalised values of each row are kept.
  4. **Validation and duplicates:** every row is checked with the API's own
     validators. A row whose email (contact) or domain (company) belongs to
     an existing active record, or to an earlier row of the file, is a
     duplicate and is skipped. Nothing is ever updated or overwritten.
     Errors name the row, the field and a code, never the value.
  5. **Commit:** a worker job, `crm_app_import_commit`, creates records in
     batches of 500 rows. Each batch is one transaction that creates the
     records and marks their rows done with the new record's ID, so a
     repeated delivery of a batch creates nothing twice, without changing
     the record tables. Duplicates are checked again at commit. One import
     runs per workspace at a time. Cancel stops after the current batch;
     what was created stays. A failed job can be resumed.
  6. **Limits:** 10 previews per user per fixed one-hour window on the
     existing limiter (failing closed with 503), the same fixed-window
     caveat as P3-E1.
  7. **Retention:** an import's rows (normalised values, personal data)
     are deleted 7 days after it finishes, or 7 days after its preview if
     it is never committed; created records are never deleted by this. The
     job's summary (status, counts, field-to-column mapping by position)
     holds no cell value and is kept. Because no SaaS-OS authority lets
     product code list every workspace, a global table `import_expiry`
     (import ID, workspace ID, due time; no personal data; SaaS-OS's
     tenant-context exclusion policy, as for `signup`) tells the
     maintenance command `python -m crm_app.import_maintenance` which
     workspaces to visit; it deletes their rows inside each workspace's
     own scope. Purge removes both.
  8. **Audit:** `crm_app.import.previewed`, `.committed`, `.completed`,
     `.failed`, `.cancelled` with counts only; each created record has its
     normal `created` audit and history entries, marked as imported.

## P3-E2 — Companies CSV export (approved 2026-10-26)

- **Status:** Approved by the owner, 2026-10-26, after the 3E2 audit:
  "Implement Phase 3E2 — Companies CSV export only". It amends P3-E1's
  "Not approved: companies export".
- **Decisions:**
  1. Route: `GET /v1/workspaces/{id}/companies/export.csv`, requiring the
     existing `crm_app.crm_data:export` (Owner, Admin; Q6). No new
     permission; `/access` keeps reporting it as `export_records`.
  2. Columns, in order: `id, name, domain, website, phone, industry, city,
     country_code, created_at, updated_at, archived_at`. Owner, tenant,
     version and creator/updater IDs, notes, activity and people counts are
     excluded, as for contacts.
  3. The company list's filters and order (`q` on name or domain prefix,
     `owner`, `archived`, `sort`, `direction`), without paging. Paging,
     the contact list's filters and unknown parameters are refused (422).
  4. The file, formula protection, the 50,000-row bound (413
     `export_too_large`, no file, no separate count) and the audit
     (`crm_app.companies.exported`, row count and filter names only, same
     transaction, none for a refused export) follow P3-E1 2 and 4-8.
  5. **Separate rate-limit budget:** ten attempts per user per window for
     companies, on the limiter key `crm-company-export:{user}`. It neither
     uses nor changes the contacts budget (`crm-contact-export:{user}`). A
     limiter failure refuses (503). **Recorded deviation (as P3-E1 7):** the
     limiter counts in fixed one-hour windows, not a rolling hour, so up to
     20 company exports can fall within one hour across a window boundary.
  6. The server code is shared with the contacts export (one read-and-audit
     helper, one route helper); the contacts export's behaviour, contract
     and limiter key are unchanged.
- **Known limitation:** the export is built in memory, so that a refusal at
  row 50,001 never leaves a partial file. A website can be up to 2,048
  characters, so a worst-case export of 50,000 companies with very long
  websites can hold well over 100 MB in rows and CSV text at once, about
  twice the contacts worst case. Typical data is far smaller. Streaming
  would avoid this but cannot refuse with 413 once the file has started;
  it is left for later.
- **Not approved:** company import, tags, custom fields, saved views, new
  permissions, migrations, file storage, SaaS-OS changes, deployment.

## P2-F — Completing Phase 2 (approved 2026-10-24)

- **Status:** Approved by the owner, 2026-10-24, after the Phase 2
  baseline and plan. The owner set the priority: complete Phase 2 before
  any further Phase 3 work.
- **Decisions:**
  1. **Tables:** `invitation_intent` (the intended role of an invitation,
     Q4/Q5) and `workspace_settings` (locale, time zone, currency) are
     approved, each with forced RLS, a `PURGE_TABLES` entry and RLS
     negative tests (gate G1 rule).
  2. **Workspace directory without a new table:** the directory lists the
     open workspaces and checks the caller's membership in each through
     public SaaS-OS calls; nothing new is stored. The index table of
     `PHASE2-PLAN.md` §6.4 (gate G5) is not built; it can replace this if
     the number of workspaces grows.
  3. **Email:** Phase 2 closes on Q4's manual-link mode. Sending goes
     through SaaS-OS `core.email` when configured (fake provider in tests,
     Mailpit for local development); no real email is sent anywhere. The
     production provider (Q3) is chosen before launch.
  4. **Security review (`PHASE2-SECURITY-REVIEW.md`):** L4, L5 and I1 are
     accepted for now and deferred to Phase 13. Policy points I2: Admins
     may suspend, revoke and change the roles of other Admins (as Q6);
     12-hour sessions without an idle timeout stay for now; sign-in and
     sign-out are logged by SaaS-OS rather than audited; the `/access`
     500 when a membership vanishes mid-request is fixed.
- **Not approved:** Phase 3C or other Phase 3 feature work; a production
  email provider; a SaaS-OS pin change.

## P2-G — Ending the identity provider's session on sign-out (approved 2026-10-24)

- **Status:** Approved by the owner, 2026-10-24, after the Phase 2 browser
  verification found that signing out of LeadStack left the ZITADEL
  session alive, so the next "Sign in" completed without a password.
- **Decisions:**
  1. **Fix in the product, without SaaS-OS changes:** after SaaS-OS's
     `POST /auth/logout`, the frontend reads `GET /v1/sign-out-url` and
     sends the browser to the provider's end-session endpoint (OIDC
     RP-Initiated Logout) with the public client ID and the fixed return
     address `<PUBLIC_APP_ORIGIN>/app`. The endpoint is configuration
     (`OIDC_END_SESSION_ENDPOINT`, checked at start-up, https in
     production); without it the start page is reloaded. The return
     address is registered on the OIDC application
     (`deploy/local/configure-zitadel.py` locally; by the deployment in
     production).
  2. **Residual accepted as Low, Phase 13:** without an `id_token_hint`
     ZITADEL's sign-out page waits for the person to choose the account;
     closing the tab there leaves the provider session alive. SaaS-OS
     does not give the application the ID token, so the no-click form
     waits on the upstream request in `PHASE2-PLAN.md` Appendix C (not
     sent; sending needs separate authorization).
- **Not approved:** a SaaS-OS change or pin move; the self-service
  sign-up of the design's `LeadStack Signup.dc.html` (excluded by P2-C).

## P2-G.1 — Sign-out without the account choice (approved 2026-10-25)

- **Status:** Approved by the owner, 2026-10-25. Amends P2-G decision 2
  for LeadStack's own login build (decision S-2); ZITADEL's published
  login image keeps the account-choice page.
- **Decision:** when ZITADEL's end-session endpoint sends the browser to
  the sign-out page with a valid logout token (it carries the registered
  return address) and no account hint, the `crm-app-login` build ends
  every ZITADEL session in that browser without a click and returns to
  the registered address. If ending a session fails, the page shows the
  error and the account list, as before.
- **Return address:** `<PUBLIC_APP_ORIGIN>/auth/login`
  (`crm_app.api.sign_out.POST_LOGOUT_PATH`), the only post-logout redirect
  URI registered on the OIDC application; it replaces `/app`. The browser
  goes straight on to a new sign-in instead of loading the application
  first. `/auth/login` is public and only starts a sign-in, so it cannot
  loop. After a sign-out without an end-session address the start page
  still waits for a click (`frontend/src/api/signInRedirect.ts`).
- **Speed:** the login build ends the sessions in a server route
  (`logout/end`), served in place of the sign-out page, so no page or script
  loads in between; the page itself appears only if that fails. The
  frontend fetches the end-session address while it signs out. Measured
  locally from "Sign out" to the sign-in form (3 runs each): 1.1 s with the
  sign-out page; 0.55-0.59 s with the server route; 0.35-0.48 s (median
  0.36 s) with the return to `/auth/login`.
- **Production configuration (not applied; needed before launch):**
  - on the production OIDC application, post-logout redirect URIs exactly
    `https://<production origin>/auth/login`, and no `/app` entry;
  - `OIDC_END_SESSION_ENDPOINT` set to the production issuer's
    `end_session_endpoint` (https, checked at start-up);
  - the login service is the `crm-app-login` image (LeadStack's build); with
    ZITADEL's published image the account-choice page remains;
  - `PUBLIC_APP_ORIGIN` is the origin above, since the return address is
    built from it.
- **Accepted risk (Low):** a link to the end-session endpoint from another
  site can now sign a person out of ZITADEL without asking (logout CSRF).
  It cannot sign anyone in, read data, or send the browser anywhere but the
  registered return address, where it starts a new sign-in (rate-limited
  like every `/auth/login`). The `id_token_hint` route (P2-G, SaaS-OS
  request not sent) would still remove the page entirely.

## S-1 — Self-service signup (approved 2026-10-24)

- **Status:** Approved by the owner, 2026-10-24, as the direction for
  implementation planning, after the read-only signup audit
  (`SIGNUP-PLAN.md` §1). **Supersedes** P2-C's condition "No public
  self-service tenant creation in this phase" and the P2-G "Not approved"
  note on the design's sign-up. Every other part of P2-C stands: workspace
  creation and role setup use supported mechanisms only, and invitations are
  never simulated.
- **Decisions:**
  1. **Policy:** self-service signup is an approved capability. It is off by
     default (`SIGNUP_ENABLED`) and must not be enabled in production until
     every launch gate in `SIGNUP-PLAN.md` §7 has evidence. Invitations stay
     supported; accepting one never creates a workspace.
  2. **v1 journey:**
     - sign-in screen → **Create account**;
     - ZITADEL-hosted registration, credentials, email verification and
       password reset;
     - a verified email required by LeadStack;
     - workspace name;
     - provisioning with the first user as Owner, permissions verified,
       activation last;
     - enter the workspace.

     Not in v1: agency or business type, templates, team invitations during
     onboarding, phone numbers, trial promises, Google or Microsoft sign-in.
  3. **Architecture:**
     - Signup UI, workflow, workspace creation and onboarding belong to
       LeadStack.
     - ZITADEL keeps credentials and email verification.
     - SaaS-OS provisioning and authorization primitives are reused.
     - There is no LeadStack password or identity system.
     - No SaaS-OS change or pin move.
     - Signup is separate from sign-in and invitation acceptance.
     - Provisioning is idempotent and recoverable.
  4. **Abuse prevention:**
     - Security finding L4 is resolved before public signup.
     - Per-user and per-client-address limits fail closed.
     - Edge rate limiting, plus a WAF or equivalent bot protection, in
       public deployments; CAPTCHA is evaluated, not assumed.
     - The `SIGNUP_ENABLED` kill switch, default off.
     - Configurable per-user workspace and platform signup limits.
     - The caller never selects a parent tenant, role or authority.
  5. **Identity:**
     - One shared customer ZITADEL organisation, subject to verifying its
       isolation.
     - MFA required for workspace Owners before public production signup.
     - The current password policy is kept unless the security review
       finds a concrete reason to change it.
     - Lockout and other existing controls are not weakened.
  6. **Email:**
     - Mailpit for local ZITADEL email testing.
     - The production provider, a verified sending domain and SPF/DKIM are
       launch dependencies.
     - The provider and domain are **not selected** (Q3).
  7. **Terms, privacy and retention:**
     - No public signup without published Terms of Service and Privacy
       Policy URLs.
     - Only required, approved consent evidence is recorded.
     - Incomplete signup attempts expire after a proposed 7 days.
     - ZITADEL users are never deleted automatically. Deletion would need a
       separate decision, because LeadStack does not call ZITADEL's
       administrative API.
  8. **Existing members:** a verified user may create additional
     workspaces within the per-user and platform limits, enforced by the
     API.
- **Implemented with this decision (2026-10-24):**
  - `SIGNUP_ENABLED`, `SIGNUP_MAX_WORKSPACES_PER_USER` and
    `SIGNUP_MAX_PER_DAY` start-up validation in `crm_app.settings`:
    - the limits have no defaults and are required when signup is on;
    - `TRUST_PROXY_HEADERS=true` is required when signup is on;
    - signup is refused in production until the launch gates pass.
  - Unit tests for these rules.
  - The L4 investigation (`SIGNUP-PLAN.md` §5): L4 is reduced, not closed.
- **Open:** launch gates LG-1 to LG-10 (`SIGNUP-PLAN.md` §7). Among them:
  - the email provider and domain;
  - the Terms and Privacy URLs;
  - verification of the ZITADEL organisation;
  - how Owner MFA is enforced;
  - the edge and WAF;
  - the numeric limits;
  - identity deletion;
  - unproven ZITADEL behaviour.
- **Not approved:** a ZITADEL administrative API integration; automatic
  identity deletion; enabling signup in production; any SaaS-OS change.

## S-1.1 — Signup limits and local registration testing (approved 2026-10-24)

- **Status:** Approved by the owner, 2026-10-24. Amends S-1. Supersedes
  the setting name `SIGNUP_MAX_PER_DAY` and S-1's "the limits have no
  defaults"; every other part of S-1 stands.
- **Decisions:**
  1. **Initial limits**, configurable, enforced on the server, failing
     closed:
     - `SIGNUP_MAX_WORKSPACES_PER_USER` = **5**;
     - `SIGNUP_MAX_ATTEMPTS_PER_24H` = **100** signup attempts across the
       platform per **rolling** 24 hours.

     These are abuse ceilings, not targets or guarantees. They are adjusted
     after observing legitimate use and abuse. Attempts that fail after
     reaching the endpoint count, so repeated failures cannot evade the
     cap. Retries, concurrent requests and different workspace details
     cannot bypass either limit. The counting and reset rules are in
     `SIGNUP-PLAN.md` §4.
  2. **Local Stage A4 approved:** ZITADEL registration, email verification
     and ZITADEL email through the local Mailpit, in local development
     only. No production identity or email change; `SIGNUP_ENABLED` is
     not set.
- **Implemented (2026-10-24):**
  - the defaults and the rename in `crm_app.settings`, with unit tests;
  - opt-in local settings in `deploy/local/configure-zitadel.py`
    (`ZITADEL_LOCAL_ALLOW_REGISTER`, `ZITADEL_LOCAL_SMTP`) and
    `deploy/local/compose.yaml` (`ZITADEL_LOCAL_EMAIL_VERIFICATION`),
    off by default, kept on across runs through `.env` (`.env.example`).
    Registration is refused without the local Mailpit, and the script
    reports every change to it;
  - README instructions.

  Browser results are in `SIGNUP-PLAN.md` §5a.
- **Pending owner decisions:**
  - whether requests refused by the rate limits or by the cap itself also
    count as attempts (`SIGNUP-PLAN.md` §4 proposes not);
  - the signup-table access model (`SIGNUP-PLAN.md` §4a, option A
    recommended).

## S-1.2 — Signup table, counting rule and Stage C (approved 2026-10-25)

- **Status:** Approved by the owner, 2026-10-25.
- **Decisions:**
  1. **Signup-table access, option A** (`SIGNUP-PLAN.md` §4a, §4b):
     - forced RLS;
     - SaaS-OS's exclusion policy stays;
     - restrictive policies limit every row to the signed-in person;
     - no fallback to application queries without RLS.

     Implementation detail within option A: the maintenance flag may read,
     never write; jobs act as each row's own person.
  2. **Counting rule for the rolling 24-hour cap:**
     - a request counts once it passes the first per-user or per-address
       rate limit and reaches the signup operation, even if validation,
       verification or provisioning fails;
     - requests refused by those limiters, or only by the cap already
       being reached, do not count;
     - check and increment are atomic and safe under concurrency, and an
       unavailable counter refuses the request.
  3. **Stage C approved,** after the security review and the negative
     tests pass, including the shared provisioning service (Stage B).
     Activation happens only after the membership, the Owner role and
     the Owner's effective permissions are created and checked.
- **Not approved:**
  - automatic creation or deletion of ZITADEL users through an
    administrative API;
  - turning signup on in production;
  - any SaaS-OS change or pin move.

  `SIGNUP_ENABLED` stays off by default.
- **Implemented (2026-10-25), uncommitted:**
  - migration `0006_signup` with `crm_app.signup` and
    `crm_app.signup_attempt`;
  - code: `crm_app.provisioning`, `crm_app.signups`,
    `crm_app.api.signups`, `crm_app.signup_maintenance` and
    `crm_app.domains.signup`;
  - the guard rules for global tables;
  - the purge participant step.

  Evidence is in `SIGNUP-PLAN.md` §4b and `PROGRESS.md`.
- **Recorded gap:** SaaS-OS v0.5.0 does not export `system_cron`, so
  maintenance is a scheduled command rather than a worker cron job.

## S-2 — LeadStack's own build of the sign-in pages (approved 2026-10-25)

- **Status:** Approved by the owner, 2026-10-25, after a local trial showed
  that ZITADEL's settings change colours, logo and texts but not the layout,
  and cannot put login name and password on one page.
- **Decisions:**
  1. **Own build of Login V2:** the sign-in pages are ZITADEL's Login V2 at
     the same release as ZITADEL, built with a small set of LeadStack files
     laid over it. It is a separate private repository, `crm-app-login`
     (neutral name, decision K4), producing the image that replaces
     `zitadel-login`. The overlay keeps sign-in itself unchanged: the
     one-form page calls Login V2's own server actions, so user lookup,
     enumeration protection, lockout, email verification and second factors
     stay ZITADEL's, and passwords never reach crm-app (ADR-0025 holds;
     ADR-0026 stays rejected).
  2. **One page:** login name and password on one form, in the design's
     sign-in layout, on every Login V2 page. Upstream's two-step page stays
     available for passkeys and other methods.
  3. **The start page goes straight to sign-in:** `/app` without a session
     sends the browser to `/auth/login` by itself, except after a sign-out
     in that tab (the provider session might still be alive) and at most
     once per 10 seconds (no loop).
  4. **Updates:** a weekly workflow in `crm-app-login` opens a pull request
     for each new ZITADEL release with the build result and release notes.
     The build refuses a changed licence or a changed upstream file the
     overlay replaces. Merging, the matching ZITADEL image change in
     crm-app and deployment stay manual. Chosen instead of Renovate or
     Dependabot: no third-party app, and the check needs the build anyway.
- **Implemented (2026-10-25):**
  - in crm-app (committed):
    - `ZITADEL_LOGIN_IMAGE` in `deploy/local/compose.yaml`; the default
      stays ZITADEL's published image;
    - the start-page redirect (`frontend/src/api/signInRedirect.ts`) with
      tests. A confirmed session clears the sign-out mark, so a later
      expiry in the same tab redirects again;
    - the opt-in local branding of Login V2 through ZITADEL's settings
      (`deploy/local/configure-zitadel.py`, `ZITADEL_LOCAL_BRANDING`);
  - `crm-app-login`: a local git repository with no remote, built and
    verified locally only. Creating its GitHub repository, running its
    workflows and publishing its image each need separate approval.
- **Pending:**
  - browser tests of the full sign-in journey in CI (Playwright, approved);
  - where the image is published for deployment;
  - the GitHub repository for `crm-app-login`.

## S-2.L — Licence of the sign-in build (recorded 2026-10-25)

- **Fact:** at v4.19.5 ZITADEL's `LICENSING.md` puts the repository under
  AGPL-3.0-only, except `apps/login/`, `packages/zitadel-client/` and
  `packages/zitadel-proto/`, which are MIT (and `proto/`, Apache-2.0).
- **Consequence:**
  - `crm-app-login` changes only MIT-licensed code, so its changes may stay
    private. The duty is to keep ZITADEL's copyright and licence notice:
    `LICENSES/zitadel-login-MIT.txt` in the repository and
    `/app/LICENSE.zitadel-login` in the image.
  - ZITADEL itself (AGPL-3.0) runs unmodified as a separate service, so it
    creates no obligation for crm-app.
- **Guard:** the build stops if a future `LICENSING.md` no longer lists
  those three paths as MIT (`scripts/check-licence.sh`); the owner then
  decides.
- This is a reading of the published licence file, not legal advice.

## Ledger of other recorded facts

- **2026-10-20:** Claude Design project
  `74b3900c-4db8-4b26-b938-fc41345f813f` has not been imported. No Claude
  Design MCP server is configured in Claude Code (`claude mcp list`).
  The design tool's own notice says standalone Claude Design closes on
  2026-12-14.
- **2026-10-20:** SaaS-OS is public on GitHub, but its `pyproject.toml`
  declares `license = { text = "UNLICENSED" }`. The owner owns both
  projects; written terms are needed before any third party works on or
  receives the product.
