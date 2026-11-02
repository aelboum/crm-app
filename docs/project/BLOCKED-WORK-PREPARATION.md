# Preparation for blocked roadmap work (2026-11-02, decision 13-P1)

Prepared under the owner's hardening mandate of 2026-11-02 ("Prepare blocked
roadmap work … where safe"). Nothing here is built or switched on: no paid
provider is connected, no CRM data leaves the platform, no billing is
active, no DNS is changed, no certificate is issued, no tracking runs, and
the SaaS-OS pin stays v0.6.0. Each section ends with the decisions the owner
must make. Facts about SaaS-OS were read from the installed v0.6.0 package
(`d980e73b0313ed63f2a59fd4a991a89f75791c0e`).

## 1. AI assistants and knowledge (Phase 9)

**What SaaS-OS v0.6.0 provides (verified):** `saas_os.inference` with
`run_inference(caller, tenant_id=…, request=InferenceRequest)` (governed,
non-streaming; `stream_inference` is not enabled), `register_use_case` /
`UseCase`, `register_ai_permissions` / `AI_PERMISSIONS`, `UsageReport`, and
typed refusals for entitlement, quota, policy, rate limit, timeout, response
size and endpoint security (`InferenceEntitlementDeniedError`,
`InferenceQuotaExceededError`, `InferencePolicyDeniedError`, …). Usage and
quotas: `saas_os.core.usage` (`ingest_event`, `check_quota`,
`consume_quota_idempotent`); entitlements: `saas_os.core.billing`
(`has_entitlement`, `require_entitlement`). No embeddings API (gap 13 in
`saas-os-gaps.md`), so knowledge retrieval stays unbuilt.

**Provider-neutral architecture (proposed):**

- A product module `crm_app.ai` owns use cases, never providers: each use
  case (first: *contact brief*, then *reply suggestion*, *conversation
  summary*) is registered with SaaS-OS, which owns the provider, model,
  keys and endpoint trust. The product never holds an AI key and never
  calls a provider directly.
- **Data boundary per use case (allowlist, not blocklist):** the contact
  brief sends first name, lifecycle stage, company name, tag names, the
  last N activity *types and dates*, and open deal stages, never email
  addresses, phone numbers, notes, message bodies, custom-field values or
  other contacts. Reply suggestions would send the last message bodies of
  that one conversation only, after the owner approves message content
  leaving the platform. Every prompt is built from typed fields, so a new
  column never leaks by accident.
- **Untrusted input:** CRM content is quoted as data inside the prompt,
  never as instructions; outputs are text shown to a member, never
  executed, never sent automatically, never written back without a
  member's action.
- **Controls:** a per-workspace switch (off by default) plus an entitlement
  (`ai.assistant`) and a monthly token quota per workspace through
  `core.usage`; a new permission `crm_app.ai:use` (members) and
  `crm_app.ai:manage` (Owner, Admin); each request audited by use case,
  outcome and token count, never prompt or output text; failures map to
  plain states (unavailable, quota reached, not entitled, refused).
- **Tenant isolation:** the use case runs with the request's workspace
  only; retrieval (later) only from that workspace's rows under RLS.

**Owner decisions (P9-0, unchanged):** the AI provider and account; plan
entitlements and the token limit; which CRM data may be sent (the allowlist
above is the proposal); whether message bodies may ever be sent.

## 2. Agency management, white label and billing (Phase 11)

**What SaaS-OS v0.6.0 provides (verified):**

- **Tenant hierarchy:** `get_ancestor_ids`, `get_descendant_ids`,
  `descendant_ids_by_depth`, `move_tenant`, `lock_ancestor_ids`, with depth
  and cycle checks.
- **Hierarchy-aware billing:**
  - `resolve_billing_owner`, billing inheritance and sponsorship;
  - merchant and billing accounts, plan offers and eligibility;
  - `combine_entitlements`;
  - a `BillingProvider` interface with `FakeBillingProvider` and `StripeBillingProvider`;
  - `process_provider_event`.
- **Usage roll-up:** `aggregate_usage_including_descendants`.

Not verified: whether membership in an agency tenant grants any access to
its client tenants; the current model gives each workspace its own
members.

**Product-model options:**

- **A. Flat workspaces, agency as people:** agency staff are invited into
  each client workspace; billing per workspace. Simplest, no hierarchy, no
  cross-workspace view.
- **B. Agency tenant with client child tenants (recommended):** an agency
  workspace is the parent of its client workspaces (SaaS-OS hierarchy).
  The agency pays for its clients through billing inheritance or
  sponsorship and sees roll-up usage. Agency staff reach a client only
  through an explicit membership in that client (no implicit inheritance
  of data access), so tenant isolation stays per workspace. An "Agency HQ"
  view lists the children and their health from ids and counts, never
  their records.
- **C. Separate agency product:** a distinct front end over the same
  tenants. Not justified yet.

**White label (with B):** a product-owned branding record per agency
(name, logo, colours, support email), applied to the agency's client
workspaces, their hosted pages and the custom domains of P12-D. Email
sender identity comes from P6-D sending domains. No reseller billing
(clients paying the agency through LeadStack) before a separate decision.

**Billing boundaries:** plans, subscriptions, entitlements and the
provider belong to SaaS-OS; the product only asks `has_entitlement` and
reports usage. No product billing tables, no product Stripe calls. Until
approved: `FakeBillingProvider` in tests only; no Stripe configuration,
keys or webhooks.

