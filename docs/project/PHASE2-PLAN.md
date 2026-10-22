# Phase 2 Plan — Identity, Workspaces and Tenant Isolation

**Status:** Drafted and refined 2026-10-21. Owner approvals of
2026-10-21: **Q6** (the role matrix, §5), **Q-purge option (a)** (upstream
first, no internal-import exception, §9.4), **Q1 as a design direction
only** (§7; command not authorized), and **S1b and S3** within the
platform's supported APIs. What exists in code is listed in §11.1;
everything else is unimplemented. It builds on decisions
P2-A to P2-E (`DECISIONS.md`, approved 2026-10-21) and on ROADMAP §7
(Phase 2, tasks 2.1–2.5).

Labels: **[V]** verified in the pinned source or this repository (file
and symbol given); **[I]** inference; **[R]** recommendation; **[U]**
unverified. SaaS-OS paths are relative to `saas_os/` in the installed
package, which is the pinned commit `5905156a99a4526e5071ce091a58667c08b0a019`
(`saas_os-0.3.0.dist-info/direct_url.json`). `docs/…` paths are SaaS-OS
documents read with `git show 5905156:docs/…`. "PUBLIC" means inside the
approved import surface (`CLAUDE.md` §3): `saas_os.api.*`,
`saas_os.inference`, `saas_os.contracts`, and the `__init__` exports of
`saas_os.core.*`, `saas_os.infra.*` and `saas_os.control_plane.*`.

---

## 1. Purpose and scope

**Purpose.** Establish trustworthy identity, workspace membership, product
roles and database-enforced tenant isolation before any CRM business data
exists (ROADMAP §7 objective).

**In scope (ROADMAP 2.1–2.5, constrained by P2-A to P2-E):**
- Identity: use the SaaS-OS OIDC session; no second identity system.
- Workspaces: operator-created workspaces, explicit membership, a
  workspace directory that grants nothing.
- The four product roles and their permissions, enforced in the backend.
- PostgreSQL isolation for every tenant-owned product table, with
  negative tests.
- Invitations: designed here; enabling real delivery is gated (§8).
- Foundations for locale, time zone and currency on the workspace.
- Resolution of the purge-participant blocker before the first
  tenant-owned table.

**Out of scope:** CRM entities (Phase 3+); public self-service signup
(P2-C); agency hierarchy access, cross-client rollups, "open as client"
(P2-B); billing (Phase 11); frontend implementation until P-6 is approved;
any change to SaaS-OS or its pin.

**Repository state at drafting [V]:** branch `main`, HEAD
`852e1230ce68bacb0f4262fd0df2ff143cbec63f`, clean, level with
`origin/main`; GitHub Actions run 39660779710 succeeded on that commit.
The repository is temporarily public by the owner's choice.

## 2. Approved decisions and constraints

| Decision | Constraint this plan must honour |
| --- | --- |
| K3 / K3.1 | SaaS-OS pinned at `5905156`; public import surface only; no SaaS-OS change |
| K5 / K5.1 | MVP list unchanged; global-ready, English first; single-region hosting |
| D-WS | A workspace is a SaaS-OS tenant, not a second security boundary |
| P2-A | Owner, Admin, Member, Read-only; backend checks; tenant-scoped permissions; last-Owner protection; stop at any unsupported gap |
| P2-B | Explicit membership per workspace; listing never grants access; no inherited access; no hierarchy APIs added or simulated |
| P2-C | Operator-created workspaces; invitation-based membership; no simulated invitations; no email integration without approval |
| P2-D | UTC storage; locale/time zone/currency; jurisdiction-specific work is explicit; purge-participant issue unresolved |
| P2-E | Generic model; IDs for relationships; typed dates; tenant-scoped records |
| P-6 | Frontend framework still open |

## 3. Current state and SaaS-OS capability matrix

### 3.1 Product today [V]
- `src/crm_app/app.py`: `create_app()` returns `build_platform_app(...)`,
  which mounts only health and `/auth` (`api/platform.py:121-122`).
- `src/crm_app/permissions.py`: `PERMISSIONS = ()`; nothing registered.
- `src/crm_app/migrations/versions/0001_create_schema.py`: schema
  `crm_app`, `REVOKE ALL … FROM PUBLIC`, `USAGE` for the runtime role; no
  tables, so no RLS yet.
- `src/crm_app/migrate.py`: SaaS-OS migrations, then the product's, then
  `register_permissions()`.
- `src/crm_app/jobs.py`: `JOB_FUNCTIONS = ()`.
- `tests/unit/test_import_surface.py`: explicitly rejects
  `saas_os.infra.db.rls` and `saas_os.core.tenancy.purge_participants`.
- Local migration role is the PostgreSQL image superuser
  (`deploy/local/init/01-roles.sh`); it bypasses RLS, so RLS can only be
  proven with the restricted runtime role.

### 3.2 Capability matrix

Key: **1** confirmed supported · **2** supported with a documented
constraint · **3** not supported at the pin · **4** unverified.

| Capability | Status | Evidence (file:symbol, PUBLIC?) |
| --- | --- | --- |
| OIDC session, `/auth/*` | 1 | `api/auth/routes.py`; cookie `saas_os_session` or Bearer (`api/auth/config.py:65`) |
| Same-origin rule for cookie mutations | 1 | ADR-0044; enforced in `api/dependencies.py:get_current_actor` (PUBLIC) |
| Tenant context per request | 1 | `api/dependencies.py:get_tenant_context` (PUBLIC): one 404 for missing tenant, closed tenant or no membership row |
| Permission check per route | 1 | `api/dependencies.py:require_permission(resource, action, *, api_key=False)` (PUBLIC): 401 → 404 → 429/503 rate limit → `can()` → 403, denial audited `api.access_denied` |
| Route policy required on every route | 2 | App refuses to start otherwise (CONSUMER-GUIDE l.240) |
| Product roles | 2 | No built-in roles; `core.rbac.create_role` (PUBLIC) creates tenant-local named roles |
| Product permissions | 2 | `core.rbac.register_permission` (PUBLIC): global catalogue, grants nothing; prefix with the product name (CONSUMER-GUIDE l.206-223) |
| Grant permission to role | 2 | `core.rbac.grant_permission` (PUBLIC): user caller must already hold the permission (anti-amplification); PROVISIONING accepted |
| Revoke permission / delete role | 2 | `revoke_permission`, `delete_role` (PUBLIC): user callers only, last-admin guard applies |
| Assign / remove role | 2 | `core.rbac.assign_role` (user caller only, must hold every permission of the role at the scope), `remove_role` (PUBLIC) |
| First role in a new tenant | 2 | `core.rbac.assign_first_role_for_new_tenant` (PUBLIC): requires `SystemCaller(PROVISIONING)`; checks only that the tenant is open; docstring forbids use outside tenant bootstrap |
| Last-administrator guard | 2 | ADR-0043; "administrator" = active member holding `membership_role:create`; raises `LastTenantAdministratorError` (PUBLIC via `core.identity`). Not an Owner guard (see §5.4) |
| Membership create / get / list | 2 | `core.identity.add_tenant_membership` (PROVISIONING or `membership:create`), `get_membership`, `list_tenant_members` (no caller, no authorization, unpaginated) |
| Membership suspend / reactivate / revoke | 1 | `core.identity.*_membership` (PUBLIC), audited, guarded; HTTP `members_router` (PUBLIC, opt-in) |
| List a user's workspaces | 3 | No public function; `/auth/me` returns only `user_id` (`api/auth/routes.py:395-401`); ADR-0045 defers a global index |
| User profile (name, email) | 3 | `core.users` stores no personal data (`core/identity/erasure.py:14-17`) |
| Invitations (create, revoke, accept) | 2 | `core.identity.create_invitation/revoke_invitation/accept_invitation` (PUBLIC): 32-byte `secrets.token_urlsafe`, SHA-256 hash stored, 7-day default / 30-day cap, row lock on accept, one-time, email bound to a verified email, uniform `InvitationInvalidError`; **no role attached** |
| Invitation HTTP routes | 2 | `api/v1` `invitations_router`, `invitation_acceptance_router` (PUBLIC, opt-in); acceptance rate-limited per user |
| Invitation email | 3 | "Deliver the invitation token to the invitee yourself" (CONSUMER-GUIDE l.288) |
| Transactional email | 2 | `core.email.send_email` (PUBLIC), SMTP only; `EmailSendResult.accepted` means accepted by the provider, never delivered (`core/email/service.py:92-98`); `SMTP_HOST` etc. |
| Notifications email to non-members | 3 | `core.notifications.dispatch_notification` needs an existing membership (composite FK) |
| Audit log | 1 | `core.audit_log.record_in_transaction` (PUBLIC); key denylist redaction only, values are the product's responsibility |
| Rate limiting | 1 | `saas_os.infra.ratelimit.enforce_rate_limit` (PUBLIC), Redis-backed, fail-closed |
| RLS policy helper | 1 | `saas_os.infra.db.tenant_rls_statements` (PUBLIC): ENABLE + FORCE + policy `USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)`; no setting ⇒ no rows, writes rejected |
| Tenant-scoped session | 1 | `saas_os.infra.db.tenant_session_scope(tenant_id: UUID)` (PUBLIC): transaction-local `set_config`, commit/rollback/close |
| Runtime role guard | 1 | `saas_os.infra.db.validate_application_role` (PUBLIC): refuses superuser/BYPASSRLS |
| Tenant FK, index, explicit predicate, grants pattern | 2 | CONSUMER-GUIDE l.124-173, l.511-512; scaffold `0001_create_items_table.py` |
| Composite tenant FKs / unique constraints guidance | 4 | Not documented for products; Core uses composite `(tenant_id, x)` FKs internally |
| RLS test helper / coverage guard | 3 | None shipped (ADR-0022; `retention.py` audit is repo-bound) |
| Tenant jobs | 2 | `saas_os.infra.jobs.register_tenant_job`, `enqueue_job` (PUBLIC): at-least-once, no dedup ID; tenant validated before the handler |
| Job lifecycle fence | 1 | `core.tenancy.tenant_job_session`, `lock_open_tenant` (PUBLIC) |
| Idempotency | 1 | `core.idempotency.run_idempotent` (PUBLIC) |
| Product outbox events | 3 | Dispatcher handler map is fixed to Core (`api/outbox_dispatcher.py:75-105`) |
| Tenant creation | 2 | `core.tenancy.create_tenant` (PUBLIC): operator with `platform.tenant:create` or `SystemCaller(PROVISIONING)`; PROVISIONING only for a root tenant or under a PENDING parent |
| Tenant activation | 2 | `core.tenancy.transition_tenant_status` (PUBLIC): PROVISIONING may do PENDING → ACTIVE only |
| Operator bootstrap command | 2 | `python -m saas_os.api.tenant_bootstrap --tenant-name --owner-issuer --owner-subject [--dry-run] [--confirm-production]` (PUBLIC); owner role gets only `("tenant","read_status")` (`api/tenant_bootstrap.py:147`); no extension hooks |
| Tenant purge | 2 | `core.tenancy.purge_tenant` (PUBLIC): `SystemCaller(TENANT_PURGE)`; DELETED → PURGING → PURGED; Core steps first, product participants once afterwards, no verification pass; failure leaves PURGING and is audited |
| Purge participant registration | 3 (public surface) | Only via `saas_os.core.tenancy.purge_participants` (NOT PUBLIC; absent from `core.tenancy.__all__`), used by the SaaS-OS scaffold and guide; unregistered product rows survive purge (CONSUMER-GUIDE l.406) |
| Operator purge CLI | 2 | `saas-os-operator purge-tenant … (--setup module:function \| --no-product-participants) --confirm <id>` (`ops/operator_cli.py:183-261`) |
| User erasure for product data | 3 | `erase_user_identity` is NOT PUBLIC and has no product hook |
| Data-subject export | 3 | None |
| Locale / time zone / currency on tenant or user | 3 | `Tenant` has name, status, parent, billing flag only (`core/tenancy/models.py:95-102`) |
| Catching `AuthorityNotAuthorizedError` | 3 (public surface) | Not exported from any `__init__` [V] |

