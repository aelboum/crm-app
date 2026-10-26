# Self-Service Signup — Audit, Plan and Launch Gates

**Decision:** S-1 (`DECISIONS.md`), approved by the owner 2026-10-24 as the
direction for implementation planning. It supersedes P2-C's exclusion of
public workspace creation.

**Status (2026-10-25):** Stages A, B and C done locally.
- The signup settings and kill switch (A2) exist and are tested, with the
  owner's limits (S-1.1).
- The L4 investigation (A1) is done; L4 is reduced, not closed (§5).
- Local ZITADEL registration, email verification and Mailpit (A4) are
  verified in a browser (§5a).
- The signup backend (B, C) is built and verified: option A for the signup
  table and the counting rule (S-1.2, §4b).

The signup screens (Stage D) are built and tested locally (§4c). Signup is
off everywhere and refused in production by start-up validation.

**Design reference:** `LeadStack Signup.dc.html` (outside the repository,
`DESIGN-FIDELITY.md`). It is a reference only. It is never served or
embedded. Only its account step is in scope (§3).

## 1. Audit baseline (read-only, 2026-10-24)

Re-verified on 2026-10-24 before this plan:
- `main` = `origin/main` = `f3e08f5`, and CI was green.
- The SaaS-OS pin is `b03d87a5272924d1e413c144dc5c3b41ac430580` (v0.5.0) in
  `pyproject.toml`, `uv.lock` and the installed package's `direct_url.json`.

Every fact below was read in code or docs, unless marked *inferred*.

**Identity: ZITADEL v4.19.5 with Login V2, same origin (D-IDL)**
- Self-registration is switched off by `deploy/local/configure-zitadel.py`
  (instance login policy: `allowRegister=false`; ZITADEL's own default is
  on). Login V2 refuses registration server-side when the policy is off
  (ZITADEL `apps/login/src/lib/server/register.ts` at v4.19.5). With a
  password, registration continues the same OIDC request back to the
  application.
- Email verification is enforced by Login V2 only when its container sets
  `EMAIL_VERIFICATION=true`. `deploy/local/compose.yaml` does not set it.
  ZITADEL sends the code itself; it expires after 1 hour by default.
- ZITADEL has no SMTP provider configured locally, so it cannot send
  verification or password-reset email today. Mailpit (profile `mail`) only
  receives LeadStack's own invitation email.
- Password policy: ZITADEL defaults (8 characters, upper case, lower case,
  number and symbol). Lockout: 5 password and 5 OTP attempts.
  `ignoreUnknownUsernames=true`, `forceMfa=false`, external identity
  providers off (D-IDL.1).
- ZITADEL offers no CAPTCHA in Login V2 (open upstream request) and no
  per-address limit on registration.

**SaaS-OS at the pin**
- No registration, email verification, password reset or identity-provider
  user management exists.
  - `core/identity/provider.py` excludes user administration.
  - `core/email` lists verification and reset as non-goals.
  - ADR-0026, an embedded login, was rejected.
- Every successful sign-in creates a `core.users` row (issuer, subject; no
  personal data) through `get_or_create_user_for_external_identity`.
- The session keeps `verified_email` only when the provider says it is
  verified. Product code reads it through the public
  `saas_os.api.dependencies.get_current_session`, as invitation acceptance
  does.
- `create_tenant(name, *, parent_id=None, caller)` accepts
  `SystemCaller(PROVISIONING)` for a root tenant. New tenants are `pending`;
  provisioning may move them `pending → active` only. Principals may act in
  `pending` and `active` tenants (`core/tenancy/lifecycle.py`). Tenant names
  are not unique.
- `assign_first_role_for_new_tenant` performs no authorization check. Its
  docstring restricts it to tenant bootstrap.
- `add_tenant_membership`, `create_role` and `grant_permission` accept
  `PROVISIONING`.
- `tenant_bootstrap.bootstrap_first_tenant` is name-keyed and grants only
  `tenant:read_status`, so it is unsuitable for public signup (*inferred*).
- ADR-0040 assigns sign-up, and its abuse controls, to the product.
- ADR-0045 §5a forbids SaaS-OS's own routes from using `SystemCaller`, and
  accepts that a product's sign-up endpoint will.
- ADR-0043: the last-administrator invariant protects administrators but
  never creates one. An Owner must hold `membership_role:create` to be one.
- `run_idempotent`, `audit_log.record` and `outbox.append_event` all require
  an existing tenant (foreign key to `core.tenants`). They cannot be used
  before the workspace exists.
- `enforce_rate_limit(key, config=...)` takes any key and fails closed with
  503 when Redis is down.
- `resolve_client_address(request, trust_proxy_headers=...)` is in the
  public `saas_os.api.auth.config`.
- Deleting a `pending` tenant needs a person with `platform.tenant:delete`;
  provisioning cannot. No retention job exists for abandoned tenants or
  users.

**LeadStack today**
- `crm_app.provision` is an operator command only. It uses the steps above
  with `PROVISIONING` and the four role templates (`roles.py`): Owner
  includes `membership_role:create` and `crm_app.owner:manage`.
- Order: create → activate → user → roles and grants → membership → Owner
  → `can()` check. Each step is its own transaction, find-or-create, and
  resumable (`tests/integration/test_provision.py`).
