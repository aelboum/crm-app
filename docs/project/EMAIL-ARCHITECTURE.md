# Email architecture, Resend runbook and DNS readiness

Status: living document, started 2026-11-01 (decision P6-S). It records
what is built, what is designed but not built, the boundary with SaaS-OS,
and the gates that keep production email off.

**Owner decisions in force (2026-11-01):** provider Resend, through
SaaS-OS v0.6.0; separate subdomains per stream; inbound email yes;
explicit approval before each campaign; customer-owned sending domains,
website integration and custom domains for hosted pages are approved
requirements. **Production sending and production inbound are NOT
authorized.** No domain has been supplied or confirmed; nothing here
assumes one exists.

## 1. Integration boundary (verified against the pinned package)

SaaS-OS v0.6.0 (`saas_os.core.email`) provides, and LeadStack uses:

- `send_email(EmailMessage)`: one message, one bare sender address, `to`,
  subject, text and optional HTML body, optional single `reply_to`, an
  optional `Message-ID`. Every address is validated
  (`validate_email_address`: no whitespace, so **no display names**).
- `ResendEmailProvider`: `POST https://api.resend.com/emails` through the
  egress client, the API key from the secrets provider (`RESEND_API_KEY`),
  an `Idempotency-Key` derived from the `Message-ID`, and
  `EmailProviderError` with `permanent`, `reply_code` and
  `retry_after_seconds` (from `Retry-After`).
- `saas_os.infra.egress.StrictEgressClient` (public), for any further
  outbound HTTPS call; `saas_os.infra.ratelimit` (Redis fixed windows);
  `saas_os.infra.jobs` (durable jobs, retries with plain exponential
  backoff, dead letters); `saas_os.infra.secrets`.

SaaS-OS v0.6.0 does **not** provide (gaps; the pin is not changed):

| Capability | Consequence in LeadStack |
| --- | --- |
| Display names in `From` | Senders are bare addresses (`team@mail.<parent>`). |
| Custom headers other than `Message-ID` | No `List-Unsubscribe` / `List-Unsubscribe-Post`, no `In-Reply-To` / `References`. Campaign sending cannot meet bulk-sender header requirements until SaaS-OS adds them (an upstream request to raise). Conversation threading uses a routing reply address instead of headers. |
| Attachments, tags, scheduling, batch send | Outbound mail is text only. |
| Resend Domains API, inbound (receiving) API, webhook verification | Product-owned adapters over `StrictEgressClient` (inbound, domains) and the product's own Svix verification (`crm_app.domains.emails.signature_valid`, 6E.1). |
| Jitter or `Retry-After` in job retries | The product keeps `email_message.next_attempt_at` (P6-S). |

Resend facts used (Resend documentation, read 2026-11-01): webhooks are
signed the Svix way and retried with the same `svix-id`; event types
include `email.sent`, `email.delivered`, `email.delivery_delayed`,
`email.bounced`, `email.complained`, `email.failed`, `email.suppressed`
and `email.received`. `email.received` carries metadata only (no body, no
headers, no attachment content); the content comes from
`GET /emails/receiving/{id}` (text, HTML, headers, `authentication` with
SPF/DKIM/DMARC results, attachment metadata) and attachments from
`GET /emails/receiving/{id}/attachments` (signed `download_url` with
`expires_at`). Domains are created with `POST /domains` (`capabilities`
`sending` / `receiving`) and the response lists the exact DNS records to
publish; `POST /domains/{id}/verify` re-checks them asynchronously
(`domain.updated` events). For receiving on a domain that already has
mail, Resend recommends a subdomain so its MX record does not compete with
the existing one.

## 2. Streams (built, P6-S)

