# Progress Record

The verified current state of the project. `ROADMAP.md` defines the
destination; this file records what is actually true. Do not record
anything here that was not verified.

**Last updated:** 2026-10-24 (Phase 2 complete, decisions P2-F and P2-G).
Earlier: 2026-11-06 (system-actor audit entries, K3.5; SaaS-OS pin moved to v0.8.0, decision K3.4); 2026-10-31 (SaaS-OS pin moved to v0.6.0, decision K3.3); 2026-10-23 (SaaS-OS pin moved to v0.5.0, decision K3.2); 2026-10-21 (SaaS-OS pin moved to v0.3.0, decision K3.1;
first local commits, decision K2.1; remote, push and first CI run,
decision K2.2; Claude Design inspection, D-DES and K5.1; Phase 2
decisions P2-A to P2-E approved)

## Current phase

- **Phase 0 — Discovery:** evidence complete. Task 0.3 was completed on
  2026-10-21 by a read-only inspection of the owner's file export of the
  Claude Design project; the Claude Design MCP workflow was not used.
  Canonical record: `DESIGN-INSPECTION.md`.
- **Phase 0.5 — Foundational decisions:** K1–K5, D-WS and P-1 to P-6
  approved and recorded in `DECISIONS.md`; K5.1 (global SaaS direction)
  approved 2026-10-21. P-6 defers the frontend framework choice, which
  is still open.
- **Phase 1 — Product foundation:** complete. Locally verified, and CI
  passed on the exact pushed commit `dbb15609cd2531d3c430f06ee9c2e7bbd7f6a1c6`
  (GitHub Actions run 39652641595, 2026-10-21), which meets acceptance
  criterion 9 (decision K2.2). CI also passed on `13d6685` (run
  39653421776).
- **Phase 2 — Identity, workspaces and tenant isolation:** complete,
  2026-10-24. Verified on current code: integration suite against
  `crm_app_test`, 229 passed; ZITADEL sign-in test (`tests/identity`),
  1 passed; the owner's browser sign-in from the LeadStack start page
  `/app` through ZITADEL and back (`/auth/me` 200 with the user ID only),
  and sign-out ending both the application and ZITADEL sessions (decision
  P2-G). CI passed on `5c06d48` (run 40094376772). Security findings are
  fixed or dispositioned (`PHASE2-SECURITY-REVIEW.md`); accepted residuals
  are deferred to Phase 13.
- **Phase 3:** slices 3A, 3B, 3C (tags), 3D (custom fields), 3E1, 3E2
  and 3F (CSV import) done. Work continues under the owner's
  autonomous-development mandate (decision M1); next is Phase 4.
- **Phase 6 slice 6D, customer-owned sending domains (decision P6-D,
  2026-11-01):** migration `0029_sending_domains` (sending_domain, global
  sending_domain_index, sender_identity; `email_message.sender_identity_id`
  and `sender_address`); `/sending-domains` and `/sender-identities` API
  (workspace permissions); Resend Domains adapter (POST create and verify,
  off by default, refused in production); signed `domain.*` events;
  Settings › Sending domains. Verified: `test_sending_domains.py`
  (no provider, refusals, exact records, one workspace per domain,
  identities, verification by signed event, sending from the workspace's
  address, waiting after a failure, isolation, removal), unit
  `test_sending_domain_rules.py` 15 (with the Resend adapter),
  `sendingDomainSettings.test.tsx` 3; unit suite 709; full integration
  suite in four batches, 786 passed (196, 195, 221, 174); Vitest 302,
  lint and build clean.
- **Phase 12 slice 12D, custom domains (decision P12-D, 2026-11-01):**
  migration `0028_custom_domains` (custom_domain, global
  custom_domain_index); `/domains` API (workspace permissions), public
  `/v1/public/domains/resolve`; daily re-check in
  `crm_app.email_maintenance`; Settings › Domains with the TXT record to
  publish. No DNS client yet (owner decision), so nothing is verified
  outside tests. Verified: `test_custom_domains.py` (claims and refusals,
  exact-record verification, one workspace per hostname, hand-over after
  the daily re-check lapses the old claim, failing lookups lapse nothing,
  removal, expiry, isolation), unit `test_custom_domain_rules.py` 18,
  `domainSettings.test.tsx` 3; unit suite plus the domain, website, email,
  foundation, rollback, table-guard, purge and workspace-route integration
  tests 843 passed; Vitest 299, lint and build clean.
- **Phase 12 slice 12W, website integration (decision P12-W, 2026-11-01):**
  migration `0027_websites` (website; `form_submission.website_id` and
  `attribution`); `/websites` API under the form permissions; the public
  form routes enforce allowed origins with CORS and a preflight, and keep
  attribution; the Forms screen has a Websites panel and embed code.
  Verified: `test_websites.py` (allowed and unlisted origins, other
  workspaces, preflights, hosted page and server callers, attribution,
  disable and remove), unit `test_website_rules.py` 20,
  `embedSnippet.test.ts` 4, `forms.test.tsx` 13; unit suite plus the
  website, form, foundation, rollback, table-guard and purge integration
  tests 820 passed; Vitest 296, lint and build clean.
- **Phase 7 slice 7C, campaign preparation (decision P7-C, 2026-11-01):**
  migration `0026_campaigns` (campaign, campaign_recipient; email purpose
  `campaign`; consent method `unsubscribe_link`); the `/campaigns` API with
  the approval workflow bound to a content hash; one-click unsubscribe;
  new permissions `campaign:read`, `campaign:manage`, `campaign:approve`;
  the Campaigns screen. Sending is unavailable (no List-Unsubscribe
  support in SaaS-OS). Verified: unit 656 (including
  `test_campaign_rules.py`); full integration suite in four batches, 770
  passed (191, 181, 221, 177; `test_campaigns.py` included, and the
  permission-registration guard passing again); Vitest 289 (including
  `campaigns.test.tsx`); lint and build clean.
- **Phase 6 slice 6E.3, inbound email (decision P6-I, 2026-11-01):**
  migration `0025_inbound_email` (global `inbound_email` and
  `conversation_route_index`; tenant `conversation_route` and
  `inbound_quarantine`; `conversation_message.inbound_email_id` and
  `attachments`); signed inbound webhook; system job
  `crm_app_inbound_process` and sweeper; routing by routing token only;
  review API and the Inbox "Needs review" panel; Reply-To on email replies
  while inbound is on. Off by default and refused in production; no real
  receiving client yet (SaaS-OS egress has no GET), so no real mail is
  received. Verified: `test_inbound_email.py` (signatures, dedup, routing,
  unknown, absent, several and forged routing addresses, quarantine,
  malformed content, attachments listed only, retries and parallel workers
  adding each email once, review access and versions, tenant isolation,
  production refusal), `test_inbound_rules.py` 15, `inbox.test.tsx` 10;
  unit suite plus the inbound, email, conversation, search, foundation,
  rollback, purge and table-guard integration tests: 789 passed, and the
  permission-registration guard failed only because campaign permissions
  (next slice) had been registered in the local test database mid-run;
  Vitest 283, lint and build clean.
- **Phase 6 slice 6S, email streams (decision P6-S, 2026-11-01):** the
  owner's email architecture decisions recorded and the integration
  boundary documented (`EMAIL-ARCHITECTURE.md`); transactional,
  conversation and campaign streams on `notify.`, `mail.` and `campaigns.`
  of `EMAIL_PARENT_DOMAIN`, with their own switches, senders and rate
  limits; migration `0024_email_streams` (`next_attempt_at`, status
  `rejected`); backoff with jitter and `Retry-After`; every email switch
  refused in production, and the send path refuses production on its own.
  Verified: unit 635 (`test_email_streams.py`, stream settings, backoff
  and rejection rules); `test_emails.py` 15; the unit suite with the
  email, booking-email, conversation, foundation and rollback integration
  tests, 743 passed before the count fix, then `test_emails.py` 15 passed.
  Not built yet: inbound email, campaigns, customer domains.
- **Gate G7, existing workspaces' roles (decision P2-G7, 2026-11-01):**
  operator command `python -m crm_app.role_upgrade` grants each product
  role what its template gained since the workspace was provisioned.
  Verified: `test_role_upgrade.py` 6 against disposable workspaces (dry run
  changes nothing; exact per-role grants; administrative grants only with
  the flag; custom grants kept; re-run changes nothing; untouched other
  workspaces; skips and refusals). Not run against the local development
  workspaces or any real one.
- **Phase 6 slice 6C.1, Inbox search and paging (decision P6-C1,
  2026-11-01):** migration `0023_conversation_search` (generated
  `search_vector` columns with GIN indexes and the inlined `crm_app.@@`
  operator); `GET /conversations` takes `q`, `status=all`, `limit` and
  `cursor` and returns `next_cursor`; the Inbox has a search box, an "All"
  status and "Load more". `EXPLAIN` shows a bitmap index scan on the GIN
  index. Verified: `test_conversation_search.py` 6 (cross-workspace,
  closed threads, literal special characters, empty results, limits,
  paging), unit `test_conversation_rules.py` 12, `inbox.test.tsx` 7; unit
  suite plus conversation, foundation and rollback integration tests 693
  passed; lint and build clean.
- **Phase 6 slice 6C, conversations foundation (decision P6-C,
  2026-11-01):** migration `0022_conversations` (conversation,
  append-only conversation_message, conversation_read); the
  `/conversations` API with `Idempotency-Key` on create and add-message;
  new permissions `conversation:read` and `conversation:reply`; the Inbox
  screen. An email reply is queued through `crm_app.emails` and shown as
  "Not sent yet"; nothing leaves while `EMAIL_SENDING_ENABLED` is off.
  Verified: `test_conversations.py` 9, `inbox.test.tsx` 5, unit 585,
  Vitest 278, tsc, lint and build clean; full integration suite in four
  batches (186, 164, 207, 171). Local `crm_app` at `0022_conversations`
  (69 contacts kept). In Chrome, in a workspace provisioned for the check
  ("E2E Inbox 6C"): a thread started by logging the contact's message, an
  email reply queued (one `conversation_reply` email, status `queued`), an
  internal note, assigned and closed; at 390 px the list and the thread
  show one at a time with a back button; no overflow, no console errors.
- **Phase 8 slice 8A.1, automation engine (decision P8-A, 2026-11-01):**
  migration `0021_automations` (automation, automation_version,
  automation_run, automation_step, global automation_due); the
  `/automations` API; trigger on contact creation; job
  `crm_app_automation_run`; sweeper
  `python -m crm_app.automation_maintenance`. Verified:
  `test_automations.py` 8, unit `test_automation_rules.py` 20.
  Slice 8A.2: Marketing › Automations screen (list, editor, activate,
  pause, delete, run history); `automations.test.tsx` 5. Also verified:
  unit 585, Vitest 273, full integration suite in four batches (201, 185,
  169, 163 + the access-map test updated for the two new actions, 25).
  Local `crm_app` at `0021_automations` (68 contacts kept). In Chrome, in
  a workspace provisioned for the check ("E2E Automations 8A"): an
  automation built in the editor, activated, then a contact created; the
  real worker (`python -m crm_app.worker`) ran the job the sweeper
  enqueued, completing the run and creating the task assigned as set;
  run history shown; no overflow at 390 px, no console errors.
- **Phase 6 slice 6E.2, booking confirmation emails (decision P6-E2,
  2026-11-01):** a booking queues a confirmation to the visitor when the
  page's new `confirmation_email` setting is on (migration
  `0020_booking_confirmation`); time in the workspace's zone, never the
  private link. Verified: `test_booking_emails.py` 4, unit 565, Vitest
  268, full integration suite in four batches (198, 192, 157, 164). Local
  `crm_app` at `0020_booking_confirmation` (68 contacts kept).
- **Phase 6 slice 6E.1, transactional email infrastructure (decision P6-E,
  2026-11-01):** Resend through SaaS-OS `send_email`; migration
  `0019_email` (`email_message`, `email_event`, global `email_index`,
  suppression origin `provider`); job `crm_app_email_send`; sweeper
  `python -m crm_app.email_maintenance`; signed webhook
  `POST /v1/public/email/resend/events`. Sending stays off
  (`EMAIL_SENDING_ENABLED`, refused in production); no real provider was
  called. Verified: `test_emails.py` 10, unit 564, full integration suite
  in four batches (193, 179, 162, 171; the two rollback tests that list
  later tables were updated and passed again, 74). Local `crm_app` at
  `0019_email` (68 contacts kept).
  Also: the worker start-up test's timeouts came from jobs other tests
  leave in the shared test Redis; it now uses its own emptied Redis
  database and passed 3 of 3 runs.
- **Phase 10 slice 10A, reports (decision P10-A, 2026-11-01):**
  `GET /reports/{contacts,deals,tasks,appointments}` for a period of
  whole days in the workspace's zone with a comparison period; Insights ›
  Reports with definitions next to every figure. Migration
  `0018_report_indexes`. Verified: `test_reports.py` 7 passed, unit 549,
  Vitest 268; full integration suite in four batches 194, 169, 162 and
  178 passed (the worker start-up test timed out once under load in
  batch 2 and passed in batch 4). Local `crm_app` migrated to
  `0018_report_indexes` (68 contacts kept). Checked in Chrome in "Local
  test workspace": the figures match its data, the appointments card
  fails alone (that workspace has no appointment grant), no overflow at
  390 px.
- **M-P1, member display names (2026-11-03):** voice set aside by the owner.
  Members set their own display name in My profile (migration
  `0035_member_profiles`, `GET`/`PUT /v1/workspaces/{ws}/me/profile`), and
  every owner, assignee, host, author and team row shows it instead of
  "Member <id>".
- **M-P2 and phone-width check (2026-11-04):** My profile states the
  device's time zone instead of a picker that could not save, and notes
  when the workspace's business zone differs (owner chose this over a
  stored member zone). Phone check at 375 px in Chrome of Contacts,
  Companies, Opportunities (board, create dialog, drawer), Tasks, the
  contact drawer and Settings: no page-level horizontal overflow; drawers
  and dialogs fit; Escape closes the drawer and returns focus to the row;
  the create dialog works by keyboard; stage moves are buttons. Fixed:
  task checkboxes are 24 px on touch screens (were 16 px); on screens
  below 760 px, choosing a Settings section brings its heading to the top
  and focuses it (its content used to start below the fold). Vitest 314.
  The queue-age health check already existed (`c6b15f4`); received
  inbound email is deliberately not counted until a receiving client
  exists (OPERATIONS.md).
- **P15-V2, voice readiness specification (2026-11-03):** `VOICE-SPEC.md`
  (requirements, architecture with Exists or Proposed SaaS-OS
  capabilities, security and permissions), `VOICE-UX-SPEC.md` (screens
  S1–S8), `VOICE-SLICES.md` (V0–V6 with approval gates and V1 test
  specifications); second provider research pass and further legal
  requirements. Documentation only; SaaS-OS #205 and #206 open with no
  response.
- **S-UP1, SaaS-OS proposals submitted (2026-11-03):** aelboum/saas-os#205
  (GET on the egress client, for inbound email) and #206 (streaming
  inference with a voice first-event deadline, for workstream 15V),
  separate, for discussion only; pin unchanged. Also
  `VOICE-ACTIVITY-COSTS.md`: a bake-off of three platforms about $60–120
  (Dutch numbers need a KvK extract and address; +3197 numbers cannot carry
  voice), legal review and DPIA about €5k–12k (boutique) or €15k–35k (large
  firm); neither approved.
- **P15-V approved (2026-11-03):** the owner approved the voice direction
  and workstream 15V with eight decisions (K5 unchanged, providers
  deferred, legal review required, no recording by default, explicit
  consent for AI outbound calls). Prepared, documentation only:
  `VOICE-PROVIDER-COMPARISON.md`, `VOICE-COST-MODEL.md` (about $0.08–0.11
  a minute at list prices; no commercial prices), `VOICE-LEGAL-REVIEW.md`
  (DPIA requirements, questions for counsel, retention),
  `VOICE-THREAT-MODEL.md` (diagrams, STRIDE, emergency stop),
  `SAAS-OS-REALTIME-PROPOSAL.md` (pin unchanged). CI run 41635128590 on
  `8089760` passed all four jobs.
- **P15-V, AI voice agents direction (2026-11-03):** the owner corrected
  the roadmap: inbound and outbound AI voice agents are an intended
  capability. Recorded as workstream 15V in Phase 15 (slices V0 to V6) and
  brief 9; `docs/project/VOICE-AGENTS-BRIEF.md` (references, capability
  scope, integrations, architecture on SaaS-OS, EU and Dutch requirements,
  roadmap). Documentation only; K5 unchanged; nothing bought, configured,
  enabled or implemented.
- **P7-V, unverified public matches (2026-11-02, brief 8 approved):** a
  public form or booking that matches an existing contact by email keeps
  its submission or booking but no longer tags the contact, records consent
  or starts automations; consent waits for an emailed confirmation link
  (7 days, hash stored, workspace-bound, idempotent; queued only, sending
  stays off). Migration `0034_consent_confirmations`; public route
  `POST /v1/public/consent/{workspace_id}/confirm`; page `/app/c/<ws>#<token>`.
  Also prepared for review, not acted on: `LOAD-TEST-PLAN.md` (not run),
  `SAAS-OS-GET-PROPOSAL.md` (pin unchanged), `ROLE-UPGRADE-DRY-RUN-REPORT.md`
  (dry run on the test database only; nothing applied).- **13-O1, operations page (2026-11-02):** `docs/project/OPERATIONS.md`
  (processes, scheduled commands and cadence, operator commands, health
  signals); further no-decision improvements listed in DECISIONS 13-O1.
  The queue-age check `python -m crm_app.health_check` (read-only, exits 1
  when work is overdue). Verified: `test_health_check.py` 2 passed; unit
  suite and static checks clean.
- **13-D1, decision briefs and screen-reader checklist (2026-11-02):**
  `docs/project/DECISION-BRIEFS.md` (eight briefs, prioritised register),
  `docs/project/SCREEN-READER-CHECKLIST.md`; the public-submission matching
  finding (brief 8) awaits the owner; the minimatch exception re-checked,
  unchanged, expiry kept. Documentation only.
- **12D.2, custom-domain DNS lookups and the edge TLS check (2026-11-02):**
  a DNS-over-HTTPS TXT resolver through the egress client (off unless
  `CUSTOM_DOMAIN_DOH_URL` is set) and `GET /v1/public/domains/allowed` for
  Caddy's on-demand TLS. No DNS changed, no certificate issued. Verified:
  unit 740 (without configuration, as CI); integration custom domains,
  websites, workspace routes, foundation and table guard (56; no schema
  change, full suite in CI); Vitest 309; lint, types, import contracts and
  build clean.
- **13-P1, preparation of blocked work (2026-11-02):**
  `docs/project/BLOCKED-WORK-PREPARATION.md` (AI, agency and billing,
  inbound email client, custom-domain DNS and TLS, tracking consent, role
  upgrades), with the owner decisions each needs. Documentation only.
- **13-R1, bound role upgrade (2026-11-02):** `role_upgrade` dry runs print
  a plan fingerprint and a JSON report; `--apply --expect` applies only the
  reviewed plan (required in production); runbook
  `docs/project/ROLE-UPGRADE-RUNBOOK.md`. Not run on any real workspace.
  Verified: `test_role_upgrade.py` 7 passed.
- **13-H5, security review of 5D, 8B, 7T, booking and the worker
  (2026-11-02):** no critical or high findings; fixed late timely mail
  (expired or no longer due), reminder starvation, one workspace stopping
  email maintenance, runs acting for a departed activator, the run failure
  count, unparseable stored definitions, the template limit race and
  repeated reminders on rescheduling; the public-trigger behaviour is
  documented. Verified: unit 727 (without configuration, as CI); full
  integration suite 809 passed (58 files, eight foreground groups); lint,
  types and import contracts clean; no frontend change.
- **13-H4, accessibility and responsive audit (2026-11-02):** the new
  screens checked in Chrome at 390 px and 1280 px (overflow, labels,
  accessible names, AA contrast); fixed the template panel and badge
  layout, the ambiguous claim date, an unlabelled checkbox group, stale
  automation wording, and a silent reminder state. Verified: Vitest 309,
  lint and build clean; screens re-checked after the fixes.
- **13-A3, dependency audit review (2026-11-02):** pip-audit clean (no
  exceptions); npm production tree clean; the one npm exception
  (GHSA-g3hv-75wg-m249, minimatch, development tools only) re-verified
  unfixable without breaking tooling, kept at its 2026-12-31 expiry (not
  extended), now with owner and remediation plan; the audit gate fails an
  exception missing either. Verified: `npm run audit` passes; with the
  owner removed it fails ("missing owner").
- **Phase 7 slice 7T, email templates (decision P7-T, 2026-11-02):**
  migration `0033_email_templates`; `/email-templates` API (campaign
  permissions; render with the reply permission); Templates panel under
  Campaigns, "Use a template" in the campaign editor and the reply
  composer. Verified: unit 727 (without configuration, as CI); full
  integration suite 807 passed (58 files, eight foreground groups); Vitest
  309; lint, types, import contracts and build clean.
- **Phase 10 slice 10B, reports as CSV (decision P10-B, 2026-11-02):**
  `GET .../reports/<name>/export.csv` for contacts, deals, tasks and
  appointments with each report's permission; a CSV button on each card.
  Verified: unit 727 (without configuration, as CI); integration
  `test_reports.py`, `test_workspace_routes.py`, `test_foundation.py` (41;
  no schema change, so the full suite runs in CI); Vitest 306; lint, types,
  import contracts and build clean.
- **Phase 8 slice 8B, automation triggers and actions (decision P8-B,
  2026-11-02):** migration `0032_automation_triggers`; `on_event` starts
  automations for a tag added, a form submitted, an online booking and a
  deal moved into a stage, once per contact; remove tag and set lifecycle
  stage actions; the editor's trigger picker. Verified: unit 725 (without
  configuration, as CI); full integration suite 799 passed (57 files, in
  eight foreground groups); Vitest 305; lint, types, import contracts and
  build clean.
- **Phase 5 slice 5D, appointment reminders (decision P5-D, 2026-11-02):**
  migration `0031_appointment_reminders` (`workspace_settings.reminder_lead_minutes`,
  `appointment_reminder`, global `reminder_workspace`); reminders queued by
  the email maintenance run, once per appointment and start time;
  `GET`/`POST /appointments/{id}/reminders`; Settings › Business profile
  lead time; Reminders section in the appointment drawer. Verified: unit 716
  (without configuration, as CI); full integration suite 793 passed (56
  files, eight groups; the table guard rerun after declaring the new table
  append-only); Vitest 304, lint and build clean.
- **13-H3, security review of the email, domain and website surface
  (2026-11-01):** no critical or high findings; fixed inbound mail without
  a DMARC pass (now reviewed), sending-domain squatting (unverified claims
  released after 7 days, migration `0030_domain_claims`), the webhook
  timestamp parse, late or mismatched domain events, and lookups of a
  suspended workspace's custom domain. Verified: unit suite 711 (run without
  configuration, as CI does); full integration suite 788 passed (55 files,
  in seven groups); Vitest 302, lint and build clean.
- **13-H2, public booking limits and link expiry (2026-11-01):** visitor
  links expire 7 days after their appointment ends; bookings and link
  lookups count against each visitor's own hourly budget instead of one
  shared per page; a workspace takes at most 200 online bookings in 24
  hours (settings `BOOKING_*`). Verified: `test_booking_limits.py` 6
  passed, booking route and table tests 46 passed, unit 549, Vitest 261.
- **Phase 4 slice 4E, a record's deals in its drawer (decision P4-E, 2026-10-31):**
  the contact and company drawers list the record's deals (every
  outcome, newest change first, at most 10, with stage, outcome and
  value) and open them on the Opportunities page; "New opportunity"
  starts a deal linked to the record. Frontend only, on the existing
  `contact_id`/`company_id` filters. Vitest 259 passed (4 new).
  Checked in Chrome on 2026-10-31 in "Local test workspace" as its
  Owner: a deal created from Anna Bakker's drawer was linked to her and
  ACME, appeared in the list at once, opened on the Opportunities page,
  and after "Mark won" showed a Won tag in ACME's drawer; no page
  overflow at 390 px, no console errors at 1440 px. Seen but not changed:
  that workspace's roles lack the appointment grant, so the contact
  drawer showed the permission notice and also "No upcoming
  appointments". Fixed in a follow-up: the drawer's Opportunities,
  Tasks, Appointments and Consent sections show no empty text while
  their list failed (test in `recordDeals.test.tsx`; Vitest 260).
- **Phase 4 slice 4D, Home dashboard foundations (decision P4-D, 2026-10-29):**
  - **Built:** `GET /v1/workspaces/{tenant_id}/activity` (`crm_app.activity:
    read`, every role): the newest 1-20 history entries across contacts
    and companies with the record's kind, ID and name, never note text or
    field values. The Home page, where a workspace now opens: overdue
    tasks and idle deals (each opening the filtered list through a new
    `view` search parameter), Contacts, Open deals, Pipeline value with its
    weighted value, Open tasks with the overdue count, pipeline by stage
    with the weighted forecast, today's appointments, tasks due today with
    completion in place (for members who may update tasks), recent
    activity linking to the record; each card loads and fails on its own,
    and a signed-out member sees one notice. Every number comes from the
    endpoint of the page it links to; the deal totals helper moved to
    `dealParts` so Opportunities and Home add amounts the same exact way.
  - **Tests:** unit route policy for the new route; integration
    `test_history.py` (12 passed: the feed's order, limit, records,
    isolation from another workspace, roles, no note text or values);
    Vitest `dashboard.test.tsx` (8, with axe) and updated landing tests;
    whole suites: Python unit 528, Vitest 255. ruff, pyright, import
    contracts, ESLint and tsc clean.
  - **Browser** (local stack, workspace "E2E Consent 7B", after adding a
    task and a €12,500.50 deal in Proposal): the numbers matched the
    Tasks and Opportunities pages (weighted €7,500.30 at 60 %), completing
    the task in place updated the counts, the idle tile opened
    Opportunities with the idle filter on, an activity entry opened the
    contact; 1440 px and 390 px without page overflow; no console errors.
- **Phase 3 screens at phone width (2026-10-29):** checked in Chrome at
  390 px (mobile emulation) on the local stack: the Contacts and Companies
  lists (view tabs and table scroll inside their own boxes), the contact
  drawer with every section, the Edit contact and Edit tags dialogs, the
  Import dialog through column mapping, counts and the refused-rows table,
  Settings › Custom fields and Tags. One fault found and fixed: the Import
  dialog's mapping step was 14 px wider than the dialog, because a dialog
  is a grid whose implicit column could not shrink below its content and a
  fieldset defaults to `min-width: min-content`; `.dialog` now uses
  `minmax(0, 1fr)` and fieldsets `min-width: 0`. Desktop dialogs
  unchanged at 1440 px; no console errors. Also fixed: a calendar test
  compared with `toBe` against an asymmetric matcher, so it failed
  whenever it ran between 10:00 and 10:30; it now uses `toEqual`. Vitest
  247 passed, ESLint and tsc clean.
