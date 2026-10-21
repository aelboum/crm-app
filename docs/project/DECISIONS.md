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