## 4. Proposed architecture [R]

- **Layers:** FastAPI routes in `crm_app.api` (one module per resource),
  each declaring exactly one `require_permission` policy; services in
  `crm_app.domains.<area>` that receive a `RequestContext` and run every
  database operation inside `tenant_session_scope(context.tenant_id)`;
  product SQLAlchemy models in `crm_app.domains.<area>.models` on
  `saas_os.infra.db.Base`.
- **Tenant source:** always `RequestContext.tenant_id` (from
  `get_tenant_context`) or `TenantJobContext.tenant_id`; never a path,
  body or payload value (CONSUMER-GUIDE l.261, l.397-402).
- **Two layers of enforcement:** application permission checks
  (`require_permission` → `can()`) decide *whether* an operation is
  allowed; forced RLS decides *which rows* any query can touch. Both are
  mandatory; neither replaces the other.
- **SaaS-OS routers (opt-in):** only `invitation_acceptance_router` is
  mounted as-is (§8). `members_router` and `invitations_router` are **not**
  mounted: they check only `membership:*` / `invitation:*`, so they could
  not enforce "an Admin may not act on an Owner", the last-Owner guard or
  the intended-role limit (§5.4). Product routes call the public Core
  functions (`core.identity.*_membership`, `create_invitation`,
  `revoke_invitation`) after those product checks. (Corrected 2026-10-21;
  the first draft proposed mounting all three.)
- **Product routes added:** role assignment and removal, workspace
  settings, workspace directory, member profiles (none exist in SaaS-OS).
- **Import-boundary guard:** the existing `test_import_surface.py` and
  import-linter contracts stay; any approved exception (§9) is named in
  both.

## 5. Roles and permissions

Refined and **approved by the owner on 2026-10-21 (Q6)** as the MVP
authorization policy. The catalogue and templates are in
`src/crm_app/roles.py`; the granted permissions are registered in the
migration step (S1b, `crm_app.permissions`). No role exists in any
workspace and nothing is granted until the provisioning command is
approved (G2). `tests/unit/test_roles.py` fails if this table and the code
disagree; reconciled on 2026-10-21: 47 permissions, 39 granted to at least
one role, 8 granted to none.

### 5.1 Principles

- Product roles are tenant-local SaaS-OS roles created by product
  provisioning code (§7); SaaS-OS has none built in and ZITADEL holds no
  roles.
- Every permission is checked in the backend by
  `require_permission(resource, action)` on the route, which first
  resolves the workspace from the caller's own membership
  (`get_tenant_context`): a foreign or unknown workspace is a 404 before
  any role is considered. All permissions apply to the active workspace
  only.
- Product permissions use the `crm_app.` prefix; platform permissions use
  the names SaaS-OS defines at the pin (`api/v1/permissions.py`,
  `api/v1/tenant_status.py`, `api/v1/tenant_suspension.py`,
  `core/rbac/service.py`).
- Roles are strictly nested (Read-only ⊂ Member ⊂ Admin ⊂ Owner) and
  fixed in Phase 2; no route edits a role's permissions.
- CRM permissions (Phases 3–4) are part of the catalogue now so that
  workspaces provisioned in Phase 2 already hold them (Q2, §7).

### 5.2 Role matrix

Kind: R read, C create, U update, D delete, A administrative. "Extra
check" is enforced by product code in addition to the permission.

| Permission | Owner | Admin | Member | Read-only | Kind | Extra check (backend) |
| --- | --- | --- | --- | --- | --- | --- |
| `tenant:read_status` | ✓ | ✓ | ✓ | ✓ | R | — |
| `tenant:suspend` | – | – | – | – | A | Not granted: locks every member out and only a platform operator can reactivate |
| `membership:read` | ✓ | ✓ | ✓ | ✓ | R | — |
| `membership:suspend` | ✓ | ✓ | – | – | A | Admin may not target an Owner; last-Owner guard |
| `membership:reactivate` | ✓ | ✓ | – | – | A | Admin may not target an Owner |
| `membership:revoke` | ✓ | ✓ | – | – | A | Admin may not target an Owner; last-Owner guard |
| `invitation:read` | ✓ | ✓ | – | – | R | — |
| `invitation:create` | ✓ | ✓ | – | – | A | Intended role may not exceed the inviter's; rate limit |
| `invitation:revoke` | ✓ | ✓ | – | – | A | Pending invitations only (SaaS-OS) |
| `membership_role:create` | ✓ | ✓ | – | – | A | SaaS-OS refuses a role with permissions the caller lacks |
| `membership_role:delete` | ✓ | ✓ | – | – | A | Admin may not remove the Owner role; last-Owner guard |
| `role_permission:grant` | – | – | – | – | A | Not granted: roles are fixed templates |
| `role_permission:revoke` | – | – | – | – | A | Not granted: roles are fixed templates |
| `api_key:self_manage` | – | – | – | – | A | Not granted in Phase 2 |
| `billing_subscription:read` | – | – | – | – | R | Not granted (Phase 11) |
| `billing_subscription:create` | – | – | – | – | A | Not granted (Phase 11) |
| `billing_subscription:cancel` | – | – | – | – | A | Not granted (Phase 11) |
| `billing_account:read` | – | – | – | – | R | Not granted (Phase 11) |
| `crm_app.workspace:read` | ✓ | ✓ | ✓ | ✓ | R | — |
| `crm_app.workspace:update` | ✓ | ✓ | – | – | U | Ordinary settings: name, locale, time zone, currency |
| `crm_app.workspace_security:update` | ✓ | – | – | – | A | Re-confirmation; security-sensitive settings only |
| `crm_app.owner:manage` | ✓ | – | – | – | A | Re-confirmation; last-Owner guard under a per-workspace lock |
| `crm_app.member_profile:read` | ✓ | ✓ | ✓ | ✓ | R | — |
| `crm_app.audit:read` | ✓ | ✓ | – | – | R | IDs and actions only; no personal data or secrets |
| `crm_app.contact:read` | ✓ | ✓ | ✓ | ✓ | R | — |
| `crm_app.contact:create` | ✓ | ✓ | ✓ | – | C | — |
| `crm_app.contact:update` | ✓ | ✓ | ✓ | – | U | — |
| `crm_app.contact:delete` | ✓ | ✓ | – | – | D | Confirmation |
| `crm_app.company:read` | ✓ | ✓ | ✓ | ✓ | R | — |
| `crm_app.company:create` | ✓ | ✓ | ✓ | – | C | — |
| `crm_app.company:update` | ✓ | ✓ | ✓ | – | U | — |
| `crm_app.company:delete` | ✓ | ✓ | – | – | D | Confirmation |
| `crm_app.opportunity:read` | ✓ | ✓ | ✓ | ✓ | R | — |
| `crm_app.opportunity:create` | ✓ | ✓ | ✓ | – | C | — |
| `crm_app.opportunity:update` | ✓ | ✓ | ✓ | – | U | Includes stage changes and won/lost |
| `crm_app.opportunity:delete` | ✓ | ✓ | – | – | D | Confirmation |
| `crm_app.pipeline:read` | ✓ | ✓ | ✓ | ✓ | R | — |
| `crm_app.pipeline:manage` | ✓ | ✓ | – | – | A | Changes affect every open opportunity |
| `crm_app.task:read` | ✓ | ✓ | ✓ | ✓ | R | — |
| `crm_app.task:create` | ✓ | ✓ | ✓ | – | C | — |
| `crm_app.task:update` | ✓ | ✓ | ✓ | – | U | — |
| `crm_app.task:delete` | ✓ | ✓ | ✓ | – | D | — |
| `crm_app.activity:read` | ✓ | ✓ | ✓ | ✓ | R | — |
| `crm_app.activity:create` | ✓ | ✓ | ✓ | – | C | — |
| `crm_app.activity:update` | ✓ | ✓ | – | – | U | — |
| `crm_app.activity:delete` | ✓ | ✓ | – | – | D | Confirmation |
| `crm_app.crm_data:export` | ✓ | ✓ | – | – | A | Bounded, audited, rate-limited |

