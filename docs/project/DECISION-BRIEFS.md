# Decision briefs and register (2026-11-02, decision 13-D1)

Each brief states the exact decision, the alternatives, a recommendation,
and the cost, security and reversibility of the choice. Background and
architecture: `BLOCKED-WORK-PREPARATION.md`. Nothing here is decided until
the owner says so; until then the current safe defaults stay (everything
off). Costs are indicative orders of magnitude, not quotes.

## Register (priority order)

| # | Decision | Blocks | Urgency |
| --- | --- | --- | --- |
| 1 | Public submissions that match an existing contact (brief 8) | **Approved 2026-11-02 and implemented (DECISIONS P7-V)** | Done |
| H | Hosting and first staging deployment (`DECISION-BRIEF-HOSTING.md`, 2026-11-07) | Every deployment, so every real user, email activation and signup | **Staging decided 2026-11-08 (DECISIONS D-STG.5):** one OVHcloud VPS, databases in containers, `crm-staging.auravox.nl`; deployed and audited (`STAGING-ACCEPTANCE-REPORT.md`). **Production hosting still open** (the brief's recommendation stands: managed PostgreSQL and Redis) |
| 2 | Parent email domain and production activation (brief 6) | All real email: confirmations, reminders, replies | High: the product's core channel |
| 3 | SaaS-OS GET support for inbound email (brief 1) | Inbound email content | High: needs an upstream release first. Proposal submitted upstream 2026-11-03: aelboum/saas-os#205 (`SAAS-OS-GET-PROPOSAL.md`); shipped upstream as `StrictEgressClient.get` in SaaS-OS v0.10.0, now pinned (K3.9); the receiving client is not built and inbound stays unauthorized |
| 4 | Role-upgrade execution (brief 7) | New features for workspaces created before them | Medium: only when such workspaces exist. Test-database dry-run report for review: `ROLE-UPGRADE-DRY-RUN-REPORT.md` |
| 5 | Custom-domain resolver and certificates (brief 4) | Hosted pages on customer domains | Medium |
| 6 | Agency workspaces and billing (brief 3) | Phase 11, paid plans | Medium: commercial model |
| 7 | AI provider, plan limits, permitted data (brief 2) | Phase 9 | Lower: no dependency for others |
| 8 | Website tracking and consent (brief 5) | Visit history | Lower: optional feature |
| 9 | AI voice agents: direction and workstream 15V (brief 9) | Any voice work; nothing else | **Direction approved 2026-11-03 (DECISIONS P15-V)**; K5 unchanged. Open: providers (`VOICE-PROVIDER-COMPARISON.md`), legal review and DPIA (`VOICE-LEGAL-REVIEW.md`), prices (`VOICE-COST-MODEL.md`), SaaS-OS streaming submitted upstream 2026-11-03 as aelboum/saas-os#206 (`SAAS-OS-REALTIME-PROPOSAL.md`). Sandbox accounts and legal counsel not approved yet; cost estimate in `VOICE-ACTIVITY-COSTS.md`. Readiness specification and slices with approval gates: `VOICE-SPEC.md`, `VOICE-UX-SPEC.md`, `VOICE-SLICES.md` (next gate: V0/V1) |
| — | minimatch audit exception (13-A3) | Nothing; development tools only | Expires 2026-12-31: decide again before then if no fix exists |

## Brief 1 — SaaS-OS GET support for Resend inbound email

- **Decision:** ask SaaS-OS to add `get` (and `delete`) to
  `StrictEgressClient`, and later approve moving the pin to the release
  that has it.
- **Alternatives:**
  - (a) the SaaS-OS change, recommended;
  - (b) keep metadata-only inbound: members see that a message arrived but not what it says;
  - (c) a LeadStack-owned HTTP client. Refused, because it would duplicate platform egress outside its controls.
- **Recommendation:** (a). LeadStack's side is about 40 lines behind the
  existing seam; the pipeline (signed webhook, routing, quarantine, review)
  is built and tested.
- **Cost:** no service cost; upstream work in SaaS-OS, plus a pin move with
  its full re-test.
- **Security:** same destination allowlist, TLS, size and time limits as
  POST. Inbound content stays untrusted (text only, attachments not fetched).
- **Reversibility:** high. The receiving client is a setting; switching it off
  returns to metadata-only.

## Brief 2 — AI provider, account, plan limits and permitted CRM data

- **Decision:**
  - which provider and account SaaS-OS's governed inference uses;
  - which plans include AI and their monthly token limit;
  - which CRM fields may be sent.
- **Alternatives:**
  - provider: a major hosted model provider under a business agreement with no training on inputs, or a self-hosted model (more operational work, lower quality);
  - data: (a) a minimal allowlist with no contact details or message text (the contact brief); (b) also message text for reply suggestions; (c) broad record access. Refused.
- **Recommendation:** a hosted provider with a no-training, no-retention
  data agreement; start with data option (a) and the contact brief only;
  AI off by default per workspace; a modest token quota per plan.
- **Cost:** usage-based per token. Small for briefs (a few thousand tokens
  each), capped by the quota. No cost until enabled.
- **Security:**
  - CRM data leaves the platform to the provider, under the agreement;
  - prompts never carry secrets;
  - CRM content is treated as untrusted data;
  - outputs are only shown, never acted on automatically;
  - the audit records use and token counts, not text.
- **Reversibility:** high. Switch off per workspace or platform-wide. Data
  already sent cannot be recalled, which is why the allowlist starts minimal.

## Brief 3 — Agency workspace and billing model

- **Decision:**
  - how agencies and their clients are modelled;
  - who pays;
  - which plans exist;
  - activating Stripe through SaaS-OS.
- **Alternatives:**
  - (A) flat workspaces with agency staff invited to each;
  - (B) an agency parent workspace with client child workspaces, using SaaS-OS's hierarchy and hierarchy-aware billing;
  - (C) a separate agency product.
- **Recommendation:** (B), with access to a client's data only through
  explicit membership in that client. The agency pays for its clients
  (billing inheritance). No reseller billing at first.
- **Cost:** Stripe's processing fees per payment; no fixed cost until live.
  Engineering for the agency view and white-label branding.
- **Security:** isolation stays per workspace (no inherited data access);
  billing data and keys stay in SaaS-OS; the agency view shows ids and
  counts, not records.
- **Reversibility:** the model is hard to reverse once customers depend on
  it (choose deliberately). Billing activation can be paused; plans can be
  withdrawn.

## Brief 4 — Custom-domain resolver and certificate infrastructure

- **Decision:**
  - which DNS-over-HTTPS resolver verifies ownership (`CUSTOM_DOMAIN_DOH_URL`);
  - the production edge and its certificate storage;
  - when hosted pages may use custom domains.
- **Alternatives:**
  - resolver: a public validating DoH resolver, or a self-hosted resolver;
  - certificates: (a) Caddy on-demand TLS gated by `/v1/public/domains/allowed`; (b) a managed edge or CDN with custom hostnames (paid per hostname); (c) certificates issued by hand (does not scale).
- **Recommendation:** a reputable validating DoH resolver, and (a) Caddy
  on-demand TLS with shared certificate storage, ACME from Let's Encrypt.
- **Cost:** the resolver and certificates are free. Edge hosting and storage are
  small. Option (b) costs per hostname per month.
- **Security:**
  - ownership is proven by a TXT token, re-checked daily;
  - certificates are issued only for verified hosts of open workspaces;
  - the app's session cookie never leaves the app host;
  - ACME rate limits need monitoring.
- **Reversibility:** high. Unset the resolver URL or remove the edge
  rule; verified domains simply stop resolving.

## Brief 5 — Website tracking and consent

- **Decision:**
  - whether to build visitor tracking at all;
  - whose consent banner is used;
  - which jurisdictions it targets and how long data is kept;
  - whether aggregate counts without consent are acceptable.
- **Alternatives:**
  - (a) no tracking; form and booking attribution, which exists, suffices;
  - (b) consent-gated tracking as proposed: nothing without consent, GPC and DNT respected, a 90-day raw retention;
  - (c) cookie-based tracking without a consent gate. Refused.
- **Recommendation:** (a) for now. If visit history is wanted, (b), using
  the site's own consent manager through a small API, and legal review of
  the wording in the target jurisdictions.
- **Cost:** storage and engineering only; consent tooling may cost the site
  owner.
- **Security and privacy:** personal data about visitors; consent records,
  export and deletion must cover it; a legal review is needed before
  launch. No compliance is claimed.
- **Reversibility:** high before launch. Once data is collected it must be
  kept or deleted under the stated retention.

## Brief 6 — Parent email domain and production activation

- **Decision:**
  - the parent domain for `notify.`, `mail.`, `campaigns.` and `inbound.` (decided: separate subdomains, Resend);
  - authorising production sending, stream by stream;
  - authorising inbound processing (after brief 1).
- **Alternatives:**
  - domain: a domain the business already owns, or a new dedicated sending domain (protects the main domain's reputation);
  - activation: all streams at once, or stepwise.
- **Recommendation:** a dedicated sending domain owned by the business;
  activate stepwise: transactional (confirmations, reminders) first after
  DNS (SPF, DKIM, DMARC) checks pass. Conversation replies follow. Campaigns
  come last, and only after one-click unsubscribe headers (SaaS-OS gap 1)
  and double opt-in (13-H1 2) exist.
- **Cost:** Resend's plan for the expected monthly volume; a domain
  registration if new.
- **Security:**
  - wrong DNS harms deliverability; the domain's reputation is shared by all workspaces;
  - in place: bounce and complaint suppression, per-stream rate limits, late mail expiry (13-H5), and the production locks;
  - activation is the first time real customers receive LeadStack mail.
- **Reversibility:** high per stream (switch off), but mail already sent
  cannot be recalled.

## Brief 7 — Role-upgrade execution

- **Decision:** approve running `role_upgrade` on real workspaces, and
  whether administrative permissions are included.
- **Alternatives:**
  - (a) the bound procedure (13-R1): dry run, review, apply with the fingerprint;
  - (b) leave old workspaces without newer features;
  - (c) recreate roles by hand. Error-prone.
- **Recommendation:** (a) for the non-administrative permissions first;
  administrative ones in a separate, explicitly approved run.
- **Cost:** none.
- **Security:** it changes what customers' members may do; it grants only
  what the approved matrix already gives new workspaces; every grant is
  audited; a backup is taken first.
- **Reversibility:** medium. Grants can be revoked from `applied.json`; there
  is no automatic undo.
- **Update 2026-11-06:** a proposed replacement runs the same additions
  through SaaS-OS's permission grant migrations instead
  (`PERMISSION-GRANT-MIGRATIONS-PLAN.md`); if approved, this brief becomes
  that plan's steps D to F.

## Brief 8 — Public submissions that match an existing contact

**Status:** approved by the owner on 2026-11-02 and implemented as decision
P7-V (see `DECISIONS.md`).

**Finding:** forms and bookings match an existing contact by the email the
visitor typed, without proving the visitor owns it. Today such a submission
can:
- add the form's tag to the contact (P7-A 6);
- record marketing consent `granted` for them (P7-B), or attach a booking to them;
- start that contact's form, booking and tag automations (P8-B), which may set
  the stage, remove tags, assign an owner or create tasks.

A stranger who knows a customer's email can therefore change that
customer's CRM state, and can record consent on their behalf. The harm is
bounded:
- each automation runs once per contact;
- rate limits apply;
- confirmation mail goes to the real address;
- campaign sending is disabled and also requires double opt-in (13-H1 2), so
  no marketing mail can result today.

- **Decision:** how much an unverified public submission may do to an
  existing contact.
- **Alternatives:**
  - (a) keep the current behaviour, documented (13-H5);
  - (b) treat a matched submission as an unverified claim: record the submission and the booking; do not add the form's tag, change consent or start automations unless the automation explicitly opts in to unverified matches;
  - (c) verify the visitor by an email link before any effect on an existing contact, which needs production email;
  - (d) never match: always create a new contact and let members merge.
- **Recommendation:** (b) now, then (c) once email is live.
  - Consent recorded from a public form for an existing contact is stored as
    `unconfirmed` and counts only after a double opt-in click.
  - New contacts created by the submission keep today's behaviour.
- **Cost:** none (engineering only).
- **Security:** closes the impersonation path into automations and consent;
  members still see every submission.
- **Reversibility:** high. A per-automation setting and a consent state.

## Brief 9 — AI voice agents (inbound and outbound)

**Status:** direction **approved** by the owner on 2026-11-03 (DECISIONS
P15-V, eight points); the full brief is `VOICE-AGENTS-BRIEF.md`. Not
authorised to build; K5 unchanged; providers deferred; legal review required
before production implementation; no recording by default; explicit,
demonstrable consent for AI outbound calls.

- **Decision:** approve AI voice agents as an intended capability with
  roadmap workstream 15V (slices V0 to V6), built after launch.
- **Alternatives:**
  - (a) record the direction now, build after launch (recommended);
  - (b) an inbound-only pilot before launch, widening the MVP;
  - (c) leave voice to an external product through the API platform.
- **Recommendation:** (a), with a hosted voice platform behind a product
  adapter and every LLM turn through SaaS-OS governed inference.
- **Cost:** none now. Later: provider fees per minute (market reference
  roughly $0.07 to $0.25 a minute before telephony), a legal review and
  DPIA, about six engineering slices.
- **Security:** a new public surface and new personal data (audio,
  transcripts); per-tenant webhook credentials, tenant derived server-side,
  fail-closed outbound checks, mandatory AI disclosure, provable consent.
- **Reversibility:** high: nothing is built; after a release, kill switches
  stop calls at once.