- It activates *before* the roles exist, which signup must not copy.
- It does not create a `workspace_settings` row; the defaults are read when
  no row exists.
- Invitations follow Q4/Q5.
  - SaaS-OS stores only the token's hash, expires it after 7 days and
    allows it once.
  - Acceptance needs the session's verified email and grants a membership
    with no role. It never creates a tenant.
- Product tables are tenant-owned with forced RLS. The guard
  (`tests/integration/test_tenant_table_guard.py`) also allows *declared
  global* tables (`tests/support.py` `GLOBAL_TABLES`, empty today).
- Security review findings that bear on public registration
  (`PHASE2-SECURITY-REVIEW.md`):
  - L4 (pre-login rate-limit key; §5 below);
  - L5 (route limit per workspace, not per actor);
  - I1 (ZITADEL console on the application origin);
  - I2 (12-hour sessions, no idle timeout; sign-in logged, not audited);
  - R2-I1 (directory timing reveals roughly how many workspaces exist).

## 2. Capability matrix: LeadStack, SaaS-OS, ZITADEL

| Capability | Owner | Reuse or build |
| --- | --- | --- |
| Credentials, registration form, passkeys, email verification, password reset, lockout, MFA | ZITADEL (Login V2) | Configure only |
| User row, session, `verified_email`, `/auth/*`, sign-out | SaaS-OS | Reuse unchanged |
| Tenant lifecycle (create, activate) | SaaS-OS | Reuse `create_tenant`, `transition_tenant_status` |
| Roles, grants, membership, first Owner | SaaS-OS primitives with LeadStack role templates | Reuse; share `provision.py`'s steps |
| Rate limiting | SaaS-OS limiter | Reuse with signup keys |
| Signup state, resume, limits, kill switch | LeadStack | Build |
| Signup screens and first-run experience | LeadStack | Build |
| Abuse controls (ADR-0040) | LeadStack and the edge | Build and deploy |
| Invitations | SaaS-OS with LeadStack role intent | Unchanged |
| Email: verification and reset | ZITADEL's SMTP | Configure (launch gate LG-1) |
| Email: invitations | SaaS-OS `core.email` | Unchanged |
| Audit before a tenant exists | Nothing available | Structured log events (as SaaS-OS does for sign-in); tenant audit from creation onward |

## 3. Approved v1 journey (S-1)

1. The visitor opens the LeadStack sign-in screen and chooses **Create
   account**.
2. That starts the existing `/auth/login`. The visitor registers on
   ZITADEL's own pages, which handle credentials, the verification code and
   any password reset. LeadStack never receives a password.
3. Back in LeadStack with a session, workspace creation requires
   `verified_email` on the session (in addition to ZITADEL's own
   enforcement).
4. The person enters a workspace name.
5. LeadStack provisions the workspace (§4), makes the person its Owner,
   verifies the Owner's permissions, and only then activates it.
6. The person enters the workspace.

**Out of scope for v1:**
- agency or business choice;
- templates, branding or phone numbers;
- inviting a team during onboarding;
- trial or plan promises;
- Google or Microsoft sign-in;
- anything else from the prototype not listed above.

Existing invitation joining is unchanged. Neither sign-in nor invitation
acceptance ever creates a workspace.

**A verified person who already belongs to workspaces** may create another,
within the per-user and platform limits.

## 4. Architecture

**Endpoints (planned, Stage C):**
- `POST /v1/signups` with `Idempotency-Key`; body `{ "workspace_name" }`.
- `GET /v1/signups/current`.

Both require a session with `verified_email`. Identity comes only from the
session. Added in Stage D: `GET /v1/signups/status`, public, answering only
`{"enabled": bool}` from the same kill switch; it changes nothing and does
not open the other two routes (§4c). The body has no field for user, parent tenant, role or authority:
unknown fields are refused (422) and nothing is echoed back.

**Provisioning (shared service, Stage B).** Each step is find-or-create and
recorded on the signup row before the next step starts:

1. Under a per-user advisory lock, create or find this user's open signup
   row. A partial unique index on the user's open signup ensures there is
   only one.
2. `create_tenant(name, parent_id=None, caller=SystemCaller(PROVISIONING))`.
   Store the tenant ID on the row in the same step, so a workspace is never
   orphaned.
3. Create the roles and grants from `ROLE_TEMPLATES`.
4. `add_tenant_membership`.
5. `assign_first_role_for_new_tenant` with the Owner role.
6. `can()` check of `membership_role:create` and `crm_app.owner:manage`.
7. `transition_tenant_status(pending → active)`, last.
8. Mark the signup complete.

Notes on provisioning:
- A partially provisioned workspace stays `pending`.
- SaaS-OS lets principals act in `pending` tenants, so `pending` is not a
  barrier on its own. Before step 6 the only member is the person signing
  up, who has no role, so the permission checks already refuse everything.
  Stage B must prove this with a test.
- The operator command keeps its behaviour and output (its
  activate-then-seed order is resumable and covered by tests). Whether it
  moves to activating last is decided in Stage B, with tests.

