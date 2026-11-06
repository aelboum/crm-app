# Replacing `role_upgrade` with SaaS-OS permission grant migrations

Status: **design for owner review, 2026-11-06. Nothing is built and no
workspace was touched.** Owner instruction: "Go" on "design first, build
second". Facts are from SaaS-OS v0.8.0 (`140d9dd`, the pinned release):
ADR 0060, `saas_os.core.permission_grants`, `saas_os.ops.operator_cli`,
CONSUMER-GUIDE §§ 266-268 and RUNBOOKS "Permission grant migrations".

## 1. Why

`crm_app.role_upgrade` gives existing workspaces' roles the permissions
that new workspaces get from `ROLE_TEMPLATES`. It uses
`SystemCaller(PROVISIONING)` beyond that caller's documented purpose
(decision P2-G7) because SaaS-OS had no sanctioned way (saas-os #88). Since
v0.7.0 SaaS-OS has one: a product declares an append-only list of
`PermissionGrantMigration`s, and the operator command
`saas-os-operator apply-permission-grants` applies each one once per
workspace, under SaaS-OS's own `SystemCaller(PERMISSION_UPGRADE)`, with a
ledger and audit rows. `role_upgrade` has never run on a real workspace
(Brief 7 is still open), so switching now costs no migration of history.

## 2. How the two differ (verified)

| | `role_upgrade` today | SaaS-OS grant migrations |
| --- | --- | --- |
| Model | State: each run diffs every role against `ROLE_TEMPLATES` | Events: each declared migration applies once per workspace, never re-evaluated |
| Unit | Whole template, all four roles | One migration = one role name + up to 100 permissions |
| Authority-changing permissions (`invitation`, `membership`, `membership_role`, `role`, `role_permission`, ...) | Granted, but held back unless `--include-administrative` | **Refused for the whole run** (`AuthorityPermissionGrantError`) |
| Caller | `SystemCaller(PROVISIONING)` (outside its purpose) | `SystemCaller(PERMISSION_UPGRADE)` (its purpose) |
| Who runs it | Anyone with the database | An enrolled platform operator holding `platform.permission_grant:apply`, even for a dry run |
| Evidence | SaaS-OS `role_permission.grant` per grant; product JSON report with permission names | The same per grant, plus a tenant `permission_grant_migration.apply` row, platform start/complete rows, and a permanent ledger (`core.permission_grant_applications`, never deleted) |
| Review binding | `--apply --expect <fingerprint>` (13-R1) | None; the dry run prints counts only, never permission names |
| Scope | Repeated `--workspace`, or `--all` (ACTIVE workspaces with all four roles) | One `--tenant`, or `--all-tenants` (PENDING, ACTIVE and SUSPENDED) |
| Concurrency | No lock | Per-workspace advisory lock; one transaction per workspace |
| Undo | Revoke from the report | No revoke kind; a member with role rights revokes per workspace, and the ledger then never re-adds it |

What this means for crm-app:

- Every permission added since the Phase 2 matrix is **not**
  authority-changing: `appointment:*`, `booking_page:*`, `form:*`,
  `suppression:*`, `conversation:*`, `campaign:*` (including `approve`),
  `automation:*` and `crm_data:import` (P5-A, P5-C, P7-A, P7-B, P6-C,
  P7-C, P8-A, P3-F). All of them can be declared.
- The authority-changing permissions (`invitation:*`, `membership:*`,
  `membership_role:*`) have been in the templates since Phase 2, so every
  workspace already has them. A future addition of that kind cannot go
  through SaaS-OS's mechanism. That is SaaS-OS's deliberate rule: such
  changes go through a workspace owner, not an operator.

## 3. Proposed design

1. **Declarations.** A new module `crm_app.permission_grants` exports
   `PERMISSION_GRANT_MIGRATIONS`, a tuple of `PermissionGrantMigration`s in
   namespace `crm_app`. One migration per (addition × role), with ids such
   as `crm_app.p5a.appointment.owner`, and the decision named in `reason`.
   Order follows the decisions. The module is append-only: an applied
   migration is never edited or removed, because SaaS-OS refuses the whole
   run on a changed digest.
2. **Initial set (the backlog).** Declare all of section 2's non-authority
   additions, per role, exactly as `ROLE_TEMPLATES` grants them now.
   Workspaces that already hold a grant are counted `already_present` and
   get an `applied` ledger row with zero grants, so they are harmless.
3. **Held-back permissions.** `role_upgrade`'s "administrative held back"
   rule becomes separate migrations for the ADMINISTRATIVE-kind grants
   (`booking_page:manage`, `form:manage`, `suppression:manage`,
   `automation:manage`, `campaign:approve`, `crm_data:import`). They are
   declared, but not shipped until the owner approves them (Brief 7's
   "separate, explicitly approved run").
4. **A guard test that ties declarations to templates.** For every role,
   template = Phase 2 baseline + the union of its declared migrations; a
   permission added to `ROLE_TEMPLATES` without a migration fails CI, and so
   does an authority-changing permission in a migration. The test also
   pins every applied migration's digest, so an edit fails CI before
   SaaS-OS refuses it in production.
5. **Retire `role_upgrade`.** Once the first real `--apply` has succeeded,
   remove the command, its probe and its tests, and mark P2-G7 superseded.
   Until then it stays, unchanged and unused.
6. **New workspaces.** Unchanged: `provisioning.seed_roles` grants the full
   current template. A later `--all-tenants` run sees them as
   `already_present`.

## 4. Gaps to close before an `--apply`

1. **Platform operator.** crm-app has never enrolled one. The production
   owner must be bootstrapped or recovered with
   `--grant platform.permission_grant:apply`
   (`python -m saas_os.api.platform_bootstrap`, an OIDC issuer and subject).
   This is an identity and production change, so it needs explicit owner
   approval.
2. **Review evidence.** SaaS-OS's dry run gives counts, not names. The
   product supplies a read-only report command
   (`python -m crm_app.permission_grants --report`) that lists, per
   migration and role, the permission names and how many workspaces lack
   them. This replaces the `role_upgrade` JSON in the change record. Run it
   next to the SaaS-OS dry run.
3. **No fingerprint binding.** Accept SaaS-OS's model (the declaration's
   digest is recorded on `--apply`, and the module is reviewed in a pull
   request), or ask SaaS-OS for an `--expect-digest` flag. Recommendation:
   accept it. The append-only module plus the guard test bind what runs.