**Not in the matrix on purpose:** workspace deletion and purge. SaaS-OS
ADR-0040 answers "May a tenant's administrator … delete their tenant? Is
purge reachable from a request?" with "Delete: no. Purge: never from a
request path". Both stay operator commands; no product role can start
them.

### 5.3 Ambiguities resolved in this proposal (each part of Q6)

| Question | Proposal | Trade-off |
| --- | --- | --- |
| May Members delete ordinary records? | Tasks yes; contacts, companies, opportunities and activity notes no | Avoids accidental loss of shared customer data and history; costs Members an Admin request for clean-ups |
| What is Admin's "limited" security role? | Ordinary settings (`workspace:update`) and member management yes; security settings and Owner management no | A compromised Admin account cannot weaken workspace security or take ownership |
| Owner assignment | Owner only, with re-confirmation and the last-Owner guard | Several Owners are allowed; transfer = grant to the new Owner, then the old Owner steps down |
| Workspace suspension | No role (operator only) | `tenant:suspend` exists at the pin, but a suspended workspace admits none of its principals and cannot be reactivated by them |
| Audit access | Owner and Admin | Members cannot see who did what; a privacy-preserving view for Members is a later option |
| Export | Owner and Admin | Bulk personal data leaves the system only through accountable roles |

### 5.4 Escalation and Owner protection

- **Admin → Owner is impossible:** SaaS-OS `assign_role` refuses a role
  holding any permission the caller lacks
  (`core/rbac/service.py:640-731`); the Owner role holds
  `crm_app.owner:manage` and `crm_app.workspace_security:update`, which
  Admin lacks. Unit-tested on the templates (S1); the live refusal is an
  integration test once roles exist (§13).
- **Admin acting on an Owner's membership:** SaaS-OS does not know product
  roles, so the product checks the target's role before calling
  `suspend_membership`, `revoke_membership` or `remove_role`. This is why
  the SaaS-OS `members_router` is not mounted (§4).
- **Self-promotion:** covered by the same `assign_role` rule; product
  routes also refuse changes to the caller's own roles, except an Owner
  stepping down.
- **Last Owner:** SaaS-OS guards the last *administrator*
  (`membership_role:create` holder, `core/rbac/administrators.py:89-102`);
  Admins hold that permission, so it would not stop the last Owner being
  removed. The product counts ACTIVE Owners and refuses (409) when the
  operation would leave none. Two Owners removing each other at once must
  not both succeed.

**Locking investigation (2026-10-21) [V]:**
- `saas_os.infra.db.acquire_tenant_advisory_lock(session, tenant_id, key)`
  (PUBLIC) takes `pg_advisory_xact_lock(hashtext(tenant), hashtext(key))`
  on the caller's session; it is released at that transaction's commit or
  rollback (`infra/db/session.py:147-175`).
- None of the Core mutations involved accepts the caller's session:
  `assign_role`, `remove_role` (`core/rbac/service.py:640, 861`),
  `suspend_membership`, `revoke_membership` (`core/identity/service.py:703,
  749`) each open their own `tenant_session_scope`. The lock and the change
  therefore cannot share one transaction.
- **A supported strategy exists, with conditions [I]:** hold the lock in
  an outer product transaction, re-count Owners after acquiring it, call
  the Core function (its own transaction commits), then commit the outer
  transaction. A second request waits on the lock and, under READ
  COMMITTED, counts after the first change is visible. It is safe only
  if (1) every Owner-changing path goes through this product code (the
  SaaS-OS membership routers stay unmounted; operator commands such as
  `erase-user` bypass it and need a runbook rule), and (2) connection-pool
  starvation is bounded: each waiter holds one connection while the lock
  holder needs a second, so a bounded wait
  (`saas_os.infra.db.set_local_statement_timeout`, PUBLIC) must turn a
  stalled wait into a refusal rather than a deadlock.
- **Not proven:** this needs the concurrency tests in §5.5 against a real
  database (two Owners removing each other; two demotions; the invariant
  "at least one ACTIVE Owner" checked afterwards, not just status codes).
  Implemented and tested locally on 2026-10-21 (§11.2): the strategy
  above in `src/crm_app/api/members.py`, with the decision rule in
  `crm_app.domains.membership.refusal_for`.

**Operator rule (G-LOCK):** administrative commands outside the product
(`saas-os-operator erase-user`, user deactivation, platform tenant
operations, direct database edits) must never remove, demote or disable a
workspace's last active Owner. A verified Owner transfer through the
product comes first. The product lock cannot cover these paths; the rule
is procedural.

### 5.5 Negative tests that make the matrix real (S7, §13)

For every route: each role without the permission gets 403; a caller
from another workspace gets the same 404 as an unknown workspace; a
suspended member gets 403. Additionally: Admin assigning Owner → refused;
Admin suspending, revoking or demoting an Owner → refused; removing,
demoting, suspending or revoking the last Owner → 409, including two
concurrent attempts; Read-only on every write route → 403; nobody can
reach a purge or deletion route (none exists).

## 6. Workspace and membership model

### 6.1 Identity association [V]
A user is the SaaS-OS `core.users` row linked to the OIDC
`(issuer, subject)` pair (`core.identity.get_or_create_user_for_external_identity`,
PUBLIC). Workspace membership is a SaaS-OS `tenant_memberships` row.
ZITADEL holds identities only; no role or workspace data is stored there.

### 6.2 Authorization of workspace access [V/R]
Every workspace route takes the workspace from the path, but the trusted
value is `RequestContext.tenant_id` after `get_tenant_context` has found a
membership row; `can()` then requires an ACTIVE membership and the
permission. Unknown workspace, closed workspace and no membership all
return the same 404, so existence is not leaked [V]. A suspended member
gets 403 [V].

### 6.3 Workspace switching [R]
There is no server-side "current workspace" state: each request names its
workspace and is authorized on its own. Switching therefore cannot carry
access over. The frontend must not cache another workspace's data across
a switch (frontend test requirement, §13).

### 6.4 Workspace directory (smallest safe design) [R]
- **Source of truth:** SaaS-OS memberships. The directory is a
  product-owned *index* `crm_app.user_workspace_index(user_id, tenant_id,
  added_at)` holding identifiers only (no workspace data), written in the
  same request or command that creates the membership (provisioning,
  invitation acceptance) and deleted when a membership is revoked.
- **Read path:** list the caller's index rows, then for each entry call
  `get_membership(tenant_id, user_id)` and check the tenant is open and the
  membership ACTIVE; drop and delete stale entries; show the workspace
  name only after that check (fail closed).
- **Security note:** this table is keyed by user, not tenant, so the
  SaaS-OS tenant RLS helper does not apply. It must contain no tenant
  business data, only IDs; access is filtered by `actor_id` in code. This
  design needs a security review before implementation (gate G5).