**Retries, races and limits:**
- The same key returns the same signup.
- Another request while a signup is open returns the open signup.
- Concurrent requests serialise on the advisory lock and the unique index.
- The limits below are checked under the same locks, so neither parallel
  requests, retries nor different workspace details can exceed them.

**Limits (decision S-1.1).** Both are enforced on the server, configurable,
and fail closed. They are abuse ceilings, not targets or guarantees, and
are adjusted once legitimate use and abuse have been observed.

- **`SIGNUP_MAX_WORKSPACES_PER_USER`, default 5.**
  - **What counts:** the workspaces this user holds through signup, plus the
    user's open (unfinished) signup. Workspaces joined by invitation do not
    count. A workspace that is deleted or purged stops counting.
  - **When it is checked:** under the per-user advisory lock, before the
    tenant is created. Concurrent requests, idempotent retries and
    different workspace names all meet the same count.
- **`SIGNUP_MAX_ATTEMPTS_PER_24H`, default 100.**
  - **What counts as an attempt:** every authenticated `POST /v1/signups`
    while signup is on that passes the per-user and per-client rate limits
    and is not itself refused by this cap. It is counted before anything
    else is checked, so these all count:
    - an unverified email;
    - an invalid name;
    - a refusal by the per-user limit;
    - an idempotent replay;
    - a provisioning failure.
  - **Not counted:**
    - requests while signup is off;
    - unauthenticated requests (401 before the handler);
    - requests refused by a rate limit or by the cap itself. Counting those
      would let one client hold the cap closed indefinitely; the rate
      limits bound how fast any one user or address can feed the counter.
  - **Reset behaviour:** a rolling window, not a calendar day. An attempt
    stops counting exactly 24 hours after it was recorded, so capacity
    frees up gradually.
  - **Why not the SaaS-OS limiter:** its counter is fixed-window
    (`saas_os.infra.ratelimit.limiter`: "Fixed-window counter, not a
    sliding-window"), so it cannot provide a rolling window. The count
    therefore needs a product-side store: a timestamp-only attempt record
    (no personal data) counted under a global advisory lock. Postgres is
    the preferred store; a Redis sorted set is the alternative (Stage C).
  - **Unavailability:** if the counter store is unavailable, the request is
    refused (503) and nothing is provisioned.
- **Confirmed by the owner (S-1.2, 2026-10-25):** requests refused by the
  first per-user or per-address rate limit, or only by the cap already
  being reached, are not counted; every request past them counts, even if
  validation, verification or provisioning fails. Check and increment are
  atomic under one advisory lock; an unavailable counter refuses (503).

**Rate limiting.** SaaS-OS limiter keys `signup:user:<id>` and
`signup:client:<address>`, the address from `resolve_client_address`. Both
fail closed (503).

**Signup state record (Stage C; built as migration 0006 after the review
in §4b, which supersedes the proposal below), a proposal that needs the security review
before its migration:**
- One table, `crm_app.signup`, with:
  - `id`, `user_id`, `idempotency_key`, `request_fingerprint`, `state`;
  - `tenant_id` (nullable until step 2);
  - `attempts`, `last_error_code`;
  - `created_at`, `updated_at`, `expires_at`.
- It holds no email, name or workspace name. The name is kept only until
  step 2, then lives on the tenant.
- The table exists before any tenant does, so it cannot carry the tenant
  RLS policy. It would be the first entry in `GLOBAL_TABLES`.
- Access model to decide in Stage C:
  - **Preferred:** forced RLS with a policy on a transaction-local user
    setting (`SET LOCAL`) written only by the signup repository. This needs
    tests for connection reuse, a missing setting and a foreign setting.
  - **Fallback:** no RLS, the runtime role holding exactly
    SELECT/INSERT/UPDATE, and every query scoped by the session's user ID.
- Either way, tests must show one user can neither read nor change
  another's signups through the API or the repository.

**§4a. Signup-table security: investigation (2026-10-24; owner decision
pending).** Facts at the pin and in this repository:

1. Product RLS today is SaaS-OS's `tenant_rls_statements`: one permissive
   policy on `app.tenant_id`, set transaction-locally by SaaS-OS's tenant
   session (`saas_os/infra/db/rls.py`, `session.py`). SaaS-OS sets **no**
   per-user database setting.
2. SaaS-OS exports `tenant_context_exclusion_statements` (public
   `saas_os.infra.db`). It is a forced-RLS policy that makes rows visible
   only in a transaction with **no** tenant context, used for its own
   platform tables. It keeps signup rows out of every tenant-scoped
   transaction, but on its own lets any non-tenant transaction read every
   user's rows.
3. This repository's guard treats every table with a `tenant_id` column as
   tenant-owned: it must have the tenant policy and be covered by the purge
   participant. A table declared global must *not* have `tenant_id`
   (`tests/catalog_rules.py`). The guard also requires exactly
   SELECT/INSERT/UPDATE/DELETE for the runtime role on every product table.
   A signup row that records its new workspace therefore needs a guard
   rule written for this case, not a renamed column to slip past the
   existing rule.
4. A foreign key from a signup row to `core.tenants` would block SaaS-OS's
   purge of that tenant. Signup rows must be removed or detached by the
   purge participant, or reference the tenant without a foreign key.

Options:

| Option | Access model | Trade-offs |
| --- | --- | --- |
| **A (recommended)** | Forced RLS. SaaS-OS's `tenant_context_exclusion_statements` policy, plus a **restrictive** product policy `user_id = current_setting('crm_app.signup_user_id')::uuid`, set transaction-locally by the signup repository from the session's user only. The recovery job sets it per row in its own transaction. Workspace ID column named for what it is, with a new guard rule for "pre-tenant global" tables (exactly these two policies, the CRUD rule, and inclusion in the purge participant). | Defence in depth matching the tenant pattern. Needs tests for connection reuse, a missing setting, a foreign setting and tenant-context exclusion. The setting is application-controlled, like `app.tenant_id`, so it guards against query mistakes, not against compromised application code. |
| B | No RLS; exact privileges; every query scoped by the session's user ID in code. | Simplest, but it is the "casual exemption" S-1 rules out; isolation rests on code review alone. |
| C | No pre-tenant table: create the tenant first and keep the state in a normal tenant-owned table. | Fails the recoverability requirement: a crash between creating the tenant and recording it leaves an orphan workspace no one can find, and "my open signup" needs a query across tenants. |

The platform attempt counter (above) holds timestamps only and no user or
tenant reference. Under option A it uses the exclusion policy alone.

**§4b. Signup-table security: design and verification (Stage C, 2026-10-25).**
The owner chose option A and confirmed the counting rule (S-1.2). The
design was checked against the real transaction model before migration
0006 was written; the migration, guards and tests followed.

1. **Policies on `crm_app.signup`:**
   - forced RLS;
   - SaaS-OS's `tenant_context_exclusion_statements` policy (permissive,
     every command: rows exist only in a transaction with no
     `app.tenant_id`);
   - four **restrictive** policies, one per command, comparing
     `user_id::text` with `NULLIF(current_setting('crm_app.signup_user_id',
     true), '')`:
     - `SELECT`: also allowed with `crm_app.signup_maintenance = 'on'`;
     - `INSERT`: `WITH CHECK` only;
     - `UPDATE`: `USING` and `WITH CHECK`;
     - `DELETE`: `USING` only.

   Comparison is as text, so a missing, empty, malformed or injected value
   matches nothing and never raises.