4. **One `--tenant` per run.** Use `--all-tenants`. A staged rollout to a
   few workspaces first would need one run per workspace, which is fine for
   a handful.
5. **Workspaces without the roles.** PENDING signup tenants and SaaS-OS-only
   tenants without the four roles get a permanent `role_missing` row for
   that migration. For signup tenants this is harmless, because
   `seed_roles` later grants the full template. Inference, not tested yet:
   to be confirmed in the local dry run.
6. **Revoked before the first run.** A grant that `role_upgrade` added and a
   member later revoked would be re-granted by the first migration run (the
   ledger has no record of it). No crm-app role holds `role_permission:*`,
   and `role_upgrade` has never run on a real workspace, so this does not
   happen today.

## 5. Plan and acceptance criteria

| Step | Done when | Needs owner approval |
| --- | --- | --- |
| A. Declarations, guard test, report command | Unit tests pass. The guard fails when a template permission has no migration, or a migration holds an authority permission. CI green | No (code only, nothing runs) |
| B. Local dry run | On the local test database only (`ENVIRONMENT=test`): a disposable platform operator from SaaS-OS's local bootstrap, then `apply-permission-grants --all-tenants` without `--apply`. Counts match the report command. A refused run's `denied` row is noted | No (disposable database) |
| C. Local apply | Same database with `--apply`: a second run changes nothing; a revoked grant is not restored; the ledger and audit rows are as documented | No (disposable database) |
| D. Production operator | The owner's operator holds `platform.permission_grant:apply` | **Yes** |
| E. First production run, non-administrative migrations | Backup, report, dry run, then `--apply --confirm-production`; outcome recorded | **Yes** (Brief 7) |
| F. Administrative migrations | Separate run | **Yes** |
| G. Retire `role_upgrade` | After E succeeds; P2-G7 marked superseded | No |

## 6. Decisions for the owner

1. Approve the design (steps A to C now, autonomously).
2. Later, separately: enrol the production platform operator (D), and the
   two production runs (E, F). These replace Brief 7.
3. Accept SaaS-OS's lack of a fingerprint (recommended) or file an
   upstream request for `--expect-digest`.
