# Staging acceptance report (2026-11-08)

The owner asked for an autonomous acceptance audit of staging. Staging
readiness is **not** production approval.

Companions: `STAGING-INFRASTRUCTURE-REPORT.md`,
`STAGING-SECURITY-REPORT.md`, `STAGING-BACKUP-RESTORE-REPORT.md`,
`STAGING-E2E-TEST-REPORT.md`. Finding IDs `S-n` are shared.

## 1. Overall result: CONDITIONAL PASS

Staging at `https://crm-staging.auravox.nl` is usable for realistic
end-to-end testing by invited testers: the CRM works end to end, tenant
isolation holds under direct API attack, the stack survives a reboot, and
a backup restores into a separate instance with isolation intact. It is
not production-ready, and these conditions remain:

1. ~~Third-party images carry fixable HIGH and CRITICAL advisories
   (S-6)~~: updated by decisions ZIT-1 and D-STG.6; a few findings remain
   inside Caddy's and ZITADEL's binaries until their next releases.
2. ~~Signing out leaves the identity-provider session alive (S-7)~~: fixed
   the same day by decision ZIT-1.
3. No second factor, and the ZITADEL console is public (S-8).
4. Backups exist only on the same VPS, are not scheduled, and leave
   plaintext copies (S-9).
5. No monitoring or alerting, and audit digests live only in container
   logs (S-10).

**Starting point:** the owner reported staging as ready, but the VPS was
empty (no Docker, no LeadStack, no DNS record). With the owner's approval
(decision D-STG.5) staging was deployed first, then audited.

## 2. Assessments

| Area | Result | Basis |
| --- | --- | --- |
| Infrastructure | **Pass after fixes** | only 22/80/443 public; restarts recover in ~32 s after S-1 and S-2 were fixed; logs rotate (S-4) |
| Authentication | **Conditional** | OIDC sign-in works; app sign-out ends the session server-side; open: S-7, S-8 |
| CRM functionality | **Pass** | every workflow in the E2E report §2, plus browser checks |
| Database and tenant isolation | **Pass** | 39 cross-workspace attempts refused; RLS forced on 60/60 product tables; isolation holds in the restored copy |
| Email | **Pass for what may be tested** | sending is off; replies stay `queued`; webhooks fail closed; nothing sent; real delivery, signatures and inbound **not tested** (not authorized) |
| Security | **Conditional** | headers, CSRF, CORS, rate limit, input handling, secrets pass; open: S-6, S-7, S-8, S-19 |
| Backup and recovery | **Conditional** | encrypted backup and restore: 15 of 15 checks pass (15:16 run), restore ~6 s; open: S-9 (local only), S-10 (digests not shipped) |
| Monitoring | **Fail (owner decision)** | health checks and `/readyz` work; no alerting, no heartbeat monitor, no log shipping |
| End-to-end workflows | **Pass with exceptions** | steps 3–15 pass; steps 1–2 (signup, email verification) blocked by design |

## 3. Tested / failed / not tested / blocked

- **Tested and passed:** listed in each companion report's tables.
- **Tested, failed, then fixed and re-verified:** S-1 (databases down
  after reboot), S-2 (resolver address), S-3 (Squid on Debian 13), S-4
  (unbounded logs), S-5 (image zlib CVEs), S-11 (drill file permission).
- **Tested and still failing:** third-party image scan (S-6, partly fixed). The
  audit-digest check passed once a digest existed (15:16 run).
- **Not tested:** signup and email verification, mobile layout in a
  browser, member and role management in the browser, session expiry,
  real email and provider webhooks, file upload on staging, failed
  deployment and rollback, load.
- **Blocked by an owner decision:** S-6 (ZITADEL images), S-7, S-8, S-9,
  S-10, S-19, memory limits with the voice PBX (S-12).

## 4. Commits, CI and changes

| Commit | Change | CI |
| --- | --- | --- |
| `bacf0c7` | start of the audit | run 42477007388 success |
| `a3685cd` | host mode for the staging stack; Squid file limit; staging issuer guard | run 42486066851 success |
| `4470baf` | backup drill readable on Linux (S-11) | run 42486500038 success |
| `1d537d0` | container log rotation; host log labels; exporter off (S-4) | run 42489043592 success |
| `7aeddf6` | PostgreSQL and Redis restart (S-1) | run 42489592730 success |
| `1170b91` | worker resolver address after reboot (S-2) | see `PROGRESS.md` |
| `bb90ab8` | Debian security updates in the image (S-5) | see `PROGRESS.md` |

Infrastructure changes on the VPS: Docker and tools installed, read-only
deploy key, stack deployed at `/srv/leadstack/crm-app`, systemd timers,
ufw 80/443, sshd X11 off, LLMNR off, two disposable users and two
workspaces. No money spent, no domain bought, no email sent, no SaaS-OS
pin or identity architecture changed.

## 5. Remaining blockers and the action each needs

| ID | Severity | Action | Who |
| --- | --- | --- | --- |
| S-6 | Low (remainder) | Take the next Caddy and ZITADEL releases (`golang.org/x/net`, `go-jose`); add an image scan to CI | Implementation |
| S-8 | Medium | Decide MFA policy (at least for the ZITADEL administrator) or restrict `/ui/console` at the edge | Owner |
| S-9 | Medium | Choose an off-host backup bucket; then a nightly backup timer with local retention and no plaintext copy | Owner, then implementation |
| S-10 | Medium | Choose a monitoring service for the heartbeat and a log store for audit digests | Owner |
| S-19 | Medium | Production identity setup with a system-user key; remove the staging bootstrap token after setup | Owner, at production setup |
| S-12 | Low | Memory limits when the voice PBX plan is known; edge health check; Redis non-root | Implementation |
| S-13, S-14, S-15, S-21 | Low | Login branding; plain rate-limit page; refusal without the workspace frame; `Server` header on the redirect | Implementation |

## 6. Recommended next phase

1. Owner decisions S-6, S-7, S-8 (identity) and S-9, S-10 (backups,
   monitoring); none costs much, two are free.
2. A hardening slice: CI image scan, third-party image refresh, the Low
   fixes, a nightly backup timer.
3. Then invite real testers to staging, still with email off.
4. Production hosting (brief H) and email activation (brief 6) remain
   separate decisions.