2. **How PostgreSQL learns who the person is:** SaaS-OS sets no
   per-user setting. `crm_app.signups._as_user()` opens every transaction
   with `set_config('crm_app.signup_user_id', <session user>, true)`
   (transaction-local), and the user comes only from the server-side
   session (`get_current_session`). A unit test pins
   `set_config(..., true)` to that one function.
3. **Refusals:**
   - not signed in: 401 before the handler;
   - signed in without a verified email: 403;
   - no person setting: no rows;
   - another person's setting: their rows only;
   - writes for another person: refused by `WITH CHECK`;
   - any transaction with a tenant: no rows, writes refused, even with
     the person or maintenance setting.
4. **Jobs:**
   - the maintenance command reads due rows with the maintenance flag,
     which allows reading only;
   - it then acts on each row in a transaction scoped to that row's own
     person, so every write passes the same person policy.

   A unit test checks that nothing writes inside a maintenance reader.
5. **The table guard:** global tables are now checked too, not exempted.
   `GLOBAL_TABLES = {signup, signup_attempt}`. Each must have:
   - forced RLS and exactly the exclusion policy;
   - for person-scoped tables (`signup`), exactly the four restrictive
     policies, with the maintenance flag only on reading
     (`global_policy_violations`).

   A global table with `workspace_id` may not reference `core.tenants`
   and must be in `PURGE_GLOBAL_REFERENCES` (`global_reference_violations`).
   The tenant rules are unchanged.
6. **Purge:** `workspace_id` has no foreign key, so SaaS-OS's purge is
   never blocked.
   - After the tenant tables, the purge participant removes the signup
     rows naming the purged workspace outside any tenant context: read
     with the maintenance flag, deleted as each row's own person.
   - It then raises `PurgeIncompleteError` if any remain.
7. **Expired and partly failed signups:**
   - **Interrupted:** a run that stops leaves the row `provisioning`
     with its last step and an error code. It resumes on the person's
     replay or the maintenance command; after 5 runs it is `failed`.
   - **Needs an operator:** a step finding an impossible state
     (`owner_check_failed`, `workspace_has_other_members`) is `failed`
     at once, for operator review.
   - **Crash between `create_tenant` and recording it:** the next run
     adopts the workspace it created. That is a `pending` workspace of
     the recorded name, created within the step's window, with no
     members and unclaimed (`signup_workspace_unique`), so no duplicate
     and no orphan.
   - **Expiry:** after 7 days an unfinished signup is `expired`. Its
     workspace, if any, stays `pending` for an operator; it is never
     activated.
   - **Retention:**
     - `failed` and `expired` rows are removed after 90 days;
     - attempt rows after 48 hours;
     - completed rows stay while their workspace exists (they count
       toward the per-person limit) and go with its purge.
   - **ZITADEL:** nothing creates or deletes a ZITADEL identity.