- **Security review of the public routes, 13-H1 (decision 13-H1, 2026-10-29):**
  - **Reviewed:** every `public_route` (booking pages and visitor
    bookings, hosted forms, signup status, sign-out address) and the three
    public pages, read-only. No critical findings; one high finding (a
    public form re-granting consent a member withdrew) is contained by
    suppression and recorded with the other items in 13-H1.
  - **Fixed:** deeply nested JSON and extreme times were 500s; both are now
    422s through `crm_app.api.inputs` (`json_body`, which also refuses a
    too-large declared `Content-Length` before reading, and `Instant`,
    1900-2999, for every time a client sends). A booking's creation audit
    entry says `"by": "visitor"`. The CI audit failure on `87cc643`
    (seroval advisory) was fixed separately in `b64f206`.
  - **Tests:** unit `test_inputs.py` (sizes, nesting, time range) and the
    booking audit assertion. Unit suite 528 passed; integration for the
    touched routes (appointments, booking pages, forms, signups, tasks)
    85 passed; ruff, pyright, import contracts clean; OpenAPI unchanged.
  - **Launch gate recorded:** `TRUST_PROXY_HEADERS=true` behind an edge
    that overwrites `X-Forwarded-For`, with a request-size cap.
- **Phase 7 slice 7B, consent and suppression (decision P7-B, 2026-10-28):**
  - **Built:** migration `0017_suppression` (table `suppression`:
    tenant-owned, forced RLS, append-only for the runtime role, in
    `PURGE_TABLES`, one lower-cased address per workspace, no link to a
    contact; `consent_record` gains `withdrawn`, `manual` and who recorded
    it, still append-only); catalogue permissions
    `crm_app.suppression:read` (Owner, Admin, Member) and `:manage`
    (Owner, Admin), reported by `/access` (gate G7 for older workspaces);
    routes to list (search, paging), add (pasted, up to 1,000, refusals by
    position) and remove suppressions; a contact's email status; recording
    consent with its exact wording and withdrawing it (a contact update),
    which suppresses the address in the same transaction and keeps an
    earlier reason; `crm_app.suppression.may_send`, the check the email
    channel must call. Settings › Suppression list and the contact
    drawer's Consent section (status, history, record, withdraw).
  - **Tests:** unit `test_suppression_rules.py` and route policies;
    integration `test_suppression_tables.py` (isolation, uniqueness,
    checks, no UPDATE, consent states, purge, rollback) and
    `test_suppression_routes.py` (roles, isolation, adding, the list,
    status, record, withdraw, removal, audit without addresses or
    wording); Vitest `consent.test.tsx` (with axe). Whole suites: Python
    unit 527, integration 681 (one worker start-up test timed out once under load and passed on its own rerun) (four sequential chunks), Vitest
    247.
  - **Browser** (local stack, dev DB migrated to 0017 without reset, new
    workspace "E2E Consent 7B"): pasted three addresses as Bounced with a
    note; recorded consent for a contact ("May receive marketing email"),
    withdrew it (the address appeared on the list as Unsubscribed ·
    Consent withdrawn, the drawer read "Suppressed"); removed an address
    at 390 px after the confirmation; no page overflow; no console errors.
  - **Not built (P7-B 1):** the public unsubscribe page and tokens (come
    with the email channel), bounce and complaint events (need a
    provider), CSV import of suppressions, double opt-in, other channels.
