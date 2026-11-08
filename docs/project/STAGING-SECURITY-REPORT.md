# Staging security report (2026-11-08)

Part of the staging acceptance audit (`STAGING-ACCEPTANCE-REPORT.md`).
Practical, non-destructive checks against `https://crm-staging.auravox.nl`
and the VPS. No external penetration test, no paid service. Finding IDs
are shared across the staging reports.

## 1. Results

| Area | Result | Evidence (measured 2026-11-08) |
| --- | --- | --- |
| TLS | **Pass** | Let's Encrypt certificate for the host only; TLS 1.2 (ECDHE-ECDSA-AES128-GCM) and 1.3 negotiate; 1.0/1.1 not offered by Caddy's defaults (the local client could not offer them, so not probed) |
| HTTPS only | **Pass** | `http://` → 301 to `https://`; `Strict-Transport-Security: max-age=31536000` |
| Security headers (app) | **Pass** | `Content-Security-Policy` (`default-src 'self'`, `script-src 'self'`, `object-src 'none'`, `frame-ancestors 'none'`), `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`; `Server` header removed on the site (not on the redirect, S-21) |
| Cookies | **Pass** | sign-in state cookie `HttpOnly; Secure; SameSite=lax; Path=/auth; Max-Age=600`; session cookie is HttpOnly (not readable by page script) |
| CSRF | **Pass** | with a valid session cookie: POST from `https://evil.example` 403, POST without `Origin` 403, `text/plain` POST from a foreign origin 403, same-origin POST 201 (SaaS-OS origin check) |
| Sign-out | **Pass** (app and identity-provider sessions, after ZIT-1) | `/auth/logout` 204, then the same cookie → 401 |
| CORS | **Pass** | foreign `Origin` gets no `Access-Control-Allow-Origin`; preflight to the API 405 |
| Authentication | **Pass** | no credentials → 401 on product routes; ZITADEL sign-in completes through OIDC (PKCE) on the app's origin |
| Authorization / tenancy | **Pass** | `STAGING-E2E-TEST-REPORT.md` §3: 30 cross-workspace reads, updates and deletes and 9 cross-workspace lists all refused (404 or 405), search does not leak, the victim's records intact |
| Rate limiting | **Pass**, note S-14 | 70 rapid `/auth/login` requests from one address: 60 × 303, then 429; keyed by the real client address (finding L4 does not occur on this topology) |
| Input validation | **Pass** | unknown field (`role`) 422; 5,000-character name 422; SQL-like search text returns 0 matches (parameterised); markup stored as text and served under the CSP |
| XSS | **Pass** (as far as tested) | `<script>alert(1)</script>` saved as a name is returned as text; the React frontend renders text, and the CSP forbids inline script |
| SSRF | **Pass** (by design) | the worker reaches the Internet only through Squid (CONNECT to public IPv4 on 443) with its own resolver; the app has no route to arbitrary hosts |
| File upload | **Not tested on staging** | CSV import is capped (6 MB at the edge, 5 MB in the app) and covered by CI tests |
| Webhooks | **Pass** (fail closed) | `/v1/public/email/resend/{events,inbound}`: 404 with no provider secret configured, before reading the body; signature and replay checks need a real Resend secret (not authorized), covered by CI tests only |
| Secrets | **Pass**, note S-19 | generated on the VPS, mode 0600 in a 0700 directory, never printed or copied off; no secret in the image or repository; secret scan of the repository passes in CI |
| Logging | **Pass after fix** (S-4) | JSON logs with request IDs; no tokens or bodies seen in sampled app and worker logs; trace spans no longer printed |
| Dependencies | **Pass** (Python, frontend) | CI `security` job: `pip-audit --strict` and the secret scan pass on every audit commit |
| Container images | **Pass after fix** for LeadStack (S-5); **open** for third-party images (S-6) | Trivy 0.57.1, HIGH/CRITICAL with a fix available |
| Containers | **Pass**, note S-12 | app, worker, migrate: read-only root filesystem, all capabilities dropped, `no-new-privileges`, non-root user `app` (uid 999) |
| Database access | **Pass** | runtime role `crm_app_runtime` and owner `crm_app_owner`: not superuser, no BYPASSRLS; 60 of 60 product tables force RLS; network connections only `hostssl` with SCRAM; not published |
| Redis | **Pass**, note S-12 | TLS only (`--port 0`), password required, not published; runs as root inside its container |
| Audit integrity | **Partial** (S-10) | audit rows written; the hourly digest is produced but lives only in container logs and was lost when the worker was recreated |
| Development settings | **Pass** | `ENVIRONMENT=production`; signup off; every email switch unset (off); no debug flag; no local-CA trust for the issuer |

