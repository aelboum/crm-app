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