| Stream | Sender domain | Purposes | Switches | Default rate (per workspace / all, per minute) |
| --- | --- | --- | --- | --- |
| Transactional | `notify.<EMAIL_PARENT_DOMAIN>` | `booking_confirmation`, `test` (later: verification, security, billing notices) | `EMAIL_SENDING_ENABLED` | 60 / 120 |
| Conversation | `mail.<EMAIL_PARENT_DOMAIN>` | `conversation_reply` | `EMAIL_SENDING_ENABLED` and `EMAIL_CONVERSATION_SENDING_ENABLED` | 30 / 60 |
| Campaign | `campaigns.<EMAIL_PARENT_DOMAIN>` | none yet (campaigns are not sendable) | `EMAIL_SENDING_ENABLED` and `EMAIL_CAMPAIGN_SENDING_ENABLED` | 20 / 60 |
| Inbound | `inbound.<EMAIL_PARENT_DOMAIN>` | receiving only | `EMAIL_INBOUND_ENABLED` | n/a |

- Every purpose maps to exactly one stream
  (`crm_app.domains.email_streams.PURPOSE_STREAMS`); an unmapped purpose
  cannot be queued or sent, so marketing content cannot travel as a
  transactional message, and transactional mail never depends on
  campaign consent (it checks only the suppression list).
- Without `EMAIL_PARENT_DOMAIN`, only transactional mail has a sender
  (`EMAIL_DEFAULT_SENDER`, for local development); conversation and
  campaign mail have none and are never sent from another stream's
  identity.
- Rate limits are counted in Redis per stream, per workspace and across
  all workspaces. A limit reached, or a limiter that cannot answer, makes
  the email wait (`next_attempt_at`); it never sends past the limit.
- Invitation emails (`crm_app.invitations`) still use
  `EMAIL_DEFAULT_SENDER` synchronously, as decided in Phase 2; moving them
  to the transactional stream is a later change that keeps invitation
  semantics.

## 3. Outbound lifecycle (built)

`queued` → `sending` (one try is under way) → `sent` (the provider
**accepted** it; not delivery) → `delivered`, `delivery_delayed`,
`bounced`, `complained` or `rejected` (from signed provider events:
`rejected` is Resend's `email.failed` or `email.suppressed` after
acceptance), or `failed` (never accepted: a permanent refusal or
`MAX_ATTEMPTS` tries) or `suppressed` (never handed over: the address is
suppressed).

- A draft is not an email: nothing is queued until a member sends a reply
  or a flow queues a confirmation.
- Idempotency: one `email_message` per send intent (the conversation API
  takes an `Idempotency-Key`); every try carries the same `Message-ID`,
  from which SaaS-OS derives Resend's `Idempotency-Key`; a claim under a
  row lock keeps two workers from sending one email.
- Retries: a transient failure releases the email with `next_attempt_at`
  = now + 30 s × 2^(tries−1) (at most one hour), stretched by up to 25 %
  random jitter, and never sooner than the provider's `Retry-After`. A job
  that arrives early only records the wait; the sweeper
  (`python -m crm_app.email_maintenance`) enqueues it when due, which also
  recovers emails whose worker died mid-try.
- Delivery events move a status forward only and are recorded once per
  provider event id; bounces and complaints suppress the address.
- Logs, audit entries and errors carry ids and codes, never addresses,
  subjects, bodies or provider texts.

## 4. Designed, not yet built

Each item below is approved by the owner and will be built in this order;
each one gets its own decision entry, tests and documentation.

1. **Inbound email (6E.3) — built (P6-I)** except the real receiving
   client (SaaS-OS's egress client has no GET; decision P6-I lists the
   options). A separate signed webhook
   (`RESEND_INBOUND_WEBHOOK_SECRET`, 404 until set and
   `EMAIL_INBOUND_ENABLED`) stores each `email.received` event once by
   `svix-id` in a global inbound table before anything else, then a durable
   job fetches the content through a product adapter. Routing uses only
   server-side data: the recipient must be a routing address
   `reply+<token>@inbound.<parent>` whose token (random, 128 bits or more,
   stored hashed) maps to one workspace and conversation; nothing in the
   email (headers, workspace names) is trusted for authorization. A sender
   that does not match the conversation's contact, a failed DMARC result,
   an unknown token or a malformed payload goes to quarantine (review by a
   member with reply permission, or by an operator for mail that matches
   no workspace); valid mail is never silently dropped. Text is preferred;
   HTML is converted to text and never rendered. Attachments are recorded
   by name, type and size only and are not downloaded until a malware
   scanner is approved and configured.