**Owner decisions:** option A, B or C; who pays (agency or client);
plans and their entitlements (contacts, members, campaigns, AI tokens);
white-label scope; the Stripe account and activation.

## 3. Inbound email: the HTTP-client limitation

**The limitation (verified):** `saas_os.infra.egress.StrictEgressClient`
exposes only `post` (client.py:184). Resend's inbound flow sends a signed
`email.received` webhook with metadata. The message content (text, HTML,
attachments) is fetched with `GET /emails/receiving/{id}` (Resend's
receiving API), so LeadStack can record and route an inbound email's
envelope but cannot fetch its body. `crm_app.inbound.configured_client()`
therefore returns none (P6-I).

**Options:**

1. **SaaS-OS adds `get` to `StrictEgressClient` (recommended, smallest):**
   the same destination allowlist, TLS, response-size cap, deadline and
   redirect refusal as `post`, and no new dependency. LeadStack then
   implements `ResendReceiving.fetch(email_id)` behind the existing
   `inbound.configured_client()` seam. That is about 40 lines plus tests,
   and the rest of the pipeline (signed webhook, idempotent record,
   routing, quarantine, review) is already built and tested. It needs a
   SaaS-OS release and the owner's approval of a pin move (K3).
2. **Webhook content only:** route on metadata and show "content
   unavailable" until (1). This is the current state, safe but of little
   use to members.
3. **A product-owned HTTP client:** refused. It would be a parallel
   platform implementation of egress (CLAUDE.md §3) and bypass SaaS-OS's
   destination controls.

**The interface asked of SaaS-OS** (upstream request, matching gap 2):
`async def get(url, *, headers, deadline) -> EgressResponse`, with the same
guarantees as `post`, and `DELETE` for gap 3 (Resend domains).

**Owner decisions:** request the SaaS-OS change; approve a pin move once
it is released; production inbound stays off until authorised.

## 4. Custom domains: DNS ownership and edge TLS

**Built (P12-D):** claims with a random TXT token at
`_leadstack-challenge.<host>`, constant-time comparison, single verified
owner, a daily re-check that lapses a domain whose record is gone, and
`GET /v1/public/domains/resolve` (Host → workspace, verified and open
workspaces only, 13-H3). Missing: the DNS resolver and TLS at the edge.

**DNS resolver (proposed):** DNS-over-HTTPS with RFC 8484 POST
(`application/dns-message`) to one approved resolver, through the existing
egress client (POST is available). This needs no new dependency and no
pin move: a `TxtResolver` adapter encodes the TXT query, posts it and
parses the answer. It needs DNSSEC-validating resolvers (the AD bit
checked), a 3-second deadline, and failures that never lapse a verified
domain (already the rule). Alternative: `dnspython` over UDP from the
worker (a new dependency, outside egress controls; not recommended).

**Edge TLS (proposed):** the edge (Caddy, as in `deploy/local/Caddyfile`)
issues certificates on demand for verified hosts only:

    {
        on_demand_tls {
            ask http://app:8000/v1/public/domains/allowed
        }
    }
    https:// {
        tls { on_demand }
        reverse_proxy app:8000
    }

`ask` must answer 200 only for a verified, open workspace's host. That is
a small variant of `resolve` taking `?domain=`, rate-limited and returning
no workspace id. ACME issuance (Let's Encrypt) is rate-limited per
registered domain; certificate storage must be shared by all edge nodes.
Hosted pages served on a custom host must keep the app's security headers
and never serve the signed-in app or its session cookie there (cookies
stay on the app host).

**Owner decisions:** the DoH resolver(s); the production edge and its
certificate storage; whether hosted pages get custom domains before
launch.

## 5. Website tracking: a privacy-preserving consent model

**Proposed model (nothing built):**

- **Off by default per workspace**; the embed script (P12-W) only sends
  page views when the workspace turns tracking on *and* the visitor has
  consented.
- **Without consent:** no cookies, no local storage, no identifiers, no
  IP storage. At most an aggregate count per page and day, if the owner
  decides aggregate counting needs no consent in the target jurisdictions
  (a legal question; no compliance is claimed).
- **With consent:** a first-party, random visitor id in a cookie scoped
  to the customer's site (13 months at most). Page views are linked to a
  contact only after that visitor submits a form or books. Consent is
  recorded in the existing consent records (P7-B) with channel `tracking`,
  the wording shown and the time; withdrawing it deletes the visitor id
  and stops collection.
- **Signals respected:** Global Privacy Control and Do Not Track mean no
  tracking, and a site's own consent manager can grant or deny through a
  small JavaScript API.
- **Data:** tenant-owned, RLS, no full URLs with query strings (path
  only), no referrer query strings, raw events kept 90 days and then
  aggregated; included in contact export and deletion.
- **Abuse limits:** origin must be the workspace's registered website
  (P12-W CORS), per-site rate limits, a body size cap.

**Owner decisions:** whether to build tracking at all; the consent banner
(LeadStack's or the site's); jurisdictions and retention; whether
aggregate counts without consent are acceptable.

## 6. Role upgrades

Prepared and tested (decision 13-R1, `ROLE-UPGRADE-RUNBOOK.md`): dry run
with a plan fingerprint and JSON report, and an apply bound to the reviewed
fingerprint (required in production). **Owner decision:** approve a run on
real workspaces, and whether administrative permissions are included.
