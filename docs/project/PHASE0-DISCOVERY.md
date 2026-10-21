# Phase 0 Discovery — Verified Baseline

Recorded 2026-10-20. Labels: **[V]** verified in a named file, command, or
source; **[I]** inference; **[R]** recommendation. Findings older than this
date must be re-verified before they are relied on.

## 1. Inspected locations

| Location | State on 2026-10-20 | Role |
| --- | --- | --- |
| `C:\Users\imran\Documents\leadstack-crm` | `main` @ `dcc2476`; 1,466 tracked files deleted (unstaged), `CLAUDE.md` modified, `ROADMAP.md` and the ZIP untracked; remote `sofioco/leadstack-crm` (public, pull-only for `aelboum`) [V] | Former AgentStack/MAROS repository. Not the product repository. Left untouched |
| `C:\Users\imran\Documents\leadstack-crm\leadstack-crm-main.zip` (copy in `Downloads`) | 47,636,561 bytes, SHA-256 `59b76000…6eee`, 2,209 entries, zip comment `dcc2476` [V] | Reference only (K1) |
| `C:\Users\imran\Documents\Leadstack` | `aelboum/leadstack` (public), 2 commits, 72 uncommitted paths [V] | Owner's earlier CRM. Untouched; code not reused (K1) |
| `C:\Users\imran\Documents\saas-os` | `main` @ `2adf634`, clean [V] | Read-only reference clone of the platform |
| `C:\Users\imran\Documents\crm-app` | New directory, fresh `git init`, no commits | Product repository (K2) |

## 2. Reference ZIP (AgentStack template)

- **Licence [V]:** PolyForm Perimeter 1.0.0, © 2026 AgentStack.Dev,
  noncompete clause. Present since the first commit, `16fdc24`.
- **Provenance [V]:** The archive's `CLAUDE.md` describes a template sold
  to buyers (`Claude-Code-Pro-Camp/agentstack-agency`). No reference to
  `aelboum` or `sofioco` appears in the archive.
- **Stack [V]:** Next.js 15.5, React 19.1, Firebase (Auth, Firestore,
  Storage), Stripe, Twilio, Resend, Upstash QStash, Puck, OpenRouter, and
  OpenAI embeddings.
- **Implemented features [V]:**
  - Contacts (no companies entity), a single fixed six-stage pipeline,
    tasks, and events.
  - Public booking with reschedule and cancel tokens.
  - A conversations index across SMS, WhatsApp, Meta (preview), and web
    chat.
  - Email broadcasts.
  - A workflow engine with dedupe IDs, run history, and send guardrails.
  - Forms and a website studio.
  - RAG knowledge base filtered by sub-account.
  - Agency → sub-accounts with snapshots.
  - Stripe platform billing.
  - `/api/v1` with hashed API keys, idempotency, and signed outbound
    webhooks.
- **Stubs or partial [V]:**
  - External calendar sync (OAuth tokens only).
  - Reviews (outbound requests only).
  - Reports (computed in the browser).
- **Security weaknesses observed (code reading, not runtime-verified):**
  - A client-supplied identity header is trusted on some public paths.
  - XSS on the MCP consent page.
  - Firestore rules allow cross-tenant document injection.
  - Client-forgeable activity history.
  - A provider token readable by collaborators.
  - Plaintext stored secrets.
  - A webhook secret carried in the query string.
  - An unauthenticated development wipe route.
  - In-memory rate limits.
  - No pagination.
  - No cross-tenant tests.
- **Useful as ideas only [R]:**
  - API key and webhook design.
  - Workflow guardrails and idempotency.
  - The booking flow.
  - Tenant-filtered retrieval.
  - Provider-adapter boundaries.
  - External lead times such as A2P 10DLC registration, Meta app review,
    and DNS.

## 3. SaaS-OS at the approved pin (`b0809ee`, v0.1.2)

**Boundary [V]:**
- ADR-0015: products live in their own repositories, and no product name
  or concept may enter SaaS-OS.
- ADR-0042: the frontend is product-owned and there is no shared UI
  package.
- ADR-0038: a single import root, `saas_os`.