2. **Campaigns (7C) — built up to approval (P7-C); sending blocked.** Drafts, segments over CRM data, preview, recipient
   estimate and eligibility (consent and suppression), then
   `draft → validated → awaiting_approval → approved → queued → processing
   → completed` (or `rejected`, `cancelled`, `failed`,
   `partially_completed`). Approval binds a hash of the content and
   audience; any change after approval returns the campaign to draft.
   Sending stays disabled: no campaign can be sent until the campaign
   stream is activated, which also needs `List-Unsubscribe` support.
3. **Customer-owned sending domains.** A workspace registers its own
   domain through the Resend Domains API (product adapter), is shown the
   exact records Resend returns, verifies, and then adds sender identities
   on that domain. A workspace can only send from a domain it registered
   and that is verified; removal or a failed re-verification stops its
   use; one domain belongs to at most one workspace.
4. **Website integration — built (P12-W)** except the tracking script. Embeddable forms and a lead-capture API for
   external sites with per-workspace site keys, allowed origins,
   attribution, consent capture and abuse limits; an optional tracking
   script, off by default.
5. **Custom domains for hosted pages — built (P12-D)** except DNS lookups and edge TLS (owner decisions). Separate from email domains:
   ownership proof by a DNS TXT token, Host-header mapping to one
   workspace, TLS where the deployment's edge supports on-demand
   certificates, takeover protection on removal.

## 5. Configuration

| Setting | Kind | Default | Notes |
| --- | --- | --- | --- |
| `EMAIL_SENDING_ENABLED` | flag | off | Global switch; refused in production. |
| `EMAIL_CONVERSATION_SENDING_ENABLED` | flag | off | Needs `EMAIL_PARENT_DOMAIN`; refused in production. |
| `EMAIL_CAMPAIGN_SENDING_ENABLED` | flag | off | Needs `EMAIL_PARENT_DOMAIN`; refused in production. |
| `EMAIL_INBOUND_ENABLED` | flag | off | Needs `EMAIL_PARENT_DOMAIN`; refused in production. |
| `EMAIL_PARENT_DOMAIN` | domain | unset | ASCII (punycode for IDN), at least two labels. |
| `EMAIL_TRANSACTIONAL_LOCAL_PART`, `EMAIL_CONVERSATION_LOCAL_PART`, `EMAIL_CAMPAIGN_LOCAL_PART` | local part | `no-reply`, `team`, `news` | No `+` (reserved for routing). |
| `EMAIL_<STREAM>_WORKSPACE_PER_MINUTE`, `EMAIL_<STREAM>_GLOBAL_PER_MINUTE` | whole number ≥ 1 | see §2 | `<STREAM>` is `TRANSACTIONAL`, `CONVERSATION` or `CAMPAIGN`. |
| `EMAIL_DEFAULT_SENDER` | address | unset | Transactional fallback without a parent domain (development). |
| `EMAIL_PROVIDER` | SaaS-OS | smtp | `resend` for Resend; `mailpit` locally. |
| `RESEND_API_KEY` | secret | unset | Secrets provider only. |
| `RESEND_WEBHOOK_SECRET` | secret | unset | Delivery events webhook; 404 until set. |
| `RESEND_INBOUND_WEBHOOK_SECRET` | secret | unset | Inbound webhook (P6-I); 404 until set and `EMAIL_INBOUND_ENABLED`. |

Secrets are read only through SaaS-OS's secrets provider; none is ever in
source, frontend configuration, logs or job payloads. Start-up validation
(`crm_app.settings.validate_settings`) refuses every email switch in
production, and the send path itself refuses to hand any email to a
provider when `ENVIRONMENT=production` (a second, independent lock).