- **Consistency:** eventually consistent with a periodic reconciliation
  job that removes entries without an ACTIVE membership; a stale entry
  can never grant access because every request is authorized
  independently.
- **Agency directory:** the same index; an agency user sees only
  workspaces they are a member of. No parent/child traversal (P2-B).

### 6.5 Member display data [R/U]
`core.users` stores no name or email. Phase 2 adds a tenant-scoped
`crm_app.member_profile(tenant_id, user_id, display_name, email)`
filled at invitation acceptance from the session's verified email and
from the operator at provisioning. Whether SaaS-OS exposes OIDC profile
claims (name) to product code is **[U]**; until verified, display name is
entered by the member. This is personal data: it is covered by purge
(§9) and needs an erasure path (P2-D).

## 7. Provisioning sequence and the PROVISIONING boundary

Investigated 2026-10-21 against the pin; nothing was run.

### 7.1 Evidence [V]

- **Documented scope.** `SystemAuthority.PROVISIONING`: "creating a
  tenant's initial authority structure before any principal in it could
  hold authority (the first-tenant bootstrap command, a consumer's own
  provisioning/seed code, test fixtures)" (`core/authority/caller.py:38-42`,
  PUBLIC via `core.authority`; ADR-0031 l.36, l.114).
- **Product-owned tenant creation is explicitly sanctioned.** ADR-0040,
  answer 3: "'create my organization' … stays a product flow built on
  `create_tenant` … The product's code passes `SystemCaller(PROVISIONING)`,
  which Core accepts only for a root tenant or beneath a `PENDING`
  parent. Abuse controls for a sign-up endpoint remain the product's."
- **The bootstrap command is for the first tenant.** CONSUMER-GUIDE §12
  "First tenant": "Creating the first tenant and its first administrator
  is an operator command of the installed package". It grants its `owner`
  role only `("tenant", "read_status")`
  (`api/tenant_bootstrap.py:147`, `FIRST_TENANT_OWNER_PERMISSIONS`) and
  has no extension hooks.
- **Technical reach is wider than the documented scope.** `create_role`,
  `grant_permission`, `add_tenant_membership` accept PROVISIONING for any
  open tenant; `assign_first_role_for_new_tenant` "checks that the tenant
  is open, not that it is new" (ADR-0045 l.214). ADR-0031's amendment:
  "A purpose is a label, not a credential … any in-process code can
  construct one". ADR-0045 l.1401 leaves narrowing this to "Separate
  decision". `revoke_permission`, `delete_role` and membership
  transitions refuse PROVISIONING.
- **Audit:** every PROVISIONING mutation is recorded as `ActorType.SYSTEM`
  with the purpose in metadata, in the same transaction
  (`core/audit_log/service.py:177-210`).
- **No documented mechanism** exists for adding permissions to roles in
  existing tenants; a search of the pinned `docs/` and `examples/` for
  "existing tenants", "backfill", "seed" and "provisioning" found none.
  A user caller cannot grant a permission it does not hold
  (anti-amplification, `core/rbac/service.py:257-290`).

### 7.2 Answers

1. **Supported sequence for a tenant and its first product Owner?** Yes:
   product provisioning code calling `create_tenant` with PROVISIONING for
   a root tenant (ADR-0040) and building the initial authority structure
   before any principal holds authority (caller.py). The SaaS-OS
   bootstrap command is the alternative for a platform's first tenant
   only and cannot give the product's roles.
2. **Product roles and permissions through documented public interfaces?**
   Yes: `register_permission`, `create_role`, `grant_permission`
   (PUBLIC, `core.rbac`).
3. **All four roles before the Owner gains authority?** Yes, if roles and
   grants are created before `assign_first_role_for_new_tenant`; no
   principal holds authority until that call.
4. **Owner's permissions without crossing the boundary?** Yes: the Owner
   role receives its grants while it has no members; the first assignment
   then confers them. Using PROVISIONING after that point is not
   sanctioned and is not planned.
5. **Failure halfway:** steps are separate transactions (as in the SaaS-OS
   bootstrap). Every step before the role assignment produces only inert
   state (a tenant or role with no member grants nothing).
6. **Retry:** safe if each step is find-or-create on unique keys (role
   name per tenant, membership per user, grant per role and permission)
   and a re-run resumes a tenant only if it has no members or only this
   owner, mirroring `api/tenant_bootstrap.py:297-332`. Must be proven by
   the G2 validation, not assumed.
7. **Future permission changes in existing workspaces:** no documented
   mechanism (Q2). Mitigation: put the MVP catalogue (Phases 2–4) into
   the templates now (§5); ask SaaS-OS for a sanctioned path before any
   workspace needs a permission it was not provisioned with.
8. **Needs upstream clarification or validation:** see §7.4.

### 7.3 Smallest supported path (proposal, gate G2)

A product operator command (`crm-app-provision`), no HTTP route, following
the SaaS-OS bootstrap's own step order so nothing depends on an
unverified ordering:

1. Refuse an unsafe database role (`validate_application_role`), refuse
   production without explicit confirmation, offer a read-only dry run.
2. `create_tenant(name, caller=SystemCaller(PROVISIONING))`, root tenant
   only; resume rule as in the SaaS-OS bootstrap.
3. `transition_tenant_status(PENDING → ACTIVE)` (an active tenant with no
   members grants nothing; same order as the bootstrap).
4. `register_permission` for the catalogue (idempotent), `create_role` ×4,
   `grant_permission` per `ROLE_TEMPLATES`, all with PROVISIONING.
5. Product rows (workspace settings), once gate G1 allows tenant tables.
6. `get_or_create_user_for_external_identity(issuer, subject)`.
7. `add_tenant_membership(..., caller=PROVISIONING)`.
8. `assign_first_role_for_new_tenant(... Owner ...)`: the only authority-
   conferring step, last.
9. Verify with `can()`; print identifiers only.

Not proposed: running `saas_os.api.tenant_bootstrap` and then granting
more with PROVISIONING (principals would already hold authority).

### 7.4 Step-by-step design (Q1 approved as design direction, 2026-10-21)

The command is **not** authorized; this is the design it must meet.
"Inert" means the step confers no authority on anyone.

| # | Step | Public API (verified at the pin) | Precondition | State after | Idempotency | If it fails here |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Create tenant | `core.tenancy.create_tenant(name, caller=SystemCaller(PROVISIONING))` | Root tenant; name rule as `api/tenant_bootstrap.py:297-332` | PENDING tenant, no members (inert) | Find by `find_tenants_by_name`; resume only if no members or only this owner | Nothing usable exists; re-run resumes |
| 2 | Activate | `core.tenancy.transition_tenant_status(id, TenantStatus.ACTIVE, caller=…)` | PENDING | ACTIVE, no members (inert) | Skip if already ACTIVE | Tenant stays PENDING; re-run continues |
| 3 | Roles and grants | `core.rbac.register_permission`, `create_role`, `grant_permission` (PROVISIONING) | Tenant open; no membership yet | Four roles with the §5.2 grants (inert: no members) | `uq_roles_tenant_name`, `uq_role_permissions_role_permission`; find before create | Partial grants on memberless roles; re-run completes them |
| 4 | Owner user | `core.identity.get_or_create_user_for_external_identity(issuer, subject)` | Exact `iss` and `sub` supplied by the operator | User row (holds nothing) | Find-or-create by design | Re-run finds it |
| 5 | Membership | `core.identity.add_tenant_membership(…, caller=PROVISIONING)` | Steps 1–4 complete | Bare membership, no role (inert) | `uq_tenant_memberships_tenant_user` | Re-run finds it |
| 6 | Owner role (last) | `core.rbac.assign_first_role_for_new_tenant(…, caller=PROVISIONING)` | Only this owner is a member; Owner role has its grants | The only authority-conferring step | `uq_membership_roles_membership_role`; skip if held | Bare membership grants nothing; re-run assigns |
| 7 | Verify | `core.rbac.can(...)` | — | Read-only check | — | Report; no change |

**Authority invariant:** before step 6, no principal holds any permission
in the tenant; after it, exactly one member holds the Owner role.
**Audit:** Core records steps 1–3, 5 and 6 with `ActorType.SYSTEM` and the
purpose (`core/audit_log/service.py:177-210`); the command prints
identifiers only. **Transactions:** each Core call is its own transaction;
there is no all-or-nothing transaction across steps (same as the SaaS-OS
bootstrap), which is why every step must be inert or idempotent.
**Verified vs assumed:** the APIs, callers and unique constraints named
above are verified at the pin; that the find-before-create resume logic
handles every crash point is an assumption until the G2 validation run.

**Tests required before the command is approved for implementation:**
dry run changes nothing; full run produces the invariant; a re-run is a
no-op; a crash injected after each step leaves an inert state that a
re-run completes; a resume is refused for a same-name tenant with other
members; production refuses without explicit confirmation; no secret or
token is printed.

### 7.5 Q2 — permissions in existing workspaces (findings)

- **New product permissions:** yes, `register_permission` (PUBLIC),
  idempotent, no caller. Registration alone changes nothing for any
  workspace.