- **Phase 5 slice 5C, public booking pages (decision P5-C, 2026-10-28):**
  - **Built:** migration `0016_booking_pages` (`booking_page` and `booking`,
    tenant-owned, forced RLS, composite links, in `PURGE_TABLES`; contact
    source `booking`; an appointment cancelled by the visitor has no
    cancelling member); catalogue permissions `crm_app.booking_page:read`
    (every role) and `:manage` (Owner, Admin), reported by `/access` (gate
    G7 for older workspaces); members' routes to list, create (idempotent),
    edit, publish (needs business hours), unpublish and delete pages; public
    routes for the page, its free times (14 days at a time), a booking
    (Idempotency-Key, 8 KiB, honeypot, per-address and per-page limits that
    fail closed) and the visitor's own booking by a token sent in the body
    (view, cancel until it starts). A booking checks the time again under
    the host's lock, creates or matches the contact (never changing a
    matched one), refuses a fourth upcoming booking of the same contact on
    the same page, and creates a confirmed appointment; the token is kept
    only as its SHA-256 and returned once. Appointments say how they were
    booked. Calendar › Booking pages (a drawer and an editor), the hosted
    page `/app/b/<workspace>/<key>`, the visitor's link
    `/app/b/<workspace>/manage#<token>` and the drawer's Source row.
  - **Tests:** unit `test_booking_page_rules.py` (free times, visitor
    details, title, token), route policies (five public routes), purge
    order, contact sources; integration `test_booking_page_tables.py`
    (isolation, links, checks, cascades, purge, rollback) and
    `test_booking_page_routes.py` (roles, isolation, publishing, the public
    page, free times, booking rules, matching, the limit, the honeypot,
    the visitor's link, audit acting as the host); Vitest
    `bookingPages.test.tsx` (with axe). Whole suites: Python unit 514,
    integration 657 (four sequential chunks), Vitest 236.
  - **Browser** (local stack, dev DB migrated to 0016 without reset, new
    workspace "E2E Booking 5C" made with `crm_app.provision`): creating a
    page; publishing refused until business hours were set, then
    published; the hosted page at 390 px listed free times by day in
    Europe/Amsterdam; a booking showed the private link; the link showed
    the booking and cancelled it; the appointment drawer at 1440 px read
    "Booked online · Intro call" and "Cancelled by the visitor"; the
    drawer at 390 px without page overflow; no console errors.
  - **Not built (P5-C 1):** emails or reminders to the visitor or the host
    (need a delivery channel), the visitor rescheduling, several hosts,
    buffers, custom questions, payments, an embed script, CAPTCHA.
- **Phase 5 slice 5B, business hours and availability (decision P5-B, 2026-10-28):**
  - **Built:** migration `0015_business_hours` (a nullable `business_hours`
    column on `workspace_settings`: seven days, Monday first, each closed or
    one `HH:MM` range in the workspace time zone; a `CHECK` on the outer
    shape), saved by the existing settings `PATCH` (version, `If-Match`,
    audit with field names; Owner and Admin) and cleared with `null`;
    `GET /appointments/availability` (open intervals in UTC for a range of at
    most 42 days, daylight saving handled on the server); the live conflict
    check's `outside_hours` flag. Outside hours is a warning, never a
    refusal. Settings › Business profile has a Business hours editor (a
    switch and two times per day; "Set business hours" offers Monday to
    Friday 09:00-17:00 until saved; "Clear business hours"); the calendar
    hatches closed time, names it in the legend, warns in the booking dialog
    and gives each team member a status line (free now, in an appointment
    until, outside business hours) from today's own queries, so the side
    panel speaks of today in any range.
  - **Tests:** unit `test_appointment_rules.py` (open intervals, a
    daylight-saving change, containment), `test_settings_values.py`
    (business hours shape) and route policies; integration
    `test_workspace_settings.py` and `test_appointment_routes.py` (hours set,
    unchanged, refused, cleared, audited; Tokyo hours as UTC intervals;
    outside-hours flag; booking outside hours allowed; bounded ranges; other
    workspaces 404); Vitest `calendar.test.tsx` and
    `BusinessSettings.test.tsx` (with axe). Whole suites: Python unit 499,
    integration 610 (four sequential chunks), Vitest 223.
  - **Browser** (local stack, dev DB migrated to 0015 without reset,
    workspace "E2E Calendar 5A"): set the suggested hours at 390 px and saved;
    the week view at 1440 px hatched before 09:00, after 17:00 and the
    weekend, the legend named it; at 16:59 the status line read "Free now",
    the dialog warned that 17:00 is outside business hours and booked it; at
    17:01 the line read "In an appointment until 5:30 PM". Day view at 390 px
    without page overflow; no console errors.
  - **Not built (P5-B 1, 2):** hours per member, holidays and days off, a
    lunch break, presence ("Away"). Enforcing hours belongs to the public
    booking page (built in 5C).
- **Phase 5 slice 5A, calendar and appointments (decision P5-A, 2026-10-28):**
  - **Order:** the owner chose to start Calendar now (2026-10-28, "Yes"),
    while the email channel waits for SaaS-OS. Calendar stays outside the
    K5 MVP list; this is the timing decision K5 asks for.
  - **Built:** migration `0014_appointments` (one table, forced RLS, in
    the purge manifest); permissions `crm_app.appointment` read (every
    role), create and update (Owner, Admin, Member), delete (Owner, Admin;
    gate G7 applies to older workspaces); routes for a range of at most 42
    days (at most 500 items, with `truncated`), upcoming appointments, the
    live conflict check, booking (`Idempotency-Key`), changes, status and
    cancel (`If-Match`) and delete. A host's overlapping booking is 409
    `appointment_conflict` with the conflicting appointments unless
    `allow_conflict` is sent, serialised by a per-host advisory lock;
    back-to-back appointments do not conflict. Cancelling is a final
    status and frees the slot. The Calendar page (Day, Week, Month; team
    filter with today's counts; Up next; status legend; click a free half
    hour to book; the drawer with status buttons, Reschedule, Cancel after
    confirmation and Delete for Owners and Admins; the booking dialog with
    the live check and "Book anyway"), and an Appointments section in the
    contact drawer that books with the contact filled in and opens an
    appointment on the Calendar.
  - **Tests:** unit `test_appointment_rules.py` and route policies;
    integration `test_appointment_tables.py` and
    `test_appointment_routes.py` (38); Vitest `calendar.test.tsx` (8, with
    axe).
  - **Browser** (local stack, dev DB migrated to 0014 without reset, new
    workspace "E2E Calendar 5A" because of G7): booked by clicking a slot,
    saw the live conflict for an overlapping time and booked anyway (two
    lanes), marked Pending, cancelled after confirming (gone from the grid
    and Up next, drawer read-only), booked from a contact's drawer and
    opened it on the Calendar. Checked at 1440 px and 390 px (Day view by
    default on phones; Week and Month without page overflow); no console
    errors.
  - **Not built (P5-A 1):** working hours and availability (built in 5B), a public
    booking page, reminders and notifications (need a delivery channel),
    external calendar sync, recurring appointments, rooms, several hosts.
    Members are shown as "You" or "Member <id>" as elsewhere, because
    member display names are not available yet.
  - **Local test note:** on this 24-core machine the default Vitest worker
    count makes some `findBy` waits time out under load; with
    `--maxWorkers=6` the whole suite passed twice (217).
- **Phase 7 slice 7A, forms and lead capture (decision P7-A, 2026-10-28):**
  - **Order:** forms come before the email channel (Phase 6), which waits
    for a SaaS-OS release with an email provider and a new pin the owner
    will authorize. Calendar (Phase 5) is outside K5 and not scheduled.
  - **Built (7A.1, `d8c7361`, CI run 40653263929 green):** migration
    `0013_forms` (`form`, `form_submission`, append-only
    `consent_record`); permissions `crm_app.form:read` (every role) and
    `crm_app.form:manage` (Owner, Admin; gate G7 applies to older
    workspaces); members' routes for forms, submissions and a contact's
    consent; the public routes `GET`/`POST /v1/public/forms/{workspace}/{key}`
    with per-address and per-form limits, a 16 KiB body, a required
    `Idempotency-Key`, a honeypot and one 404 for unknown, draft and closed
    forms. A submission creates a Lead (source Form) or matches the active
    contact by email without changing it (only the form's tag is added),
    records consent with the exact wording, and counts the submission.
  - **Built (7A.2):** the Forms list, the editor (fields with move, remove
    and an Add palette; a live preview from the same renderer as the hosted
    page; tag, contact owner, thank-you message and consent wording; save,
    publish and unpublish with `If-Match`; copy link; delete), the
    submissions table, the hosted page `/app/f/{workspace}/{key}` (no app
    frame, no sign-in, errors per field) and a Consent section in the
    contact drawer.
  - **Tests:** unit `test_form_rules.py` (22) and route policies (public
    routes are the only public API routes besides signup status);
    integration `test_form_tables.py` and `test_form_routes.py`; full
    integration suite 564 passed in sequential chunks; unit 473; Vitest
    209, run twice, including `forms.test.tsx` (10, with axe).
  - **Browser** (local stack, dev DB migrated to 0013 without reset, a new
    local workspace provisioned because of G7): created, renamed and
    published a form with consent wording; on the hosted page at 390 px an
    empty submission showed the per-field messages, then a real one showed
    the thank-you message; the submission appeared as "New lead" and the
    contact (source Form, stage Lead) shows the consent with its wording.
    Editor and list checked at 1440 px and 390 px with no horizontal
    scroll; no console errors other than the expected 422.
  - **Not built (P7-A 1):** landing pages, embedding on other sites, view
    counts and conversion, "Start automation", CAPTCHA, double opt-in,
    file uploads, custom-field targets, a retention period for
    submissions. A suspended workspace's public form is refused by the
    same check as a closed one; that path has no integration test because
    no role may suspend a workspace in tests.
- **Phase 4 slice 4C, tasks (decision P4-C, 2026-10-27):**
  - **Built:** migration `0012_tasks` (`task`: title, priority, optional
    due time with time zone and assignee, completion with who and when,
    optional links to a contact, company and deal cleared rather than
    cascaded when the record is deleted); `crm_app.tasks` and its routes
    (list with status, assignee, overdue, due window, link filters, four
    orders and cursors; the four tab counts; create with
    `Idempotency-Key`; update, complete and reopen with `If-Match`;
    delete, which Members may do per Q6); the Tasks page (assignee filter,
    tabs with counts, quick add with Today / Tomorrow / Next week at 17:00
    local time, groups Overdue / Today / Upcoming / No due date, complete,
    edit with an exact date and time, delete); an "Open tasks" section with
    quick add in contact, company and deal drawers; "+ New → Task".
  - **Tests:** unit `test_task_rules.py` and the route-policy table (with
    Q6's task-delete exception); integration `test_task_tables.py` (13)
    and `test_task_routes.py` (10: roles, isolation, links, validation and
    naive times, idempotent create, versions, completing and reopening,
    filters, counts, order, paging, audit without titles); Vitest
    `tasks.test.tsx` (5, with axe).
  - **Browser** (local stack, dev DB migrated to 0012 without reset): added
    three tasks, grouped Today / Upcoming / No due date with matching tab
    counts; completed one (Completed tab, struck through); added a task
    from a deal's drawer, linked to the deal; fits 390 px; no console
    errors.
  - **Limitations:** no reminders or notifications, recurring tasks,
    descriptions or bulk actions; "Today" is the viewer's day, not the
    workspace's time zone; members show by ID.
- **Phase 4 slice 4B, deals (decision P4-B, 2026-10-27):**
  - **Built:** migration `0011_opportunities` (`opportunity` with composite
    keys to a stage of its own pipeline, RESTRICT, and to contacts and
    companies, SET NULL of the link; `numeric(15,3)` amounts; open, won,
    lost with a required lost reason) and the append-only
    `opportunity_event` history (no UPDATE for the runtime role; `seq`
    orders entries); `crm_app.opportunities` and its routes (list with
    filters, five orders and cursors; summary per stage and currency;
    create with `Idempotency-Key`; update and outcome with `If-Match`;
    delete for Owner and Admin; history); stage removal with `move_to`;
    the Opportunities page (board with drag-and-drop and summary totals,
    table with outcome filter and sorting, drawer with stage stepper, Mark
    won, Mark lost with a reason, Reopen, Delete, history; create and edit
    dialog with contact and company pickers); Settings › Sales pipeline
    asks where a removed stage's deals go; "+ New → Opportunity".
  - **Money:** decimal strings end to end; the server refuses more minor
    digits than the currency has (never rounds); the currency is the
    workspace's when the deal is created; totals are summed per currency
    in exact decimals (the UI adds them with integer arithmetic) and
    formatted from the string.
  - **Tests:** unit `test_opportunity_rules.py` (money per currency,
    transitions, cursor types) and the route-policy table; integration
    `test_opportunity_tables.py` (34: RLS, cross-workspace writes,
    composite keys, value, outcome and history rules, append-only history,
    order, deletions, purge, rollback to 0010) and
    `test_opportunity_routes.py` (16: roles, isolation on every route and
    reference, money, validation, idempotent create, versions, lifecycle,
    history order and content, filters, orders, paging, summary parity,
    currency at creation, stage removal with and without `move_to`,
    concurrent updates and concurrent stage removal against creates,
    audit without titles, amounts or reasons); Vitest
    `opportunities.test.tsx` (8, with axe) and updated pipeline settings
    and app-frame tests.
  - **Browser** (local stack, dev DB migrated to 0011 without reset): a
    deal created from the dialog with a contact picked; stage moved from
    the drawer and by dragging a card; marked lost with a reason (stage
    locked), reopened; history in order; summary and column totals;
    removing the stage holding the deal moved it to the proposed stage with
    a "stage removed" history entry; board, table and drawer fit 390 px
    (the board scrolls inside itself); no console errors.
  - **Limitations:** one pipeline; no tags, custom fields, import or export
    for deals; no "Avg. days in stage" or "Won this month" metrics; card
    order within a column is by last update; members show by ID; the
    production bundle is over Vite's 500 kB warning (as before this slice).
- **Phase 4 slice 4A, pipeline and stages (decision P4, 2026-10-27):**
  - **Built:** migration `0010_pipelines` (`pipeline`, `pipeline_stage`:
    forced RLS, composite keys, case-insensitive unique names, positions
    unique per pipeline and checked at commit, in `PURGE_TABLES`);
    `crm_app.pipelines` and `GET /pipelines` (every role; the default
    pipeline "Sales" with four stages is created on the first read, once,
    under the tenant advisory lock), rename, add, change, reorder and
    remove stages (`pipeline:manage`, Owner and Admin; one version for the
    whole pipeline, `If-Match` on every change; 1-15 stages; audited by ID
    without names); `/access` `manage_pipeline`; Settings › Sales pipeline
    (move up and down buttons instead of drag, so it works from the
    keyboard).
  - **Tests:** unit `test_pipeline_rules.py` and the route-policy table;
    integration `test_pipeline_tables.py` (RLS, cross-workspace writes,
    composite key, rules, deferred positions, cascade, purge, rollback to
    0009) and `test_pipeline_routes.py` (roles, concurrent first reads,
    versions, validation, limits, cross-workspace 404s, audit); Vitest
    `pipelineSettings.test.tsx` (8, with axe).
  - **Browser** (local stack, dev DB migrated to 0010 without reset): the
    default pipeline appeared on first visit; adding "Closing" at 90 % and
    moving a stage down were saved (API shows version 3, positions 0-4);
    fits 390 px; no console errors.
  - **Limitations:** one pipeline per workspace (the design's switcher is
    not shown); no deals yet, so removing a stage moves nothing until 4B
    adds the move-to rule (P4 4A.6).
- **Phase 3F CSV import (decision P3-F, 2026-10-26/27):**
  - **Owner decisions:** import is Owner and Admin only, enforced
    server-side; staging data is kept 7 days; imported records are never
    deleted by that cleanup.
  - **Built, in pushed increments:**
    - 3F.1 (`3bce9b6`): permission `crm_app.crm_data:import` (Owner,
      Admin; `/access` `import_records`), migration `0009_imports`
      (`import_job`, `import_row`, global `import_expiry`);
    - 3F.2 (`623e65c`): `POST /imports` takes the CSV as the body (5 MB,
      10,000 rows, UTF-8 or Windows-1252, comma/semicolon/tab), proposes
      or takes a mapping, validates rows with the API's rules, marks
      duplicates (active records and earlier rows) to skip; list, detail
      and an error report of row, field and code; 10 previews per hour;
    - 3F.3 (`e7157ca`): `commit`, `cancel`, `resume`; the worker job
      `crm_app_import_commit` creates records in batches of 500 with the
      same rules, history and audit as typed records, idempotent on
      redelivery, one import at a time per workspace;
    - 3F.4: `python -m crm_app.import_maintenance` deletes staged rows
      when due (7 days after finishing, or after a never-committed
      preview, which becomes `expired`); the Import dialog on Contacts
      and Companies (file, column mapping, counts, refused rows, error
      report, import with progress, stop, resume).
  - **Tests:** unit `test_import_rules.py`; integration
    `test_import_tables.py`, `test_imports.py`, `test_import_commit.py`
    (job function run directly: batches, redelivery, cancel, failure and
    resume), `test_import_maintenance.py`; Vitest `imports.test.tsx` (7,
    with axe). The full integration suite runs in five chunks locally
    because of memory pressure on this machine.
  - **Browser** (local stack; a fresh local test workspace provisioned for
    a throwaway Owner, because workspaces created before 3F.1 lack the new
    permission, gate G7): a 6-row file previewed as 3 ready, 1 duplicate,
    2 refused with their reasons; importing through the running worker
    created the 3 contacts with source "import" (the formula-like name kept
    as text); the dialog and page fit 390 px; no console errors.
  - **Limitations:** owners, tags, custom fields and company links are not
    imported; nothing is ever updated or merged; the preview limit is a
    fixed window (as P3-E1); workspaces provisioned before 3F.1 cannot
    import until SaaS-OS offers a way to grant new permissions (G7); the
    maintenance command must be scheduled by the deployment.
- **Phase 3D custom fields (decision P3-D, 2026-10-26, under M1):**
  - **Built, in four pushed increments:**
    - 3D.1 (`744f499`): migration `0008_custom_fields`:
      `custom_field_definition` (forced RLS, purge) and `custom_fields
      jsonb` on contacts and companies (an object, at most 32 KB); the
      history allow-list gains `custom_fields`;
    - 3D.2 (`dad1e8a`): `GET/POST/PATCH /custom-fields`, `/archive`,
      `/restore` (read for every role, changes for Owner and Admin); keys
      and types fixed for good; 50 active fields per entity; audit with
      entity, key and type;
    - 3D.3 (`9af64b2`): values on record create and update, merged key by
      key and validated against the active fields (`unknown_custom_field`,
      `invalid_custom_field` naming the key); records show active fields
      only; history and audit name keys, never values;
    - 3D.4: Settings › Custom fields (per entity, key suggested from the
      label, choice options one per line, edit, archive and restore), the
      drawer's "Custom fields" card with "Manage" for Owners and Admins,
      typed inputs in both record dialogs that send only changed keys,
      and the history label.
  - **CI fix:** 3D.3's first CI run failed in `test_tag_tables.py`'s
    rollback: the new value tests left history entries naming
    `custom_fields`, which the 0007 rule refuses. Every rollback test now
    removes entries naming fields newer than its target first
    (`NEWER_HISTORY`); the product code was not at fault.
  - **Tests:** integration `test_custom_field_tables.py` (24),
    `test_custom_field_routes.py` (10), `test_record_custom_fields.py`
    (7); unit `test_custom_field_values.py` (46) and route policy; Vitest
    `customFields.test.tsx` (5, with axe).
  - **Browser** (local stack, Owner 1280 px, Member 390 px): the Owner
    created five fields (text, number, date, yes/no, choice), set values
    in the contact dialog (typed inputs: number, date, selects) and saw
    them formatted in the drawer card with "Manage"; the Member saw the
    card without "Manage", could edit values in the dialog (scrolling at
    390 px, no overflow), and a direct field creation got 403. No console
    errors other than that deliberate 403.
  - **Limitations:** no filtering, sorting or CSV export by custom fields
    yet (P3-D 7); removing a choice option keeps stored values; the type
    selector keeps its last choice after adding a field.
- **Phase 3C tags (decision P3-C, 2026-10-26, under M1):**
  - **Built, in four pushed increments:**
    - 3C.1 (`aaf5ff6`): migration `0007_tags` with `tag`, `contact_tag`,
      `company_tag` (forced RLS, composite keys, cascades, purge); the
      history allow-list gains `tags`;
    - 3C.2 (`3850aec`): `GET/POST/PATCH/DELETE /tags` (read for every
      role, changes for Owner and Admin via `workspace:update`), names
      unique regardless of case, 500 per workspace, audit by ID only;
    - 3C.3 (`b70318b`): `PUT .../{record}/tags` (record update, If-Match,
      20 per record, history and audit naming `tags`), `tags` on every
      record, a `tag_id` filter on both lists and both exports;
    - 3C.4: tag pills and a Tags column, the Tag filter, the drawer's
      Tags section and "Edit tags" dialog, Settings › Tags, and the
      history label.
  - **Tests:** integration `test_tag_tables.py` (21), `test_tag_routes.py`
    (10), `test_record_tags.py` (7); unit route policy and name rules;
    Vitest `tags.test.tsx` (9, with axe). CI passed on 3C.1-3C.3 (run
    40390565926 for 3C.3); 3C.4 is recorded with its own CI run below.
  - **Browser** (local stack, Owner desktop 1280 px, Member 390 px): Owner
    created four tags in Settings, tagged a contact in the dialog (and
    created "Event 2026" there), saw pills in the drawer and list, the
    "Updated tags" history entry, and the Tag filter narrowing the list to
    that contact. The Member saw the tags, could choose existing tags but
    had no "New tag" field, and a direct create got 403; Settings › Tags
    was read-only. No horizontal overflow, no console errors.
  - **Security review:** an independent review of the whole slice found no
    Critical or High issues. Applied: tag names also refuse Unicode format
    and separator characters (zero-width, direction marks, U+2028/2029),
    and assignment takes a KEY SHARE lock on the tags it adds. Corrected:
    migration 0007's docstring overstated how short its `activity` lock
    is; in one Alembic transaction the ACCESS EXCLUSIVE lock lasts until
    commit (no production data exists yet; later changes to large tables
    must split their steps). Accepted: the duplicate pre-check compares
    with Python's `lower()`, the database index with PostgreSQL's; the
    index decides, and a mismatch only changes which 409 a client sees.
  - **Limitations:** tags are not exported in CSV yet (P3-C 7); the Tags
    column is hidden below 760 px; tag counts per tag are not shown.
- **Phase 3E2 companies CSV export (decision P3-E2, 2026-10-26):**
  - **Built:**
    - `GET /v1/workspaces/{id}/companies/export.csv`: Owner and Admin; the
      company list's filters and order, without paging; 11 columns;
      50,000 rows at most; 10 attempts per user per window, on a budget
      separate from contacts; audited as `crm_app.companies.exported`;
    - the read-and-audit step and the route's limiter, size and file
      handling shared with the contacts export, whose behaviour and
      limiter key are unchanged;
    - the Export button on Companies, with progress and an error state for
      each refusal; the button, notices and export hook are shared with
      Contacts (`records/useRecordExport.ts`, `ExportButton`,
      `ExportNotices`).

    No migration, new permission, file storage or SaaS-OS change.
  - **Tests:**
    - unit: 4 more for the CSV contract (company columns, a protected and
      quoted company row, the empty file, the file name), and the route
      policy for the new route;
    - integration (`test_company_export.py`, 17):
      - roles (Owner, Admin 200; Member, Read-only 403; non-member 404;
        no session 401);
      - isolation: another workspace's owner ID selects nothing, and its
        companies never appear;
      - 14 filter and order cases matched against the list, including
        name and domain search, `owner=me`, the three archive views and
        every sort in both directions; the empty result is the header;
      - paging, contact-only, malformed and unknown parameters refused;
      - headers, encoding and values; stored values unchanged;
      - 50,000 rows succeed and 50,001 give 413 with no audit entry;
      - the 11th export gives 429 with Retry-After; contacts and companies
        budgets are independent both ways; a limiter outage gives 503
        with no audit entry;
      - audit holds counts and filter names only;
    - Vitest (`companyExport.test.tsx`, 11): button state, the filters
      sent (none of the contact filters), the download name, progress,
      413/429/403/503/500/network states, a safe file name, and axe
      checks. The contacts export tests pass unchanged.
    - **Totals:**
      - unit: 301 passed;
      - full integration suite: 288 passed;
      - frontend: 157 tests, lint, type check, build and `npm audit`;
      - ruff, pyright, import contracts, `pip-audit` and the secret scan:
        clean; `gen:api` regenerates the committed schema unchanged.
    - **Security review:** an independent review found no Critical, High or
      Medium issues.
  - **Browser** (local stack; Owner and Member throwaway identities;
    1280 px and 390 px emulated):
    - **Owner, desktop:** searching `xp-` and exporting downloaded a file
      with the byte-order mark, CRLF records, the 11 columns, protected
      `'=cmd Holdings`, `'+31 20 555 0101`, `'@Logistics` and `'-Food`,
      quoted `Émile, "Bakkerij"` and `https://xp-zhang.example/?a=1,b=2`,
      intact `Zoë` and `张伟`, and the list's order.
    - **Response headers:** `text/csv; charset=utf-8`, `attachment;
      filename="companies-2026-10-26.csv"`, `no-store`.
    - **Owner, 390 px:** the empty archived view exported only the header,
      with the "Companies exported" toast.
    - **Member, 390 px:** the button was disabled with its reason, and a
      direct request got 403 JSON with no data.
    - **Both widths:** no horizontal overflow and no JavaScript errors.
  - **Limitations:**
    - the limiter's window is fixed, not rolling (P3-E2 5);
    - a worst-case export of 50,000 companies with very long websites can
      use well over 100 MB of memory (P3-E2);
    - Chrome automation saved the downloads as `.tmp` files; the name was
      verified in the response header and in Vitest.
- **Phase 3E1 contacts CSV export (decision P3-E1, 2026-10-26):**
  - **Built:**
    - `GET /v1/workspaces/{id}/contacts/export.csv`: Owner and Admin;
      the list's filters and order, without paging; 50,000 rows at most;
      10 attempts per user per window; audited;
    - `export_records` in `/access`;
    - the Export button on Contacts, with progress and an error state for
      each refusal.

    No migration, new permission, file storage or SaaS-OS change.
  - **Tests:**
    - unit: 24 for the CSV contract, plus route policy and the role
      matrix;
    - integration (`test_contact_export.py`, 14):
      - roles; isolation through the path, the filters and company names;
      - every filter and order matched against the list;
      - the archive views; refused paging and unknown parameters;
      - headers, encoding and values; stored values unchanged;
      - 50,000 rows succeed and 50,001 give 413;
      - the 11th export gives 429 with Retry-After; a limiter outage
        gives 503 with no audit entry;
      - audit holds counts and filter names only;
    - Vitest (`export.test.tsx`, 10): button state, the filters sent, the
      download name, progress, 413/429/403/503/500/network states, a safe
      file name, and axe checks.
    - **Totals:**
      - unit: 297 passed;
      - full integration suite: 271 passed;
      - frontend: 146 tests, lint, type check, build and `npm audit`;
      - ruff, pyright, import contracts, `pip-audit` and the secret scan:
        clean.
    - **Security review:** an independent review found no Critical or
      High issues. Its one hardening point is applied: the CSV is built off
      the event loop.
  - **Browser** (local stack; Owner and Member throwaway identities;
    1280 px and 390 px emulated):
    - **Owner, desktop:** a filtered export downloaded a file with the
      byte-order mark, CRLF records, the 14 columns, protected `'=cmd`,
      `'@home`, `'+31…` and `'-Head…`, and quoted `Jansen, "Sam"`.
      `Zoë`, `Émile` and `张伟` were intact, the company name resolved,
      and the order matched the list.
    - **Response headers:** `text/csv; charset=utf-8`, `attachment;
      filename="contacts-2026-10-26.csv"`, `no-store`.
    - **Owner, 390 px:** an empty archived view exported only the header.
    - **Member:** the button was disabled with its reason, and a direct
      request got 403 JSON with no data.
    - **Both widths:** no horizontal overflow and no JavaScript errors.
  - **Limitation:**
    - the limiter's window is fixed, not rolling (P3-E1 7);
    - in the automated browser, Chrome left the downloads as `.tmp` files
      instead of renaming them to the server's name. The name itself was
      verified in the response header and in Vitest.
- **Phase 3A hardening (owner-approved 2026-10-26; frontend only):**
  - **Built:**
    - a searchable company picker in the contact form. It uses the
      existing company list API (prefix search, cursor pages, active
      companies only) in place of the first-50 select;
    - "Load more people" in the company drawer, with an end-of-list line
      and a next-page failure state that keeps the loaded people;
    - select errors and the picker linked to their messages
      (`aria-describedby`, `aria-invalid`);
    - a fixed accessible name on the workspace switcher;
    - dialogs scroll inside a phone-height screen (pre-existing: the
      contact form's actions were out of reach at 390 × 844);
    - the chosen company name wraps on narrow screens;
    - focus returns to the company control after a choice, a cancel or a
      removal. The down arrow moves from the search box into the results,
      and Escape closes only the search, not the contact dialog. Every
      search starts empty.
  - **No change to:** backend, migrations, permissions, the API schema,
    the SaaS-OS pin, invitations or `crm-app-login`.
  - **Tests:** 18 new Vitest cases in `records.test.tsx`, covering:
    - picker paging, search, a stale-response race, empty, error and
      retry states, keyboard and Escape handling, and removing the
      company;
    - field-error descriptions and axe checks;
    - People paging and its failure state;
    - archive, and a blocked restore;
    - the owner filter and sorting;
    - 403 and 500 states;
    - the `?create=contact` link, for creators and read-only members;
    - company edit with `If-Match`;
    - narrow-screen layout and the switcher name.

    Frontend total: 136 tests. Unit tests: 272 passed. Full integration
    suite: 257 passed. An independent review found no blocking bugs; its
    four keyboard and focus findings are fixed.
  - **Browser** (local stack, 1280 px and 390 px emulated):
    - a company beyond the first 50 found by "Load more" and by search,
      chosen by mouse and by keyboard, and saved on the new contact;
    - Zylo Logistics' People list went from 50 to 56 with "All 56
      people shown.";
    - a real 429 from the rate limiter (after seeding) showed the error
      state, and Try again recovered;
    - field errors are linked to their controls, including a real server
      422 on Stage;
    - the switcher is named at both widths;
    - no horizontal overflow, and no console messages on the test page.
  - **Local test data:** 61 companies and 57 contacts in the throwaway
    workspace "E2E Stage D 8cab83".
- **Self-service signup (decision S-1, 2026-10-24):** planned in
  `SIGNUP-PLAN.md`; supersedes P2-C's exclusion. Verified on 2026-10-24:
  baseline `f3e08f5` = `origin/main`, SaaS-OS pin `b03d87a` unchanged.
  Implemented (commit approved by the owner 2026-10-24): `SIGNUP_ENABLED` and the two limit settings with start-up
  rules in `crm_app.settings` (off by default; refused in production until
  the launch gates pass; requires `TRUST_PROXY_HEADERS=true`), their unit
  tests, and `.env.example` documentation. No endpoint, table, migration,
  ZITADEL configuration or screen exists for signup yet.
  - **L4:** investigated through the local edge. It does not reproduce
    locally; forged `X-Forwarded-For` is ignored. Reduced, not closed
    (`SIGNUP-PLAN.md` §5).
  - **Launch gates LG-1 to LG-10 open** (`SIGNUP-PLAN.md` §7).
  - **S-1.1 (2026-10-24, committed `6ba67d4`):** limits 5
    workspaces per user and 100 attempts per rolling 24 hours as
    configurable defaults (`SIGNUP_MAX_ATTEMPTS_PER_24H` replaces
    `SIGNUP_MAX_PER_DAY`).
  - **Stage A4, local only (2026-10-24; re-verified 2026-10-25):** opt-in
    ZITADEL registration, email verification and Mailpit, kept on across
    runs by three `.env` settings (README.md). Browser-verified
    (`SIGNUP-PLAN.md` §5a):
    - registration from the LeadStack login build creates an active
      identity with an unverified email;
    - the verification email reaches Mailpit only;
    - until verified, even the right password stops at "Verify user" and
      no LeadStack session exists;
    - the email's link opens the code page filled in; after Continue the
      identity is verified and signed in, and the session carries
      `verified_email`;
    - sign-out, and sign-in again with the password, work;
    - LeadStack's signup routes still answer 404 with a valid session.
  - **Signup-table security:** investigated (`SIGNUP-PLAN.md` §4a); owner
    decision pending.
- **Branded sign-in (2026-10-24, owner-approved before slice 3C):** the
  signed-out screens of `/app` and invitation links are a LeadStack
  sign-in screen after the design's `LeadStack Signup.dc.html`
  (`DESIGN-FIDELITY.md` §4e). Verified: frontend tests, lint, type check
  and build; backend gates unchanged and green; the ZITADEL sign-in test
  (`tests/identity`), 1 passed; in Chrome, **Sign in** reached ZITADEL
  Login V2 on `localhost:8000` and Back returned to a usable screen;
  phone width 390 px emulated. No backend, SaaS-OS or identity-provider
  configuration changed; P2-C unchanged (no sign-up, no public workspace
  creation, no Google or Microsoft sign-in). Commit `04a4bb6`; CI passed
  (run 40097066377, all four jobs).
  - **Not verified in this change:** a full browser sign-in with a
    password (covered by the identity test through ZITADEL's session
    API and by the owner's earlier browser check of the same flow);
    Firefox, Safari, a real phone and a screen reader.
  - **Open gap, owner decision needed:** SaaS-OS answers a failed or
    cancelled sign-in at `/auth/callback` (and a refused `/auth/login`)
    with plain JSON (`400 Invalid login callback.`, 401, 502 or 503), not
    a LeadStack page. The product can only change this by wrapping
    those platform responses or by an upstream SaaS-OS change.
  - **Local note:** starting the server from Git Bash without
    `MSYS2_ENV_CONV_EXCL=AUTH_POST_LOGIN_PATH` (README) makes
    `/auth/login` answer "Authentication is not configured"; seen again
    during this check, not a product defect.

- **Self-service signup, Stages B and C (decision S-1.2, 2026-10-25;
  committed `13604fa`, CI run 40212699571 green):**
  - **Built:**
    - migration `0006_signup`: `crm_app.signup` (option A, forced RLS)
      and `crm_app.signup_attempt`;
    - `POST /v1/signups` and `GET /v1/signups/current`, 404 while
      `SIGNUP_ENABLED` is off, which it is by default;
    - the shared provisioning service; the operator command keeps its
      behaviour;
    - resumable provisioning that activates last;
    - limits and the counting rule;
    - the maintenance command, the purge step and the guard rules for
      global tables.
  - **Verified:**
    - pre-migration RLS probe: 28 of 28 passed (`SIGNUP-PLAN.md` §4b);
    - unit tests: 265 passed;
    - `tests/integration/test_signups.py`: 26 passed, covering
      everything in the owner's list, plus the maintenance command in a
      fresh process, and the platform cap under concurrent requests
      released by a barrier (`SIGNUP-PLAN.md` §4b);
    - the counting order fixed in review: a malformed `Idempotency-Key`
      or a body that is not JSON is now refused after the attempt is
      counted, not before;
    - a regression found by the full suite and fixed: after the
      provisioning refactor, the operator command no longer imported
      `saas_os.core.rbac` before `create_tenant`, so a fresh process
      failed with `NoReferencedTableError` (`core.delegation_grants`).
      `provision.py` and `signups.py` now import it first;
      `test_provision.py` passes again;
    - the table guard;
    - the OIDC identity test (sign-in, session, sign-out): 1 passed;
    - frontend: 83 tests, lint, type check, build;
    - ruff, pyright, import contracts, lock check and secret scan:
      clean.
    - **Full integration suite:** 254 passed, 0 failed (15 min 22 s,
      after the fix).
  - **Not done:**
    - Stage D (screens);
    - launch gates LG-1 to LG-10;
    - scheduling the maintenance command in a deployment (none exists).
  - **Local:** the development database has migration 0006, and the API
    was restarted with `SIGNUP_ENABLED` unset.

- **LeadStack sign-in pages (decision S-2, 2026-10-25; the crm-app part
  committed `8c88357`, CI run 40217274678 green; `crm-app-login` local
  only):**
  - **What exists:** `crm-app-login` is a local repository with no remote.
    It builds Login V2 v4.19.5 with a LeadStack overlay: 4 replaced and 6
    new files, the one-page form and the design's layout on every page.
  - **The image build** (`crm-app-login:dev`) checks the commit, the MIT
    licence and the hashes of the 4 replaced upstream files. Upstream's
    TypeScript check runs as part of it.
  - **Verified in Chrome against the local stack**, using a throwaway test
    user:
    - the wrong password gets the generic "Failed to authenticate.";
    - the right one leads to email verification, then back to `/app`
      signed in;
    - pressing Enter on the one form signs in;
    - the layout at 1440 px and at a 390 px phone width, with no sideways
      scrolling;
    - no visible "Zitadel" in English, Dutch, German or French;
    - `/app` without a session goes straight to sign-in;
    - after a sign-out it stays on the sign-in screen;
    - the image answers its health check;
    - "Forgot password?" with no login name asks for one; with one, it
      sends the code and opens "Set Password" in the layout. The new
      password was not set.
  - **Design match:** the first page now follows the account step of
    `LeadStack Signup.dc.html`, checked against computed styles:
    - `#F4F5F7` page, content in a 560 px column starting at the top;
    - the Geist Mono label, then a 26 px heading;
    - a provider button with the "or with email" rule;
    - 40 px fields;
    - the action bar with the primary button and arrow on the right, then
      the line about creating an account.

    Deliberate differences:
    - no step rail, since sign-in has no steps;
    - Google and Microsoft appear only once configured in ZITADEL, so a
      passkey button takes their place;
    - the language picker stays;
    - a brand bar below 760 px.

    Signing in, and the message for a missing field, were rechecked after
    the change.
  - **crm-app's frontend:** 84 tests pass, lint and type check are clean,
    and the build succeeds. The extra test covers the fix from the S-2
    review: a confirmed session clears the sign-out mark.
  - **Not verified:**
    - passkeys and other methods, through `flow=steps`;
    - completing a password reset;
    - lockout reached through the one form;
    - registration through the new layout;
    - Firefox, Safari, a real phone and a screen reader.
  - **Not run:** the CI workflows (there's no remote), and browser tests
    in CI (not written yet).
  - **Unchanged:** sign-out still stops on ZITADEL's "choose the account"
    page (P2-G residual, Low).
- **Self-service signup, Stage D (2026-10-26; `SIGNUP-PLAN.md` §4c):**
  - **Built:**
    - `GET /v1/signups/status`, public, `{"enabled": bool}` from the same
      kill switch; the other signup routes still answer 404 while it is off;
    - the sign-in screen's **Create account** entry (only when the status is
      on; it leads to the login build's "Create one");
    - the start page's workspace-name step, with one idempotency key per
      attempt, bounded progress checks, resumption, and every refusal of
      the real contract (400/409/403/404/429/503, network failure);
    - invitation precedence through the existing flow. A server-side
      pending-invitation check would need a new cross-tenant query and was
      not built (finding in §4c).
  - **Verified:**
    - unit 272 passed;
    - full integration suite 257 passed;
    - frontend 118 tests (31 for Stage D, two axe checks), lint, type
      check and build;
    - ruff, pyright, import contracts, pip-audit, npm audit and the
      secret scan: clean.
  - **Local A4 repaired:**
    - the three `ZITADEL_LOCAL_*` opt-ins and
      `ZITADEL_LOGIN_IMAGE=crm-app-login:dev` are now in the untracked
      `.env`;
    - `configure-zitadel.py` run twice with the same result (registration
      on, Mailpit active, post-sign-out address kept);
    - `zitadel-login` recreated with `EMAIL_VERIFICATION=true`.
  - **Browser (local ZITADEL v4.19.5, LeadStack login build):**
    - a disposable identity registered;
    - it stopped at "Verify user" with `/auth/me` 401;
    - the email arrived in Mailpit;
    - restarting the sign-in before verifying returned to "Verify user";
    - the emailed code signed the person in;
    - with signup off, the step reported "not available";
    - layout checked at 1280 px and at 390 px (no horizontal scroll);
    - sign-out returned straight to the sign-in form.
  - **End-to-end browser run (2026-10-26, owner-authorized; code
    `2680bf4`; local stack only):**
    - **Setup:** the local dev server on 127.0.0.1:8001 was stopped (its
      identity checked first). The test ran on a temporary server with
      `SIGNUP_ENABLED=true` set in that process only; `.env` was
      unchanged.
    - **Identities:** each run used its own throwaway identity and a
      unique workspace name.
    - **Desktop (1280 px):**
      - the sign-in screen offered "Create one", and registration ran
        through the hosted login;
      - before verification, `/auth/me` and `POST /v1/signups` both
        answered 401;
      - the code arrived in Mailpit, and verifying it signed the person in;
      - the workspace-name step appeared, and `POST /v1/signups` answered
        201 `complete`;
      - the browser opened `/app/w/{id}/settings`;
      - `/access` showed the Owner role with every action allowed; the
        workspace had one member, the Owner;
      - a business-settings save through the UI succeeded (version 0 to 1).
    - **Mobile (390 px, emulated):** the same journey, with no
      horizontal overflow on the sign-in page, the start page or the new
      workspace.
    - **Console:** no JavaScript errors. The only failed loads logged were
      expected statuses: 401 before sign-in, 404 from the first
      `GET /v1/signups/current`, and 422 from a malformed manual test
      request.
    - **Signup off:** with the server restarted without `SIGNUP_ENABLED`,
      the status answered `false`, no Create workspace option appeared,
      and `POST /v1/signups` and `GET /v1/signups/current` answered 404.
    - **Regressions:**
      - an existing member's **Create workspace** opened the step, and
        Cancel closed it;
      - the desktop Owner invited the mobile identity. With the link
        opened, the start page showed "You have an invitation waiting"
        and no Create workspace option;
      - accepting the invitation added a membership without a role and
        created no signup or workspace;
      - sign-out returned straight to a fresh sign-in.
    - **Not re-run:** `tests/identity`, because the restored server holds
      port 8001.
    - **Pre-existing, not Stage D:** at mobile width the header's workspace
      switcher button has no accessible name.
    - **Afterwards:**
      - the temporary server was stopped, and the dev server restarted
        with the same command and `.env`, signup off;
      - the local database keeps the test identities, their two
        workspaces, one accepted invitation and one settings change;
        nothing that existed before was changed.
  - **Unchanged:** LeadStack's own signup stays off (`SIGNUP_ENABLED` unset,
    refused in production); launch gates LG-1 to LG-10 remain open.

## Repository state

- **Directory:** `C:\Users\imran\Documents\crm-app`, branch `main`.
- **Commits** on `main` (decisions K2.1 and K2.2):
  - `0bdbfdb4ef382b1b64b28b7589123a425f6b9cf4` — Phase 1 foundation on
    SaaS-OS v0.1.2 (`b0809ee`), 44 files;
  - `35e13e8873ba47ac8a4da752bfa089a6c72ec01f` — SaaS-OS v0.3.0 upgrade
    (decision K3.1), 10 files; installed pin
    `5905156a99a4526e5071ce091a58667c08b0a019`;
  - `df6d810a267095c351659b84cb9d7f728427d36f` — project records for the
    local commits;
  - `dbb15609cd2531d3c430f06ee9c2e7bbd7f6a1c6` — CI keeps a result for
    every commit on `main` (per-commit concurrency group, no
    cancellation on `main`);
  - a documentation-only follow-up recording the remote and CI result.
- **Remote:** `https://github.com/aelboum/crm-app`, default branch
  `main`, created and pushed 2026-10-21 (decision K2.2). Visibility on
  2026-10-22 (`gh repo view`): **public**, by the owner's choice; the
  owner intends to make it private later. Further
  pushes need approval each time; pull requests, merges, tags,
  releases and deployment are not authorized.
- **Untracked local files, never committed (covered by `.gitignore`):**
  - `.env` and `.env.test`: local-only random credentials and the local
    OIDC client ID;
  - `.venv/`;
  - `deploy/local/.bootstrap/` (ZITADEL's bootstrap token);
  - tool caches.
- **Local Docker services** (project `crm-app-local`, all bound to
  127.0.0.1): `db` on 55432, `redis` on 56379, `zitadel` on 8081.
  `zitadel-db` publishes no port. (Changed 2026-10-22, decision D-IDL: `edge`
  on 8000 fronts the application and ZITADEL; ZITADEL publishes no port.) They are still running. Stop them with
  `docker compose -f deploy/local/compose.yaml --env-file .env --profile identity down`.
- **Untouched (verified by `git status` on 2026-10-20):**
  - `C:\Users\imran\Documents\leadstack-crm`: 1,466 deletions, `CLAUDE.md`
    modified, 2 untracked; `CLAUDE.md` and `ROADMAP.md` hashes unchanged;
  - `C:\Users\imran\Documents\Leadstack`: `a4422a0`, 72 uncommitted paths;
  - `C:\Users\imran\Documents\saas-os`: `2adf634`, clean. On 2026-10-21
    it was at `5905156` (v0.3.0, advanced by the owner) and clean; it was
    only read for the K3.1 upgrade.

## Phase 1: what was built

| Area | Files |
| --- | --- |
| Manifest, pin, tools | `pyproject.toml`, `uv.lock` (72 packages; Python 3.13.14) |
| Configuration validation | `src/crm_app/settings.py` |
| Entrypoints | `src/crm_app/app.py` (`create_app` factory), `worker.py`, `migrate.py` |
| Product migrations | `src/crm_app/migrations/` (revision `0001_crm_app_schema`: schema `crm_app`, USAGE for the runtime role, PUBLIC revoked) |
| Placeholders for later phases | `jobs.py`, `permissions.py`, `domains/` (all empty) |
| Local services | `deploy/local/compose.yaml`, `deploy/local/init/01-roles.sh`, `.env.example`, `.env.test.example` |
| CI | `.github/workflows/ci.yml` (quality, integration, security) |
| Secret-scan baseline | `.secrets.baseline` (4 audited false positives: placeholder URLs in the env examples, the pin SHA, the migration head) |
| Docs | `README.md` (with the proprietary notice), `docs/architecture/saas-os-integration.md` |
| Tests | `tests/unit` (43), `tests/integration` (7), `tests/identity` (1, opt-in) |

## Phase 1 acceptance criteria (PHASE1-PLAN.md §11)

| # | Criterion | Result | Evidence (2026-10-20) |
| --- | --- | --- | --- |
| 1 | Locked install from a clean clone; installed SaaS-OS = `b0809ee` | **Passed (clean copy)** | Copied the 44 trackable files to a fresh directory with an empty uv cache. `uv lock --check` exit 0; `uv sync --locked` exit 0; installed commit `b0809eeb…`. A true `git clone` needs a commit, which is not yet authorized |
| 2 | ruff, pyright, import-linter, import-allowlist test | **Passed** | `ruff format --check .`: 32 files already formatted. `ruff check .`: all checks passed. `pyright`: 0 errors. `lint-imports`: 2 kept, 0 broken. `tests/unit/test_import_surface.py` passed |
| 3 | Migrations after the platform's, idempotent, permissions registered | **Passed** (no permissions exist yet) | `test_both_migration_histories_are_at_head`: platform `f6a2c8e4b1d9`, product `0001_crm_app_schema` after two runs. Schema grants checked by `test_application_role_has_usage_but_cannot_create_in_the_product_schema` |
| 4 | App starts with a safe role, refuses an unsafe role, health and readiness | **Passed** | `test_application_starts_and_reports_ready` (`/healthz` 200, `/readyz` 200, `/auth/me` 401). `test_application_refuses_a_role_that_can_bypass_rls` (`UnsafeDatabaseRoleError`) |
| 5 | Worker starts with product jobs merged; `--check` passes | **Passed** (no product jobs yet) | `test_worker_starts_and_passes_its_health_probe`; negative case `test_worker_health_probe_fails_when_no_worker_runs` |
| 6 | OIDC login against local ZITADEL; `/auth/me` returns the user ID | **Passed** (ZITADEL v4.19.5) | `CRM_APP_IDENTITY_TEST=1 pytest tests/identity`: 1 passed. Covers login, `/auth/me` = `{user_id}`, cross-origin logout refused (403), logout, and no secrets in the server log |
| 7 | Configuration validation fails closed without printing values | **Passed** | `tests/unit/test_settings.py`, `tests/unit/test_entrypoints.py` (marker strings absent from stdout and stderr) |
| 8 | pip-audit and detect-secrets clean | **Passed** | pip-audit on a hashed export (SaaS-OS excluded): "No known vulnerabilities found". detect-secrets hook exit 0, and exit 1 on a planted credential |
| 9 | CI passes on the exact commit evaluated | **Not met** | No commit or push is authorized. Local stand-in: the CI integration job was dry-run against a fresh PostgreSQL 16 container using the CI credentials and `01-roles.sh` over TCP; 7 passed |
| 10 | SaaS-OS unmodified; other repositories unchanged | **Passed** | `git status` of all three repositories (see above) |

**Totals:** unit 43 passed; integration 7 passed (against local services,
and again in the CI dry run); identity 1 passed. All runs were local on
Windows 11 with Docker Desktop. Linux CI has not run.

## SaaS-OS upgrade to v0.3.0 (decision K3.1, 2026-10-21)

The table above records the evidence at `b0809ee`. On the new pin
`5905156` every check was run again, locally:

| Check | Result |
| --- | --- |
| `uv lock` | Only the saas-os entry changed (0.1.2 → 0.3.0); 72 packages, the other 71 unchanged |
| `uv sync --locked`, `uv lock --check` | Exit 0; installed `saas-os` 0.3.0, `direct_url.json` commit `5905156…`, not editable |
| `ruff format --check .` / `ruff check .` | 32 files already formatted / all checks passed |
| `pyright` / `lint-imports` | 0 errors / 2 kept, 0 broken |
| `pytest tests/unit` | 43 passed (includes the pin test, now asserting `5905156`) |
| `pytest tests/integration` (local services, `.env.test`) | 7 passed; platform migration head still `f6a2c8e4b1d9` |
| `CRM_APP_IDENTITY_TEST=1 pytest tests/identity` | 1 passed |
| `saas-os-local-identity` rerun against the local ZITADEL | Exit 0; existing project and application found, nothing created, client ID unchanged |
| detect-secrets hook | Exit 0, after replacing the audited false-positive hash of the pin SHA in `.secrets.baseline` |
| pip-audit (hashed export, SaaS-OS excluded) | "No known vulnerabilities found" |

| Clean copy (criterion 1): trackable files copied to a fresh temporary directory, empty uv cache | `uv sync --locked` and `uv lock --check` exit 0; installed commit `5905156…`; unit tests 43 passed; directory removed afterwards |

CI on GitHub: see "Criterion 9: CI on the pushed commit" below.

## Bulk actions on contacts (decision P3-BK, 2026-11-07)

| Check | Result |
| --- | --- |
| `uv run pytest tests/integration/test_bulk_actions.py` | 4 passed: assign to 3 contacts (an unknown and another workspace's skipped as `not_found`, the other untouched), repeating changes nothing; tags added and removed, stage set, archive and restore; each contact's own history and audit; outsider owner, bad stage, no tag, 101 or 0 contacts, unknown action and Read-only refused |
| `uv run pytest tests/unit` | 774 passed |
| Frontend `records.test.tsx`; typecheck; lint | 33 passed; clean |

## Customers' webhooks (decision P12-H, 2026-11-07)

| Check | Result |
| --- | --- |
| `uv run pytest tests/integration/test_webhooks.py` | 7 passed: `http://`, other schemes, credentials in the address and a Member refused; the key shown once, `no-store`, the query string never shown; nothing recorded without an address; a contact created and updated, a deal moved and a form submitted each record one delivery for this workspace's address and none for another's; data is the agreed set, `contact.updated` without values; history without payloads; removal repeatable and final |
| Affected integration suites (automations, booking pages and emails, consent, forms, history, imports, integrations, deals, records) | 142 passed |
| `uv run pytest tests/unit` | 769 passed |
| Frontend `integrationSettings.test.tsx`; typecheck; lint | 5 passed; clean |

Not tested end to end: `appointment.booked` with an address attached, and
a real delivery through the egress proxy.

## Invited names, deleted tags, campaigns on the calendar (2026-11-19, owner: "apply all 4")

Decisions M-P2 (migration `0049_invitation_name`), P7-ST and the P7-SC
calendar follow-up; the campaign detail's email is now the group
"Campaign email", so "Preview" names only the preview section.

| Check | Result |
| --- | --- |
| `uv run pytest` integration: campaigns, campaign schedule, member profiles, invitations, foundation, crm tables | 79 passed |
| `uv run pytest tests/unit` (no environment) | 812 passed |
| `npx vitest run --maxWorkers=2` | 37 files, 399 passed |
| `tsc -b`; `eslint .`; `ruff`; `pyright` | clean |

`frontend/src/api/invitations.ts` was already not Prettier-formatted
before this change and is left as it was. Not deployed to staging.

## Automation step that sets a contact custom field (2026-11-20, owner: "go")

Decision P8-F, migration `0051_custom_field_step`. An automation step sets a
contact custom field to a fixed value. It is checked when activated and at
each run. If the field has been archived or the value no longer fits, the
step is skipped with a code. Also fixed: the run history returned a server
error for runs with a notify, round-robin or business-hours step.

| Check | Result |
| --- | --- |
| `pytest tests/integration` (automations, triggers, notify, round robin, business hours, campaigns, campaign schedule, custom fields and record values, custom domains, foundation) against `crm_app_test` | 114 passed |
| `pytest tests/unit` | 829 passed |
| `ruff format --check`; `ruff check`; `pyright`; `lint-imports` | clean; 2 contracts kept |
| `crm_app.openapi`, `npm run gen:api` | `openapi.json` and `schema.d.ts` regenerated (the step list) |
| `npx vitest run --maxWorkers=3` | 37 files, 411 passed |
| `tsc -b`; `eslint .`; `npm run build` | clean |

The first full `vitest` run with default workers had 25 timeouts, spread
over 16 unrelated files and different on a second run; with three workers
everything passed. Deployed to staging below.

## Automation step that sends a marketing email (2026-11-22, owner: "A")

Decision P8-E, migration `0055_automation_email`. A step sends one
marketing email from a template to the run's contact. Only an Owner or
Admin may activate an automation with this step (403
`campaign_approval_required` otherwise); activation is the approval, and
the template's subject and body are frozen into the active version. At
send time the step checks consent, suppression and the address, adds the
campaign unsubscribe footer, and keeps a daily limit per automation
(default 200, 1 to 1000, 24-hour window). The email is queued only after
the step commits, and a retried step sends nothing twice. Unsubscribing
suppresses the contact without firing campaign triggers. When sending is
not configured (staging runs with `ENVIRONMENT=production`) the step is
skipped as `sending_unavailable`, except in a rehearsal workspace, where
the email is recorded and closed unsent.

| Check | Result |
| --- | --- |
| `pytest tests/unit` (no environment) | 886 passed |
| `pytest tests/integration --deselect tests/integration/test_directory.py` against `crm_app_test` | 965 passed, 3 failed |
| The 3 failures: migration-head and table lists in `test_foundation`, `test_crm_tables`, `test_note_activity_tables` not yet naming 0055; lists updated, those 3 files rerun | 85 passed |
| `ruff format --check`; `ruff check`; `pyright`; `lint-imports` | clean; 2 contracts kept |
| `crm_app.openapi`, `npm run gen:api` | `openapi.json` and `schema.d.ts` regenerated (the step list) |
| `npx vitest run --maxWorkers=3` | 38 files, 428 passed |
| `tsc -b`; `eslint .`; `npm run build` | clean |

`test_directory.py` was left out: its 5 timeouts come from the about
28,649 tenants left in the local test database, not from this change. Not
deployed to staging and not checked in a browser.

## Staging deployed at `5b68d14` (2026-11-22, owner: "go")

From `1a9d8ce`: the automation step that sends a marketing email (P8-E),
migration `0055_automation_email` (one new table, two widened checks; no
data changed on upgrade).

| Check | Result |
| --- | --- |
| CI on `5b68d14` | passed (run 45043959184, all 5 jobs) |
| Before: `audit_store.sh collect`; `backup_drill.py` | kept 0 new lines (200 in all); **15 passed, 0 failed** |
| Image | built on the VPS after `HEAD` was checked, `crm-app:5b68d14`; `VERSION=5b68d14`; previous image `crm-app:1a9d8ce` |
| `$C up -d --wait` | every service healthy; `migrate` exited 0 |
| `public.alembic_version` | `0055_automation_email` |
| `/readyz` | 200 |

Rolling back the code needs a downgrade to `0054_wait_for_field` first.
Staging workspaces are not rehearsal workspaces, so the step is skipped
as `sending_unavailable` there. Not checked in a browser.

## Staging deployed at `1a9d8ce` (2026-11-22, owner: "Do 1 then 5")

From `94c62c8`: the Automations intro (`2154ef5`), field waits woken by the
change and the wait's end in the run history (`1a9d8ce`). No migration.

| Check | Result |
| --- | --- |
| CI on `2154ef5`; on `1a9d8ce` | passed (runs 45014919558, 45023760468) |
| Before: `audit_store.sh collect`; `backup_drill.py` | kept 0 new lines (192 in all); **15 passed, 0 failed** |
| Image | built on the VPS after `HEAD` was checked, `crm-app:1a9d8ce`; `VERSION=1a9d8ce`; previous image `crm-app:94c62c8` |
| `$C up -d --wait` | every service healthy; `migrate` exited 0 |
| `public.alembic_version` | `0054_wait_for_field` (unchanged) |
| `/readyz` | 200 |

Not checked in a browser: the run table's new wait text.

## Field waits woken by the change; staging run checked (2026-11-22, owner: "do1 and2 after that 3")

- **1. Automations intro** names the field-value wait (`2154ef5`).
- **2. Live run on staging (`94c62c8`, Staging Alpha, as the owner):** test
  fields `QA Seats` (number) and `QA Renewal` (date), tags "QA seats filled"
  and "QA renewal day", automations "QA wait for seats" (contact created,
  wait for QA Seats at most 1 day, add tag) and "QA renewal day" (QA
  Renewal on the day at 00:00, add tag), contacts QA Waiter and QA Renewer.
  Read from the database: QA Waiter's run waited with its next look 10
  minutes on and the end one day on; after QA Seats was filled in, the next
  look completed both steps (tag added). QA Renewer, dated today, was
  started by the date look and tagged. Both automations were then paused;
  QA Renewer's own field wait finishes when its day runs out. The test
  records stay in Staging Alpha.
- **3a. Woken at once:** a change to the awaited field (contact screen or
  API, or another automation's custom-field step) makes the waiting run
  due now (`automations.wake_field_waits`, decision P8-J follow-up).
- **3b. Run history:** `field_wait_until` in the runs API; the run table
  shows "until" a waiting run's next time, or "for a field value, at most
  until" the day the wait gives up.
- **3d:** not built. An index for the date look needs a `jsonb @>` query,
  which the SaaS-OS database surface the product may use cannot express.
- **3c:** a yearly date trigger waits for a product decision.

| Check | Result |
| --- | --- |
| `pytest tests/integration/test_automation_field_wait.py` | 4 passed |
| `pytest tests/integration` (full suite) | 961 passed, **5 errors**: `test_directory.py` (all five) time out at setup after 600 s, also when run alone |
| `pytest tests/unit` | 875 passed |
| `ruff format --check`; `ruff check`; `pyright`; `lint-imports` | clean; 0 errors; 2 contracts kept |
| `npx vitest run` | 38 files, 426 passed |
| `tsc -b`; `eslint`; `npm run build` | clean |

The `test_directory.py` errors are not from this change: `GET /v1/workspaces`
(`crm_app.directory.list_workspaces`, unchanged since P2-F) reads every open
workspace one by one, and the local test database has grown to about 28,600
workspaces from repeated runs, so the probe outlasts its 600 s limit. CI
starts from an empty database. The scan is a real limit to fix before many
workspaces exist. Not deployed to staging.

## Staging deployed at `94c62c8` (2026-11-21, owner: "Yes")

From `ae5f9d0`: the date trigger (P8-I, `5515563`) and the step that waits
for a contact field's value (P8-J, `94c62c8`). Migrations
`0053_date_reached_trigger` and `0054_wait_for_field`.

| Check | Result |
| --- | --- |
| CI on `5515563`; on `94c62c8` | passed (runs 44941627379, 44949149948) |
| Before: `audit_store.sh collect`; `backup_drill.py` | kept 0 new lines (162 in all); **15 passed, 0 failed**, this backup is the rollback point |
| Image | built on the VPS after `HEAD` was checked, `crm-app:94c62c8`; `VERSION=94c62c8`; previous image `crm-app:ae5f9d0` |
| `$C up -d --wait` | every service healthy; `migrate` exited 0 |
| `public.alembic_version` | `0054_wait_for_field` |
| Schema | `automation_step_action_check` names `wait_for_field`; `automation_run.field_wait_until` and `automation_date_workspace` exist |
| `/readyz` | 200 |

- Browser check as the Staging Alpha owner (2026-11-22): the trigger list
  offers "A date in a contact field comes" with the day offsets, the hours
  and the hint; Staging Alpha has no contact date field, so the field list
  says "No contact date fields yet". The step picker offers "Wait for a
  field value"; the step lists the contact fields ("Plan"), "7 days" and
  the hint. The dialog was closed, nothing saved.
- Not checked: a run that waits or starts on a date on staging. The page
  intro does not yet name the field-value wait.

## Automation step that waits for a contact field's value (2026-11-21, owner: "go 1 and then 3")

Decision P8-J, migration `0054_wait_for_field`. A "Wait for a field value"
step keeps the run on that step until the contact's custom field has a
value (any stored value, `false` and `0` included), looked at again every
10 minutes. After 1 to 365 days without one the step is skipped as
`timed_out`; a field archived meanwhile skips it as `field_gone`. The run
goes on either way.

| Check | Result |
| --- | --- |
| `pytest tests/integration` (full suite) against `crm_app_test` at `0054` | 965 passed (1:05:45) |
| `pytest tests/integration/test_automation_field_wait.py` and the related automation suites | 55 passed |
| `pytest tests/unit` | 875 passed |
| `ruff format --check`; `ruff check`; `pyright`; `lint-imports` | clean; 0 errors; 2 contracts kept |
| `crm_app.openapi`, `npm run gen:api` | `openapi.json` and `schema.d.ts` regenerated (the step action) |
| `npx vitest run` | 38 files, 426 passed |
| `tsc -b`; `eslint .`; `npm run build` | clean |

Not built: waking a run as soon as the contact changes (up to 10 minutes'
delay), and showing the wait's end in the run history. Not deployed to
staging.

## Automation trigger on a contact's date (2026-11-21, owner: "go 1 and then 3")

Decision P8-I, migration `0053_date_reached_trigger`. An automation starts
for a contact on the day its date in a contact date field, moved by -365 to
365 days, falls in the workspace's time zone, once the chosen hour has come.
The automation maintenance run looks at each registered workspace every 5
minutes. Each automation still runs at most once per contact.

| Check | Result |
| --- | --- |
| `pytest tests/integration` (full suite) against `crm_app_test` at `0053` | 962 passed (1:04:04) |
| `pytest tests/integration/test_automation_date_trigger.py` | 3 passed |
| `pytest tests/unit` | 866 passed |
| `ruff format --check`; `ruff check`; `pyright`; `lint-imports` | clean; 0 errors; 2 contracts kept |
| `crm_app.openapi`, `npm run gen:api` | `openapi.json` and `schema.d.ts` regenerated (the trigger type) |
| `npx vitest run` | 38 files, 425 passed |
| `tsc -b`; `eslint .`; `npm run build` | clean |

Not tested: a yearly repeat (not built), and the look against a large
workspace (no JSON index). Not deployed to staging.

## Staging deployed at `ae5f9d0` (2026-11-21, owner: "go 1 and then 3")

From `cd3a844`: the automation step that waits until a contact's date
(P8-D, `67fc907`) and two PROGRESS records. Migration
`0052_wait_until_date`.

| Check | Result |
| --- | --- |
| CI on `67fc907`; on `ae5f9d0` | passed (runs 44928993991, 44931521063) |
| Before: `audit_store.sh collect`; `backup_drill.py` | **15 passed, 0 failed**; this backup is the rollback point |
| Image | built on the VPS after `HEAD` was checked, `crm-app:ae5f9d0`; `VERSION=ae5f9d0`; previous image `crm-app:cd3a844` |
| `$C up -d --wait` | every service healthy |
| `public.alembic_version` | `0052_wait_until_date` |
| `automation_step_action_check` | names `wait_until_date` |
| `/readyz` | 200 |

- Browser check as alice: the step picker offers "Wait until a date"; the
  step shows the day offsets, the hours and the hint. Staging Alpha has no
  contact date field, so the field list says "No contact date fields yet";
  the dialog was cancelled, nothing saved. A run that waits was not
  started on staging.
- Rolling back past `0052` needs its downgrade, which deletes
  `wait_until_date` steps; staging has none.

## Automation step that waits until a contact's date (2026-11-21, owner: "go 1, then 2 and 3 toghether then 4")

Decision P8-D, migration `0052_wait_until_date`.

- A `wait_until_date` step waits until a day relative to a contact date
  field (`offset_days` -365..365) at an hour (0-23) in the workspace's time
  zone. Activation is refused unless the field is an active contact date
  field.
- When the contact has no date, or the time has already passed, the step is
  skipped (`no_date`, `date_passed`) and the run goes on. A date changed
  after the wait began does not move the wait.
- Editor: "Wait until a date" step with the date field, days before or
  after, and the hour.
- Waiting until a field merely gets a value is not built (see P8-D).

| Check | Result |
| --- | --- |
| `pytest tests/unit` | 857 passed |
| `pytest tests/integration` against `crm_app_test` | 959 passed (1:04:08) |
| `ruff format --check`; `ruff check`; `pyright`; `lint-imports` | clean; 2 contracts kept |
| `crm_app.openapi`, `npm run gen:api` | regenerated (the new step type) |
| `npx vitest run --maxWorkers=3` | 38 files, 424 passed |
| `tsc -b`; `eslint .`; `npm run build` | clean |

Not deployed to staging.

## Staging deployed at `cd3a844` (2026-11-21, owner: "go 1, then 2 and 3 toghether then 4")

From `f5cca88`: deal conditions in automations (P8-H), the Campaigns report
as CSV (P10-C.1) and the review fixes in `cd3a844`. No migration.

| Check | Result |
| --- | --- |
| CI on `cd3a844` | passed (run 44919668154) |
| Before: `audit_store.sh collect`; `backup_drill.py` | **15 passed, 0 failed**; this backup is the rollback point |
| Image | built on the VPS, `crm-app:cd3a844`; `VERSION=cd3a844`; rollback image `crm-app:f5cca88` |
| `$C up -d --wait` | every service healthy |
| `public.alembic_version` | `0051_custom_field_step` (unchanged) |
| `/readyz` | 200 |

- The first build ran from the old checkout: `sudo git fetch` failed host
  key verification and the chain went on. It was rebuilt after a plain
  `git fetch`, with `HEAD` checked against `cd3a844` before the build.
- Browser check as alice (Owner of Staging Alpha), after the owner signed
  in: the automation editor offers the "Deals" condition (open, won, lost)
  and "Open deal stage" (the workspace's four stages, with yes and no
  steps); the dialog was cancelled, nothing saved. The Campaigns card in
  Reports has "Download Campaigns as CSV"; the export for the last 30 days
  answered 200, `text/csv`, `report-campaigns-2026-11-21.csv`, 38 rows. The
  AI brief is not shown on a contact because `use_ai_brief` is false: the
  P9-B administrative grants were not run on staging, as the owner chose.
  The brief itself is therefore not checked on staging.

## Deal conditions in automations and the Campaigns report as CSV (2026-11-21, owner: "do all four")

Decisions P8-H and P10-C.1, no migration of the database.

- **P8-H:** an automation condition can read the contact's deals: `deal`
  ("has" or "has none" with the outcomes open, won, lost) and `deal_stage`
  (an open deal in one of the named stages; a won or lost deal in that
  stage does not count). A stage that no longer exists, or belongs to
  another workspace, refuses activation. The deals are read once, when the
  run starts, and only when the condition names them.
- **P10-C.1:** `GET .../reports/campaigns/export.csv` (`crm_app.campaign:read`)
  and a CSV button on the Campaigns card. The rows carry counts and
  campaign IDs, never campaign names or recipients.
- Option 1 of the four (a browser check on staging) waits for the owner's
  sign-in; option 2 (the P9-B administrative grants on staging) was
  skipped by the owner. Neither is deployed.

| Check | Result |
| --- | --- |
| `pytest tests/unit` | 848 passed |
| `pytest tests/integration` against `crm_app_test` | 956 passed (1:02:26) |
| `ruff format --check`; `ruff check`; `pyright`; `lint-imports` | clean; 2 contracts kept |
| `crm_app.openapi`, `npm run gen:api` | regenerated (the CSV route) |
| `npx vitest run --maxWorkers=3` | 38 files, 422 passed |
| `tsc -b`; `eslint .`; `npm run build` | clean |

Not deployed to staging.

## Staging deployed at `f5cca88` (2026-11-20, owner: "go ahead")

From `6d5708b`: the automation condition on a contact custom field (P8-G),
campaigns in Reports (P10-C) and the contact brief (P9-B), with the CI
fixes `1d3cab3` (route map) and `f5cca88` (probe typing). No migration.

| Check | Result |
| --- | --- |
| CI on `f5cca88` | passed (run 44810843453) |
| Before: `audit_store.sh collect`; `backup_drill.py` | **15 passed, 0 failed**; this backup is the rollback point |
| Image | built on the VPS, `crm-app:f5cca88`; `VERSION=f5cca88` |
| `$C up -d --wait` | every service healthy |
| `public.alembic_version` | `0051_custom_field_step` (unchanged) |
| `/readyz` | 200 |
| Running app's OpenAPI | lists `.../contacts/{contact_id}/brief` and `.../reports/campaigns` |
| App log, first 2 minutes | no error lines |

Not yet run on staging: the administrative grant list
(`crm_app.p9b.contact_brief.administrative.*`), so existing staging
workspaces have no `ai.inference:run` and do not show the AI brief; AI
stays off there in any case. Not checked in a browser. Rollback is
code-only to `crm-app:6d5708b`.

## Contact brief route and permission (2026-11-20, owner: "do all 4")

Decision P9-B, no migration of the database. `POST .../contacts/{id}/brief`,
the allowlisted facts read from the database, `ai.inference:run` for Owner,
Admin and Member (new workspaces; existing ones only through the held-back
administrative list), and the "AI brief" section in the contact drawer. AI
stays off by default, so the answer on every workspace today is
`unavailable`.

Also fixed: `107f472` (P10-C) was pushed without updating
`tests/unit/test_routes.py` for the new report route; the full unit suite
was not run before that push. The route map now lists both new routes.

| Check | Result |
| --- | --- |
| `pytest tests/unit` | 840 passed |
| `pytest` integration: AI settings, permission grants, provision, role upgrade, workspace routes, contact brief, foundation | 63 passed, 2 failed, then 33 passed after adding `use_ai_brief` to the two expected action maps |
| `ruff`; `pyright`; `lint-imports` | clean; 2 contracts kept |
| `crm_app.openapi`, `npm run gen:api` | regenerated (`BriefOut`) |
| `npx vitest run --maxWorkers=3` | 38 files, 420 passed |
| `tsc -b`; `eslint .`; `npm run build` | clean |

Deployed to staging above (`f5cca88`).

## Campaigns in Reports (2026-11-20, owner: "do all 4")

Decision P10-C, no migration. `GET .../reports/campaigns` and a Reports
card: campaigns queued in the period, recipients by outcome, unsubscribes.

| Check | Result |
| --- | --- |
| `pytest tests/integration/test_report_campaigns.py test_reports.py` | 15 passed |
| `pytest tests/integration/test_campaigns.py test_report_campaigns.py` (after moving the outcome rule into `outcome_of`) | 25 passed |
| `ruff`; `pyright`; `lint-imports` | clean; 2 contracts kept |
| `crm_app.openapi`, `npm run gen:api` | regenerated (`CampaignsReport`) |
| `npx vitest run src/records/reports.test.tsx` | 13 passed |
| `tsc -b`; `eslint` | clean |

Deployed to staging above (`f5cca88`).

## Automation condition on a contact custom field (2026-11-20, owner: "do all 4")

Decision P8-G, no migration. A condition can read one contact custom field
("is one of", "is none of", "is present", "is missing"). The Automations
introduction now names the custom field step and the condition kinds
(option 4).

| Check | Result |
| --- | --- |
| `pytest tests/integration/test_automation*.py` against `crm_app_test` | 29 passed |
| `pytest tests/unit` | 840 passed |
| `ruff format --check`; `ruff check`; `pyright`; `lint-imports` | clean; 2 contracts kept |
| `crm_app.openapi` | no change (the definition is free-form JSON checked by the domain) |
| `npx vitest run src/records/automations.test.tsx` | 18 passed |
| `tsc -b`; `eslint .`; `npm run build` | clean |

Deployed to staging above (`f5cca88`).

## Staging deployed at `6d5708b` (2026-11-20, owner: "Go 1 and 2")

From `f77a204`: the automation step that sets a contact custom field
(P8-F) and the run-history fix. Migration `0051_custom_field_step` (widens
the step action check; no data change).

| Check | Result |
| --- | --- |
| CI on `6d5708b` | passed (run 44744843860) |
| Before: `audit_store.sh collect`; `backup_drill.py` | **15 passed, 0 failed**; this backup is the rollback point |
| Image | built on the VPS, `crm-app:6d5708b`; `VERSION=6d5708b` |
| `$C up -d --wait` | every service healthy; `migrate` exited 0 |
| `public.alembic_version`; `automation_step_action_check` | `0051_custom_field_step`; the check lists `set_custom_field` |
| `/readyz` | 200 |
| alice, Automations editor | "Set a custom field" is offered; adding it shows the contact field "Plan", a text value and the hint; cancelled, nothing saved |
| App and worker logs, first 30 minutes | no error lines |

Disposable staging data deleted as alice through the app (owner: "Go 1
and 2"): draft automation "Campaign trigger check"; draft campaign
"Rehearsal check (copy)"; campaign "Schedule check (copy)" (approved and
scheduled as a rehearsal, so cancelled first, then deleted; never queued,
nothing sent). Kept: completed rehearsal "Schedule check", automation
"Tag new 56367", template "Welcome 56367".

Rollback: code to `crm-app:f77a204` is safe without a downgrade (0051 only
adds an allowed value); the old code does not know the new step, so pause
any automation that uses it first.

## Staging deployed at `f77a204` (2026-11-20, owner: "Go Ahead")

From `6d3e5d3`: campaign automations named and listed (P8-C follow-up).
Frontend only, no migration.

| Check | Result |
| --- | --- |
| CI on `f77a204` | passed (run 44721678675) |
| Before: `audit_store.sh collect`; `backup_drill.py` | **15 passed, 0 failed**; this backup is the rollback point |
| Image | built on the VPS, `crm-app:f77a204`; `VERSION=f77a204` |
| `$C up -d --wait` | every service healthy; `migrate` exited 0 |
| `/readyz` | 200, database and redis healthy |
| alice, Automations | the introduction names the campaign triggers; "Campaign trigger check" reads "When a contact unsubscribes from Schedule check · 0 steps" |
| alice, "Schedule check" detail | "Automations started by this campaign" lists "Campaign trigger check", Draft, "on unsubscribing" |
| alice, "Rehearsal check (copy)" detail | says no automation starts; "New automation for this campaign" opens the editor at `?create=automation&campaign=` with "A campaign email is sent to a contact" and this campaign chosen; cancelled, nothing saved |
| App and worker logs, first 15 minutes | no error lines |

Rollback: code to `crm-app:6d3e5d3` (no schema change).

## Campaign automations named and listed (2026-11-20, owner: "Do both")

Decision P8-C follow-up. Each automation's summary names its campaign, and
the Automations introduction mentions the campaign triggers. A campaign's
detail lists the automations it starts and offers "New automation for this
campaign". Frontend only: no API or migration change.

| Check | Result |
| --- | --- |
| `npx vitest run --maxWorkers=2` | 37 files, 409 passed |
| `tsc -b`; `eslint .`; `npm run build` | clean |

Deployed to staging above.

## Staging deployed at `6d3e5d3` (2026-11-20, owner: "Go ahead")

From `6d52347`: deleting campaigns never queued (P7-DL) and campaign
triggers for automations (P8-C, migration `0050_campaign_triggers`).

| Check | Result |
| --- | --- |
| CI on `48319bb` and `6d3e5d3` | passed (runs 44691578319 and 44695631343) |
| Before: `audit_store.sh collect`; `backup_drill.py` | **15 passed, 0 failed**; this backup is the rollback point |
| Image | built on the VPS, `crm-app:6d3e5d3`; `VERSION=6d3e5d3` |
| `$C up -d --wait` | every service healthy; `migrate` exited 0 |
| Database after migrate | `campaign_recipient_email_idx` exists; `automation_trigger_check` allows `campaign_sent` and `campaign_unsubscribed` |
| `/readyz` | 200, database and redis healthy |
| alice, a draft duplicated from "Rehearsal check (copy)" | "Delete" shows; the confirmation "Delete campaign?" appears first; after "Delete" the campaign is gone from the list and the detail closes; audit `crm_app.campaign.deleted` with `status` and `content_hash` only |
| alice, an approved and a completed campaign | no "Delete" (approved: cancel first; completed: "Archive") |
| alice, New automation | the trigger list offers both campaign triggers; the campaign picker lists "Any" and the workspace's campaigns; the hint for the unsubscribe trigger shows |
| alice, draft "Campaign trigger check" (unsubscribe, "Schedule check") | saved as a draft; stored `campaign_unsubscribed` naming that campaign; not activated |
| App and worker logs, first 20 minutes | no error lines |

"Campaign trigger check" (a draft, never activated), "Rehearsal check
(copy)" and "Schedule check (copy)" are disposable test data. The sent
trigger cannot be exercised on staging (rehearsals send nothing), nor
the unsubscribe trigger end to end (no real email carries the link).
Rollback: code to `crm-app:6d52347` after downgrading to
`0049_invitation_name`; a full rollback restores the backup taken above.

## Campaign triggers for automations (2026-11-20, owner: "do 2 then 4, then 3")

Decision P8-C: triggers `campaign_sent` and `campaign_unsubscribed`, for
one campaign or any; migration `0050_campaign_triggers`.

| Check | Result |
| --- | --- |
| `uv run crm-app-migrate` on the test database | 0050 applied |
| `uv run pytest` integration: campaigns, campaign schedule, automations, automation triggers, automation notify, foundation | 54 passed |
| `uv run pytest` integration: emails, migrations as owner, table guard, purge, suppression routes | 51 passed |
| `uv run pytest tests/unit` (no environment) | 816 passed |
| `npx vitest run --maxWorkers=2` | 37 files, 405 passed |
| `tsc -b`; `eslint .`; `npm run build`; `ruff`; `pyright` | clean |

Deployed to staging above. On staging the sent trigger cannot start:
the workspace rehearses campaigns and nothing is sent.

Item 4 (Prettier) was not done: the repository has no Prettier
configuration, dependency or CI check, and 101 of 153 frontend source
files differ from Prettier's defaults. The earlier notes here that some
files "failed the Prettier check" compared them with an unconfigured
tool; they are not a gate. Adopting a formatter is the owner's choice.

## Deleting campaigns never queued (2026-11-20, owner: "do 2 then 4, then 3")

Decision P7-DL: `DELETE /campaigns/{id}` for draft, validated, rejected and
cancelled campaigns, confirmed first in the detail. No migration.

| Check | Result |
| --- | --- |
| `uv run pytest` integration: campaigns, campaign schedule | 25 passed |
| `uv run pytest tests/unit` (no environment) | 812 passed |
| `npx vitest run --maxWorkers=2` | 37 files, 403 passed |
| `tsc -b`; `eslint`; `ruff`; `pyright` | clean |

Deployed to staging above.

## Staging deployed at `6d52347` (2026-11-20, owner: "Go Ahead")

From `ac22cc3`: the calendar asks for its range (P7-SC follow-up) and
removing deleted tags from an audience (P7-ST follow-up). No migration.

| Check | Result |
| --- | --- |
| CI on `6d52347` | passed (5 of 5 jobs, run 44612481380) |
| Before: `audit_store.sh collect`; `backup_drill.py` | **15 passed, 0 failed**; this backup is the rollback point |
| Image | built on the VPS, `crm-app:6d52347`; `VERSION=6d52347` |
| `$C up -d --wait` | every service healthy; `migrate` exited 0 |
| `/readyz` | 200, database and redis healthy |
| alice, Calendar (week Nov 16 – 22) | asks `status=approved&scheduled_from=2026-11-15T23:00:00.000Z&scheduled_to=2026-11-22T23:00:00.000Z`; lists "Schedule check (copy)", Fri, Nov 20, 11:00 PM; no "Show more campaigns" (one page) |
| alice, "Rehearsal check (copy)", only the deleted tag | the note shows and no removal is offered |
| alice, same campaign after adding the "Lead" stage | "Remove the deleted tag" shows; the confirmation "Remove deleted tags?" appears first; after "Remove" the audience is `stages: ["lead"]`, `tag_ids: []`, status draft; audit `crm_app.campaign.updated` with `removed_deleted_tags = 1` |
| App and worker logs, first 10 minutes | no error lines |

"Rehearsal check (copy)" and "Schedule check (copy)" are disposable test
data. Rollback: code to `crm-app:ac22cc3`; a full rollback restores the
backup taken above.

## Calendar range and removing deleted tags (2026-11-19, owner: "go 1 then 2 and 3")

Decisions P7-SC follow-up (the list's `scheduled_from` and `scheduled_to`;
the calendar sends its range) and P7-ST follow-up
(`POST /campaigns/{id}/remove-deleted-tags`, confirmed first). No
migration.

| Check | Result |
| --- | --- |
| `uv run pytest` integration: campaigns, campaign schedule | 24 passed |
| `uv run pytest tests/unit` (no environment) | 812 passed |
| `npx vitest run --maxWorkers=2` | 37 files, 401 passed |
| `tsc -b`; `eslint .`; `ruff`; `pyright` | clean |

`CalendarPage.tsx` and `CampaignsPage.tsx` already failed the Prettier
check before this change, and their formatting is left as it was.
Deployed to staging below.

## Staging deployed at `ac22cc3` (2026-11-19, owner: "go 1 then 2 and 3")

From `2365891`: a name suggested when inviting (M-P2, migration
`0049_invitation_name`), deleted tags in an audience (P7-ST) and scheduled
campaigns on the calendar (P7-SC follow-up).

| Check | Result |
| --- | --- |
| CI on `ac22cc3` | passed (5 of 5 jobs, run 44524351352) |
| Before: `audit_store.sh collect`; `backup_drill.py` | **15 passed, 0 failed**; this backup is the rollback point |
| Image | built on the VPS, `crm-app:ac22cc3`; `VERSION=ac22cc3` |
| `$C up -d --wait` | every service healthy; `migrate` exited 0 |
| Migration | `invitation_intent.display_name` present |
| `/readyz` | 200 |
| alice, "Rehearsal check (copy)" | "A tag in this audience was deleted. Edit the audience before checking it." |
| alice, scheduling | duplicated "Schedule check" as "Schedule check (copy)", checked, submitted, approved, scheduled for Fri 20 Nov 23:00 (Amsterdam) |
| alice, Calendar | "Scheduled campaigns" lists "Schedule check (copy)", Fri, Nov 20, 11:00 PM, linking to Campaigns |
| alice, invite with a name | the dialog shows "Name (optional)" and its hint; the list shows "Named Check · named-invite-check@example.test"; the invitation was then revoked; the name is stored in `invitation_intent` |
| App and worker logs, first 30 minutes | no error lines |

"Schedule check (copy)" stays scheduled as disposable test data; if it is
not unscheduled first, it runs as a rehearsal (nothing is sent). Rollback:
code to `crm-app:2365891` (it ignores the new column); a full rollback
restores the backup taken above.

## Staging deployed at `2365891` (2026-11-19, owner: "go ahead")

From `4a82f68`: scheduled campaigns (P7-SC, migration
`0048_campaign_schedule`), preview for a contact (P7-PV) and "Add your
name" (M-P1 follow-up).

| Check | Result |
| --- | --- |
| CI on `2365891` | passed (5 of 5 jobs, run 44514175017) |
| Before: `audit_store.sh collect`; `backup_drill.py` | **15 passed, 0 failed**; this backup is the rollback point |
| Image | built on the VPS, `crm-app:2365891`; `VERSION=2365891` |
| `$C up -d --wait` | every service healthy; `migrate` exited 0 |
| Migration heads | `0048_campaign_schedule` (`campaign.scheduled_at`, `campaign.scheduled_by_user_id`, `campaign_queue.due_at` present), SaaS-OS `e1f5a8c3b7d9` |
| `/readyz` | 200 |
| alice, preview of "Rehearsal check (copy)" for Elena | "Hello Elena, …" with the footer and "[unsubscribe link]"; "Not in this campaign's audience." |
| Scheduling, end to end | disposable contact "Schedule Check" (`schedule-check@example.test`, consent, tag "Schedule check") and campaign "Schedule check", approved as alice; alice scheduled it in the browser for 11:48 UTC ("Scheduled for", Unschedule offered); the maintenance run queued it at 11:48:12 and it completed as a rehearsal: 1 email, `failed`/`rehearsal`, nothing sent; the time cleared; the queue empty |
| Audit of "Schedule check" | created, validated, submitted, approved, scheduled, queued (`scheduled: true`), completed (`rehearsal: true`) |
| carol, Team & roles | her own row shows "Add your name"; alice shows as "Alice Owner"; dave by ID; the new note |
| App and worker logs, first 20 minutes | no error lines |

"Rehearsal check (copy)" can no longer be checked: its tag was deleted,
so it has no audience (the refusal is correct). "Schedule check", its tag
and contact stay as disposable test data. Rollback: code to
`crm-app:4a82f68` (it ignores the three new columns); a full rollback
restores the backup taken above.

## Scheduling, preview, member names and a Read-only test user (2026-11-19, owner: "go ahead with all 4")

Decisions P7-SC (scheduled campaigns, migration `0048_campaign_schedule`),
P7-PV (preview for one contact) and the M-P1 follow-up ("Add your name").

| Check | Result |
| --- | --- |
| `uv run pytest` integration: crm tables, note/activity tables, foundation, campaigns, campaign schedule | 106 passed |
| `uv run pytest tests/unit` (no environment) | 812 passed |
| `npx vitest run --maxWorkers=2` | 37 files, 394 passed |
| `tsc -b`; `eslint .`; `ruff`; `pyright`; Prettier on `api/campaigns.ts` | clean |

Deployed to staging at `2365891` (above).

**Read-only test user on staging.** `dave@crm-staging.auravox.nl`, created
like carol (ZITADEL v2 user API, login client token, email verified;
password in `.local/test-users.env` as `DAVE_*`, never printed), joined
Staging Alpha through alice's manual-mode invitation (no email) and was
given the Read-only role. Checked as dave (staging at `4a82f68`):

| Check | Result |
| --- | --- |
| `GET …/access` | roles `["Read-only"]`; only read actions true |
| Contacts | list 200; Import and Export disabled ("Only Owners and Admins…"); no New contact; `export.csv` 403 |
| Campaigns | list and report 200; `results.csv` 403; no New campaign or New template; the archived campaign's detail has no buttons |
| Invitations | 403 |

alice also set her own display name ("Alice Owner") under My profile on
staging; the Team list then showed it instead of her member ID.

## Staging deployed at `4a82f68` (2026-11-19, owner: "Go ahead")

From `f90b4e8`: campaign results CSV (P7-RX), duplicate (P7-DU) and list
orders (P7-SO). No migration.

| Check | Result |
| --- | --- |
| CI on `4a82f68` | passed (5 of 5 jobs, run 44499527248) |
| Before: `audit_store.sh collect`; `backup_drill.py` | **15 passed, 0 failed**; this backup is the rollback point |
| Image | built on the VPS, `crm-app:4a82f68`; `VERSION=4a82f68` |
| `$C up -d --wait` | every service healthy |
| Migration head | `0047_campaign_archive` (unchanged) |
| `/readyz` | 200 |
| alice (Owner), `results.csv` of "Rehearsal check" | 200, `text/csv`, `campaign-results-2026-11-19.csv`; header `email,contact_id,outcome,added_at,unsubscribed_at`; 2 rows, both `rehearsed` |
| alice, the detail | "Download CSV", "Unarchive" and "Duplicate"; Duplicate opened the new draft "Rehearsal check (copy)" in the current list; Sort menu offers Newest first, Last updated, Name A to Z |
| carol (Member) | `results.csv` 403, report 200; the detail offers Unarchive and Duplicate, no Download CSV |
| Audit | one `crm_app.campaign.results_exported` (row count 2); one `crm_app.campaign.created` with `duplicated_from`; the refused download left none |
| App and worker logs, first 15 minutes | no error lines |

"Rehearsal check (copy)" stays as a disposable draft. Rollback: code to
`crm-app:f90b4e8`.

## Member test user on staging (2026-11-19, owner: "Go 1, 2,3 and 4", item 2)

`carol@crm-staging.auravox.nl` is a disposable staging user with the
Member role in "Staging Alpha", so role checks can be tried in the browser
next to `alice@` (Owner). Created with the ZITADEL v2 user API (the login
client's token on the VPS, email marked verified); the random password is
in `.local/test-users.env` (0600, VPS only) as `CAROL_*`, never printed.
She joined through the product's own flow: alice created a manual-mode
invitation (a link, no email sent), carol signed in and accepted it, and
alice gave her the Member role.

| Check, signed in as carol (staging at `f90b4e8`) | Result |
| --- | --- |
| `GET …/access` | roles `["Member"]`; `manage_campaigns` true; `approve_campaigns`, `export_records`, `revoke_member` false |
| Contacts | Export disabled: "Only Owners and Admins can export contacts"; `GET …/contacts/export.csv` 403 |
| Team & roles | no Invite button; `GET …/invitations` 403 |
| Campaigns | list and report 200; "New campaign" offered (Members draft) |

## Campaign results CSV, duplicate and list orders (decisions P7-RX, P7-DU, P7-SO, 2026-11-19)

The Results card downloads each recipient's outcome as CSV (Owners and
Admins); any campaign can be duplicated into a new draft; the list sorts
by newest, last updated or name. No migration.

| Check | Result |
| --- | --- |
| `uv run pytest tests/integration/test_campaigns.py` | 17 passed |
| `uv run pytest tests/unit` (no environment) | 812 passed |
| `npx vitest run --maxWorkers=2` | 37 files, 389 passed |
| `tsc -b`; `eslint .`; `ruff`; `pyright` | clean |

Deployed to staging at `4a82f68` (above).

## Staging deployed at `f90b4e8` (2026-11-19, owner: "Go ahead")

From `c7ef73e`: campaign list search, filter and paging (P7-CL). No
migration.

| Check | Result |
| --- | --- |
| CI on `f90b4e8` | passed (5 of 5 jobs, run 44468316590) |
| Before: `audit_store.sh collect`; `backup_drill.py` | **15 passed, 0 failed**; this backup is the rollback point |
| Image | built on the VPS, `crm-app:f90b4e8`; `VERSION=f90b4e8` |
| `$C up -d --wait` | every service healthy |
| Migration head | `0047_campaign_archive` (unchanged) |
| `/readyz` | 200 |
| Signed in as the Alpha Owner (test account) | archived list, search "rehears": "1 campaign", "Rehearsal check" with its results line; status "Cancelled": "0 campaigns", "No campaigns match" |
| App log, first 5 minutes | no error lines |

Rollback: code to `crm-app:c7ef73e`.

## Campaign list search, filter and paging (decision P7-CL, 2026-11-19)

The campaign list has a name search, a status menu, a match count and
"Load more" (pages of 50, newest first). No migration.

| Check | Result |
| --- | --- |
| `uv run pytest tests/integration/test_campaigns.py tests/unit/test_routes.py tests/unit/test_paging*.py` | 51 passed |
| `uv run pytest tests/unit` (no environment) | 812 passed |
| `npx vitest run --maxWorkers=2` | 37 files, 383 passed |
| `tsc -b`; `eslint .`; `ruff`; `pyright` | clean |

Deployed to staging at `f90b4e8` (above).

## Staging deployed at `c7ef73e` (2026-11-19, owner: "Go 1 then 2")

From `2ad0d63`: archived campaigns (P7-AR, migration
`0047_campaign_archive`) and the results line in the campaign list.

| Check | Result |
| --- | --- |
| CI on `1122c6c`, `c7ef73e` | passed (5 of 5 jobs on `c7ef73e`) |
| Before: `audit_store.sh collect`; `backup_drill.py` | 0 new lines (34 kept); **15 passed, 0 failed**; this backup is the rollback point |
| Image | built on the VPS, `crm-app:c7ef73e`; `VERSION=c7ef73e` |
| `$C up -d --wait` | every service healthy; `migrate` exited 0 |
| Migration heads | `0047_campaign_archive` (columns `archived_at`, `archived_by_user_id` present), SaaS-OS `e1f5a8c3b7d9` |
| `/readyz` | 200 |
| Signed in as the Alpha Owner (test account) | list line "2 recipients · Rehearsed, not sent 2"; Archive on "Rehearsal check" hid it ("No campaigns yet"); "Show archived" lists it with its results |
| Database after | the campaign `completed`, archived; one `crm_app.campaign.archived` audit entry |
| App and worker logs, first 10 minutes | no error lines |

"Rehearsal check" stays archived (Unarchive restores it). Rollback: code to
`crm-app:2ad0d63` (it ignores the two new columns); a full rollback
restores the backup taken above.

## Campaign results in the list (decision P7-RP, 2026-11-19)

Each started campaign in the campaign list shows one line, for example
"12 recipients · Delivered 7 · Bounced 1", from the campaign's report;
frontend only.

| Check | Result |
| --- | --- |
| `npx vitest run --maxWorkers=2` | 37 files, 381 passed |
| `tsc -b`; `eslint .` | clean |

Not deployed to staging.

## Archived campaigns (decision P7-AR, 2026-11-19)

A finished or cancelled campaign can be archived from its detail and
found again with "Show archived"; Unarchive returns it to the list.
Nothing is deleted. Migration `0047_campaign_archive`.

| Check | Result |
| --- | --- |
| `uv run pytest tests/integration/test_campaigns.py test_foundation.py tests/unit/test_routes.py` | 34 passed |
| `uv run pytest` crm tables, migrations as owner, tenant table guard, purge, emails | 71 passed |
| `uv run pytest tests/unit` (no environment) | 812 passed |
| `npx vitest run src/records/campaigns.test.tsx` | 14 passed |
| `tsc -b`; `eslint .`; `ruff`; `pyright` | clean |

Not deployed to staging.

## Staging deployed at `2ad0d63` (2026-11-19, owner: "Go ahead")

From `d015929`: the inbound receiving client (P6-R; off, staging cannot
receive) and campaign results (P7-RP). No migration in the release.

| Check | Result |
| --- | --- |
| CI on `2ad0d63` | run 44411565528 passed |
| Before: `audit_store.sh collect`; `backup_drill.py` | 0 new lines (32 kept); **15 passed, 0 failed** (254 digest windows, no findings); this backup is the rollback point |
| Image | built on the VPS, `crm-app:2ad0d63`; `VERSION=2ad0d63`; app and worker run it |
| `$C up -d --wait` | every service healthy; `migrate` exited 0 |
| `/readyz`; `GET .../campaigns/{id}/report` without a session | 200; 401 |
| Email switches in `app.env` | none set; `CAMPAIGN_REHEARSAL_WORKSPACES` kept |
| Signed in as the Alpha Owner (test account), campaign "Rehearsal check" | Results: recipients 2, rehearsed (not sent) 2, unsubscribed 0, with the note that acceptance is not delivery |
| App and worker logs, first 3 minutes | no error lines |

Rollback: code only, `sudo docker tag crm-app:d015929 crm-app:staging` and
`$C up -d --wait app worker`.

## Rehearsal data removed from staging (2026-11-18, owner: "last 3")

Signed in as the Staging Alpha Owner (test account), through the app:
deleted the contacts Rita Rehearsal and Ravi Rehearsal and the tag
"Rehearsal 2026-11-18" (audit: two `crm_app.contact.deleted`, one
`crm_app.tag.deleted`; no app errors). The campaign "Rehearsal check"
stays: the product has no route to delete a campaign and a completed one
cannot be cancelled, and no manual database edit was made. Its two
recipient rows remain with the contact link cleared and the
`@example.com` test addresses. Rehearsal itself is still on for Staging
Alpha and Beta.

## Campaign results (decision P7-RP, 2026-11-18)

A campaign's detail shows its results once queued: recipients, each email
outcome that occurred (accepted by the provider, delivered, bounced,
marked as spam, suppressed, not sent, unknown, rehearsed) and
unsubscribes, from `GET …/campaigns/{id}/report` (every role). Opens and
clicks are not tracked.

| Check | Result |
| --- | --- |
| `uv run pytest tests/integration/test_campaigns.py` | 13 passed |
| `npx vitest run` (frontend) | 376 passed |
| `tsc -b`; `eslint .` | clean |

## Inbound receiving client (decision P6-R, 2026-11-18)

`crm_app.inbound.ResendReceiving` fetches a received email from Resend's
receiving API through SaaS-OS's egress `get`; it is used only while
`EMAIL_INBOUND_ENABLED` is on outside production with a Resend key. No
pin move; nothing switched on; staging (`ENVIRONMENT=production`) cannot
receive.

| Check | Result |
| --- | --- |
| `uv run pytest tests/unit/test_inbound_receiving.py tests/unit/test_inbound_rules.py` | passed |
| `uv run pytest tests/integration/test_inbound_email.py` (main pass through the real adapter) | 18 passed |

Not tested: a real call to Resend (not authorized).

## Campaign rehearsal on staging (decision P7-R, 2026-11-18, owner: "A")

Deployed `d015929` (CI run 44375966790, 5 of 5; drill before: 15 of 15)
with `CAMPAIGN_REHEARSAL_WORKSPACES` naming Staging Alpha and Staging
Beta. Rehearsed as the Alpha Owner (test account) in the browser:

| Step | Result |
| --- | --- |
| Tag "Rehearsal 2026-11-18"; contacts Rita and Ravi at `*.rehearsal@example.com`, lead, tagged, consent recorded | 201 / 200 each |
| Campaign "Rehearsal check", segment: that tag; validate, submit, approve | estimate 2 eligible, 0 excluded; approved |
| Campaigns page | notice "Rehearsal workspace: ... no email is sent"; buttons Edit, **Queue as a rehearsal**, Cancel campaign |
| Queue as a rehearsal | status Queued |
| `leadstack-job@crm_app.email_maintenance` | "campaigns processed 1, failed 0, waiting 0" |
| Campaign; its emails | `completed`; 2 emails `failed` / `rehearsal`, `sent_at` empty, both to the test addresses; `campaign_queue` empty |
| Audit | `queued` by the Owner; `completed` by `crm_app.campaign_send` with `rehearsal: true` |
| Every campaign email on staging | 2, both `failed` |
| Egress proxy, app, worker logs (15 min) | no errors; no request to Resend |

The test tag, contacts and campaign stay in Staging Alpha as rehearsal
data. Rollback: remove `CAMPAIGN_REHEARSAL_WORKSPACES` from `app.env` and
restart app and worker; code to `crm-app:855c200`.

## Staging deployed at `855c200` (2026-11-18, owner: "Deploy staging")

| Check | Result |
| --- | --- |
| CI on `855c200` | run 44370063063, 5 of 5 jobs passed |
| Before: `audit_store.sh collect`; `backup_drill.py` | 0 new lines (12 kept); **15 passed, 0 failed** (244 digest windows, no findings); this backup is the rollback point |
| Image | built on the VPS, `crm-app:855c200`; `VERSION=855c200` |
| `$C up -d --wait` | every service healthy; `migrate` exited 0 |
| Migration heads | `0046_campaign_queue`, SaaS-OS `e1f5a8c3b7d9` |
| `/readyz`; `/app/u/<ws>` | 200; 200 |
| `/v1/tenants/<ws>/ai/usage`, `/usage/monthly`, `/limits` without a session | 401 each |
| One-click unsubscribe, unknown token | 204 |
| `leadstack-job@crm_app.email_maintenance` run by hand | exit 0; "campaigns processed 0, failed 0, waiting 0" (campaign sending is off) |
| Signed in as the Alpha Owner (test account), Settings › AI | "AI usage" card: "No AI use yet."; monthly read 200, 12 months, 0 calls |
| App and worker logs, first 10 minutes | no error lines |

Rollback: code to `crm-app:c94d156` (migration 0046 only adds an empty
table, which the older code ignores); a full rollback restores the backup
taken above.

## AI usage in Settings › AI (decision P9-U, 2026-11-18)

SaaS-OS's usage router is mounted unchanged (`/v1/tenants/{id}/ai/usage`,
`/usage/monthly`, `/limits`, `ai.usage:read`); Settings › AI shows usage
this month by feature and over the last 12 months.

| Check | Result |
| --- | --- |
| `uv run pytest tests/integration/test_ai_settings_routes.py` | 8 passed (Owner, Admin 200; Member, Read-only 403; other workspace 404; no session 401) |
| `uv run pytest tests/unit` | 808 passed (OpenAPI regenerated: additions only) |
| `npx vitest run --maxWorkers=2` | 37 files, 373 passed (`aiSettings.test.tsx` 7) |
| `npx tsc --noEmit`, `npm run lint`, `ruff`, `pyright` | clean |

Not deployed to staging. No AI provider exists, so every workspace shows
"No AI use yet."

## Campaign sending job (decision P7-S, 2026-11-18)

Queued campaigns are now processed by the email maintenance run, 500 new
recipients per campaign per run, as the component `crm_app.campaign_send`.
Migration `0046_campaign_queue`. Nothing is turned on: sending still needs
the campaign stream, which is off on staging and refused in production.

| Check | Result |
| --- | --- |
| `uv run pytest tests/integration/test_campaigns.py ... test_emails.py` (campaigns, table guards, foundation, purge, migrations as owner, tenant table guard, emails) | 137 passed |
| `uv run pytest tests/unit` | 808 passed |
| `ruff check`, `ruff format --check`, `pyright` on `src/crm_app` and `tests` | clean |

Not run locally: the full integration suite (CI runs it). Not deployed to
staging.

## Staging audit digest store (decision D-STG.7, 2026-11-18)

Owner: "Go 1 then 2 then 4" (item 1). On the VPS at checkout `2865826`
(the running image stays `crm-app:c94d156`):

| Check | Result |
| --- | --- |
| `audit_store.sh collect`, first run | 10 lines kept from the worker's current log |
| `audit_store.sh seed` (17:42 UTC) | 243 records copied from `core.audit_digests` into `seed.log` |
| `collect` again; `seed` again | 0 new lines; seed refused ("a seed is taken once"), exit 1 |
| Truncating `audit_digest.log` as root | refused, `Operation not permitted`; both files carry the append-only attribute; directory `root` 0700 |
| `leadstack-audit-store.timer` | installed and enabled, every 10 minutes |
| `sudo .venv/bin/python deploy/staging/backup_drill.py` | **15 passed, 0 failed**: `audit_digest verify` over 263 lines (worker log, `audit_digest.log`, `seed.log`), 243 windows from 2026-11-08 14:00 to 2026-11-18 17:00 UTC, no findings; app 137 tables / 1,430 rows and ZITADEL 144 / 2,308 rows match |
| `uv run pytest tests/unit/test_staging_timers.py` | 6 passed |

Limits: the windows before the seed are checked against the database's
own copy of their records, so a change made to them before 2026-11-18
would not show. The store is on the same host (root can clear the
attribute); the external log store stays an owner decision (S11).

## Staging deployed at `c94d156` (2026-11-18, owner: "Deploy staging")

From `7423c7a`: SaaS-OS v0.15.0 (K3.10, K3.11), Settings › AI (P9-S), the
email headers and the unsubscribe page (E-H1). Staging runs
`ENVIRONMENT=production` with no email switch set, so nothing can be sent
and campaigns cannot be queued.

| Check | Result |
| --- | --- |
| CI on `c94d156` | run 44306022129, 5 of 5 jobs passed |
| Backup before deploying (`backup_drill.py`) | 14 passed, 1 failed. Passed: both databases backed up, encrypted, restored into a separate PostgreSQL; every table's row count matches (app 127 tables, 1,369 rows; ZITADEL 144, 2,279); RLS identical; the app role safe; one workspace sees none of another's rows. Failed: `audit_digest verify --partial` on the exported worker log, `chain_start_missing`: the worker has run since 2026-11-08 and Docker keeps its last 5 × 10 MB of log, so the export starts at 2026-11-16 and the chain's first record has rotated away. The database is not at fault; staging has no append-only log store (the stand-in is the container log) |
| Image | built on the VPS, `crm-app:c94d156`, saas-os 0.15.0 |
| `up -d --wait` | migrate exited 0; app and worker healthy |
| Migration heads | SaaS-OS `e1f5a8c3b7d9`, product `0045_email_headers`; `email_message.message_id` exists |
| `/readyz` | 200 |
| `/app/u/{workspace}` | 200, the app page |
| `POST /v1/public/unsubscribe/{workspace}/{unknown token}` | 204 (answers alike for unknown links) |
| `GET /v1/workspaces/{id}/ai`, `/ai/budget` without a session | 401 |
| App and worker logs, first 10 minutes | no error lines |

**AI permissions on staging** (owner: "apply AI permissions on staging",
2026-11-18), with `crm_app.role_upgrade` per `ROLE-UPGRADE-RUNBOOK.md`:
the dry run (`--include-administrative`, fingerprint `4371572593bb384c`)
listed only `ai.policy:read`, `ai.policy:manage`, `ai.usage:read` and
`ai.budget:manage` for Owner and Admin in the two staging workspaces;
`--apply --expect 4371572593bb384c` granted exactly those; a second dry
run grants nothing; the audit log has 16 `role_permission.grant` entries.
AI stays off in both workspaces and no provider is configured.

**Settings › AI signed in** (owner: "use the staging test accounts on
crm-staging.auravox.nl", 2026-11-18), in a headless Chrome with one
isolated session per test user:

| Check | Result |
| --- | --- |
| Alice (Owner, Staging Alpha) opens Settings › AI | page shows AI, Features, "no AI models available yet", Data preferences, Monthly AI budget |
| Alice turns AI on, reloads | still on (stored on the server) |
| Alice turns Contact brief on, then off; turns AI off | each switch follows; no error shown |
| Alice sets a 10 EUR cap, then removes it | "Within budget, 10 EUR"; then "No budget set" |
| Bob (Owner, Staging Beta) reads Alpha's `/ai`, `/ai/budget`; `PUT /ai/enabled` | 404 `tenant not found` for each |
| Bob opens Alpha's Settings › AI in the app | "You can't open this workspace" |
| Bob reads Beta's `/ai` | 200, AI off |
| Alpha afterwards (as Alice) | AI off, Contact brief off, budget unconfigured |
| Logs of every staging service, the 25 minutes around the check | no error lines |

Not checked on staging: the Member view (the notice in place of the
settings). Both staging test users are Owners, so no Member was available;
the frontend test `aiSettings.test.tsx` and the route tests cover it.
Rollback: the code
alone can go back to `crm-app:7423c7a`; the SaaS-OS v0.14.0 schema is
forward-only once used (K3.10), so a full rollback means restoring the
backup taken above (2026-11-18, before the deploy) and losing later changes.

## Unsubscribe and threading headers (decision E-H1, 2026-11-18)

Campaign emails carry one-click `List-Unsubscribe` headers; conversation
replies carry `In-Reply-To` and `References`. Migration
`0045_email_headers`. Nothing is sent anywhere.

| Check | Result |
| --- | --- |
| `pytest tests/unit` | 807 passed |
| `test_emails.py`, `test_conversations.py`, `test_campaigns.py`, `test_foundation.py` | passed |
| `pytest tests/integration` (full) | 919 passed (58 min); `test_campaigns.py` rerun on the final code: 9 passed |
| Frontend `vitest run --maxWorkers=2`, `build` | 371 passed (37 files); built |
| `ruff check` / `ruff format --check` / `pyright` / `lint-imports` | clean / clean / 0 errors / 2 kept, 0 broken |

The body's unsubscribe link opens `/app/u/{workspace}#{token}`, which
unsubscribes only when the person presses the button (3 page tests, with an
accessibility scan).

Not verified: a real provider's handling of the headers; a mail client's
threading.

## Workspace AI settings (decision P9-S, 2026-11-18)

Settings › AI over SaaS-OS's `saas_os.inference.settings`: AI on or off,
the contact brief, model choice and order, data preferences, the monthly
budget and the workspace's cap. Owners and Admins only. AI stays off
everywhere; no provider or model is configured.

| Check | Result |
| --- | --- |
| `pytest tests/integration/test_ai_settings_routes.py` | 7 passed |
| `pytest tests/integration` (full) | 916 passed, 1 failed: the Read-only `access` expectation lacked the four new AI actions; updated, and `test_workspace_routes.py` then passed (25) |
| `pytest tests/unit` | 804 passed |
| `ruff check` / `ruff format --check` / `pyright` / `lint-imports` | clean / clean / 0 errors / 2 kept, 0 broken |
| OpenAPI | only additions: six paths, ten schemas |
| Frontend `typecheck`, `lint`, `build` | clean |
| Frontend `vitest run --maxWorkers=2` | 368 passed (36 files). With the default worker count on this machine, 1 to 10 unrelated tests hit the 5 s timeout under load; each passes alone |

Not verified: granting a configured model and an AI call (needs a
platform operator's provider and model, not authorized); the page in a
browser.

## SaaS-OS upgrade to v0.15.0 (decision K3.11, 2026-11-17)

On the new pin `cdede95` (v0.15.0, from v0.14.0 `fb842ff`), locally on
Windows, on `main`:

| Check | Result |
| --- | --- |
| Tag | `v0.15.0` resolves to `cdede95…`; `git tag -v v0.15.0`: good ED25519 signature by the owner's key |
| `uv lock --upgrade-package saas-os`, `uv lock --check`, `uv sync --frozen` | Only the saas-os entry changed (0.14.0 → 0.15.0); installed from commit `cdede95…` |
| `saas_os.inference.settings` | Imports; nine functions and eleven types as in SaaS-OS's public API snapshot |
| `ruff format --check .` / `ruff check .` | clean |
| `pyright` / `lint-imports` | 0 errors / 2 kept, 0 broken |
| `pip-audit --strict --require-hashes` (CI's export) | No known vulnerabilities |
| detect-secrets hook over the changed files | Exit 0, after replacing the audited false-positive hash of the pin SHA in `.secrets.baseline` |
| `pytest tests/unit` | 803 passed; includes the pin test, now asserting `cdede95` |
| `pytest tests/integration`, `.env.test`, local PostgreSQL | 910 passed (55 min); migration head unchanged at `e1f5a8c3b7d9` |

No product code changed and no migration was added. Gap 20 is closed
upstream; AI stays off in every workspace until the Settings › AI slice
is built and a member turns it on. Staging still runs `7423c7a`:
deploying needs the owner's go-ahead. Not run locally: `tests/identity`
(opt-in, needs the local ZITADEL) and the frontend checks (no frontend
file changed).

## SaaS-OS upgrade to v0.14.0 (decision K3.10, 2026-11-17)

On the new pin `fb842ff` (v0.14.0, from v0.10.0 `0f9bf4d`; v0.11.0 to
v0.13.0 skipped), locally on Windows, on `main`:

| Check | Result |
| --- | --- |
| Tag | `v0.14.0` resolves to `fb842ff…`; `git tag -v v0.14.0`: good ED25519 signature by the owner's key |
| `uv lock --upgrade-package saas-os`, `uv lock --check`, `uv sync --frozen` | Only the saas-os entry changed (0.10.0 → 0.14.0); installed from commit `fb842ff…` |
| `ruff format --check .` / `ruff check .` | 421 files already formatted / all checks passed |
| `pyright` / `lint-imports` | 0 errors / 2 kept, 0 broken |
| detect-secrets hook over tracked and untracked files | Exit 0, after replacing the audited false-positive hashes of the pin SHA and the migration head in `.secrets.baseline` |
| `pytest tests/unit` | 803 passed; includes the pin test, now asserting `fb842ff` |
| `pytest tests/integration`, `.env.test`, local PostgreSQL | 910 passed (1 h 0 min); applies the eleven new platform migrations to head `e1f5a8c3b7d9`, twice |

No product code changed. Gaps 21 and 22 are closed upstream; gap 20 is
only partly closed, so AI stays off in every workspace
(`saas-os-gaps.md`). Staging still runs `7423c7a`: deploying this needs
the owner's go-ahead, and once v0.14.0 has run against a database a
rollback is forward-only (DECISIONS K3.10). Not run locally:
`tests/identity` (opt-in, needs the local ZITADEL) and the frontend
checks (no frontend file changed).

## AI provider decision and contact-brief groundwork (decision P9-P, 2026-11-09)

The owner chose Groq first, under Zero Data Retention, with no training and
pay-as-you-go billing, and made provider independence mandatory. SaaS-OS
v0.10.0's governed inference was inspected and meets the architecture
(details in P9-P). Three gaps are recorded, not filed: 20, no supported way
to turn AI on for a workspace (blocking); 21, no money limit; 22, no tenant
usage read. Brief 2, the register, `BLOCKED-WORK-PREPARATION.md` section 1
and the roadmap's Phase 9 status are updated.

Built: `crm_app.domains.ai_brief` (the allowlist of facts and the data
part) and `crm_app.ai` (use-case definition, request, outcome states).

| Check | Result |
| --- | --- |
| `pytest tests/unit` | 803 passed (new: `test_ai_brief.py`, 11 in-process; `test_ai_states.py`, a SaaS-OS probe in a fresh interpreter with a stub in place of `run_inference`) |
| ruff check and format, pyright, lint-imports, secret scan | clean; 2 contracts kept |

Not done: no route, permission or start-up registration; nothing reads a
contact's facts from the database yet; no provider is configured anywhere,
and no request has been sent to any provider.

## Phone-width pass on staging (2026-11-08)

Browser window at 400 CSS px (Chrome's narrowest), staging `ad247c2`,
workspace "Staging Alpha". A script measured every element of the page
against the viewport, ignoring content inside its own scrolling container.

| View | Horizontal overflow |
| --- | --- |
| Home (Business overview and My day), Reports, Inbox, Business profile, Campaigns, Forms, a form's editor, Contacts, Calendar, Opportunities, Tasks, Automations | none (page width 400 on every one) |

Looked at by eye: the conversion funnel (labels whole, shares beside the
bars), the 12-week lead trend (12 columns fit, every other week labelled),
sources, recent conversations, the form's "Automations started by this
form" section and the contact fields stack in one column. No fix needed.
Not covered: 375 px exactly (the window does not go below 400), dialogs
other than the campaign editor's audience, and touch-only behaviour.

## Staging deploy of P2-BP, P7-FA, P7-CC (`ad247c2`, 2026-11-08)

Migration `0044_business_profile` ran on deploy (the five columns exist; no
data changed, so no backup was taken first, as the runbook allows). All
services healthy, `/readyz` 200. Browser, workspace "Staging Alpha": the
contact fields and "Show these on booking pages" appear under Business
profile; the campaign editor's audience has the Company search. Nothing
was saved. Not checked in the browser: a form's automations (staging has
no form) and a booking page showing the details (none chosen).

## Companies in a campaign's audience (decision P7-CC, 2026-11-08)

| Check | Result |
| --- | --- |
| Frontend typecheck, lint, build; full suite `--maxWorkers=6`; secret scan | clean; 363 passed (new: a chosen company shows by name, is removed from its chip, another is added by search, and the saved segment carries it; axe clean) |

No backend change.

## Starting an automation from a form (decision P7-FA, 2026-11-08)

| Check | Result |
| --- | --- |
| Frontend typecheck, lint; full suite `--maxWorkers=6` | clean; all passed (new: the form lists its own and any-form automations, not another form's; "New automation for this form" opens the editor with the trigger set; hidden without read access; axe clean) |

No backend change.

## The business's contact details (decision P2-BP, 2026-11-08)

| Check | Result |
| --- | --- |
| Integration `test_business_profile.py`, `test_booking_page_routes.py`, `test_workspace_settings.py`, `test_foundation.py`, `test_migrations_as_owner.py` | all passed (new: normalised storage, Member refused, malformed values 422, "" clears and null keeps, booking page shows the details only when chosen and none when all are empty; head `0044_business_profile`) |
| Unit, whole suite (no environment); pyright; ruff | 791 passed; clean |
| Frontend typecheck, lint; full suite `--maxWorkers=6` | clean; 360 passed (new: contact fields and switch saved with trimming and clearing; public page shows the links only when present; axe clean) |

## Home "My day" view (decision P4-M, 2026-11-08)

| Check | Result |
| --- | --- |
| Frontend typecheck, lint, build; full suite `--maxWorkers=6` | clean; 358 passed (new: the switch, My day's titles and subline, business cards left out, each card asks with `assignee=me`, `host=me`, `assigned=mine`, `owner=me`, the choice remembered; axe clean) |

| Staging (`7b48676`), browser at 1280 px, workspace "Staging Alpha" | the switch shows beside the greeting; My day shows the subline, "My appointments today", "My tasks due today", "My conversations" and the attention strip; the business cards are hidden; switching back restores them |

No backend change. Not verified: phone widths in a browser.

## Home setup checklist and 30-day tile changes (decision P4-S, 2026-11-08)

| Check | Result |
| --- | --- |
| Integration `test_setup.py`, `test_workspace_settings.py` | 19 passed (new: a new workspace has done nothing; a contact, deal, business hours and a second member tick only their steps; another workspace unaffected; reader 200, other workspace and outsider 404, anonymous 401) |
| Unit, whole suite (no environment, as CI) | 784 passed; route policy for `/setup` added |
| Ruff, pyright, import contracts, secret scan | clean |
| Frontend typecheck, lint, build; full suite `--maxWorkers=6` | clean; 357 passed (new: checklist progress and steps, a step opens its page, Hide remembered, hidden when all done and never requested for Members; tile notes for contacts and deals; axe clean) |

| Staging (`288412b`), browser at 1280 px, workspace "Staging Alpha" (Owner) | checklist "3 of 7 done" (contact, deal, automation ticked); "Set your business hours" opens Settings › Business profile; tiles "6 added in 30 days (previous 30: 0)" and "2 created in 30 days (previous 30: 0)" |

Not verified: phone widths in a browser; Hide on staging (tested in the suite).

## Conversion funnel, lead trend and Home cards (decision P10-F, 2026-11-08)

| Check | Result |
| --- | --- |
| Integration `tests/integration/test_reports.py` | 12 passed (new: funnel figures and CSV, the 12-week trend with won contacts, 4-week trend, refused week counts, outsiders) |
| Unit, whole suite (no environment, as CI) | 784 passed (new: trend start, week limits, local day) |
| Route policies `tests/unit/test_routes.py` | 13 passed (funnel, trend and funnel CSV guarded by `crm_app.contact:read`) |
| Ruff format and lint, pyright, secret scan | clean |
| Frontend typecheck, lint, build; full suite `--maxWorkers=6` | clean; 354 passed (new: funnel steps and shares, empty and refused funnel; Home trend, sources, conversations, attention counts, Inbox opened on "without an owner", refused trend; axe clean) |

| Staging (`crm-staging.auravox.nl`, `283a8c7`, then `8d3e125`), browser at 1280 px, workspace "Staging Alpha" | Home: unread and unowned conversation items, 12-week trend, sources (Manual 100%), recent conversations; "without an owner" opens the Inbox on Unassigned; Reports funnel 6 / 0 / 1 / 1. Found and fixed (`8d3e125`): the 34% bar floor cut "Booked an appointment" short; bars now fit their label |

Not verified: phone widths in a browser; trend figures across a
daylight-saving change (the integration test avoids week edges).

## Staging deployed and audited (decision D-STG.5, 2026-11-08)

Staging runs at `https://crm-staging.auravox.nl` on the owner's OVHcloud
VPS, every service in containers on that host. Overall: **CONDITIONAL
PASS** (`STAGING-ACCEPTANCE-REPORT.md`); not production approval.

| Check | Result |
| --- | --- |
| Public exposure | only 22, 80, 443 open from outside |
| Sign-in | ZITADEL OIDC on the app origin, in the browser; app sign-out ends the session server-side (cookie 401 afterwards) |
| Tenant isolation | 39 cross-workspace API attempts refused (404/405); search no leak; RLS forced on 60/60 product tables |
| CRM workflows | contacts, companies and links, tags, custom fields, deal stages and outcome, conversation, appointment, automation, template, reports, exports (`STAGING-E2E-TEST-REPORT.md`) |
| Security | CSP, HSTS, CSRF (foreign-origin 403), CORS, rate limit (60 then 429), input handling; app image 0 HIGH/CRITICAL after `bb90ab8` |
| Backup and restore | encrypted, restored into a separate instance in ~6 s; 14 of 15 checks (the audit-digest check waits on log shipping) |
| Reboot | back in ~32 s after the fixes in `7aeddf6`, `1170b91` |

Fixed during the audit: S-1 to S-5, S-11 (commits `a3685cd` to
`bb90ab8`); then S-7 and S-13 and most of S-6 by decision ZIT-1 (ZITADEL
v4.20.1, `crm-app-login` PR #1 merged as `ae70622` and running on staging).
Open, needing owner decisions: S-6 remainder (Caddy, Unbound, Squid;
ZITADEL's Go dependencies), S-8 (MFA,
public console), S-9 (backups off-host), S-10 (monitoring, log store),
S-19 (bootstrap tokens). Not tested: signup and email verification, mobile
layout in a browser, member management in the browser, real email.

## The Inbox's contact panel (decision P6-CX, 2026-11-08)

| Check | Result |
| --- | --- |
| Frontend `inbox.test.tsx` | 15 passed (new: the panel shows the contact, email, tag and deal, a deal opens on Opportunities, the toggle hides and shows it, "View full record" opens the contact; axe clean) |
| Frontend typecheck, lint; full suite `--maxWorkers=6` | clean; 348 passed |
| Browser, 1280 px (local stack, workspace "E2E Inbox 6C") | the panel shows beside the thread; the list and its filters fit after narrowing them; the toggle hides it and the thread widens |

Not verified: widths below 1280 px in a browser (the window cannot be
resized); there the panel and its toggle are hidden by CSS.

## Integrations shown by name (decision P12-N, 2026-11-08)

| Check | Result |
| --- | --- |
| `uv run pytest tests/integration/test_integrations.py` | 7 passed (new: a Member reads every integration's ID and name, the disabled one too; an API key 401; another workspace's list is empty and its route refuses this workspace's owner) |
| `uv run pytest tests/unit` | 779 passed (route policy `membership:read`; OpenAPI schema current) |
| `ruff format --check`, `ruff check`, `pyright`, `lint-imports` | clean; 2 contracts kept |
| Frontend typecheck, lint; full suite `--maxWorkers=6` | clean; 346 passed (`notes.test.tsx`: an entry made through a key reads "Zapier (integration)") |

Not verified: a browser check (the local workspace has no integration
entries; the label path is the one members' names already use).

## Waiting for business hours in automations (decision P8-W, 2026-11-08)

| Check | Result |
| --- | --- |
| `uv run pytest tests/integration/test_business_hours_wait.py` | 4 passed: skipped with `no_hours` while no hours are set, the run going on; at 03:00 the run waits until 09:00 and a retried job changes nothing; at 09:00 it finishes; at midday it goes straight on; an extra key refused (422) |
| Related integration suites (automations, triggers, notify, rules, round-robin, foundation head `0043_business_hours_wait`, migrations, CRM tables) | 67 passed |
| `uv run pytest tests/unit` | 779 passed (the next opening, including daylight saving and a closed week) |
| `ruff format --check`, `ruff check`, `pyright`, `lint-imports` | clean; 2 contracts kept |
| Frontend typecheck, lint, Prettier; `automations.test.tsx` | clean; 10 passed (the step is sent with no arguments; the warning shows only while hours are not set; axe clean) |
| Full frontend suite, `--maxWorkers=6` | 346 passed |

| Browser, desktop (local stack, workspace "E2E Automations 8A", no hours set) | the step shows its hint and the "Business hours are not set" notice; nothing was saved |

Not verified: the 390 px width in a browser (the Chrome window cannot be
resized); a run waiting in the browser (covered by the integration test).

## Round-robin assignment in automations (decision P8-R, 2026-11-08)

| Check | Result |
| --- | --- |
| CI on backend commit `a0d3ffa` | quality, frontend, security, image and integration jobs passed (includes `tests/integration/test_round_robin.py`) |
| Frontend `automations.test.tsx` | 8 passed: the new test adds the step, finds the first two members ticked, ticks a third and sends `assign_round_robin` with all three; axe scan clean |
| Frontend `npm run typecheck`, `npm run lint`, Prettier on changed files | clean |
| Full frontend suite, `npx vitest run --maxWorkers=6` | 344 passed (with default workers, 4 known load-timing tests failed and passed alone) |
| Local dev database | migrated to `0042_round_robin` with `crm-app-migrate` |

| Browser, desktop (local stack, workspace "E2E Automations 8A", one member) | the step shows its hint and one ticked member; saving is refused with the editor's general "Some steps are incomplete" message and nothing is saved. The default fieldset border was removed so it matches other steps |

Not verified: the 390 px width in a browser (the Chrome window could not be
resized; the step reuses the trigger's wrapping checkbox row); a
workspace with two or more members in the browser (covered by the
frontend test).

## Integrations and API keys (decision P12-K, 2026-11-07)

| Check | Result |
| --- | --- |
| `uv run pytest tests/integration/test_integrations.py` | 6 passed: Owners and Admins create Member or Read-only integrations (Admin and Owner refused, Members 403); a key shown once, `Cache-Control: no-store`, never listed; a key creates, reads and updates contacts, deals, tasks and companies, audited as `service_account`; deleting, integrations, members, automations, another workspace, key plus session and a wrong key refused; Read-only reads only; a third key 409; revoked and disabled keys 401 at once |
| Affected integration suites (history, notifications, deals, grants, provisioning, records, role upgrade, tasks, workspace routes) | 112 + 25 passed |
| `uv run pytest tests/unit` | 769 passed (key routes pinned; Owner and Admin only; owner-granted additions checked) |
| Frontend `integrationSettings.test.tsx`, `WorkspacePage.test.tsx`; typecheck; lint | 13 passed; clean |

## Automation notify action (decision P8-N, 2026-11-07)

| Check | Result |
| --- | --- |
| `uv run pytest tests/integration/test_automation_notify.py` | 5 passed: a bad message and a recipient from another workspace refused; the owner and a named member notified with the message, no actor; a retried step notifies nobody twice; the list shows the note and "Ann Lee"; no owner and a departed member skip with `no_owner` / `member_gone` |
| Related integration suites (notifications, automations, triggers, foundation head `0040_automation_notice`, migrations as the non-superuser owner, member reminders) | 46 passed |
| `uv run pytest tests/unit` | 767 passed |
| Frontend: `npm run typecheck`, `npm run lint`; `automations.test.tsx` and `AppFrame.test.tsx` | clean; 30 passed |
| Full frontend suite locally | 332 of 335; the 3 failures (`pipelineSettings`, `bookingPages`, `companyExport`) pass alone, the known local load timing |

## Scheduled commands and heartbeat (decision D-STG.3, 2026-11-07)

| Check | Result |
| --- | --- |
| `uv run python deploy/staging/schedule_local.py` | **11 passed, 0 failed**: the 6 timer commands and `health_check` exit 0 in the production image; the heartbeat pings with the worker running, sends nothing with it stopped, pings again once it is back |
| `systemd-analyze calendar` / `verify` (Debian 12 container) | every calendar and unit accepted (only the Windows mount's executable bits warned) |
| `uv run pytest tests/unit/test_staging_timers.py` | 5 passed |

Not covered: a monitoring service raising the alert (not chosen), systemd
on a real host, audit-digest log shipping.

## Backup and restore drill (decision D-STG.2, 2026-11-07)

`uv run python deploy/staging/backup_drill.py` against the local staging
stand-in: **15 passed, 0 failed**.

| Check | Result |
| --- | --- |
| Backups | app and ZITADEL databases through `saas_os.infra.db.backup.orchestrator run`; both artifacts are `age` ciphertexts |
| Restore | both into fresh databases on a separate PostgreSQL (own internal network, TLS from the local CA) through `orchestrator restore` |
| Contents | exact row counts match table by table (app 125 tables / 739 rows; ZITADEL 144 / 2,150); both migration versions match |
| Security | RLS identical table by table (105 tables force RLS, 58 in `crm_app`); `verify_restored_database` passes; the app role is still safe; one workspace's context sees 4 own roles and 0 of the other's |
| Audit | `saas_os.ops.audit_digest verify --partial` passes against the worker's exported digest line |

Stand-in limits: the app database is dumped as the stand-in's superuser
(SaaS-OS gap 18); the orchestrator needs a container (gap 17); no
off-provider copy; same host. Details in `DECISIONS.md` D-STG.2.

## Data changes in migrations under forced RLS (decision M-RLS, 2026-11-07)

| Check | Result |
| --- | --- |
| `uv run pytest tests/unit/test_migration_data_writes.py` | 2 passed; on the code before the change it reports all 20 unwrapped data changes |
| `uv run pytest tests/integration/test_migrations_as_owner.py` (local PostgreSQL 16) | 3 passed: both histories applied by a NOSUPERUSER NOBYPASSRLS owner; a bare `UPDATE` changes 0 rows, inside `all_rows` 2, RLS forced again; product downgrade to base and upgrade again as that owner |
| Existing migration round trips (`test_foundation`, `test_suppression_tables`, `test_booking_page_tables`, `test_crm_tables`, `test_emails`) | 99 passed |
| `uv run pytest tests/unit` | 756 passed |
| ruff, ruff format, pyright, lint-imports | clean |

## Local staging rehearsal (decision D-STG, 2026-11-07)

`deploy/staging/`, run locally with the `stateful-local` profile; every
container healthy. `uv run python deploy/staging/verify_local.py`: **35
passed, 0 failed** (24 at D-STG; 11 identity checks added by D-STG.1, after
`identity_local.py`).

| Criterion | Checked |
| --- | --- |
| E1 | `/healthz`, `/readyz` 200 over HTTPS through Caddy |
| E2 | start-up refuses `sslmode=disable` and `redis://` |
| E3 | SaaS-OS `e2b7c4d9a1f6` and product `0039_member_reminders` at head, applied over TLS by an owner that is no superuser and cannot bypass RLS; the app holds no migration or admin credential |
| E4 (part) | ZITADEL v4.19.5 and Login V2 on the app's origin; the app starts the flow, ZITADEL authenticates the administrator (session and finalised authorization request through its v2 API, as Login V2 does), the callback lands on `/app`; `saas_os_session` is Secure and HttpOnly; `/v1/sign-out-url` continues to `/oidc/v1/end_session`; after `/auth/logout`, `/auth/me` is 401. Not checked: a real browser, MFA, ZITADEL's session ending |
| E5 | through that session the user's own provisioned workspace answers 200; another owner's workspace and its members answer 404; the directory lists only the user's own |
| E6 | `EMAIL_SENDING_ENABLED`, the conversation and campaign streams, inbound and customer domains each refused at start-up in production |
| E7 | the worker's direct connection fails; its proxy allows CONNECT to a public IPv4 on 443 and refuses port 80, a host name, 10.0.0.1 and 172.16.0.10 |
| E10 | the edge refuses a 7 MB body (connection closed) and a 100 KB public body (413), passes a small public body (422 from the app), and replaces a client's `X-Forwarded-For` |

Not covered yet: the browser and MFA parts of E4, E8 and E9 (backups,
monitoring). Findings: `DECISIONS.md` D-STG (the SaaS-OS proxy healthcheck,
strict certificate checks, and the RLS risk for data migrations, since
resolved by M-RLS) and
D-STG.1 (ZITADEL initialises as a non-superuser owner).

## Production image (decision D-IMG, 2026-11-07)

| Check | Result |
| --- | --- |
| `docker build --tag crm-app:local-check .` | built, 333 MB |
| Image contents | user `app`; no git, uv, pip or curl; no `.env` file; SaaS-OS 0.10.0 at `0f9bf4d`; 40 migration files; `frontend/dist` present |
| `crm-app-migrate` from the image, test database | exit 0 |
| API from the image | healthy; `/healthz`, `/readyz`, `/app/` 200; `/v1/workspaces` 401 |
| Worker from the image | `crm-app-worker --check` exit 0 while running |
| CI `image` job check, locally | passes; fails as intended against a base image that has pip |

## Hosts' in-app appointment reminders (decision N-2, 2026-11-07)

Migration `0039_member_reminders`; `crm_app.member_reminders`, run by
`crm_app.email_maintenance`. Locally on Windows:

| Check | Result |
| --- | --- |
| `ruff format --check .` / `ruff check .` / `pyright` / `lint-imports` | clean / clean / 0 errors / 2 kept |
| `pytest tests/unit` | 753 passed |
| `pytest` on the 13 member-reminder, notification, reminder, booking, appointment, email, purge, table-guard and foundation integration files, `.env.test` | 167 passed |
| `crm_app.openapi` and `npm run gen:api` | `frontend/openapi.json` and `schema.d.ts` regenerated (the new kind) |
| Frontend `typecheck`, `lint`, `src/shell` tests | clean; 22 passed |

Found and fixed on the way: the first revision id was 33 characters,
longer than Alembic's `varchar(32)`; renamed to `0039_member_reminders`.
Not run locally: the full integration suite and the full frontend suite
(CI).

## Hosting decision brief (2026-11-07)

`DECISION-BRIEF-HOSTING.md`: three architectures compared against SaaS-OS
v0.10.0's deployment requirements, with costs, risks, a staging plan and
the owner's decisions. Nothing selected, bought or deployed.

## Unknown send outcomes (decision E-R1, 2026-11-07)

Migration `0038_email_outcome_unknown`; `crm_app.emails` stops retrying an
email whose outcome is unknown unless the provider de-duplicates the
repeat, and then only inside its window. Locally on Windows:

| Check | Result |
| --- | --- |
| `ruff format --check .` / `ruff check .` | 364 files formatted / all checks passed |
| `pyright` / `lint-imports` | 0 errors / 2 kept, 0 broken |
| `pytest tests/unit` | 753 passed |
| `pytest` on the 12 email, booking, reminder, campaign, consent, conversation and inbound integration files, `.env.test` | 138 passed (includes the four new E-R1 tests; the probe's own-row count moved from 8 to 15) |
| `pytest tests/integration/test_foundation.py` | passed; product head `0038_email_outcome_unknown` |
| Frontend `typecheck`, `lint` | clean |
| Frontend `npm test` | 330 passed and 3 failed in the full parallel run (`forms`, `opportunities`, `pipelineSettings`); the three files pass alone (29 of 29). Load on this machine, not this change: none of them renders an email status |

Not run locally: the full integration suite (CI).

## SaaS-OS upgrade to v0.10.0 (decision K3.9, 2026-11-07)

On the new pin `0f9bf4d` (v0.10.0, from v0.8.0 `140d9dd`; v0.9.0
skipped), locally on Windows, on `main`:

| Check | Result |
| --- | --- |
| Tag | `v0.10.0` resolves to `0f9bf4d…`; `git tag -v v0.10.0`: good ED25519 signature by the owner's key |
| `uv lock --upgrade-package saas-os`, `uv lock --check`, `uv sync --frozen` | Only the saas-os entry changed (0.8.0 → 0.10.0); installed `saas-os` 0.10.0 from commit `0f9bf4d…` |
| `ruff format --check .` / `ruff check .` | 363 files already formatted / all checks passed |
| `pyright` / `lint-imports` | 0 errors / 2 kept, 0 broken |
| detect-secrets hook over tracked files | Exit 0, after replacing the audited false-positive hash of the pin SHA in `.secrets.baseline` |
| `pytest tests/unit` | 752 passed; includes the pin test, now asserting `0f9bf4d` |
| `pytest` on the integration files this move can affect (`test_foundation`, `test_emails`, `test_booking_emails`, `test_email_templates`, `test_inbound_email`, `test_permission_grants`, `test_sending_domains`, `test_custom_domains`, `test_history`), `.env.test` | 85 passed |
| `npm run gen:api` | `frontend/src/api/schema.d.ts` unchanged |

No product code changed (K3.9). The migration head is unchanged
(`e2b7c4d9a1f6`). Not run locally: the full integration suite (left to
CI), `tests/identity` (opt-in, needs the local ZITADEL) and the other
frontend checks (no frontend file changed).

## In-app notifications (decision N-1, 2026-11-06)

Members get notifications in the header bell when someone else assigns
them a task, conversation or appointment, and when a visitor books or
cancels on their booking page. The table is product-owned
(`crm_app.member_notification`, migration `0037_member_notifications`)
because SaaS-OS v0.8.0's `in_app` channel has no type, reference, read
state or paging. Filed upstream as aelboum/saas-os#230. The routes are
`/v1/workspaces/{ws}/me/notifications`, plus `/read-all` and `/{id}/read`.
The Tasks page now opens a task from `?record=`. A review found three
issues, all fixed before commit: reopening the same linked task, a silent
"Mark all read" failure, and timestamps from the application clock (both
now use the database clock).

| Check | Result |
| --- | --- |
| `ruff format --check .` / `ruff check .` / `pyright` / `lint-imports` | Clean / clean / 0 errors / 2 kept |
| `pytest tests/unit` (no configuration in the environment) | 752 passed |
| `pytest tests/integration` (full suite) | 852 passed |
| `test_notifications`, `test_booking_page_routes` after the clock fix | 26 passed |
| Frontend `tsc -b`, `eslint`, `vitest run --maxWorkers=3`, `vite build` | Clean, clean, 333 passed, built |

The frontend suite with default parallelism timed out 1 to 3 settings and
consent tests (5 s limit) on this machine. All of them pass alone and in
the full run with 3 workers, so this looks like CPU contention; CI is the
check.

Not done: a browser check at desktop and 390 px (the local identity stack
was not running). Not built: overdue and upcoming reminders, notifications
for form submissions, owner changes and automation failures, preferences,
email or push delivery, and real-time updates.

## Quick wins (decision UI-Q1, 2026-11-06)

Frontend only: contact conversations, "+ New" › Appointment and
Conversation, palette record search, campaign tag and owner filters, the
account menu and avatar, the Forms text, and the template preview
(DECISIONS.md UI-Q1).

| Check | Result |
| --- | --- |
| `tsc -b` / `eslint .` | Clean / clean |
| `vitest run` | 328 passed (14 new or changed tests, each new view with an axe scan) |
| `vite build` | Built |

Not done: a browser check at desktop and 390 px. The changes reuse
existing components and styles, and are covered by component tests.

## History sources (decision K3.8, 2026-11-06)

History entries made by a booking page, a form or an automation now name
that source instead of a member (migration `0036_activity_source`). The Home
feed and record history show "Booking page: <name>", "Form: <name>" or
"Automation: <name>". SaaS-OS issues #224 (email headers) and #225 (domain
management) filed.

| Check | Result |
| --- | --- |
| `ruff format --check .` / `ruff check .` / `pyright` / `lint-imports` | Clean / clean / 0 errors / 2 kept |
| `pytest tests/unit` (no configuration in the environment, as in CI) | 752 passed |
| `test_booking_page_routes`, `test_form_routes`, `test_automations`, `test_foundation`, `test_note_activity_tables` | 142 passed |
| Frontend `tsc -b`, `eslint`, `vitest run`, `vite build` | Clean, clean, 314 passed, built |

Not done: a browser check of the feed. The change is one label in two
existing lists, covered by the component tests.

## Permission grant migrations, steps A to C (decision K3.7, 2026-11-06)

`crm_app.permission_grants` declares 27 standard and 12 administrative
migrations, with a read-only report. SaaS-OS issue #223 filed (gap 14).

| Check | Result |
| --- | --- |
| `ruff format --check .` / `ruff check .` | All formatted / all checks passed |
| `pyright` / `lint-imports` | 0 errors / 2 kept, 0 broken |
| `pytest tests/unit` | 751 passed (8 new in `test_permission_grants.py`) |
| `pytest tests/integration/test_permission_grants.py` | 7 passed |
| Local trial on a throwaway database (`PERMISSION-GRANT-MIGRATIONS-PLAN.md` §7) | Dry run = report; applied once; second run unchanged; revoked grant not restored; database dropped |

## Visitor and automation-step attribution (decision K3.6, 2026-11-06)

Bookings, visitor cancellations, form submissions, consent confirmations
and automation steps are now audited as `crm_app.booking_page`,
`crm_app.public_form`, `crm_app.consent_link` and `crm_app.automation_run`,
with the member as `on_behalf_of_user_id`. Emails queued by those paths have
no `created_by_user_id`. Rows and authorization are unchanged.

| Check | Result |
| --- | --- |
| `ruff format --check .` / `ruff check .` | All formatted / all checks passed |
| `pyright` / `lint-imports` | 0 errors / 2 kept, 0 broken |
| `pytest tests/unit` | 743 passed |
| `test_booking_page_routes`, `test_form_routes`, `test_booking_emails`, `test_automations`, `test_consent_confirmations` | 52 passed after updating the expected actor |
| `pytest tests/integration` (one ordered run) | 832 passed, 0 failed (45 min) |

## System-actor audit entries (decision K3.5, 2026-11-06)

New `crm_app.system_audit` writes SaaS-OS system-actor entries for the
paths that changed workspace data with no member acting and recorded no
entry: unsubscribe link, email worker and email events for emails queued
by nobody, provider suppression without a member, Resend domain events,
the sending-domain claim sweep, the custom-domain re-check, the import
retention sweep, inbound processing and automation run endings. Member
attributions under approved decisions are unchanged.

| Check | Result |
| --- | --- |
| `ruff format --check .` / `ruff check .` | All formatted / all checks passed |
| `pyright` / `lint-imports` | 0 errors / 2 kept, 0 broken |
| `pytest tests/unit` | 743 passed (3 new in `test_system_audit.py`) |
| `pytest` over the 24 integration files for suppression, bookings, reminders, conversations, consent, forms, automations, campaigns, emails, inbound, sending and custom domains, imports | 278 passed |

The full integration suite runs in CI.

Gap 14 (new, `saas-os-gaps.md`): the SaaS-OS email outcome errors are not
public, so the K3.4 email-retry follow-up stays blocked.

## SaaS-OS upgrade to v0.8.0 (decision K3.4, 2026-11-06)

On the new pin `140d9dd` (v0.8.0, from v0.6.0 `d980e73`; v0.7.0 skipped)
every check was run again, locally on Windows, on `main`:

| Check | Result |
| --- | --- |
| Tag | `v0.8.0` resolves to `140d9dd…`; `git tag -v v0.8.0`: good ED25519 signature by the owner's key |
| `uv lock --upgrade-package saas-os`, `uv lock --check`, `uv sync` | Only the saas-os entry changed (0.6.0 → 0.8.0); installed `saas-os` 0.8.0 from commit `140d9dd…` |
| `ruff format --check .` / `ruff check .` | All formatted / all checks passed |
| `pyright` / `lint-imports` | 0 errors / 2 kept, 0 broken |
| detect-secrets hook over tracked files | Exit 0, after replacing the audited false-positive hashes of the pin SHA and of the SaaS-OS migration head in `.secrets.baseline` |
| `pytest tests/unit` | 740 passed; includes the pin test, now asserting `140d9dd` |
| `pytest tests/integration` against `crm_app_test`, in six sequential groups (memory) | 147 passed and 2 errors; 140 passed and 1 failed; 134 passed, 1 failed and 8 errors; 146, 119 and 127 passed |
| The four affected files run again, each on its own | `test_health_check` 2, `test_import_commit` 8, `test_task_tables` 13, `test_owner_protection` 10: all passed |

The errors were `relation "crm_app.email_index"` / `"crm_app.task" does
not exist` at setup: the shared test database was left below the product
head by an earlier test in the same ad-hoc group (the groups were cut by
file name, not the usual grouping). Each file passed alone on the final
code. The concurrency test
`test_two_owners_removing_each_other_leave_exactly_one_active_owner[drop_role]`
failed once under load and passed on its own; watch it in CI.

No product code changed: crm-app has no outbox consumer or webhook
subscription, passes no `initiated_by`, neither reads nor writes
`core.platform_audit_log`, and never deletes `core.users` rows (K3.4).
The expected SaaS-OS migration head in `tests/integration/test_foundation.py`
is now `e2b7c4d9a1f6`.

Not run for this move: `tests/identity` (opt-in, needs the local
ZITADEL) and the frontend checks (no frontend file changed). The local
development database `crm_app` was not migrated; `crm_app.migrate` moves
it to `e2b7c4d9a1f6` on its next run.

## SaaS-OS upgrade to v0.6.0 (decision K3.3, 2026-10-31)

On the new pin `d980e73` every check was run again, locally on Windows,
on `main`:

| Check | Result |
| --- | --- |
| Tag | `v0.6.0` is annotated and signed, resolves to `d980e73…`; GitHub reports the signature verified (`valid`) |
| `uv lock --upgrade-package saas-os`, `uv lock --check`, `uv sync --frozen` | Only the saas-os entry changed (0.5.0 → 0.6.0); 72 packages, the other 71 unchanged; installed `saas-os` 0.6.0 from commit `d980e73…` |
| `ruff format --check .` / `ruff check .` | All formatted / all checks passed |
| `pyright` / `lint-imports` | 0 errors / 2 kept, 0 broken |
| detect-secrets hook over tracked files | Exit 0, after replacing the audited false-positive hashes of the pin SHA and of the SaaS-OS migration head in `.secrets.baseline` |
| `pytest tests/unit` | 542 passed (528 before, plus 14 in the new `tests/unit/test_provision_request.py`); includes the pin test, now asserting `d980e73` |
| `pytest tests/integration` against `crm_app_test`, in four sequential batches (memory) | 188 passed; 124 passed and 1 failed; 194 passed and 1 failed; 190 passed |

The two failures:

- `test_both_migration_histories_are_at_head` named the old SaaS-OS head
  `f6a2c8e4b1d9`. The expected head is now `b3d5f7a9c2e4`; the test passed
  in batches 3 and 4.
- `test_worker_starts_and_passes_its_health_probe` timed out after 60
  seconds in batch 3, with no error output from the probe. It passed in
  batch 2 on the same pin, twice on its own (11 s and 8 s) and again in
  batch 4. Recorded as a timing flake under load; watch it in CI.

Every integration file passed in its last run on the final code.

The local development database `crm_app` was migrated with
`python -m crm_app.migrate`: SaaS-OS head `b3d5f7a9c2e4`, product head
`0017_suppression`. The migration only widens a check; existing rows were
kept (68 contacts present afterwards).

Code change: `crm_app.provision.validate_request` refuses a control
character in the name, issuer or subject before the run starts, as
SaaS-OS v0.6.0 refuses them during it.

Not run for this move: `tests/identity` (opt-in, needs the local
ZITADEL) and the frontend checks (no frontend file changed).

## SaaS-OS upgrade to v0.5.0 (decision K3.2, 2026-10-23)

On the new pin `b03d87a` every check was run again, locally on Windows,
in a separate worktree of the branch `deps/saas-os-v0.5.0`:

| Check | Result |
| --- | --- |
| `uv lock` | Only the saas-os entry changed (0.3.0 → 0.5.0); 72 packages, the other 71 unchanged |
| `uv sync --locked`, `uv lock --check`, `uv pip check` | Exit 0; installed `saas-os` 0.5.0, `direct_url.json` commit `b03d87a…`, not editable; all installed packages compatible |
| `ruff format --check .` / `ruff check .` | 61 files already formatted / all checks passed |
| `pyright` / `lint-imports` | 0 errors / 2 kept, 0 broken |
| `pytest tests/unit` | 92 passed (includes the pin test, now asserting `b03d87a`, and the import-surface test) |
| `pytest tests/integration` (CI settings, disposable PostgreSQL 16 and Redis 7 containers, `01-roles.sh`) | 55 passed: foundation 7, owner protection 8, provisioning 8, tenant-table guard 11, workspace routes 21; containers removed afterwards |
| detect-secrets hook | Exit 0, after replacing the audited false-positive hash of the pin SHA in `.secrets.baseline` |
| pip-audit (hashed export, SaaS-OS excluded) | "No known vulnerabilities found" |
| Clean copy: trackable files copied to a fresh temporary directory, empty uv cache | `uv lock --check` and `uv sync --locked` exit 0; installed commit `b03d87a…`; `uv pip check` clean; unit tests 92 passed |
| Clean pip install of the pinned reference in a new Python 3.13 environment | `pip freeze` prints the reference; version 0.5.0; `direct_url.json` commit `b03d87a…`; `pip check` clean |

Not run for this move: `tests/identity` (opt-in, needs the local
ZITADEL) and the frontend checks (no frontend file changed).

## Criterion 9: CI on the pushed commit (2026-10-21)

GitHub Actions run 39652641595 (`push` to `main`), head commit
`dbb15609cd2531d3c430f06ee9c2e7bbd7f6a1c6`, which is the remote `main`
(`git ls-remote origin refs/heads/main`). Conclusion: success.

| Job | Result | Evidence from the run log |
| --- | --- | --- |
| quality | success | 32 files already formatted; ruff: all checks passed; pyright: 0 errors; import-linter: 2 kept, 0 broken; unit: 43 passed |
| integration | success | 7 passed against the PostgreSQL 16 and Redis 7 service containers (`CRM_APP_REQUIRE_INTEGRATION=1`, so missing settings fail instead of skipping) |
| security | success | pip-audit: no known vulnerabilities; detect-secrets hook passed |

This was the first run on Linux. The local integration suite was not
rerun after the CI concurrency commit because Docker Desktop was
stopped; that commit changes only `.github/workflows/ci.yml`.

## Security assumptions and unverified behaviour

- **Migration role (development and CI only):** the migration role is the
  PostgreSQL bootstrap superuser. Production needs a dedicated
  schema-owner role with only the rights the migrations need. That design
  is not done.
- **RLS on product tables:** the RLS policy itself is not exercised yet,
  because no tenant table exists. RLS predicate-free and cross-tenant tests
  start with the first table (Phase 2).
- **SUBTREE access:** not tested.
- **Same-origin rule:** verified only for `POST /auth/logout`.
- **ZITADEL v4.19.5:** not the version SaaS-OS was qualified against. It
  was verified only by the local login test.
- **Lifetimes:** session cookie and token lifetimes are SaaS-OS defaults
  and were not reviewed.
- **Development secrets:** read from `.env` in the working directory. In
  production they come from the process environment or `*_FILE` mounts.
  No production secret store is selected.
- **Logging:** SaaS-OS logs carry request IDs. Console tracing prints span
  attributes. The identity test checked that no configured password
  appeared in the server log; broader log-content review is not done.
- **CI workflow:** never executed on GitHub. Linux differences, such as
  `PGHOST` handling and the `psql` client on the runner, are untested.
- **Third-party login pages:** the identity test drives ZITADEL's HTML
  login pages and may break on a ZITADEL upgrade. It is therefore opt-in
  and not part of CI.

## Blockers

| Blocker | Impact | Needed |
| --- | --- | --- |
| Frontend framework not chosen (P-6) | Frontend work | Resolved 2026-10-22: React + Vite SPA (`DECISIONS.md` P-6.1) |
| Missing designs (states, a generic CRM version, membership, consent) | Frontend work on MVP screens | Design requests in `DESIGN-INSPECTION.md` §6, before standalone Claude Design closes on 2026-12-14 |
| No email provider configured | Real invitation delivery (P2-C) and the MVP email channel | An approved transactional email provider and credentials; until then nothing may be shown as sent |
| Purge participants outside the approved import surface | Removal of product data on tenant purge, before the first tenant table | Since K3.2 the pinned SaaS-OS v0.5.0 exports the registration API from `saas_os.core.tenancy`. Still needed: the participant and its tests under gate G1 (Q-purge), as separately approved work |
| ZITADEL v4.19.5 instead of the proposed v4.19.0 | Recorded under P-4 | Owner confirmation |

## Open questions recorded for later phases

- D-WS details: agency access and initial provisioning are now decided
  (P2-B, P2-C); the product-owned workspace index for the switcher is
  designed in the Phase 2 plan.
- Whether `SystemCaller(PROVISIONING)` may seed product roles right
  after the tenant bootstrap, and add permissions to existing workspaces
  later (P2-A open point). Settle in the Phase 2 plan.
- The purge-participant registry module is documented but not a package
  export (P2-D). Settle its use before the first tenant table.
- Multi-region hosting and data residency (K5.1).
- The timing of calendar/booking, campaigns, automation, AI, and
  reporting relative to the K5 MVP.
- The sibling repository's ownership and permission, before any reuse.
- Written terms for SaaS-OS (`UNLICENSED`) before third-party
  involvement.
- A trademark check on the product name before any public use.

## Next authorized action

None beyond reporting. Phase 1 is complete and Phase 0 task 0.3 is
done. Phase 2 is in progress (2026-10-21), following
`PHASE2-PLAN.md`. Owner decisions that day: Q6 approved (role matrix);
Q-purge option (a), upstream first with no internal-import exception;
Q1 approved as a design direction only; S1b and S3 approved within
supported APIs. Done and committed (plan §11.1):
- the permission catalogue and role templates (`src/crm_app/roles.py`);
- registration of the 39 granted permissions in the migration step
  (`crm_app.permissions`), with no role created or granted anywhere;
- structural schema guards that keep tenant-owned tables out until the
  purge gate G1;
- two read-only routes, `GET /v1/workspaces/{id}` and
  `/v1/workspaces/{id}/members`.

All checks pass locally:
- unit tests (77), plus the static, secret and dependency checks;
- integration tests (33), including the tenant-table guards and the
  workspace route tests, run against local services;
- the opt-in identity test (1).

Committed as `a069a6a1675802139e8862d0f639388d521b95c7` on `main` and
pushed; local and remote `main` matched and the working tree was clean.
GitHub Actions run 39675570028 on that commit: **success**.
- quality: 77 unit tests passed; pyright 0 errors; import contracts 2
  kept.
- integration: 33 passed against CI's PostgreSQL and Redis services.
- security: secret scan passed; dependency audit found no known
  vulnerabilities.

No merge, release or deployment.

Not done: tenant tables, the purge participant, the provisioning command,
and any route that changes memberships, roles or Owners (gates G1, G2,
G-LOCK in plan §14). Both upstream requests are drafted and have not been
sent: purge-participant registration (plan Appendix A) and adding
permissions to existing workspaces (plan §7.5, draft in Appendix B).
Tenant isolation is untested, because no tenant-owned table exists.

**Since then (2026-10-21; plan §11.2):**
- **Provisioning command (S6, gate G2):** `python -m crm_app.provision`,
  8 integration tests against `crm_app_test` pass. No real workspace has
  been provisioned.
- **Membership and role routes with last-Owner protection (S7, gate
  G-LOCK):** 8 integration tests pass, including 15 rounds of competing
  Owner removals. In every round the database kept exactly one active
  Owner. The operator rule for paths outside the product is in plan §5.4.
- **Totals:** unit 83, integration 49, static and secret checks pass.
- **Committed** as `19e7dce3f05c90580dcc930fc7e49fde617acda0` on `main`
  and pushed (2026-10-22, owner-approved). GitHub Actions run 39742030028
  on that commit: **success** (quality, integration, security).
- G1 (tenant tables) remains blocked.

Both upstream request drafts are now complete with acceptance criteria
and expected tests (plan Appendices A and B, 2026-10-22); neither has
been sent.

Next: every remaining Phase 2 step waits on an owner decision or an
external dependency (plan §15): sending the upstream requests (G1, G7),
provisioning a real workspace, Q3–Q5 (invitations) and P-6 (frontend).

**2026-10-22, owner decisions:** both upstream requests opened
(aelboum/saas-os#87, #88); P-6 decided as a React + Vite SPA (P-6.1);
Q4 manual invitation link and Q5 two-step role confirmation approved.
Next: frontend scaffold and Phase 2 screens (plan §16, F1). G1 waits on #87.

**F1 (2026-10-22, plan §11.3):** the frontend shell and the member screens,
served by the API under `/app`, plus `GET /v1/workspaces/{id}/access`.
Frontend 15 tests, unit 91 and integration 55 (full suite, `crm_app_test`) pass locally.
Not yet tried in a real browser against ZITADEL (done since; see below).

**Browser validation (2026-10-22, real Chrome, local ZITADEL; plan §11.3):**
- **Setup:** app server started by Claude with the owner's approval,
  against the disposable `crm_app_test` database and the local OIDC client.
  The owner signed in to ZITADEL themselves; no credential passed through
  Claude. A throwaway workspace was seeded in `crm_app_test` only (the
  owner plus fake Owner, Admin, Member and suspended Member). The server
  was stopped afterwards. Compose services were not touched.
- **Verified in the browser:**
  - sign-in redirect (PKCE S256, callback `/auth/callback`) and return
    to `/app`;
  - member list, roles and statuses;
  - suspend and reactivate;
  - remove (Escape cancels and sends nothing; Confirm revokes);
  - removing another Owner's Owner role after confirmation (200);
  - stepping down as the last Owner, refused with the right message
    (409);
  - opening a workspace by ID with the keyboard;
  - an unknown workspace getting the neutral not-found message;
  - sign-out.
- **Page checks:** no application console errors and no CSP violations
  (only a wallet extension's warnings). The self-hosted font loaded. The
  session cookie is not readable from JavaScript.
- **Defects found and fixed (tests added, frontend now 17 tests):**
  - keyboard focus fell to `<body>` when a removed member's row
    disappeared; it now moves to the result message;
  - after sign-out the previous workspace's data stayed on screen; the
    app now returns to the start page.

  Both fixes were rechecked in the browser.
- **Gaps found, not fixed:**
  - Sign-out ends only the app session. The ZITADEL session survives, so
    "Sign in" succeeds again without a password. SaaS-OS's logout does
    not end the provider session; an upstream request is drafted (plan
    Appendix C), not sent.
  - In Git Bash on Windows, `AUTH_POST_LOGIN_PATH=/app` is rewritten
    into a Windows path and sign-in fails with "Authentication is not
    configured"; this is now documented in the README.
  - `HEAD /app` returns 405 (only GET is registered).
- **Not tested in a browser:** the Admin view (actions on Owners hidden),
  automated contrast measurement, screen-reader output, and mobile width.
- **Uncommitted:** the two fixes, their tests, and these documents. The
  owner has not authorized a commit for this cycle.

**Same-origin sign-in (2026-10-22, decision D-IDL):**
- Local ZITADEL now sits behind the `edge` service on
  `http://localhost:8000`, with Login V2.
- **Verified:**
  - live discovery shows issuer `http://localhost:8000`;
  - in Chrome, the whole sign-in stayed on `localhost:8000`, from `/app`
    through `/oauth/v2/authorize` and `/ui/v2/login/...` to
    `/auth/callback` and back to `/app`; the owner entered their own
    credentials;
  - a membership change through the edge succeeded, so the same-origin
    check passes behind the proxy;
  - no application console errors;
  - with a throwaway Caddy and an echo server using the same Caddyfile,
    the app received only `saas_os_session`, never the provider cookies.
- **Observed gaps:**
  - a sign-in left open for more than 10 minutes ends on a raw 400 page
    at `/auth/callback` (SaaS-OS's transaction lifetime; its page);
  - Login V2 offers self-registration and is shown in the browser's
    language;
  - sign-out still leaves the ZITADEL session alive (Appendix C).
- **Uncommitted:** `deploy/local/compose.yaml`, `deploy/local/Caddyfile`,
  `.env.example`, `.env.test.example`, README and docs. The owner's
  `.env` was updated locally (backup `.env.backup-2026-10-22`, untracked);
  `.env.test` still names the old issuer.

**Sign-in settings (2026-10-22, decision D-IDL.1):**
- `deploy/local/configure-zitadel.py` applied the settings to local
  ZITADEL. It printed the resulting values, and a second run changed
  nothing.
- **Checked in the browser:** Login V2 no longer shows a registration
  link.
- **Not yet tried by hand:** lockout and the hidden-unknown-username
  behaviour.
- **Login V2 response headers** (observed through the edge):
  - `frame-ancestors 'none'`, `X-Frame-Options: deny`, `nosniff`, and
    `no-store` caching;
  - its own Content-Security-Policy allows `'unsafe-inline'` and
    `'unsafe-eval'` scripts and names the internal `http://zitadel:8080`
    for images and fonts. That policy belongs to ZITADEL's official
    image; changing it would mean customizing that image (SaaS-OS
    ADR-0025 uses the official one). Because Login V2 shares the app's
    origin, this is the weaker side of the shared-origin trade-off
    ADR-0025 accepted;
  - it also sends HSTS, which browsers ignore over plain HTTP.
- **Commits:** the earlier work is committed as `4e576e7` and `3023ff5`;
  GitHub Actions run 39754775922 succeeded (quality, frontend,
  integration, security). The settings script and these notes are
  committed together, after these notes were written.

**2026-10-22 (later), Phase 3 design, app frame and design fidelity (uncommitted):**
- **Phase 3 design:** a build-ready plan for Contacts and Companies is in
  `PHASE3-PLAN.md`. It is planning only; no table or migration (G1).
  Owner questions are in its §18.
- **App frame, rebuilt to the design** (`frontend/src/shell/`,
  `components/ui/`):
  - the header, the sidebar (232/60 px, collapsible groups) and the
    design's placeholder page for every unbuilt module;
  - Settings › Team & roles in the design's settings layout, with a
    read-only role matrix generated from Q6;
  - shared Button, Badge, Dialog, DataTable, Toast and state components.
  - Unbuilt features are labelled "soon" or "not available yet";
    nothing pretends to work.
- **Design fidelity:**
  - Inventory: every file in the export was inspected from source.
  - Comparison: geometry and styles of the frame and the Team & roles
    page were compared numerically against the prototype, served locally
    at the same viewport.
  - Six material differences were fixed; the remaining deviations are
    listed with reasons.
  - Details: `DESIGN-FIDELITY.md`.
- **Quality:**
  - `HEAD /app` returns 200.
  - Lighthouse accessibility scores 100 with no failed audits on
    Settings and on a placeholder page, colour contrast included.
  - Keyboard order and focus are checked, as is the phone layout at
    390 px (emulated).
  - The Admin view is checked with a test Admin session.
  - A real CSP violation (React Aria's injected stylesheet) is fixed with
    a hash-only allowance, and the favicon 404 is removed.
  - Test sessions were created only in `crm_app_test` and revoked
    afterwards.
- **Tests:** frontend 25; Python unit 92.
- **Not verified:**
  - pixel overlays (no image library);
  - Firefox and Safari;
  - screen reader output;
  - the phone layout in a real window (the Chrome window could not be
    resized; DevTools emulation was used).
- **Committed locally** (owner-authorized, 2026-10-22; **not pushed**):
  backend and tests `dc1b4f7`, frontend `2e722e7`, and these documents in
  the following commit. CI has not run on them.

**Settings › My profile (2026-10-22, uncommitted):**
- Implemented in the design's layout with only what exists: the real role
  line, disabled fields with a note that profiles cannot be stored yet
  (G1), the browser's time zone shown read-only, and "Manage" disabled.
- No storage, endpoint or migration.
- Compared against the design at 1280 px; one mismatch fixed
  (`DESIGN-FIDELITY.md` §4a).
- Frontend tests: 28 passed. Lighthouse accessibility 100 (0 failed) on
  My profile; no console messages; no overflow at 390 px.
- Review fix: the role shown is now the most senior one, not the
  alphabetically first.
- Screens compared so far: the app frame, Team & roles and My profile.
  The other design screens are placeholders or not started.

**My profile committed locally; palette (2026-10-22):**
- **My profile:** commit `02a6129`, local and not pushed. Validated on its
  own in a clean worktree: types, lint, 28 tests and the build pass.
- **Earlier pushes:** commits `dc1b4f7`, `2e722e7` and `3080d20` were
  pushed; GitHub Actions run 39766719219 succeeded (quality, frontend,
  integration, security).
- **⌘K palette:** implemented with page navigation only; it never
  searches records (`DESIGN-FIDELITY.md` §4b). Committed locally with
  owner authorization; not pushed. Frontend tests: 29 passed.
- **Screens compared so far:** the app frame, Team & roles and
  My profile. The palette is checked for behaviour and accessibility but
  not compared geometrically. No other design screen is implemented or
  verified.
- **Outstanding:** Firefox and Safari, and a real screen reader; none is
  available in this environment.

**Pushes, palette comparison and #87 (2026-10-22):**
- **Pushed:** `02a6129` (My profile), as a fast-forward. GitHub Actions
  run 39769519580: **success** (quality, frontend, integration,
  security).
- **Palette:** committed locally as `264c639`; not pushed.
- **Palette comparison against the design** (`DESIGN-FIDELITY.md` §4b),
  1280×609, numeric:
  - the panel, input, rows, header, footer, empty state and backdrop
    match;
  - three differences fixed: input text colour, panel height (it
    overflowed the viewport because of the note row), and placeholder
    contrast;
  - these fixes are uncommitted.
- **#87:** still open with no response; no newer SaaS-OS release. A
  refined technical proposal is in `PURGE-API-PROPOSAL.md`; it is not
  sent. G1 stays closed.

**Later on 2026-10-22:**
- **Pushed:** `264c639`, `c6af3ef` and `3376e37`.
  - GitHub Actions run 39771257565 on `3376e37` **failed** in the quality
    job's format step: `ruff format` also formats Python blocks in
    Markdown, and the proposal's example lacked blank lines.
  - Fixed in `e0fe0fd`; run 39771661933 **succeeded** (quality,
    frontend, integration, security).
- **SaaS-OS #87:** the owner-approved comment was posted
  (issuecomment-6339887993). No reply yet. G1 stays closed.

## Gate G1: purge participant (2026-10-23)

SaaS-OS v0.5.0 (#94) exports the purge-registration API; the owner moved
the pin to it (K3.2, crm-app pull request #1, `9bdf803`). On that pin:

- `crm_app/purge.py`: participant `crm_app.crm_data`, registered in
  `create_app()`, the worker and the operator's `--setup`; empty manifest
  `PURGE_TABLES`, which is also the coverage guard's list.
- Checks, run locally on Windows: `ruff format --check`, `ruff check`
  (pass); `pyright` (0 errors); `lint-imports` (2 kept); unit tests 106
  passed (14 new); integration tests against the disposable `crm_app_test`
  database and local Redis: 60 passed (5 new, in `test_purge.py`), probe
  schemas dropped afterwards.
- Not run: `tests/identity` (needs the local ZITADEL) and the frontend
  checks (no frontend file changed).
- G1 recorded as passed (`DECISIONS.md` G1). No tenant-owned table
  exists yet; each one still needs its own approval.

## Phase 3 slice 3A backend (2026-10-23 to 2026-10-24)

Decision P3-A; plan `PHASE3-PLAN.md` §19. Pushed to `main`:

| Commit | Content |
| --- | --- |
| `cde18ec` | P3-A decision; `PHASE3-PLAN.md` corrections and §19 |
| `2a6ea5b` | 3A.1: migration 0002 (`company`, `contact`), RLS, constraints, `PURGE_TABLES`, isolation, rollback and real operator-purge tests |
| `dad9132` | 3A.2: record service and API, validation, audit, idempotency, permission and route tests |
| `58cb900` | 3A.3: keyset lists, search, filters, sorting, list tests |
| `8724359` | Pre-push review fixes: idempotency keys scoped to the member; company deletion unlinks contacts as versioned, audited changes; FK race mapped to 422; deadlocks to 409 |
| `b288a4b` | Frontend lockfile: zod 4.6.5 -> 4.6.7 (GHSA-mrhx-c7xc-m3w5, dev-only via eslint-plugin-react-hooks) |

- Each 3A commit was checked on its own exported tree before it was
  committed: 3A.1 unit 108 / integration 89; 3A.2 unit 148 / integration
  103; 3A.3 unit 170 / integration 121 (all against the disposable
  `crm_app_test` database). The review fix: unit 171 / integration 126.
- CI: run 40034894076 on `8724359` passed quality, integration and
  security; the frontend job failed only its `npm audit` step on the new
  zod advisory. Run 40036417310 on `b288a4b` passed all four jobs.
- Not run: `tests/identity` (needs the local ZITADEL).
- Known limitations: `PHASE3-PLAN.md` §19.8.
- Next: 3A.4, the Contacts and Companies screens.

## Slice 3A.4 and hardening (2026-10-24, overnight mandate)

| Commit | Content | CI |
| --- | --- | --- |
| `ee355d3` | ROADMAP and PROGRESS: slice 3A outcomes | run 40037220673, all green |
| `9974bfb` | `/access` reports contact and company permissions | with `77f2c29` |
| `77f2c29` | Contacts and Companies screens (3A.4), DESIGN-FIDELITY §4c | run 40039613717, all green |
| `d20f743` | Header "New > Contact" opens the new-contact dialog | run 40040321310, all green |

- Frontend: 42 jsdom tests (13 new for the record screens and the New
  menu) with axe scans; typecheck, lint and build pass. The bundle-size
  warning predates this work (618 kB before, 660 kB now).
- **Blocked:** checking the screens in a real browser. The local app
  server is not running, and starting it would migrate the local
  development database and need a ZITADEL sign-in, both of which need the
  owner.
- List performance with 100,000 contacts measured on the disposable test
  database: every case under the 300 ms target (`PHASE3-PLAN.md` §19.8).
- Read-only security review of the slice: no critical or high finding;
  four low findings fixed, the rest recorded with reasons
  (`PHASE3-PLAN.md` §19.8).
- Pushed `8787e6c` (hardening; CI run 40041973473 passed quality,
  integration and security, but the frontend job failed its `npm audit`
  step on two new undici advisories) and `5288398` (undici 8.11.2 ->
  8.12.3 in the lockfile only; run 40042487578, all four jobs green).
- Phase 2 security review (read-only): `PHASE2-SECURITY-REVIEW.md`. No
  critical or high finding. Fixed: removed members proven refused with a
  live session (M1), mixed Owner races (L1), NUL bytes in static paths
  (L2), `Cache-Control: no-store` on API and sign-in responses (L3).
  Deployment points L4, L5 and I1 are for Phase 13. Phase 2 stays open.
- Next recommended: the owner reviews the screens in a browser and
  `PHASE2-SECURITY-REVIEW.md`, and chooses the next Phase 3 slice
  (`PHASE3-PLAN.md` §20; export needs no new table).

### Browser check of Contacts and Companies (2026-10-24)

The owner approved a browser check. The local app was started against the
local development database (migrations applied first, no output), the
owner signed in through local ZITADEL, and the owner created a local test
workspace with `crm_app.provision` ("Local test workspace", test data only).

- Checked in Chrome at desktop width, no console errors: company create
  with required-name validation, domain derived from the website and the
  country code upper-cased; New > Contact; contact validation (email or
  phone), create with company, stage and owner; duplicate email in a
  different case refused with "Open existing"; edit; Open leads view;
  search; Stage filter and Clear; archive, restore and confirmed delete;
  a company's people opening the contact. The audit log recorded every
  change with the signed-in user as actor.
- Fixed from the check: a 1 px vertical scrollbar beside the view tabs;
  New-menu labels truncated; the delete confirmation now says
  "Delete contact?" / "Delete company?" with a "Delete permanently" button;
  empty lists say records appear there; opening a deleted record's link
  said the workspace did not exist and now says the record no longer
  exists (new test).
- Not checked: phone width (the browser window could not be resized),
  "Load more" (too few records), Firefox and Safari.

### Slice 3B approved; 3B.1 schema (2026-10-24)

The owner approved slice 3B (decision P3-B, D1-D9; Q6 amended by D3).
3B.1 adds migration `0003_notes_activity`: the `note` and `activity`
tables with forced RLS, composite keys to their record, `ON DELETE
CASCADE` from the record (and from the note for `note_added`), payload
`CHECK`s for D5, a backfill of one `created` entry per existing record
(D7), and the runtime role without UPDATE on `activity` (D6). Both tables
are in `PURGE_TABLES` and the guard lists; the guard now requires UPDATE to
be absent on append-only tables.

- Tests (disposable `crm_app_test`): visibility only inside the own
  workspace; no writes into another workspace; the runtime role cannot
  UPDATE or TRUNCATE `activity`; cross-workspace record and note references
  refused with RLS bypassed; note text and payload rules; cascades from a
  deleted note and record, also as the runtime role; the real operator
  purge removes all four tables for that workspace only; the backfill and
  rollback from 0003 to 0002 and back.
- Results: unit 185 passed; integration 177 passed.
- No application route uses the tables yet (3B.2 and 3B.3).

### 3B.2 record history (2026-10-24)

- Every contact and company change now writes its history in the same
  transaction as the change and its audit entry (`crm_app.records`):
  `created`; `updated` with the names of the plain fields;
  `stage_changed`, `owner_changed`, `company_linked`/`company_unlinked`;
  `archived`, `restored`; and `company_unlinked` on each contact a deleted
  company unlinks. A no-op update writes nothing; a refused change writes
  nothing.
- `GET /contacts/{id}/activity` and `GET /companies/{id}/activity`
  (`activity:read`, every role): newest first, keyset cursor bound to the
  record, `limit` 1-100. Company links show the company's current name, or
  none once it is deleted.
- Tests: `test_history.py` (the full sequence of changes and their
  payloads, no field values in responses, a refused change, company
  changes, a deleted company, paging, cursor and parameter checks, every
  role reads, outsiders and other workspaces get 404); the route-policy
  table. Unit 185 passed; integration 186 passed (177 in the full run plus
  the 9 history tests, which failed there on a result-to-dict bug, fixed and
  re-run).

### 3B.3 note routes (2026-10-24)

- `crm_app.notes` and `crm_app.api.notes`: list and add notes on a contact
  or company (`activity:read`, `activity:create`); edit (`If-Match`) and
  permanently delete a note (`PATCH`/`DELETE /notes/{id}`, declared with
  `activity:create`). The service allows the author, or a caller holding
  `activity:update`/`activity:delete` read with SaaS-OS `can()` (D3); others
  get 403 `not_note_author`. Each note carries `can_edit`/`can_delete` for
  the caller; `/access` reports `create_note`, `edit_any_note`,
  `delete_any_note`.
- Text: plain text normalised once (`domains.records.note_body`: LF line
  breaks, trimmed, 1-10,000 characters, no control characters other than
  tab and LF), mirrored by the database `CHECK`; refusals never echo it.
- Adding locks the record, so a note is never added to a record archived
  or deleted meanwhile; editing locks the record for the archived check
  (D8). Adding a note leaves the record's version unchanged. `POST`
  accepts an `Idempotency-Key` scoped to the acting member.
- Every change writes its history (`note_added`, `note_deleted`) and its
  audit entry (`crm_app.note.created`/`.updated`/`.deleted`, metadata
  `record_type` and `record_id` only) in the same transaction. Deleting a
  note removes its text and its `note_added` entry (D4).
- Tests: `test_note_routes.py` (who may add, read, edit and delete;
  per-caller rights; concurrent edits; text rules and storage; history
  excerpts and deleted text; archived records; idempotency including a
  concurrent pair; other workspaces; paging; record deletion; audit
  metadata without text) and unit tests for the text rules and their match
  with migration 0003. The note probe raises the per-route rate limit for
  its own process only, as the list test does. Unit 198 passed;
  integration 198 passed.
- Not tested directly: a member moved to Read-only cannot change their own
  older notes; this follows from the routes requiring `activity:create`
  (route-policy test) and `_rights` returning none without it.

### 3B.4 drawer notes and activity (2026-10-24)

- `frontend/src/api/notes.ts` (queries and mutations; note keys under the
  record's key, so record changes also refresh its history) and
  `frontend/src/records/NotesSection.tsx` (Notes and Activity sections),
  used by the contact and company drawers. The "not available yet" lines
  no longer mention notes and activity. Design comparison:
  `DESIGN-FIDELITY.md` §4d.
- Note text is rendered as React text with `white-space: pre-wrap`; no
  HTML is ever inserted. Controls follow the API's per-note
  `can_edit`/`can_delete` and `/access` `create_note`.
- Tests: `notes.test.tsx`, 8 tests including an axe scan. Frontend 51
  passed; typecheck, lint and build pass.

### 3B.5 review, performance and browser check (2026-10-24)

Slice 3B is complete; details and accepted limitations in
`PHASE3-PLAN.md` §21.4.

- Security review (read-only, independent): no critical or high finding.
  Fixed: edit responses built in the writing transaction; record-then-note
  lock order for note edits and deletes. Accepted with reasons: no
  per-record note cap (route rate limit exists; Phase 13), a same-instant
  create/delete 404, SaaS-OS's unsalted idempotency fingerprint, history
  fields readable with `activity:read`.
- Performance on the local disposable test database (105,000 notes,
  110,000 history entries): every first page p95 at most 29 ms, twenty
  pages deep at most 26 ms; rows removed afterwards.
- Browser check in Chrome (desktop width, local ZITADEL sign-in) after
  migrating the local development database to 0003 (backfill: one
  `created` entry per existing record). Found and fixed: Edit now moves
  focus into the text and back; a changed edit now also asks before the
  drawer closes. The local test notes were deleted afterwards.
- Phase 2 remains open: invitations and the email provider, workspace
  settings and the directory, the ZITADEL sign-in test run, and the
  owner's review of `PHASE2-SECURITY-REVIEW.md`.

### Phase 2 completion: decisions and first increment (2026-10-24)

- Priority changed by the owner: complete Phase 2 before Phase 3C or other
  Phase 3 work. Baseline verified: `main` = `origin/main` = `3e7110d`,
  clean; CI green on the last three commits; SaaS-OS v0.5.0.
- Decision P2-F (`DECISIONS.md`): tables `invitation_intent` and
  `workspace_settings` approved; the directory is built without a table;
  Phase 2 closes on Q4's manual-link invitations (Mailpit locally, fake
  provider in tests, production provider before launch); security-review
  items L4, L5, I1 accepted for Phase 13 and the I2 policy points decided.
- Fixed: `/access` answered 500 when a membership was removed between the
  permission check and the handler; it now gives the same 404 as for any
  non-member (`tests/unit/test_access.py`).
- `PHASE2-SECURITY-REVIEW.md` now records the owner's review: no finding
  remains open.
- The local CRM containers (database, Redis, edge, ZITADEL) stopped during
  this session, apparently under memory pressure; local integration tests
  and the ZITADEL test wait for them. CI runs the integration suite.

### Phase 2: workspace directory (2026-10-24, decision P2-F 2)

- `GET /v1/workspaces` (`crm_app.directory`, `crm_app.api.workspaces`):
  the signed-in person's workspaces, by name, ID and name only. No table:
  it reads the open workspaces from SaaS-OS and keeps those where the
  person holds an ACTIVE membership and that still admit members; the
  SaaS-OS platform tenant is left out. The route needs only a signed-in
  person (SaaS-OS `authenticated` policy, the one such product route,
  pinned by `tests/unit/test_routes.py`) and is rate-limited per person
  (`saas_os.infra.ratelimit`, now on the import allow-list as a public
  package). Listing grants nothing: each workspace is still authorized on
  its own.
- Frontend: the start page lists "Your workspaces" as links (with an empty
  state) above "Open by ID"; the header's workspace menu lists the other
  workspaces and switches to the chosen one.
- Tests: `tests/integration/test_directory.py` (active memberships only;
  suspended, revoked and closed workspaces and strangers' workspaces are
  left out; an outsider gets an empty list and no session gets 401; listing
  grants nothing: suspended and revoked 403, closed and foreign 404);
  unit route-policy test; frontend `HomePage.test.tsx` (list, links, empty
  state, axe) and `AppFrame.test.tsx` (switching). Unit 200 passed;
  frontend 56 passed. The local services were stopped, so the integration
  tests ran in CI only.

### Phase 2: workspace settings (2026-10-24, decision P2-F 1)

- Migration `0004_workspace_settings`: one row per workspace (`tenant_id`
  primary key) with locale (BCP 47), time zone (IANA) and default currency
  (ISO 4217), shape `CHECK`s, forced RLS, CRUD grants, and a
  `PURGE_TABLES` entry. No row means the defaults: `en`,
  `Europe/Amsterdam`, `EUR` (first market, K5). Times stay stored in UTC.
- `GET /v1/workspaces/{id}/settings` (`crm_app.workspace:read`, every role)
  and `PATCH` (`crm_app.workspace:update`, Owner and Admin) with
  `If-Match` (version 0 before the first save; two first saves at once
  leave one winner and a 409 for the other). Values are validated against
  the full IANA and ISO 4217 lists and normalised
  (`crm_app.domains.settings`); refusals never echo them. Each save is
  audited (`crm_app.workspace_settings.updated`, field names only).
  `/access` reports `update_workspace`.
- Frontend: Settings › Business profile (the design's card): workspace
  name shown read-only (SaaS-OS has no rename), language and region, time
  zone and default currency with a live example, Save with the version,
  the stale-version message with "Load the latest", and read-only for
  Members and Read-only members. The design's phone, email, website,
  address and hours are named as not available.
- Tests: unit (`test_settings_values.py`: normalisation, refusals without
  echo, defaults, and the stored forms matching the migration's patterns;
  route policies), integration (`test_workspace_settings.py`: defaults,
  role matrix, normalisation, versions and the first-save race, refusals,
  other workspaces, audit metadata, runtime-role RLS, table `CHECK`s), and
  frontend (`BusinessSettings.test.tsx`, with an axe scan). Unit 217 and
  frontend 60 passed locally; the integration tests run in CI while the
  local services are stopped.

### Phase 2: invitations (2026-10-24, decisions Q4, Q5, P2-F)

- Migration `0005_invitation_intent`: per invitation the intended role, the
  inviter and the delivery (`manual` or `email`); no token, link or
  address. Forced RLS, CRUD grants, `PURGE_TABLES` entry.
- `crm_app.invitations` and `crm_app.api.invitations`: list (`invitation:
  read`), create (`invitation:create`, rate-limited per inviter, at most
  100 pending per workspace, inviting an Owner needs `crm_app.owner:manage`)
  and revoke (`invitation:revoke`); Owner and Admin hold all three. SaaS-OS
  creates the invitation (hashed token, 7-day expiry, one pending per
  address). Delivery by `INVITATION_DELIVERY` (validated at start-up):
  `manual` (default, Q4) returns the link once, labelled not sent; `email`
  sends it through SaaS-OS `send_email` and, if the provider refuses,
  revokes the invitation and answers 502 `delivery_failed`. The link is
  `/app/invite/<workspace>#<token>`; the token is never stored, logged,
  audited or listed. `crm_app.invitation.intent_recorded` is audited with
  the role and delivery.
- Acceptance is SaaS-OS's route, now mounted:
  `POST /v1/tenants/{id}/invitations/accept` (signed in, verified email
  equal to the invited one, once; one 404 for every refusal). The new
  member has no role (Q5) and appears as "Awaiting role" with "Give <role>
  role", which uses the existing role route and its Owner rules.
- Frontend: Invite dialog (Admins cannot pick Owner), the link dialog
  ("Not sent — deliver it yourself", copy button, shown once), the
  Invitations card with Revoke, members shown by their invited address,
  and the acceptance page `/app/invite/<workspace>`: the token is taken
  from the fragment, removed from the address bar, kept only in this tab's
  sessionStorage across sign-in, and forgotten once used; the start page
  offers to continue a waiting invitation.
- Local development: `INVITATION_DELIVERY`, `EMAIL_PROVIDER`,
  `MAILPIT_SMTP_HOST` and `EMAIL_DEFAULT_SENDER` documented in
  `.env.example`; an opt-in Mailpit service (`--profile mail`, the same
  pinned image SaaS-OS uses) catches invitation emails.
- Tests: unit (settings for delivery, route policies), integration
  (`test_invitations.py`: role matrix, the Owner rule, manual links,
  validation and duplicates, acceptance bound to the verified email and
  used once, awaiting role and Admin confirmation, revocation, email mode
  with SaaS-OS's `FakeEmailProvider` including a failed send that revokes,
  no token in logs, listings, audit or the intent table, runtime-role RLS
  and table `CHECK`s), frontend (`Invitations.test.tsx`,
  `InvitePage.test.tsx`, with axe scans). Unit 220 and frontend 70 passed
  locally; the integration tests run in CI while the local services are
  stopped.
- Not done: removing intent rows of long-expired invitations (they hold
  IDs and a role only and go with the workspace's purge); a per-workspace
  cleanup can follow.

### Phase 2: review of the completion work (2026-10-24)

Independent read-only review of the directory, settings and invitations:
no critical or high finding (`PHASE2-SECURITY-REVIEW.md`, "Review of the
Phase 2 completion work"). Fixed: the pending cap now holds under
concurrency (per-workspace advisory lock; new integration test); the
intent is recorded before an email is sent and a failed clean-up is
logged without secrets; the Owner rule moved into the service; a waiting
invitation is also forgotten on sign-out. Accepted with reasons: the two
transactions behind an invitation, the provider seeing emailed tokens
(production TLS is enforced by SaaS-OS), and the directory's per-workspace
reads.
