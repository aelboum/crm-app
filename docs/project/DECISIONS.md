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