- **Updating existing roles:** only `grant_permission` (PUBLIC). A user
  caller must already hold the permission (anti-amplification,
  `core/rbac/service.py:257-290`), so no Owner can grant a brand-new
  permission. PROVISIONING technically works on any open tenant, but its
  documented scope is "initial authority structure", and ADR-0045 l.214
  and l.1401 flag that reach as un-narrowed and undecided. **Not within
  the documented scope.**
- **Retry and partial failure:** each grant is its own transaction and
  unique per role and permission, so a re-run would be safe, but there is
  no documented upgrade or migration pattern to rely on (none found in the
  pinned `docs/` or `examples/`).
- **Templates do not update existing roles:** editing `ROLE_TEMPLATES`
  changes only workspaces provisioned afterwards.
- **Required upstream capability:** a sanctioned, audited operation for a
  consumer to add a registered permission to named roles in existing
  tenants (for example a documented PROVISIONING use for "permission
  migrations", or an operator command). Until then: no grants to existing
  workspaces; the MVP catalogue is already complete in the templates.
- **Upstream (informational):** export `AuthorityNotAuthorizedError`
  publicly, so refusals can be handled without an internal import.

## 8. Invitation lifecycle and email dependency

### 8.1 What SaaS-OS provides [V]
Creation by a user holding `invitation:create`; 32-byte URL-safe token,
stored only as a SHA-256 hash; returned once; 7-day default, 30-day cap;
duplicate pending invitation refused; revocation; acceptance by a
signed-in user with a verified email that matches, under a row lock,
one-time, with a uniform error; audit events `invitation.create`,
`.revoke`, `.accept`. It does **not** send email and does **not** attach
a role.

### 8.2 Product additions [R]
1. **Creation:** Owner or Admin only (`invitation:create`). The product
   stores the *intended* role in `crm_app.invitation_intent(tenant_id,
   invitation_id, role, invited_by, created_at)` (RLS). The intended role
   is validated at creation: an Admin may not invite an Owner (same rule
   as §5.4).
2. **Token handling:** the raw token exists only in memory during the
   create request and in the email body; it is never logged, stored, put
   in a job payload or returned to the inviter's UI [R]. Therefore the
   email is sent **synchronously** in the create request
   (`send_email`, 10 s default timeout).
3. **Delivery state** is separate from invitation state:
   `not_attempted`, `accepted_by_provider` (from
   `EmailSendResult.accepted`, with `provider_message_id`), `failed`
   (error class only). The UI may say "accepted for sending", never
   "delivered". Bounce tracking is out of scope.
4. **No provider configured:** creation is refused with a clear error
   ("email delivery is not configured"); no invitation row is left
   behind (revoke on failure). Alternative for the owner to decide (Q4):
   a "copy invitation link" mode that shows the link once to the inviter,
   labelled "not sent — deliver it yourself", with delivery state
   `manual`.
5. **Send failure:** revoke the just-created invitation and report the
   failure; "resend" = revoke the old invitation and create a new one
   (new token), rate-limited.
6. **Acceptance:** SaaS-OS route (`invitation_acceptance_router`); the
   member then has a bare membership with no role.
7. **Role assignment after acceptance:** `assign_role` needs a user caller
   holding the role's permissions, so the invitee cannot assign it.
   Proposal (Q5): the new member appears as "awaiting role" and an Owner
   or Admin confirms the intended role with one action. No caller
   impersonation, no PROVISIONING. Until then the member can do nothing
   (no permissions) — fail closed.
8. **Expiry and cleanup:** SaaS-OS expiry applies; a product job removes
   `invitation_intent` rows for expired or revoked invitations after 30
   days.
9. **Abuse controls:** `infra.ratelimit` limits per inviter and per
   workspace on create/resend; a per-workspace cap on pending invitations.
10. **Audit and privacy:** Core audits the lifecycle; product events
   (role confirmed, delivery result) via `record_in_transaction` with IDs
   only; invitee email never in logs.
11. **Concurrency:** duplicate acceptance is handled by Core's row lock;
   role confirmation is idempotent (assigning an already-held role is a
   no-op).

### 8.3 What blocks a working invitation flow
- **Q3:** approval of an email provider and SMTP credentials (external
  service, possibly paid). Without it, real invitations cannot be
  enabled.
- **Q4:** whether a manual-link mode is acceptable meanwhile.
- **Q5:** the two-step role confirmation.
- Members can be added by the operator command in the meantime only for
  the first owner; there is no other supported path to add members
  without invitations.

## 9. Tenant purge — blocking decision

Investigated 2026-10-21 against the pin; nothing was run.

### 9.1 Evidence [V]

- **Public purge API:** `core.tenancy.purge_tenant(tenant_id, *, caller,
  actor_user_id=None, registry=None)` (PUBLIC), `SystemCaller(TENANT_PURGE)`
  only. Runs Core's steps, then each registered participant **once**
  (`core/tenancy/service.py:1850-1857`), then Redis dead-letter cleanup,
  then PURGED (`:1877-1905`). Each step is its own transaction.
- **Participant contract:** `TenantPurgeParticipant` protocol with `name`
  and `purge_tenant_data(tenant_id)` (`core/tenancy/purge_participants.py:50-87`).
  Called only while the tenant is locked PURGING; idempotency "is this
  method's own responsibility, by contract, not something Core enforces or
  verifies"; failure is reported by raising.
- **Registration:** only `saas_os.core.tenancy.purge_participants.default_registry()`;
  absent from `core.tenancy.__all__`. SaaS-OS's own update policy
  classifies everything under `saas_os/core/*` except `__init__.py` as
  INTERNAL (`infra/update/policy.py`, `Category.INTERNAL`).
- **Contradiction inside SaaS-OS:** its documents treat the interface as
  public. MULTI-TENANCY.md l.53: a Product "participates by registering a
  `saas_os.core.tenancy.purge_participants.TenantPurgeParticipant` — an
  explicit interface a Product implements and registers with Core";
  `examples/reference-consumer/reference_consumer/purge.py` "imports
  Core's published `TenantPurgeParticipant` interface"; the consumer
  scaffold does the same; CONSUMER-GUIDE l.423: "Register it in every
  process that can run `purge_tenant()`".
- **Operator command:** `saas-os-operator purge-tenant … (--setup
  module:function | --no-product-participants) --confirm <id>`
  (`ops/operator_cli.py:183-261`). It refuses to run with neither option
  and refuses a `--setup` that registers nothing.

### 9.2 Answers

1. **Registration through a supported public API?** No. Only through the
   internal-classified submodule.
2. **Can the public purge command run product participants?** Yes, via
   `--setup module:function`, but that function must itself register into
   `default_registry()`, which needs the internal import.
3. **Custom participant list test-only?** Yes. `purge_tenant` docstring:
   "`registry` is an override for test isolation only; real callers never
   need to pass it." (`core/tenancy/service.py:1703-1704`).
4. **A product step fails:** classified `participant_error`; the tenant
   stays PURGING; `tenant.purge_failed` is audited with the participant's
   name as `failed_step` and the exception type only; a re-run repeats all
   steps and calls every participant again.
5. **Success while product data remains?** Yes, in three ways: no
   participant registered (unregistered rows "survive", CONSUMER-GUIDE
   l.406); the operator passes `--no-product-participants`; or a
   participant returns without removing everything (Core does not
   verify).
6. **Locking against concurrent writes:** principals are refused from
   DELETED onwards (`can()`, `get_tenant_context`; MULTI-TENANCY.md l.61);
   `lock_open_tenant(session, tenant_id)` (PUBLIC) takes the tenant row
   `FOR SHARE` so a write cannot interleave with the transition, and
   `tenant_job_session` (PUBLIC) fences jobs. Product code must use them;
   SaaS-OS cannot force it.
7. **Documented public extension point without an internal import?** No.
8. **Is an upstream addition the cleanest resolution?** Yes: export the
   protocol and the registration function from `saas_os.core.tenancy`.
   Because SaaS-OS's own documents already call the interface published,
   the missing export looks like an upstream inconsistency [I].

### 9.3 Options

| Option | Available now? | Security | Maintenance / upgrade | Testing |
| --- | --- | --- | --- | --- |
| Supported public extension point | No | — | — | — |
| **Upstream export** of the protocol and registration from `saas_os.core.tenancy` | Needs a SaaS-OS change, release and an approved pin move | Cleanest | Normal pin upgrade | Same tests as below |
| Custom `registry=` passed to `purge_tenant` by a product command | Technically | Contradicts "test isolation only"; bypasses the packaged command | Two purge paths to keep consistent | Same |
| **Narrow, temporary import exception** | Yes | Uses the path SaaS-OS documents for consumers | Internal module may change without notice; re-check on every pin move | Same |

### 9.4 Decision: upstream first (owner, 2026-10-21)

**Approved: option (a).** Request a public purge-registration API from
SaaS-OS and wait for a release that provides it. **No internal-import
exception is approved or in place**; `crm_app` does not import
`saas_os.core.tenancy.purge_participants`, and
`tests/unit/test_import_surface.py` still rejects it. Consequently no
tenant-owned table, purge participant or product purge code exists, and
`tests/support.PURGE_COVERED_TABLES` stays empty.

**Why the documents and the module policy conflict:** SaaS-OS documents
the participant interface as the consumer's way in (MULTI-TENANCY.md
l.53, CONSUMER-GUIDE l.406-423, the scaffold and reference consumer),
while its own update policy (`infra/update/policy.py`) classifies the
module as INTERNAL and `core.tenancy` does not export it. This product's
import rule (CLAUDE.md §3) follows the module policy.