## 2. Findings

### S-5 High — Two HIGH advisories in the app image's zlib (fixed)
- **Evidence:** Trivy on `crm-app:staging`: `zlib1g`
  1:1.3.dfsg+really1.3.1-1+b1, CVE-2026-85091 (heap overflow in
  `gz_vacate`) and CVE-2026-76844, fixed in `deb13u1`. The newest
  `python:3.13-slim` still carried the old package.
- **Root cause:** the runtime stage inherited the base image's packages;
  CI audits Python dependencies only, not the image's OS packages.
- **Remediation:** the runtime stage applies Debian's security updates
  (`bb90ab8`).
- **Verification:** rebuilt image has `deb13u1`; Trivy: 0 HIGH, 0
  CRITICAL; deployed. **Owner decision:** no. **Follow-up:** add an image
  scan to CI (proposed, not done).

### S-6 High — Fixable HIGH and CRITICAL advisories in third-party images (partly fixed)
- **Evidence:** Trivy, HIGH/CRITICAL with a fix: Caddy 2.11.4 (1 critical,
  31 high across its layers), ZITADEL v4.19.5 (1 critical, 25 high),
  ZITADEL Login v4.19.5 (2 critical, 13 high), Unbound (4 high), Squid
  6.6 (6 high); PostgreSQL 16 and Redis 7: none.
- **Impact:** Caddy, ZITADEL and its login UI face the Internet.
- **Root cause:** the images are pinned by digest (good for
  reproducibility) and have not been refreshed since they were chosen.
- **Remediation:** refresh the pins to current patch releases and re-run
  the staging checks. **Owner decision: yes** for ZITADEL and its login
  (identity, decision D-STG.1); the others can follow in a routine
  dependency slice.
- **Update, same day (decision ZIT-1):** ZITADEL and the login moved to
  v4.20.1; staging runs LeadStack's login build. Server 26 → 12 findings,
  mostly false matches; the real remainder (`go-jose`, `golang.org/x/net`)
  waits for a ZITADEL release. Caddy, Unbound and Squid remain open for a
  dependency slice.

### S-7 Medium — Signing out leaves the ZITADEL session alive (fixed, decision ZIT-1)
- **Evidence:** after "Sign out", ZITADEL's page asks to choose the
  account; without that click, "Sign in" continues as the same person
  without a password (observed in the browser).
- **Impact:** on a shared computer the next person gets in.
- **Root cause:** staging runs ZITADEL's published login image; the fix
  is LeadStack's own login build (`crm-app-login`, PR #1), decision
  P2-G.1.
- **Remediation:** merge and publish `crm-app-login`, run it on staging.
  **Owner decision: yes** (merging PR #1 and publishing a login image need
  approval).
- **Verification (after ZIT-1):** sign-out returns straight to the
  LeadStack sign-in, which asks for the password again.

### S-8 Medium — No second factor; ZITADEL console reachable (open)
- **Evidence:** sign-in asked for a password only; `/ui/console` and the
  ZITADEL management APIs are served on the public origin (decision
  ADR-0025's route list); the ZITADEL administrator has a password and no
  second factor.
- **Impact:** a stolen password is enough, for members and for the
  identity administrator.
- **Remediation:** require MFA in ZITADEL's login policy (at least for the
  administrator), or restrict `/ui/console` and the admin APIs at the edge
  to an allow-list. **Owner decision: yes** (identity settings).

### S-19 Medium — Bootstrap tokens on the host (open)
- **Evidence:** the stack's ZITADEL wrote two personal access tokens
  (an instance-administrator machine user and the login client), valid to
  2100, to `.local/bootstrap/`; `identity_local.py` uses the first.
- **Impact:** anyone with root on the host has full control of the
  identity provider. Acceptable for staging, not for production.
- **Remediation:** production uses a system-user key (SaaS-OS ADR-0025
  §7); for staging, remove the administrator token after setup.
  **Owner decision:** with the production identity setup.

### S-14 Low — The rate limit shows raw JSON in the browser
- `{"detail":"Rate limit exceeded."}` replaces the page when
  `/auth/login` is limited. Remediation: a plain page. Owner decision: no.

### S-21 Low — The HTTP redirect names the server
- The `http://` → `https://` redirect carries `Server: Caddy` (the site
  itself removes it). Remediation: remove it in `edge/extra-host.caddy`.

## 3. Not tested

- Session expiry in practice (the default lifetime is 12 hours; not
  waited out).
- Webhook signature and replay handling on staging (no provider secret).
- File upload limits on staging.
- TLS 1.0/1.1 refusal by probe (client limitation).
- Destructive or external penetration testing (out of scope).