## 6. Activation gates (all open)

Production email is turned on only by a change that records each gate as
passed, approved by the owner:

1. The owner supplies the parent domain and confirms ownership.
2. The four subdomains are created in Resend (sending for notify, mail,
   campaigns; receiving for inbound) and **the records Resend returns** are
   published by the domain owner; Resend shows each as verified.
3. DMARC is published for the parent domain and checked.
4. The owner approves the sender policy (which local parts, reply-to
   behaviour) and the production rate limits.
5. Webhook endpoints are configured in Resend over HTTPS with their own
   signing secrets, stored in the production secrets provider.
6. A test send and a test inbound message pass on the verified domains
   with internal addresses only.
7. For campaigns additionally: `List-Unsubscribe` support (SaaS-OS, or an
   approved alternative), the unsubscribe flow, and the per-campaign
   approval workflow verified.
8. For inbound attachments additionally: an approved malware scanner.
9. For inbound at all: an approved receiving client (decision P6-I) and a
   retention period for unmatched rows.

## 7. DNS readiness checklist (per domain, when a real domain exists)

Do not invent values: every record comes from Resend's response for that
domain (`POST /domains` or the dashboard), copied exactly.

- [ ] Domain ownership confirmed by the owner (registrar access).
- [ ] `notify.`, `mail.`, `campaigns.` created in Resend with sending
      enabled, in the agreed region; `inbound.` with receiving enabled.
- [ ] SPF: the Return-Path (`send.` by default) TXT and MX (feedback)
      records exactly as Resend lists them.
- [ ] DKIM: the `resend._domainkey` record exactly as listed.
- [ ] DMARC: a `_dmarc.<parent>` TXT policy the owner chooses (start with
      `p=none` and reporting, then tighten); alignment checked.
- [ ] MX for `inbound.<parent>`: the receiving MX Resend lists, as the
      lowest priority value on that subdomain only, so the parent domain's
      own mail is not affected.
- [ ] No tracking subdomain unless open/click tracking is approved (it is
      not, today).
- [ ] Resend shows every record and the domain as verified.
- [ ] Webhook endpoints registered over HTTPS (TLS valid), secrets stored.
- [ ] Test delivery to internal mailboxes passes SPF, DKIM and DMARC.
- [ ] Test inbound to a routing address lands in the right conversation;
      an unknown address is quarantined.

## 8. Runbook

- **Check configuration:** start the app or worker; validation lists every
  email setting problem by name without printing values.
- **Stuck emails:** `python -m crm_app.email_maintenance` (every minute)
  re-enqueues emails whose retry time passed and drops orphans.
- **Rate limits:** raise `EMAIL_<STREAM>_*_PER_MINUTE` only with the
  owner's approval; a waiting email shows `last_error = rate_limited`.
- **Webhook secret rotation:** add the new secret in Resend, store it,
  restart, then remove the old one; events signed with an unknown secret
  are refused (401) and Resend retries them.
- **Dead letters:** SaaS-OS `list_dead_letters` shows jobs that exhausted
  their tries; the email row keeps its own status and the sweeper's next
  pass retries it while tries remain.

## 9. Incidents and recovery

- **Provider outage or 5xx:** emails stay `queued` with backoff; nothing
  is lost. No action until it recovers.
- **Burst of bounces or complaints on a stream:** turn that stream's
  switch off (others keep working), investigate, and keep suppressed
  addresses suppressed.
- **Suspected key leak:** revoke the Resend API key in Resend, issue a new
  one into the secrets provider, restart; turn sending off meanwhile.
- **Wrong recipient or content:** a sent email cannot be recalled; the
  audit trail names the email id and the member whose action queued it.
- **Webhook flood or forgery:** requests are size-limited, rate-limited per
  address and refused without a valid recent signature before parsing.