**Operator rule (to go into the purge runbook):** this product's tenants
are never purged with `--no-product-participants`. No product-side check
can stop an operator who bypasses product participants explicitly; the
rule is procedural, not technical.

**Acceptance criteria for resuming tenant-table work (gate G1):**
1. A SaaS-OS release exports the participant protocol and a registration
   function (or equivalent) from a public package, documented for
   consumers.
2. The owner approves moving the pin to that release (new K3 decision),
   with the usual upgrade checks.
3. `crm_app/purge.py` registers one participant through that public API
   in every process that can purge (`create_app()`, the worker, and the
   operator command's `--setup`).
4. The participant deletes child tables first, then re-reads every table
   in the manifest and raises if any row for the tenant remains.
5. Integration tests pass: a purge of a test tenant leaves zero product
   rows; a failing participant leaves PURGING with a `tenant.purge_failed`
   audit row naming it; a re-run completes; the coverage guard lists every
   tenant table.

The upstream request draft is in Appendix A (not sent).

#### Superseded proposal (kept for the record)

The draft recommendation offered a narrow, temporary import exception
with these terms; the owner did not approve it:

- **Module and symbol:** `saas_os.core.tenancy.purge_participants.default_registry`
  only. The participant class satisfies the runtime-checkable protocol
  structurally and imports nothing else from that module.
- **Why the public API is insufficient:** §9.2 answers 1, 2 and 7.
- **Isolation:** one product module, `crm_app/purge.py`, with a
  `register()` setup function used by `create_app()`, the worker and
  `saas-os-operator purge-tenant --setup crm_app.purge:register`.
  `tests/unit/test_import_surface.py` gains a file-specific allowance for
  exactly that module and symbol; any other use still fails.
- **Making success honest:** the participant deletes child tables first
  and then re-reads every manifest table, raising if any row for the
  tenant remains, so Core cannot record PURGED while manifest data
  remains. The integration guard (`test_every_tenant_table_is_covered_by_tenant_purge`)
  fails if a tenant table is missing from the manifest. Remaining gaps
  that code cannot close: an operator using `--no-product-participants`
  (runbook rule: never for this product) and a process that calls
  `purge_tenant` without registering (registration in every entry point,
  tested).
- **Required tests:** a purge of a test tenant leaves zero product rows;
  a failing participant leaves PURGING with a `tenant.purge_failed`
  audit row naming it; a re-run completes; a participant finding leftover
  rows raises; the operator command with `--setup crm_app.purge:register`
  registers exactly one participant; product writes after DELETED are
  refused.
- **Upgrade risk:** the module is internal; every pin move must re-verify
  its symbols (added to the K3 upgrade checklist).
- **Removal condition:** the first approved pin whose `saas_os.core.tenancy`
  exports the registration; the exception is removed in that same
  change.

**Until gate G1's acceptance criteria are met, Phase 2 creates no
tenant-owned table.** The S2 guards enforce this in tests.

### 9.5 Design rules that follow [I/R]

- Product tables must not hold a `NO ACTION` foreign key to Core tables
  that purge deletes (`tenant_memberships`, `roles`, `invitations`, …):
  Core deletes those before participants run, so such a key would make
  purge fail on every retry. Reference them by plain ID, or reference
  `core.tenants` and `core.users`, which are kept.
- Product writes take `lock_open_tenant(session, tenant_id)` in the write
  transaction; product jobs run inside `tenant_job_session`.

## 10. Frontend framework comparison (P-6 stays open)

The Claude Design prototype runs on React 18 through the design tool's
own runtime; that is not a reason to choose React. Versions below are
not verified for this plan [U]; licences must be confirmed before
adoption.

| Criterion | React SPA (Vite, TanStack Router + Query, React Aria Components, react-intl, React Hook Form + Zod) | Next.js (React, SSR) | Vue SPA (Vite, Vue Router, TanStack Query for Vue, vue-i18n, VeeValidate, Reka UI) | Nuxt (Vue, SSR) |
| --- | --- | --- | --- | --- |
| Accessibility | Strongest headless primitives (React Aria: focus, keyboard, ARIA patterns) | Same libraries | Good (Reka UI); smaller ecosystem of audited primitives | Same as Vue |
| i18n | react-intl (ICU messages, plural, dates, currency) | Same, plus routing locales | vue-i18n (mature, ICU-like) | Built-in module |
| Routing / structure | Type-safe file or code routes; per-module code splitting | Built-in; server components add concepts | Vue Router, mature | Built-in |
| FastAPI integration | Typed client generated from OpenAPI; same-origin static hosting keeps SaaS-OS cookie and Origin rules simple | Adds a Node server between browser and API; cookie/Origin handling must be re-checked against ADR-0044 | Same as React SPA | Same concern as Next.js |
| Forms / validation | Mature; schema shared with generated types | Same | Mature | Same |
| Server state | TanStack Query (cache, invalidation, pagination) | Same | TanStack Query for Vue / Pinia | Same |
| Design system | Large component and token tooling | Same | Good | Same |
| Testing | Vitest + Testing Library + Playwright + axe | Same, plus server tests | Same tooling | Same |
| Operations | Static assets only | Second runtime to deploy, patch and secure | Static assets only | Second runtime |
| Developer workflow | Largest hiring and AI-tooling familiarity | Same | Simpler mental model | Simpler, opinionated |

**Recommendation (awaiting explicit approval) [R]:** a **React SPA built
with Vite**, served same-origin with the API, using TanStack Router and
Query, React Aria Components for accessibility, react-intl for
localisation and a typed client generated from the FastAPI OpenAPI
schema. SSR frameworks are not recommended: the app is behind sign-in,
SEO is irrelevant, and a Node server adds a second runtime and a new
place to get cookie and same-origin rules wrong. Vue SPA is a credible
alternative with a simpler model; React is preferred for its
accessibility primitives and ecosystem depth. Adding Node tooling is a
new major framework and needs approval (CLAUDE.md §9).

## 11. Implementation sequence and dependencies

| Step | Work | Depends on | Can start |
| --- | --- | --- | --- |
| S1 | Permission catalogue and role templates in code, inert (no registration, no grants) | — | **Done 2026-10-21** (see below) |
| S1b | Register the granted catalogue in the migration step (`crm_app.permissions.PERMISSIONS` = `crm_app.roles.GRANTED`) | Q6 | **Done 2026-10-21** |
| S2 | Structural schema guards (done); app-role and two-tenant fixtures, route-policy matrix test (with the first tables and routes) | — / S5 | **Guards done 2026-10-21**; rest with S5, S7 |
| S3 | Read-only workspace routes (done); membership and role routes wait for G-LOCK | S1b | **Partly done 2026-10-21** (see below) |
| S4 | Purge participant module, manifest and purge integration test | **G1** (purge decision) | After G1 |
| S5 | First tenant-owned tables: `workspace_settings`, `member_profile`, `invitation_intent` with RLS, grants, lock fence; directory index table | S2, S4, **G5** (directory review) | After G1 and G5 |
| S6 | `crm-app-provision` command with dry run | S1, S5, **G2** (provisioning approval + local validation) | After G2 |
| S7 | Membership and role management routes; product last-Owner guard | S3, S6 | After S6 |
| S8 | Workspace directory and switcher API; reconciliation job | S5, S7 | After S7 |
| S9 | Invitations: intent, send, two-step role confirmation | S7, **G3** (email provider) for real delivery; **G4** (Q4/Q5 decisions) | Code behind a disabled flag after G4; enable after G3 |
| S10 | Workspace settings API (locale, time zone, currency) | S5 | After S5 |
| S11 | Security review, full CI evidence, Phase 2 report | S1–S10 | Last |
| F1 | Frontend shell and Phase 2 screens | **G6** (P-6 approval) and the missing design states | Not in Phase 2 exit criteria; after G6 |

### 11.1 Status of S1–S3 (2026-10-21)

- **S1 (done):** `src/crm_app/roles.py` holds the approved catalogue
  (`PLATFORM_PERMISSIONS`, `PRODUCT_PERMISSIONS`; 47 pairs), the four
  `ROLE_TEMPLATES`, `UNGRANTED` (8 pairs no role holds) and `GRANTED`
  (39 pairs). It imports nothing from SaaS-OS.
- **S1b (done):** `crm_app.permissions.PERMISSIONS` is now `GRANTED`, so
  `crm-app-migrate` registers those 39 pairs with
  `saas_os.core.rbac.register_permission` (PUBLIC). Verified at the pin:
  registration is an idempotent upsert into the global, non-RLS
  `core.permissions` catalogue that "grants nothing" (CONSUMER-GUIDE §8;
  `core/rbac/service.py:391-430`); the runtime role may write it through
  SaaS-OS's default privileges on `core`
  (`infra/db/migrations/versions/81ac56902107_create_core_rbac_tables.py`,
  module docstring). No role is created and no workspace receives a
  permission. The 8 ungranted pairs are not registered by the product.
  `register_capability_permissions()` is not called: the product mounts
  none of the SaaS-OS capability routers.
- **S2 (guards; corrected 2026-10-21):** `tests/integration/test_tenant_table_guard.py`
  reads `pg_namespace`, `pg_class`, `pg_attribute` (skipping dropped
  columns) and `pg_policy`, and checks privileges with
  `has_table_privilege` for the configured runtime role. The earlier
  version read `information_schema.role_table_grants` and `.columns`,
  which only show rows visible to the querying role and grants it made or
  received. A grant by another role, such as a future schema-owner role,
  would have been invisible, and the guard would have passed. The rules
  are pure functions in `tests/catalog_rules.py`:
  - exactly SELECT/INSERT/UPDATE/DELETE, and no TRUNCATE/REFERENCES/TRIGGER;
  - RLS enabled and forced;
  - exactly the `tenant_rls_statements` policy shape: one permissive
    policy for every command and role, scoped by `app.tenant_id`, with no
    WITH CHECK;
  - purge coverage.

  `tests/unit/test_catalog_rules.py` tests each rule, including that an
  unchecked privilege fails rather than passes. The guard also fails if
  the `crm_app` schema or the runtime role is missing, and refuses views
  and foreign tables in `crm_app`. Platform tables are never counted:
  every product query is restricted to the `crm_app` schema. Because no
  product table exists, three self-tests run the same queries and rules
  against SaaS-OS's `core.role_permissions` (created with
  `tenant_rls_statements`), so the guard is shown to detect what it must
  rather than pass on empty results. The unit `test_schema_guard.py` and
  the shared `migrated` fixture are unchanged. None of this proves runtime
  isolation.