**Pre-migration negative tests** (a temporary schema in `crm_app_test`,
the runtime role, SaaS-OS `session_scope` and `tenant_session_scope`, a
pooled connection reused): **28 passed, 0 failed.**
- No setting: no rows; inserting is refused.
- Person A:
  - reads only A's rows;
  - cannot update or delete B's rows;
  - cannot insert a row for B;
  - cannot hand A's own row to B.
- A tenant context hides every row and refuses inserts, also with the
  person or maintenance setting.
- The same pooled connection's next transaction sees nothing (the
  setting resets to `''`).
- Malformed or foreign settings (`'not-a-uuid'`, `''`, `' '`, a random
  UUID, `' OR 1=1 --`) see nothing, with no error.
- The maintenance flag reads all rows but cannot update, delete or
  insert.
- The runtime role cannot alter the protection: `NO FORCE`, `DISABLE`,
  `DROP POLICY` and `row_security = off` are all refused.
- **Recorded risk:** a *session-level* `set_config` would outlive its
  transaction on a pooled connection (reproduced). It is prevented by
  code (`_set_local`, `is_local = true`) and a unit test, not by the
  database.

**Counting order (as built).** The per-user and per-address limiters run
in the route's dependency. The handler then counts the attempt under the
cap's advisory lock. Only after that does it read and validate the
`Idempotency-Key` header and the JSON body, so a malformed key (400) or a
body that is not JSON (422) is refused *and counted*, like an unverified
email or an invalid name.

**Concurrency evidence (2026-10-25,
`test_concurrent_requests_never_exceed_the_cap_and_refusals_are_not_counted`).**
Every round releases all requests together with a `threading.Barrier`,
against the real advisory lock and table:
- 40 calls to `record_attempt` at a cap of 7, ten rounds: exactly 7
  counted, 33 refused and 7 stored, every round;
- 24 HTTP requests at a cap of 6, five rounds, each request with its own
  person, workspace name and key:
  - six each of an unverified session, an invalid name, a malformed key
    and a valid request;
  - every round: exactly 6 admitted with the status their kind implies,
    18 refused with 429, and 6 stored;
  - workspaces created equal the valid requests admitted.

The test was then run five more times (75 rounds), with no failure. With
the counter unavailable (INSERT revoked), 8 concurrent requests all got
503 and created nothing.

**SaaS-OS gap found:** v0.5.0 schedules system jobs only through
`saas_os.infra.jobs.queue.system_cron`, which is not part of its public
surface. Maintenance is therefore a command
(`python -m crm_app.signup_maintenance`) that the deployment runs every
few minutes, plus resumption on the person's own replay. It is a candidate
upstream request (export `system_cron`), not sent.

**Recovery (implemented, §4b).** `python -m crm_app.signup_maintenance`
(not a worker cron job: see the SaaS-OS gap in §4b) resumes signups idle
for more than 2 minutes, using the same service. After 5 runs a signup is
marked `failed` with an error code, for operator review. A workspace left
`pending` can then be deleted by an operator (`saas-os-operator
delete-tenant`, then purge).

**Expiry and retention (implemented, §4b).**
- An unfinished signup expires after **7 days**. `failed` and `expired`
  rows are removed after 90 days, attempt records after 48 hours.
- Expiring a signup row **does not delete** anything in ZITADEL, and does
  not delete the `core.users` row (no personal data).
- Deleting a ZITADEL identity would need LeadStack to call ZITADEL's
  administrative API, which it does not do (ADR-0023). That needs a
  separate architecture and security decision. Until then an operator
  reviews abandoned identities manually (LG-7).

**Audit.**
- Before the tenant exists: structured log events with request ID, user ID,
  signup ID and outcome code only. No email, name, token or code.
- From step 2 onward, SaaS-OS records tenant audit rows for creation,
  membership and roles.

**Frontend (Stage D).**
- **Create account** on the sign-in screen.
- A workspace-name step for signed-in people with no open invitation in the
  tab. A waiting invitation takes precedence.
- Progress, error and limit messages, then navigation to
  `/app/w/{id}/settings`.
- The prototype file is never served.

### 4c. Stage D as built (2026-10-26)

**Status endpoint.** `GET /v1/signups/status` (public route policy, no
session) returns `{"enabled": bool}` from `crm_app.settings.signup_enabled()`,
the same switch that makes `POST /v1/signups` and `GET /v1/signups/current`
answer 404. It carries no limit, configuration or count. Tests:
`tests/unit/test_signup_status.py` (unset, false and true; the other routes
stay 404 while off and need a session while on; the route is read-only) and
`tests/unit/test_routes.py` (policy).

**Contract as the frontend uses it** (from the code, not the plan):
- refusals carry SaaS-OS's plain-text `detail`: `workspace_limit_reached`
  and `idempotency_key_reused` (409), `invalid_workspace_name` (**400**, not
  422; 422 is a malformed body), `"Not authorized."` (403);
- a 403 from `POST` is ambiguous: the same answer comes from the
  same-origin check. The screen names the verified-email requirement only
  when `GET /v1/signups/current` also answers 403 (it has no origin check);
- 429 and 503 carry `Retry-After`; the button stays disabled that long.