| Capability | Status | Key evidence / constraint |
| --- | --- | --- |
| Bootstrap | Verified | `saas_os.api.platform.build_platform_app(*, title, version)`. Fail-closed: every route needs a policy, and the application DB role must not bypass RLS |
| Identity (OIDC) / ZITADEL | Verified / with constraints | `/auth/login`, `/auth/callback`, `/auth/logout`, `/auth/me` (user ID only). ZITADEL is configured via `OIDC_*`; `saas-os-local-identity` exists. Self-service signup not verified |
| Tenancy | With constraints | Direct membership required per request (`get_tenant_context`). Tenant creation needs an operator or `SystemCaller(PROVISIONING)`. No "my tenants" API |
| Authorization | Verified | `require_permission(resource, action, *, api_key=False)`; RBAC with deny and delegation grants; last-administrator guard |
| PostgreSQL / migrations | Verified | Two Alembic histories, platform first; separate migration and application roles; product code imports DB primitives from `saas_os.infra.db` |
| RLS | Verified; the product must apply it | `tenant_rls_statements` emits ENABLE + FORCE + a policy on `current_setting('app.tenant_id', true)`. `tenant_session_scope` uses `set_config(..., true)`, which is transaction-local |
| Jobs | With constraints | arq, at-least-once delivery, retries, then dead-letter. `worker.main(argv, *, extra_functions, extra_cron_jobs)`. `enqueue_job` has no delay and no dedupe ID |
| Idempotency, audit log, egress guard | Verified | `saas_os.core.idempotency`, `saas_os.core.audit_log`, `saas_os.infra.egress` |
| Billing | With constraints | Plans, subscriptions, entitlements, and quotas; Stripe adapter only |
| Secrets | Partial | Environment variables / `.env` only; no per-tenant credential store; `saas_os.core.crypto` for field encryption |
| Observability | Partial | JSON logs with redaction and OTel console tracing. No metrics |
| Email | Partial | Transactional SMTP with one sender; marketing and bulk email out of scope |
| AI inference | With constraints | `saas_os.inference.run_inference`. No streaming, tool calls, or embeddings |
| Webhooks | With constraints | Outbound via outbox; products cannot register outbox consumers; Stripe is the only inbound verifier |
| Health | Verified | `/healthz`, `/readyz`, `worker --check` |
| Consumer testing | With constraints | No pytest plugin ships. Integration tests against real PostgreSQL and Redis (CONSUMER-GUIDE §13) |
| Configuration | Verified | Import-time configuration. Required variables: `ENVIRONMENT`, `DATABASE_URL`, `MIGRATIONS_DATABASE_URL`, `APP_DB_USER`, `PLATFORM_CONFIG_DB_USER`, `REDIS_URL`, `OIDC_ISSUER_URL`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `PUBLIC_APP_ORIGIN` |

**Install check [V]:** A clean install of the pin under Python 3.13.14
resolved 34 packages, including fastapi 0.156.0, SQLAlchemy 2.1.5,
alembic 1.20.0, and pydantic 2.14.1. With placeholder configuration
(nothing connected), every public module listed in `PHASE1-PLAN.md` §3
imported, and `build_platform_app` constructed an application offline.
Without `ENVIRONMENT` and `REDIS_URL`, several modules refuse to import,
so configuration is checked at import time.

**Gaps the product must handle without modifying SaaS-OS [I]:**
- Delayed and scheduled per-tenant work.
- Product event fan-out.
- Discovering a user's workspaces.
- Agency access to client workspaces.
- Per-tenant provider credentials.
- Marketing email, bounce handling, and suppression.
- Embeddings.
- Metrics.
- Realtime delivery.
- File storage.

## 4. GoHighLevel reference (public sources, 2026-10-20)

**Pricing [V]** (`gohighlevel.com/pricing`):

| Plan | Monthly | Annual |
| --- | --- | --- |
| Starter | $97 | $970 |
| Unlimited | $297 | $2,970 |
| Agency Pro | $497 | $4,970 |

Usage-based channel fees and AI plans are billed on top.

**Recommendations for this product [R]:**
- **MVP:** contacts and companies, pipelines, the inbox data model with
  one email channel, and forms.
- **Phase 3–5:** single-user booking.
- **Later:** SMS (A2P 10DLC), WhatsApp/Meta, reviews, and external
  calendar sync.
- **Not early:** voice, the funnel/site builder, SaaS-mode resale, and
  white label.
- **Remove:** any "GBP chat" channel. Google Business Messages shut down
  on 2024-07-31.

**Candidate differentiators [I]:**
- Truthful delivery and execution state.
- Predictable cost with spend caps.
- Tenant-safe, suggest-first AI.
- Fewer, finished modules.
- Consent and suppression by construction.

## 5. Claude Design

**Not imported [V].** No Claude Design MCP server is configured. The
`DesignSync` tool is limited to the user-started `/design-sync`
design-system flow. No local copies of the project files were found.
Frontend work is blocked until the project is imported and inspected
(ROADMAP §24).

**Update 2026-10-21 — task 0.3 complete [V].** The owner exported the
project as `Design system questionnaire-handoff.zip` (211,140 bytes,
SHA-256 `128683965341eeace19746a8c8e0b70987bf484f41590036b19b068c030b55d7`)
and it was inspected read-only, outside the repository; nothing was
copied in. The 2026-10-20 status above is kept as history. Findings,
provenance limits (the bundle does not contain the project ID), the
design-to-roadmap mapping and the missing-design backlog are recorded
once, in `DESIGN-INSPECTION.md`; decisions in `DECISIONS.md` (D-DES,
K5.1, P2-A to P2-E). Frontend implementation still waits for decision
P-6 and the Phase 2 decisions.