- **S3 (partly done):** `src/crm_app/api/workspaces.py`, mounted by
  `create_app()`:
  - `GET /v1/workspaces/{tenant_id}` → `require_permission("crm_app.workspace", "read")`;
    returns the workspace's id, name and status from `core.tenancy.get_tenant`.
  - `GET /v1/workspaces/{tenant_id}/members` → `require_permission("membership", "read")`;
    returns memberships (id, user id, status, role names) with `limit`
    (1–200) and `offset`, from `list_tenant_members`, `list_roles` and
    `list_membership_roles`. Member names and emails are not shown:
    SaaS-OS stores none and the product profile table waits for G1.

  **Member visibility (2026-10-21):** revoked memberships, which are
  terminal, are never listed. Suspended ones are listed only to callers
  holding `membership:reactivate` (Owner and Admin under §5.2), decided by
  a backend `can()` check for the calling member. Everyone else sees
  active memberships only. The rule is `crm_app.domains.membership.visible_statuses`;
  its status values are checked against the pinned SaaS-OS enum
  (`tests/unit/test_membership_visibility.py`). No personal data is
  returned (user IDs only), and the role matrix is unchanged.

  Both are read-only and return real data only. Each uses the workspace
  from `context.tenant_id`; unknown, foreign or closed workspaces get the
  platform's uniform 404, a member without the permission gets 403.
  Evidence: `tests/unit/test_routes.py` builds the application and runs
  SaaS-OS's own `assert_route_policies`, which reports exactly these two
  routes with exactly these permission policies, no API-key access and
  no non-GET product route (passed). `tests/integration/test_workspace_routes.py`
  with `workspace_route_probe.py` covers allowed, 403, 404 for outsiders,
  other workspaces and unknown IDs, 401, the member list's contents and
  page bounds; **not run** (local services stopped).

  **Deferred:** every route that changes memberships, roles, invitations,
  Owners or workspace settings (needs G-LOCK, and for invitations G3/G4);
  workspace settings and member profiles (need tenant tables, G1);
  workspace deletion and purge (operator-only by design, never a route).

### 11.2 S6 and S7 (2026-10-21, uncommitted, validated locally)

- **S6, provisioning command:** `src/crm_app/provision.py`
  (`python -m crm_app.provision`), implementing the §7.4 sequence with
  public SaaS-OS functions only. Validated by `tests/integration/test_provision.py`
  (8 tests against `crm_app_test`):
  - a dry run changes nothing;
  - a run creates the workspace (active), the four roles with exactly the
    template grants, and one active Owner;
  - a re-run performs nothing;
  - runs interrupted after workspace creation, after activation and after
    partial role creation are completed;
  - a same-name workspace with another member is refused and left
    unchanged;
  - output holds identifiers only.

  The production confirmation flag is enforced before any database
  access. **No real workspace has been provisioned.**
- **S7, membership and role routes:** `src/crm_app/api/members.py`:
  - `POST …/members/{membership_id}/roles` (`membership_role:create`);
  - `DELETE …/members/{membership_id}/roles/{role}` (`membership_role:delete`);
  - `POST …/suspend`, `…/reactivate`, `…/revoke` (`membership:*`).

  Rules:
  - only Owners touch Owners or grant the Owner role;
  - nobody changes their own membership or roles, except an Owner
    stepping down;
  - Owner changes need `confirm_owner_change`;
  - the last active Owner can never be removed, demoted, suspended or
    revoked.

  Validated by `tests/integration/test_owner_protection.py` (8 tests):
  - 15 rounds (5 each of revoke, suspend and Owner-role removal) of two
    Owners targeting each other simultaneously: exactly one request
    succeeded each time, and the database held exactly one active Owner
    afterwards;
  - transfer (grant, then step down) works;
  - ten refused cases leave the persisted roles and Owners unchanged;
  - an Admin manages ordinary members;
  - another workspace's membership is a 404.

  `tests/unit/test_membership_visibility.py` covers the rule's branches;
  `tests/unit/test_routes.py` the seven route policies.
- **Remaining limits:**
  - concurrency was tested with two competing requests in one process;
  - paths outside the product are covered only by the operator rule
    (§5.4);
  - under contention the lock wait is bounded at 5 s (409 `busy`);
    pool-exhaustion behaviour under heavy load is not load-tested.

Next work needs: G1 (tenant tables). G2 needs owner authorization before
any real workspace is provisioned.

## 12. Security and privacy considerations

- Isolation is enforced twice: permission checks in the API and forced
  RLS in PostgreSQL. A missing tenant setting yields zero rows.
- Runtime database role: no superuser, no BYPASSRLS, DML grants per
  table only (existing `validate_application_role` check at startup).
- Migration role: owns schema changes only; production needs a
  dedicated schema-owner role (already recorded in `PROGRESS.md`).
- Tenant identifiers from clients are never trusted; uniform 404 for
  unknown or foreign workspaces.
- Unique constraints and indexes on tenant tables include `tenant_id`;
  foreign keys between product tables include `tenant_id` where possible
  (composite) so a row cannot reference another tenant's row [R; SaaS-OS
  guidance is U].
- Jobs: `register_tenant_job`, handlers inside `tenant_job_session`,
  idempotent through `run_idempotent` or unique keys; never read the
  tenant from payload data.
- Logs and audit: IDs only; no tokens, invitation links, email bodies or
  personal data; the SaaS-OS redaction is a key denylist only.
- Personal data in Phase 2: member display name and email, invitee email.
  Covered by purge (§9) and needing a product erasure path (P2-D,
  SaaS-OS has none for product data).
- Same-origin rule (ADR-0044) applies to all cookie-authenticated
  mutations, including product routes.
- `AuthorityNotAuthorizedError` is not publicly exported; product code
  must not import it. Handle refusals through the HTTP layer's mapped
  errors or a broad, documented catch at the service boundary [R];
  request an upstream export.
- Global foundations: timestamps `timestamptz` in UTC; workspace locale
  (BCP 47), time zone (IANA), default currency (ISO 4217) validated
  server-side; per-member locale and time-zone overrides; phone numbers
  stored in E.164 when introduced (Phase 3). Jurisdiction-specific
  consent, retention and subject-access work stays in later phases.

## 13. Acceptance criteria and test plan

No new test has been run for this plan. Every item below must pass in CI
on the exact commit evaluated before Phase 2 is complete.