**Screens (`frontend/src/pages/CreateWorkspace.tsx`, `HomePage.tsx`,
`SignInScreen.tsx`, `api/signups.ts`).**
- Sign-in screen: **Create account** appears only when the status says on.
  It leads to `/auth/login`, where the login build offers "Create one"
  (SaaS-OS's `/auth/login` passes no `prompt=create`). When the status is
  unknown the screen claims neither that signup exists nor that it does not.
- Start page: the workspace-name step appears at once for a person with no
  workspace, or behind **Create workspace** for one who has workspaces; it
  is offered when the status is on or unknown (the backend decides), and
  never while an invitation waits in the tab.
- One `Idempotency-Key` per attempt, kept in `sessionStorage` with its
  normalized name (memory when storage is unavailable), reused for retries
  after network failures, 429/503 and timeouts, replaced only after
  `idempotency_key_reused`, a failed or expired signup, or a new name;
  removed on completion and on sign-out.
- Provisioning: the screen follows `GET /v1/signups/current` for about a
  minute (1 s rising to 10 s), then offers **Check again**, which repeats
  the same attempt so the backend resumes it. An unfinished signup found on
  arrival is resumed. Success is shown only by opening the workspace once
  the state is `complete`.

**Invitation precedence: finding.** SaaS-OS v0.5.0 offers no invitee-side
lookup: invitations can be listed only per workspace by its Owners and
Admins (`saas_os.api.v1.invitations.list_invitations`), and the token
lives only in the emailed link's fragment. A server-side "does this person
have a pending invitation" check would need a new cross-tenant query by
verified email, which is an architecture and security decision and was not
built. Instead:
- an invitation opened in the tab hides the step entirely;
- the step tells invited people to open their invitation link, and that
  creating a workspace does not join theirs;
- the two flows cannot corrupt each other: accepting creates no workspace
  (`test_accepting_an_invitation_creates_no_signup_or_workspace`), and
  creating a workspace leaves every invitation usable.
Remaining limitation: an invited person who lost the tab and ignores the
hint can create a separate workspace first; their invitation still works.

## 5. Security finding L4: investigation (2026-10-24)

**Finding:**
- Behind the edge, SaaS-OS's pre-login rate limit keys on the proxy's
  address unless `TRUST_PROXY_HEADERS=true`.
- With it, SaaS-OS uses the last `X-Forwarded-For` hop, the one the proxy
  appended.

**Verified locally (Caddy 2.11.4 edge; uvicorn on 127.0.0.1:8001;
`RATE_LIMIT_REQUESTS_PER_WINDOW=5`; local stack only).** The test exhausted
`/auth/login` from the host with a different forged `X-Forwarded-For` on
each request, then called it from a second client (the `zitadel-login`
container) through the same edge:

| `TRUST_PROXY_HEADERS` | Host, 6 requests | Second client |
| --- | --- | --- |
| unset | 303 ×5, then 429 | 303 |
| `true` | 303 ×5, then 429 | 303 |

**Interpretation:**
- The forged header never helped: Caddy drops client-sent `X-Forwarded-For`
  from untrusted peers.
- The finding does **not** reproduce locally. Uvicorn's default proxy-header
  handling trusts the loopback peer (Docker Desktop delivers Caddy's
  connections from 127.0.0.1), so `request.client` is already the visitor's
  address. The access log showed `172.24.0.1` for the host and `172.24.0.7`
  for the container.
- L4 is therefore specific to the deployment. It appears when the
  application is reached over a non-loopback address, as in a containerised
  production topology.

**Done (this change):**
- Start-up validation refuses `SIGNUP_ENABLED=true` without
  `TRUST_PROXY_HEADERS=true`.
- `.env.example` documents both settings and the condition that makes
  trusting the header safe: the application is reachable only through the
  edge.

**Not done:** there is no production topology yet. **Status: L4 reduced,
not closed.** It closes at launch gate LG-5, when the production edge
proves both:
- the application is reachable only through the edge;
- two clients get independent limits, and a forged header is ignored.

## 5a. Stage A4: local ZITADEL registration and email verification (2026-10-24)

**Setup (local only):**
- `deploy/local/configure-zitadel.py` gained two opt-in settings:
  - `ZITADEL_LOCAL_ALLOW_REGISTER=true` sets the login policy's
    `allowRegister`;
  - `ZITADEL_LOCAL_SMTP=mailpit` adds the local Mailpit as ZITADEL's SMTP
    provider (`mailpit:1025`, sender `zitadel@crm-app.localhost`) and
    activates it; idempotent.
- `deploy/local/compose.yaml` passes `EMAIL_VERIFICATION` to Login V2 from
  `ZITADEL_LOCAL_EMAIL_VERIFICATION`.
- All three default to off, so D-IDL.1's settings stand unless someone opts
  in.
- Applied to the local instance with all three on; read-back confirmed
  `allowRegister: true` and the Mailpit provider active.
- LeadStack signup stayed off (`SIGNUP_ENABLED` unset). No production
  setting was touched.

**Observed in Chrome, each user in its own isolated browser context:**

| # | Scenario | Result |
| --- | --- | --- |
| 1 | Registration offered | "Register new user" appeared on Login V2 only after a reload (Login V2 caches settings briefly). The form asks for first and last name, email and passkey or password, under ZITADEL's password rules. No terms or privacy links (none configured, LG-2). |
| 2 | Register U1 with verification **off** | U1 returned straight to `/app` signed in: `/auth/me` 200. The stored session has no `verified_email`. ZITADEL sent no email. |
| 3 | Register U2 with verification **on** | Login V2 stopped at "Verify user" and sent a code ("Verify email", in Mailpit). `/auth/me` was 401: no LeadStack session before verification. |
| 4 | Bypass: restart sign-in while unverified (`/auth/login`, choose the account, enter the password) | Back to "Verify user"; still no LeadStack session. A **new** code was sent. |
| 5 | Enter the newest code | Returned to `/app` signed in; the session has `verified_email`. |
| 6 | Sign out, then sign in with the password | Sign-out ended both sessions (ZITADEL's account-choice page, the known P2-G residual). Sign-in with the password returned to `/app`. |
| 7 | Password reset | "Reset Password" sent a "Reset password" email to Mailpit (not completed). |
| 8 | U1 (registered unverified) signs in with verification on | Stopped at "Verify user". |
| 9 | U1's session from row 2, kept after verification was turned on | Still valid (`/auth/me` 200, no `verified_email`). |
| 10 | Admin (verified at setup) signs in | Unaffected. Invited U2 and U1 as Members (manual links). |
| 11 | U2 accepts | "You have joined the workspace"; invitation accepted. |
| 12 | U1's unverified session tries to accept | Invitation **not** accepted (database read-back). The browser page closed before its message could be read; the acceptance route refuses sessions without `verified_email`. |

**Answer: can an unverified identity obtain a usable LeadStack session?**
- With `EMAIL_VERIFICATION` on: **no** (rows 3, 4 and 8).
- With it off, or for a session issued before it was turned on: **yes**, a
  session without `verified_email` (rows 2 and 9). That session can see
  only the empty start page. It cannot accept an invitation (row 12), and
  the planned signup endpoint refuses it (§4).
- LeadStack's own `verified_email` check is therefore required, not
  optional.

**Findings for the security review (LG-8, LG-9):**
1. Login V2 pages say "Create your Zitadel account" and "Login with
   Zitadel": the provider's name is visible, against SaaS-OS ADR-0023's
   aim of an invisible ZITADEL. Branding is a launch task.
2. Login V2 puts the email and names in URL query strings
   (`/register/password?email=…`, `/verify?loginName=…`). They reach browser
   history, and any access log that records URLs. The production edge must
   not log query strings for `/ui/v2/login`.
3. Sessions issued while verification was off stay valid for their
   lifetime, up to 12 hours (I2). Turning verification on in production
   must happen before registration is opened, never afterwards.
4. Each new sign-in by an unverified user sends another code (rows 4 and
   8); repeated sign-ins could be used to flood an inbox. This needs the
   edge rate limit on `/ui/v2/login` (LG-5).
5. Not tested: registering with an email that already exists
   (enumeration); passkey registration; completing a password reset;
   organisation selection by scope.

**Re-verified 2026-10-25** with the LeadStack login build (S-2), a new
disposable identity on `crm-app.localhost` and the settings kept in `.env`:
- "Create one" on the sign-in page leads to registration; the identity is
  created active with an unverified email;
- one "Verify email" message reached Mailpit, and nothing left the machine;
- a fresh sign-in with the right password stopped at "Verify user" and sent
  a second code; `/auth/me` was 401 throughout;
- the email's link (`/ui/v2/login/verify` with code, user, organisation and
  request) opened the code page filled in; after **Continue** ZITADEL
  marked the email verified and the browser returned to `/app` signed in;
  the session row carries the verified address;
- sign-out, then sign-in with the password, worked without a new email;
- `POST /v1/signups` and `GET /v1/signups/current` answered 404 with that
  valid session (kill switch off);
- `configure-zitadel.py`:
  - refuses registration without `ZITADEL_LOCAL_SMTP=mailpit`;
  - is idempotent with the opt-ins;
  - without them, turns registration off **and says so**;
  - with them, turns it back on.

Not tested: the published `zitadel-login` image with these settings (only
the LeadStack build was used this time; the published image was used on
2026-10-24), and delivery to any real mailbox (by design).

**Local state left in place:**
- registration on, verification on, Mailpit running;
- two throwaway test users, `signup-u1-44983a` and `signup-u2-44983a`,
  both `@crm-app.localhost`; U2 is an Awaiting-role member of
  "Local test workspace".

To revert, rerun the script without the opt-in variables and recreate
`zitadel-login` without `ZITADEL_LOCAL_EMAIL_VERIFICATION` (README).

## 6. Staged plan

| Stage | Depends on | Content | Acceptance criteria |
| --- | --- | --- | --- |
| **A. Security and configuration** | S-1 | A1 L4 investigation (done, §5). A2 `SIGNUP_ENABLED` (default off) and both limits with the owner's defaults (done, S-1.1). A3 the application and edge rate-limit requirements (written: §4, LG-5). A4 local ZITADEL registration, email verification and Mailpit as ZITADEL's SMTP, opt-in by script and compose settings, documented in the README (done and browser-verified, §5a). | A1/A2: unit tests pass (`tests/unit/test_settings.py`); production refuses the switch. A4: locally, with Mailpit, a new person registers, receives a code in Mailpit, verifies, returns to `/app` with `verified_email`; unverified sign-in is refused; password reset email arrives; existing sign-in, sign-out and invitation acceptance still pass (identity test plus browser). |
| **B. Provisioning foundation** | A2 | **Status 2026-10-25: built with C, verified locally, uncommitted** (`crm_app.provisioning`; `test_provision.py` unchanged and green; the interruption, concurrency and activation tests run through signup in `test_signups.py`). Extract the steps of `provision.py` into a shared service. The operator CLI keeps its behaviour and output. The signup variant activates last, never accepts a parent, and seeds `workspace_settings` only if a decision asks for it. | `test_provision.py` unchanged and green. New tests: interruption after each step resumes correctly; two concurrent provisions of the same signup create one tenant; before activation the new tenant refuses every product action; after it, the Owner passes `can()` for `membership_role:create` and `crm_app.owner:manage` and counts as an administrator under ADR-0043. |
| **C. Signup backend** | B; security review of the §4 table design | **Status 2026-10-25: built and verified locally** (§4b; `tests/integration/test_signups.py`, 26 tests, including the cap under concurrent requests released by a barrier). Migration for `crm_app.signup` (declared global, chosen access model); `POST /v1/signups`, `GET /v1/signups/current`; limits; rate limits; recovery and expiry job; structured events. | Integration tests: success; replay with the same key; a different key while one is open; parallel requests produce one workspace; per-user and daily caps hold under parallel requests; unverified session refused; kill switch off returns 404; limiter down returns 503; forged `parent_id`, `role`, `user_id` or `tenant_id` fields refused; cross-user read and write refused at API and repository level; cross-tenant isolation of the new workspace; crash at each step then resume; expiry after 7 days; logs and errors contain no email, token, code or workspace name; acceptance of an invitation creates no signup or tenant. |
| **D. Frontend** | C | **Create account** on the sign-in screen (to `/auth/login`); the workspace-name step; progress, error, limit and kill-switch states; entry into the workspace. | Vitest for every state, axe clean; no input that collects credentials anywhere; invitation precedence; browser check at desktop and 390 px; sign-out unchanged. |
| **E. Verification and release readiness** | A-D | Full gate run; security review of the signup surface; staging verification; launch checklist (§7). | Repository gates green (ruff, pyright, import contracts, unit, integration, frontend, audits, secret scan); review without open Critical or High; every LG item has evidence recorded here; the production refusal in `settings.py` removed only by the change that records that evidence. |

## 7. Launch gates and open decisions

Public signup stays off in production until every gate has recorded
evidence. Start-up validation enforces this in code (`settings.py`).

| ID | Gate or decision | Status |
| --- | --- | --- |
| LG-1 | Production email provider and sending domain for ZITADEL's verification and reset email, with SPF, DKIM (and DMARC) on that domain (Q3) | **Open: not selected** |
| LG-2 | Published Terms of Service and Privacy Policy URLs, configured in ZITADEL's legal settings and linked from LeadStack; which consent evidence to record, if any, approved | **Open: no published documents exist** |
| LG-3 | The shared customer ZITADEL organisation verified: registration lands only there; console and administrative roles are not granted to customers; login policy, lockout and `ignoreUnknownUsernames` apply to it | **Open: plan only** |
| LG-4 | Owner MFA: the mechanism (for example ZITADEL `forceMfa` for the customer organisation, or a LeadStack check of the session's `multi_factor` before Owner actions) and its verification | **Open: mechanism not chosen** |
| LG-5 | Production edge: the application reachable only through the edge; L4 verified closed there (§5); edge rate limiting on `/ui/v2/login/register*`, `/auth/*` and `/v1/signups`; a WAF or equivalent bot protection deployed; CAPTCHA evaluated, not assumed | **Open** |
| LG-6 | Signup limits | **Set (S-1.1):** 5 workspaces per user, 100 attempts per rolling 24 hours, as defaults. Counting rule confirmed (S-1.2, §4) and enforced in Stage C; revisit the numbers once real use and abuse have been observed. |
| LG-7 | Abandoned identities: default is manual operator review, no automatic deletion; any deletion needs a separate decision (ADR-0023) | **Default recorded; deletion not approved** |
| LG-8 | ZITADEL behaviour: `EMAIL_VERIFICATION` enforcement; enumeration through registration; organisation selection; Login V2 registration defects | **Partly proven locally (§5a):** verification is enforced, and an unverified identity gets no session while it is on. **Still open:** whether registering an existing email reveals it; organisation selection by scope; the findings in §5a (provider name shown, email in URLs, sessions that predate enforcement, a second code sent on each sign-in). |
| LG-9 | Security review of the signup surface (Stage E) without open Critical or High findings | **Open** |
| LG-10 | Operator runbook: turning signup off, reviewing failed signups, deleting abandoned `pending` workspaces | **Open** |

## 8. Required security tests (summary)

The tests are listed by stage in §6. Every stage must also show:
- No credential, verification code, token, email or workspace name appears
  in logs, error bodies or audit metadata.
- The existing sign-in, sign-out (P2-G) and invitation tests still pass
  unchanged.
