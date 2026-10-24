# Phase 2 Security Review

**Date:** 2026-10-24. **Kind:** read-only code and configuration review of
the Phase 2 scope (identity, workspaces, tenant isolation), done under the
owner's overnight mandate. It is evidence towards the Phase 2 exit
criteria (`ROADMAP.md` §7), not a sign-off: **Phase 2 is not complete**
(invitations, workspace settings and the workspace directory remain, and
the owner has not reviewed this record).

**Scope:** `src/crm_app` (app, settings, permissions, roles, provision,
migrate, worker, jobs, purge; the workspace, member, access, SPA and error
routes; migrations 0001 and 0002), how the product uses SaaS-OS
authentication (`build_platform_app`, `/auth`, session cookies,
`require_permission`, `get_tenant_context`), `deploy/local`, the example
settings files, the frontend's session handling, and the tests that claim
isolation. `.env` was not opened. The contacts and companies slice had its
own review (`PHASE3-PLAN.md` §19.8).

## Result

No critical or high finding, and no cross-tenant access path. Two gaps in
test evidence and two defects were fixed the same day; the rest are
deployment or policy points recorded for Phase 13.

| ID | Severity | Finding | Status |
| --- | --- | --- | --- |
| M1 | Medium (evidence) | No product test proved that a suspended or revoked member is refused | **Fixed**: `test_suspended_and_revoked_members_lose_access_with_a_live_session`. Their sessions are issued while they are active members; after suspension or revocation every workspace route answers 403 |
| L1 | Low (evidence) | Owner races covered only same-operation pairs | **Fixed**: two mixed races (A revokes B while B drops A's Owner role; both Owners step down at once), five rounds each; every round leaves exactly one active Owner and exactly one success |
| L2 | Low | `/app/<path>` with a NUL byte could raise a 500 | **Fixed**: `crm_app.api.spa` refuses it (404); unit test |
| L3 | Low | Authenticated JSON had no `Cache-Control` | **Fixed**: `NoStoreMiddleware` sets `no-store` on `/v1/` and `/auth/` responses that set none; unit and integration tests |
| L4 | Low (deployment) | Behind Caddy, SaaS-OS's pre-login rate limit keys on the proxy address unless `TRUST_PROXY_HEADERS` is set, so one client could exhaust `/auth/login` for everyone | **Accepted, deferred to Phase 13** (owner, P2-F): set and document `TRUST_PROXY_HEADERS` for the production proxy topology only |
| L5 | Low (platform) | SaaS-OS's route rate limit is per workspace and path, so one member can use a route's budget for the whole workspace | **Accepted, deferred to Phase 13** (owner, P2-F): consider a per-actor limit; platform behaviour, not product code |
| I1 | Info (local) | The local edge serves ZITADEL's console on the application origin; bootstrap tokens are long-lived; local Redis has no password (bound to 127.0.0.1) | **Accepted, deferred to Phase 13** (owner, P2-F): keep the identity console off the application origin in production |
| I2 | Info (policy) | Admins may suspend, revoke and promote other Admins (only Owners are protected); sessions last 12 hours with no idle timeout; sign-in and sign-out are logged, not audited (platform); `/access` can answer 500 if a membership vanishes mid-request | **Decided** (owner, P2-F): Admins managing Admins stays (as Q6); 12-hour sessions without idle timeout stay for now; sign-in and sign-out stay logged by SaaS-OS; the `/access` 500 is **fixed** (same 404 as a non-member; `tests/unit/test_access.py`) |

## Checked and found sound

- **Sessions:** HttpOnly, SameSite=Lax, `Secure` by default (refused off in
  production); a 256-bit cookie secret stored hashed; sign-out revokes the
  session; membership status is re-read on every request.
- **CSRF:** cookie-authenticated changes require an exact `Origin` match
  and a same-origin `Sec-Fetch-Site` when sent (SaaS-OS).
- **OIDC:** PKCE, single-use state, nonce, ID-token validation, a fixed
  callback and a validated same-origin post-login path (no open redirect).
- **Workspace context:** every product route declares one
  `require_permission`; handlers use the validated context, never the
  path; unknown, foreign, suspended-tenant and non-member requests get the
  same 404.
- **Privilege changes:** SaaS-OS's membership and invitation routers are
  not mounted; role names are a fixed enum; self-changes are refused
  except an Owner stepping down; Owner changes need an Owner and an
  explicit confirmation; every Owner-affecting path takes the same
  per-workspace lock and reads facts after acquiring it.
- **Provisioning:** refuses production without `--confirm-production`,
  is idempotent, assigns the Owner role last, refuses to claim a workspace
  with other members, prints identifiers only.
- **Static serving and CSP:** no traversal, hidden files or symlink
  escapes; hashed assets immutable, the index revalidated; no `unsafe-*`
  in the CSP.
- **Migrations:** 0001 revokes PUBLIC and grants only USAGE; 0002 forces
  RLS in the same migration as its grants, with composite tenant keys.
- **Secrets:** none tracked; example files hold placeholders only.

## Exit criteria (ROADMAP §7) against evidence

| Criterion | Evidence | State |
| --- | --- | --- |
| Authentication works against the intended identity provider | `tests/identity/test_oidc_login.py` against local ZITADEL | Test exists; opt-in and not in CI; not run during this review |
| Workspace context is trustworthy | Route probes, including removed members (M1) | Evidenced in CI |
| Authorization is enforced server-side | Route-policy test, role matrix, Owner races (L1) | Evidenced in CI |
| Tenant-isolation tests pass | Table guard, `test_crm_tables.py`, record route and list tests | Evidenced in CI |
| Database migrations are reproducible | `test_foundation`, rollback test | Evidenced in CI |
| No known critical cross-tenant vulnerability remains | This review and the slice 3A review | None known |

Remaining for Phase 2 itself: invitations (G3/G4), workspace settings,
the workspace directory, and a run of the identity test against ZITADEL.

## Owner review (2026-10-24, decision P2-F)

The owner reviewed this record and decided every open item: M1, L1, L2
and L3 are fixed with tests in CI; L4, L5 and I1 are accepted and deferred
to Phase 13; the I2 policy points are decided as recorded in the table,
and the `/access` defect in I2 is fixed. No finding remains open.