| Deliverable | Acceptance criteria | Tests |
| --- | --- | --- |
| Permissions and roles | Four roles exist in every provisioned workspace with exactly the §5.2 grants | Unit: catalogue and templates; integration: inspect grants after provisioning |
| Route policies | Every route declares one policy; every role gets exactly the §5.2 outcome | Matrix test: each route × each role × own/foreign workspace |
| Escalation | Admin cannot assign Owner; nobody can raise their own role; Read-only cannot write | Integration negative tests |
| Last Owner | Removing, demoting, suspending or revoking the last Owner returns 409, including two concurrent attempts | Integration + concurrency test |
| Tenant isolation (RLS) | As the runtime role: no tenant setting ⇒ 0 rows; tenant A cannot read, update, delete or insert B's rows; joins and direct IDs reveal nothing; a reused pooled connection carries no tenant setting | Integration negative tests per tenant table |
| RLS coverage | Every `crm_app` table with `tenant_id` has RLS enabled and forced, the policy, the grants and a purge-manifest entry | Catalog-scan test |
| Jobs | A job for tenant A cannot touch B; a duplicate delivery has no double effect | Integration tests with two tenants |
| Provisioning | Dry run changes nothing; a real run creates the §7.3 structure; a rerun is a no-op; a crash at each step leaves an inert, resumable state | Integration tests with injected failures |
| Workspace directory | Lists only workspaces with an ACTIVE membership; revoked or suspended entries disappear; listing never grants data access | Integration tests |
| Workspace context | Unknown, foreign and closed workspaces return the same 404; suspended member gets 403 | Integration tests |
| Invitations | Token never logged or stored raw; expiry, revocation and one-time use hold; concurrent acceptance yields one membership; no "sent" without `accepted=True`; no provider ⇒ refusal (or labelled manual link); role applied only after Owner/Admin confirmation | Integration tests with `FakeEmailProvider` (success and failure); log-scan test |
| Purge | After a successful purge of a test tenant, zero product rows remain for it; a failing participant leaves PURGING and an audit entry; rerun completes | Integration test calling `purge_tenant` (registry override allowed in tests) |
| Settings | Locale, time zone and currency validated; times stored in UTC | Unit + integration |
| Audit | Each membership, role, invitation and provisioning event has an audit row without personal data | Integration tests |
| CI | All existing gates plus the above pass on GitHub Actions for the exact commit | CI run evidence |

### 13.1 Test status (2026-10-21, local, Windows)

| Check | Result |
| --- | --- |
| `uv lock --check` | PASS |
| `ruff format --check .` (43 files) | PASS |
| `ruff check .` | PASS |
| `pyright` | PASS (0 errors) |
| `lint-imports` | PASS (2 kept, 0 broken) |
| `pytest tests/unit` | PASS (83 on 2026-10-21 after S6/S7; 77 before), including `test_roles.py`, `test_schema_guard.py`, `test_routes.py`, `test_catalog_rules.py`, `test_membership_visibility.py` |
| `pytest tests/integration` (33 tests, including `test_tenant_table_guard.py` and `test_workspace_routes.py`), `.env.test` exported, local PostgreSQL 16 and Redis 7 started by the owner | **PASS** (33 passed, 0 skipped; 49 after S6/S7, all modules, `crm_app_test`) |
| `CRM_APP_IDENTITY_TEST=1 pytest tests/identity` (local ZITADEL) | **PASS** (1) |
| `detect-secrets-hook` (all tracked and new files) | PASS |
| `pip-audit` (hashed export, SaaS-OS excluded) | PASS (no known vulnerabilities) |
| `git diff --check` | PASS |

The integration run verified, against a real database:
- that `crm-app-migrate` (run twice) registers the 39 pairs as the
  runtime role (`test_the_migration_step_registered_every_granted_permission`
  reads `core.permissions`);
- that every product table is tenant-owned or explicitly declared global
  (`tests/support.GLOBAL_TABLES`, empty), so no table can escape the RLS
  and purge checks by lacking a `tenant_id` column;
- the S2 guards, including their self-tests on `core.role_permissions`;
- the S3 route behaviour: 200 for permitted members, 403 for a member
  without the permission, the same 404 for outsiders, other workspaces
  and unknown IDs, 401 without a session, 422 for an oversized page, and
  the member-visibility rule.

Still unproven: runtime RLS isolation of product data and purge
correctness (they need tenant tables, gate G1), and Owner protection
under concurrency (G-LOCK).

## 14. Approval gates

| Gate | Blocks | Needs |
| --- | --- | --- |
| G0 | All Phase 2 implementation | Owner approval of this plan |
| G1 | First tenant-owned table (S4, S5) | The acceptance criteria in §9.4: a SaaS-OS release with a public purge-registration API and an approved pin move (Q-purge decided 2026-10-21: upstream first) |
| G-Q6 | Registering the catalogue (S1b) and any route (S3, S7) | **Passed 2026-10-21** (Q6 approved) |
| G-LOCK | Any route that removes, demotes, suspends or revokes an Owner, or assigns Owner (S7) | The §5.4 concurrency tests passing against a real database (needs the local services or CI), and approval of the operator rule for paths outside the product |
| G2 | Automated role setup / provisioning command (S6) | Owner approval of Q1 and a separately approved local validation run |
| G3 | Real invitation delivery | Email provider and credentials approved (Q3); may involve cost |
| G4 | Invitation implementation (S9) | Decisions Q4 and Q5 |
| G5 | Directory index table (S5, S8) | Security review of §6.4 |
| G6 | Any frontend work | P-6 approval and the missing design states |
| G7 | Permissions for existing workspaces in Phases 3+ | Decision on Q2 |
| G8 | Phase 2 completion | Security review and CI evidence (S11) |

## 15. Open decisions for the owner

Decided 2026-10-21: Q6 (approved), Q-purge (upstream first, no
exception), Q1 (design direction only), S1b and S3 (within supported
APIs). Still open:

1. **Q-purge follow-up:** authorize sending the upstream request in
   Appendix A (no external action has been taken).
2. **Q1 → G2:** authorize implementing the provisioning command against
   §7.4, and separately a local validation run.
3. **Q2 (G7):** authorize sending the upstream question in §7.5; until
   answered, no grants to existing workspaces.
4. **G-LOCK:** allow the local services to be started (or rely on CI) so
   the Owner-protection concurrency tests can run before S7; approve the
   operator rule that `erase-user` and other operator commands are not
   used to remove a workspace's last Owner.
5. **Q3 (G3):** which transactional email provider, and when?
6. **Q4 (G4):** manual invitation link while no provider is configured,
   or no invitations until one is?
7. **Q5 (G4):** two-step role confirmation after acceptance?
8. **P-6 (G6):** frontend framework; recommendation in §10.

Unchanged and still open elsewhere: multi-region hosting and data
residency (K5.1); ZITADEL v4.19.5 confirmation (P-4); product erasure and
export policy (P2-D).

## 16. Recommended next action

1. Let the integration suite run (start the local services, or push for
   CI) so the S1b registration, the S2 guards and the S3 route tests run
   for the first time.
2. Authorize sending the two upstream requests (Appendix A and §7.5).
3. Then decide G2 (provisioning command) and G-LOCK (Owner routes).

## Appendix A — Upstream request draft (not sent)

Prepared 2026-10-21 for the SaaS-OS repository. **Not sent; no issue or
pull request exists.** Sending it needs separate authorization.

**Title:** Export the tenant-purge participant registration through a
public API

**Context.** A consuming product must remove its own tenant-scoped data
when `saas_os.core.tenancy.purge_tenant()` runs. SaaS-OS documents the
mechanism for this: a product implements `TenantPurgeParticipant` and
registers it (MULTI-TENANCY.md "Core/Product purge responsibility",
CONSUMER-GUIDE §11 "Register it in every process that can run
`purge_tenant()`", the consumer scaffold and the reference consumer).

**Problem.** The protocol and the registry
(`TenantPurgeParticipant`, `TenantPurgeParticipantRegistry`,
`default_registry`) live only in
`saas_os.core.tenancy.purge_participants`, which `saas_os.core.tenancy`
does not export. SaaS-OS's own update policy (`saas_os/infra/update/policy.py`)
classifies everything under `saas_os/core/*` except `__init__.py` as
INTERNAL. A consumer that follows the public-surface rule therefore
cannot register a participant, and the documented alternative
(`purge_tenant(registry=...)`) is described as "an override for test
isolation only". The documentation and the module policy disagree.

**Request.** Export, from `saas_os.core.tenancy` (or another public
package), the participant protocol and a registration function, for
example `register_purge_participant(participant)`, and document it as the
supported consumer API. Keep `saas-os-operator purge-tenant --setup`
working with it.

**Expected behaviour and compatibility.**
- Existing imports of `saas_os.core.tenancy.purge_participants` keep
  working for at least one release (re-export, not a move).
- Registration semantics unchanged: in-process, ordered, duplicate names
  refused.
- `purge_tenant()` behaviour unchanged: participants run once after Core's
  steps under the PURGING fence; a failure leaves PURGING and is audited.

**Tests we would expect upstream.**
- The public symbols are importable from the public package and listed in
  its `__all__`.
- A participant registered through the public function runs during
  `purge_tenant()` and the operator command with `--setup`.
- The public-surface classification test treats the new export as
  PUBLIC_API.

**Related (separate requests, same audience):** a sanctioned way to add a
newly registered permission to existing tenants' roles (§7.5), and a
public export of `AuthorityNotAuthorizedError` (§7.5).
