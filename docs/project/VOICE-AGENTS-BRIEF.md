# AI voice agents: decision brief and roadmap proposal

**Status:** direction **approved** by the owner on 2026-11-03 (decision P15-V,
with eight points; §11). AI voice agents, inbound and outbound, are a
planned post-launch LeadStack capability (workstream 15V). **This is not
authorisation to build.** Decision K5 (the MVP scope) is unchanged, and voice
stays deferred until the owner explicitly approves a scope change. Nothing
here purchases a service, creates a provider account, configures a phone
number, enables a call, changes SaaS-OS or moves its pin.

Recorded as decision P15-V (`DECISIONS.md`) and brief 9
(`DECISION-BRIEFS.md`); roadmap workstream 15V (`ROADMAP.md`, Phase 15).

---

## 1. Correction

On 2026-11-03 the owner was told that AI call agents were "not a planned
part of the roadmap". That was wrong in substance. The product vision
(`ROADMAP.md` §1) combines the reference LeadStack/AgentStack template and
GoHighLevel, and both have AI voice agents. The error came from Phase 0:
`PHASE0-DISCOVERY.md` §2 listed the reference template's features without
its voice module (now corrected there). The roadmap named voice only as a
"potential channel" (6.2) and a "potential later feature" (Phase 15), with
no workstream. This brief gives it one.

## 2. The decision asked of the owner

1. **Direction (asked now):** record AI voice agents, inbound and outbound,
   as an intended LeadStack capability with its own workstream (15V),
   sequenced after launch, outside the K5 MVP. *Recommended: yes.*
2. **Later decisions (not asked now; listed in §11):** the scope change that
   would bring voice into a release, the voice platform and telephony
   providers, the legal review and DPIA, prices and plan limits, and the
   SaaS-OS capabilities it needs.

## 3. What the references do (feature ideas only)

### 3.1 Reference template (`leadstack-crm-main.zip`; K1: ideas only, PolyForm Perimeter noncompete; no code, schema, text or asset reused)

Read from the archive in place, never run:

- **Inbound agent** on a hosted voice platform (Vapi) that does speech
  recognition, speech synthesis and turn-taking, and calls the product's own
  LLM endpoint each turn, so voice shares the workspace's persona, knowledge
  base, hours and escalation rules with chat and SMS. Configurable:
  greeting, voice (fixed list), maximum call length, model, escalation
  keywords and e-mail, number mode (the tenant's own Twilio number, or a
  platform number).
- **Outbound:** click-to-call from a contact with a consent checkbox; bulk
  campaigns by tag, pipeline stage or everyone, with suppression of recently
  called contacts, one queued step per recipient at a per-minute pace,
  rescheduling outside calling hours, cancel (queued only, or also hang up
  live calls), and a test call.
- **After the call:** a provider-side summary and extracted fields (name,
  e-mail, callback wanted, interest), contact match or create, follow-up
  tasks, a missed-call text-back workflow, per-recipient campaign outcomes
  (interested, not interested, callback, no answer, voicemail, failed), a
  call list and detail page with the transcript.
- **Compliance gate:** valid number, opt-out flag, consent flag plus operator
  acknowledgement, country allow-list, calling window in the contact's local
  time, daily and per-number caps, a pluggable (empty) do-not-call scrub.
- **What it lacks, and LeadStack must not repeat:** no AI disclosure line;
  no in-call "stop calling me" handling (nothing ever sets the opt-out
  flag); the scrub and the cap check fail open; test calls bypass every
  check; recordings are not kept; calls are not in the inbox or linked to
  deals; no per-minute metering; no transfer to a human; no booking during
  the call. Security: one webhook secret shared by all tenants, sent in the
  URL, with the tenant taken from the URL path; call metadata (contact and
  campaign ids) trusted without a tenant check; non-idempotent post-call
  side effects; a campaign step that can dial twice; tenant telephony
  credentials handed to the voice platform.

### 3.2 GoHighLevel Voice AI (official help centre, checked 2026-11-03)

- **Agents:** a prompt, welcome message, voice, model and language, a
  prompt optimiser, multiple languages, a knowledge base the prompt
  searches, working hours, a number or number pool (LC Phone or Twilio
  only).
- **In-call actions:** transfer to a person or number, book into a calendar,
  a custom action (real-time webhook), trigger a workflow, update contact
  fields, send SMS; contacts and opportunities created or updated.
- **Outbound:** only from a workflow action: 10 calls a minute and 5,000 a
  day per location, a number at most once a day and 14 times in 14 days,
  08:00–20:00 in the contact's time zone, same-country numbers only.
- **After the call:** call logs with summary, transcript and recording, the
  summary optionally copied to contact notes, a dashboard (calls, actions,
  transfers, bookings, a "directional" sentiment), public APIs and webhooks.
- **Pricing (their model, for reference):** per minute, a voice engine
  ($0.045) plus speech synthesis ($0.015 to $0.17 depending on the voice)
  plus LLM tokens plus telephony; agencies resell with a markup or a fixed
  per-minute rate per sub-account.
- **Compliance:** consent is left to the business (platform consent checks
  were removed in June 2026); the platform enforces identity verification,
  do-not-disturb, the calling window, frequency caps, an AI disclosure
  (three styles) and an optional recording notice. No EU-specific guidance
  was found.

### 3.3 What LeadStack takes from them

Shared configuration across chat and voice; knowledge-grounded answers;
transfer to a person; booking into calendars; workflow triggers; call logs
with transcript, summary and outcome; outbound by single call, workflow and
campaign with pacing, windows and frequency caps; per-minute metering and
agency resale. **And, unlike both:** consent proven before any outbound AI
call, a mandatory AI disclosure, in-call opt-out that takes effect at once,
human review of outcomes before they change the CRM, fail-closed checks,
per-tenant webhook credentials, and EU data residency.

## 4. Capability scope (the full intended set, delivered in stages, §10)

1. **Agent configuration:** name, purpose (reception, qualification,
   booking, follow-up), instructions, greeting, language(s), a voice chosen
   from a vetted list (no cloning of real people in the first releases),
   business hours and after-hours behaviour, maximum call length, the
   knowledge sources it may use, the actions it may take, transfer targets,
   and a versioned draft, test and active lifecycle like automations.
2. **Business knowledge:** the Phase 9 knowledge sources, retrieved per
   workspace only, treated as untrusted text.
3. **Inbound calls:** the agent answers a workspace number (always, after
   hours, or after no person answers), treats the caller's number only as a
   *claim* (caller ID can be spoofed; the P7-V rule), answers, qualifies,
   books, takes a message, or transfers.
4. **Outbound calls:** one contact from the record; from an automation
   action; and bulk voice campaigns with an audience, pacing, windows, caps
   and per-campaign approval like e-mail campaigns.
5. **Call transfers:** warm or cold transfer to a member's or the business's
   number, with a spoken handover; a fallback message if nobody answers.
6. **Transcripts and summaries:** a turn-by-turn transcript where permitted,
   a generated summary, and extracted fields. **No call recording** until an
   approved recording policy and legal review exist (P15-V point 7).
7. **Call outcomes:** a fixed list (answered by a person, voicemail, no
   answer, busy, failed, transferred, booked, qualified, not interested,
   callback requested, opted out), set by rules and the model, and
   confirmed or corrected by a person where it changes CRM data.
8. **Human review:** a review queue. Proposed contact updates, deal stage
   moves and tasks from a call wait for a member's approval unless the
   workspace explicitly allows automatic application for a given field;
   flagged calls (complaint, opt-out, low confidence, failed disclosure) are
   always queued.
9. **Usage limits and metering:** minutes, calls and campaign size per plan;
   hard stops; per-workspace and per-agency budgets; usage visible in
   reporting and billing.

## 5. Integration with the product

| Area | Integration |
| --- | --- |
| Contacts and companies | A call is linked to a contact (matched by number as an unverified claim, or created only for a new caller); the company through the contact; call history on the record; voice consent and opt-out on the contact |
| Deals and pipelines | Calls linked to a deal; proposed stage moves and values through the review queue; "deal stage changed" can trigger an outbound follow-up call |
| Appointments and calendars | The agent offers times from the existing availability rules (5B, 5C) and books through the same service as public booking, with the same limits; reminder calls later, after e-mail reminders |
| Conversations | Each call is a conversation message of channel `voice` (6C model), with transcript and summary, so the inbox shows calls beside e-mail; internal notes and assignment unchanged |
| Automations | Triggers: call completed, call outcome, missed call, opted out; actions: place an AI call (subject to every outbound check), add a task, tag; the loop and duplicate safeguards of 8A and 8B apply |
| Knowledge bases | Phase 9 sources, per workspace, with retrieval logged per call |
| Reporting and usage | Calls, minutes, outcomes, bookings, transfers, opt-outs, cost per workspace and per agent; CSV export (10B); usage events through SaaS-OS `core.usage`; plan limits through `core.billing` entitlements |

## 6. Technical architecture

### 6.1 What SaaS-OS v0.6.0 provides, and what it does not (verified in the pinned package)

| Need | v0.6.0 | Consequence |
| --- | --- | --- |
| Governed LLM call | `saas_os.inference.run_inference`, non-streaming | Usable for one turn at a time, with full governance |
| Streaming LLM | `stream_inference` refuses every request (`streaming_not_enabled`) | Low-latency streamed replies need a SaaS-OS release |
| Audio (speech recognition, speech synthesis, realtime) | None | Must come from a voice platform behind a product adapter, or a future SaaS-OS capability |
| Outbound HTTP | `StrictEgressClient.post` only | Placing calls is POST (fine); fetching recordings and transcripts usually needs GET (`SAAS-OS-GET-PROPOSAL.md`) |
| Outbound WebSocket (media streams) | None | A LeadStack-run audio pipeline is not possible today |
| Inbound webhooks | Signature and replay primitives in `core.webhooks`; the product owns its receiver (as for Resend) | Product-side receivers with per-tenant verification |
| Usage and quotas | `core.usage` events, `consume_quota`, `get_entitlements` | Minutes and calls metered without a parallel billing system |
| Secrets | `infra.secrets` | Provider keys by reference, never in the database or the frontend |
| Jobs, outbox, rate limits, feature flags | Present | Campaign pacing, post-call processing, kill switches |
| Object storage (recordings) | Not in the public surface | Recordings stay at the provider, or need a storage decision |

### 6.2 Options for the real-time path

- **A. Hosted voice platform, LeadStack as the brain (recommended first).**
  A voice platform (examples: Vapi, Retell, or a telephony provider's own
  conversational product) handles the phone line, speech recognition,
  turn-taking, interruptions and speech synthesis. For each turn it calls a
  LeadStack endpoint, which builds the prompt from the workspace's agent,
  contact context (where verified) and knowledge, and calls
  `run_inference`. In-call actions (book, transfer, take a message) are
  LeadStack tools behind the same endpoint. The LLM call stays inside
  SaaS-OS governance (authority, data classification, admission, usage).
  *Cost:* platform per-minute fee plus speech synthesis plus LLM plus
  telephony. *Risk:* without streaming, each turn waits for a full reply
  (latency to be measured), so replies must be short; audio and transcripts
  pass through the platform (a processor agreement and EU hosting needed).
- **B. Hosted platform with its own LLM.** Lowest latency and least work,
  but customer data reaches an LLM outside SaaS-OS governance, which the
  architecture forbids without an explicit data-authorisation decision.
  *Not recommended.*
- **C. LeadStack-run media pipeline.** The telephony provider streams audio
  to a LeadStack voice gateway, which runs streaming speech recognition, the
  LLM and speech synthesis through adapters. Full control and EU residency,
  but it needs SaaS-OS streaming inference, outbound WebSocket egress and a
  latency-critical service, and much more operational work. *A later
  option* if cost, residency or quality justify it.

### 6.3 Components (option A)

- **`crm_app.voice` domain** (product-owned, like campaigns): agents and
  versions, numbers, calls, call events, transcript segments, campaigns and
  recipients, review items, voice consent and suppression; PostgreSQL with
  forced RLS, versioned migrations, append-only event and transcript tables.
- **Provider adapters** behind protocols (`VoicePlatform`, `Telephony`), as
  for e-mail: place a call, end a call, configure an agent, provision a
  number, verify a webhook. One implementation per approved provider plus a
  test double; no provider SDK outside the adapter.
- **Turn endpoint:** authenticated per tenant (§6.4); a hard deadline, then
  a spoken fallback line and a callback task; short replies (a token cap);
  tools limited to the agent's allowed actions, each re-authorised
  server-side.
- **Event receivers** (call status, end of call, recording ready): verified,
  stored first, processed by a job (the inbound-email pattern, P6-I), at
  most once per provider event id.
- **Jobs:** campaign stepping (one recipient at a time, a row lock,
  re-checking every outbound rule immediately before dialling), post-call
  processing (summary, extraction, review items, automations), the
  retention purge, usage reconciliation against the provider's billing.
- **Frontend:** agent editor with a test console, number settings, call log
  and detail (transcript where permitted, summary, outcome; no recording
  player until a recording policy is approved), review queue, campaign editor and approval, usage page; every
  control disabled with a reason while voice is off.

### 6.4 Security and tenant isolation

- The workspace is derived server-side from the provider's call, agent or
  number id through a LeadStack mapping table, **never** from a URL path, a
  query string or call metadata.
- Each workspace (or provider sub-account) has its own webhook secret, sent
  in a header, verified in constant time with replay protection (the
  `core.webhooks` primitives); no URL carries a secret.
- Provider credentials per agency or workspace through `infra.secrets`;
  tenant telephony credentials never handed to another provider.
- Contact context reaches the model only when the caller is verified (an
  outbound call LeadStack placed, or a verified callback); an inbound caller
  ID alone unlocks no CRM data beyond what the business publishes.
- Tools are re-authorised per call against the agent's allowed actions and
  the workspace's permissions; no tool can read another contact's record,
  export data, or change settings.
- Prompts, transcripts, knowledge and caller speech are untrusted input (the
  Phase 9.4 prompt-injection defences); the model never sees secrets.
- Proposed permissions: `voice_agent:read`, `voice_agent:manage` and
  `voice_number:manage` (administrative), `voice_call:read`,
  `voice_call:place`, `voice_recording:read` (restricted),
  `voice_campaign:manage`, `voice_campaign:approve` (administrative),
  `voice_review:decide`.
- Test calls only to numbers the member has verified (a code sent first),
  counted against usage and audited; no check is bypassed.
- Logs carry ids, codes and durations, never transcripts, full numbers or
  audio.

### 6.5 Reliability

- Idempotency on every provider event (a unique provider event id) and on
  every side effect (one task, one review item, one automation run per call
  and kind).
- Campaign dials under a row lock, with a "dialled" state set before the
  provider call; a provider timeout is reconciled by status, never retried
  blindly (a second dial is worse than a missed one).
- Fail closed: if consent, suppression, caps or the window cannot be
  checked, the call is not placed.
- A deadline on every turn and a spoken fallback; provider outages pause
  campaigns and alert operators; the health check (13-O1) gains the voice
  queues.
- Kill switches per workspace, per agency and platform-wide (a feature
  flag), stopping new calls within a minute.

### 6.6 Cost controls

- Per-plan entitlements (minutes a month, concurrent calls, campaign size)
  with `consume_quota` before each call and hard stops; a maximum call
  length; daily spend caps per workspace and per agency.
- Short replies and a token cap per turn; one summary per call.
- Stock voices first (premium voices cost up to about ten times more,
  judging by GoHighLevel's rates); premium voices as a plan option later.
- Usage reconciled daily against the provider's own billing; a mismatch
  alerts operators.
- Agency resale (markup or fixed rate) belongs to Phase 11 billing, not to
  the voice module.

## 7. EU and Dutch requirements (summary of sources; legal review required before any release)

A research summary, not legal advice; dated 2026-11-03.

| Topic | Requirement | Status | LeadStack control |
| --- | --- | --- | --- |
| AI disclosure | AI Act Art. 50(1): people talking to an AI must be told, unless obvious; LeadStack is likely the *provider*, the business the *deployer*; information at the first interaction (50(5)) | Applies from 2 Aug 2026 (in force) | A fixed disclosure in every greeting that the business cannot remove; recorded as spoken in the call events |
| Synthetic audio marking | Art. 50(2): machine-readable marking of synthetic audio; reportedly 2 Dec 2026 for systems already on the market before 2 Aug 2026 (Digital Omnibus, Regulation 2026/1744), immediately for new ones | In force for new systems (the Omnibus text was not read directly) | Speech providers that mark their output; confirm with counsel |
| Imitated real voices | Art. 50(4) deepfake disclosure; GDPR biometric data | In force | No voice cloning in the first releases |
| Manipulation | AI Act Art. 5 bans manipulative or deceptive techniques (since 2 Feb 2025); the Unfair Commercial Practices Directive bans persistent unwanted calls and hidden commercial intent | In force | Agent instructions bounded by product rules; complaints and opt-outs flagged for review |
| Automated calls | ePrivacy Art. 13(1); Telecommunicatiewet 11.7(1): automated calling systems need prior consent the sender **can prove**, for all end-users, businesses included | In force | Cautious reading: an AI agent counts as automated, so **no outbound AI call without recorded, provable consent to AI calls**, business or consumer |
| Telemarketing to people | Tw 11.7(2): consent for calls to natural persons (sole traders included); a free, easy way to object offered on every call; no existing-customer exception for calls since 1 July 2021 | In force | Consent with method, wording and time (the P7-B model, channel `voice`); in-call opt-out recorded at once |
| Business numbers | Tw 11.7(3): without consent, only numbers a business published for this purpose; the Bel-me-niet register has had no legal basis since 2021 | In force | Not usable for AI calls under the cautious reading above |
| Caller ID | Tw 11.7(8): never withheld | In force | Calls only from a verified number shown to the callee |
| Fines | ACM up to €900,000 or 1% of turnover; AI Act Art. 50 breaches up to €15M or 3% | In force | Per-campaign approval, audit trail, consent evidence export |
| Calling hours | No statutory hours found; the Dutch telemarketing code (Code Telemarketing 2024) is self-regulation (not read in full) | Self-regulation | Default set after reading the code (proposal: weekdays 09:00–20:00 local time, no Sundays or public holidays), never widened beyond it |
| Recording | Criminal law: a participant may record (Sr 139a, 139c). GDPR (AP guidance): a legal basis, and the caller told **at the start of the call** that it is recorded and why; access on request | In force | **No recording** (P15-V point 7) until an approved policy and legal review; then a spoken notice before recording starts and export per contact |
| Privacy | GDPR: voice is personal data, biometric only when used to identify someone; a DPIA (the AP's list covers communications data and behavioural observation); processor agreements with each provider; minimisation; the absolute right to object to direct marketing (Art. 21) | In force | DPIA before any pilot; processor agreements; no speaker identification; an objection stops all voice marketing |
| Transfers | EU-US Data Privacy Framework in force; appeal C-703/25 P pending | In force, at risk | Prefer EU-hosted speech and model processing; a fallback if the framework falls |
| Telecom status | Offering numbers to the public as LeadStack's own service may require ACM registration and 112 duties (EECC Art. 109) | In force | Numbers come from a licensed provider under the business's or agency's own account; LeadStack does not become a telecom provider |
| Retention | No fixed period; storage limitation (GDPR Art. 5(1)(e)) | In force | Documented separately for each kind of data in `VOICE-LEGAL-REVIEW.md` §3: no recordings; transcripts, summaries and metadata on their own periods |

Open legal questions for counsel: whether a conversational AI agent is an
"automated calling system" (the cautious reading is assumed above); the
final Omnibus text on Art. 50(2); the Code Telemarketing details; consent
wording valid for AI calls; and the provider and deployer split for
disclosure and marking.

## 8. Alternatives for the overall decision

1. **Record the direction and the workstream now; build after launch
   (recommended).** No cost now; legal and provider research can start; K5
   intact.
2. **Bring an inbound-only pilot forward, before launch.** Earlier market
   value, but it widens the MVP, needs a provider contract, a DPIA and the
   SaaS-OS asks first, and delays launch work.
3. **Leave voice to an external product connected through the API platform
   (Phase 12).** Least work, but no shared CRM context, review queue or
   compliance controls, which are the point.

## 9. Cost, security and reversibility of the recommendation

- **Cost now:** none. Later: provider fees per minute (GoHighLevel's public
  rates suggest roughly $0.07 to $0.25 a minute all-in before telephony;
  LeadStack's own costs are unknown until providers are chosen), a legal
  review and DPIA, and the engineering of about six slices (§10).
- **Security:** a new public surface (the turn endpoint and event
  receivers) and new personal data (audio, transcripts); mitigated by §6.4
  and §7.
- **Reversibility:** high until a release, since nothing is built. After a
  release, kill switches stop calls at once and data follows the retention
  rules.

## 10. Roadmap proposal: workstream 15V (after launch, outside K5)

Each slice keeps the Definition of Done, negative authorisation tests and
the usual gates. No slice places a real call before slice V4's approval.

| Slice | Scope | Depends on | Exit criteria |
| --- | --- | --- | --- |
| V0 Decisions | Scope change from K5; provider choice; legal review and DPIA; plan limits and prices; SaaS-OS requests filed (streaming inference, GET egress, optionally audio) | Owner | Decisions recorded; DPIA signed off; processor agreements identified |
| V1 Foundation | `crm_app.voice` schema (agents, versions, numbers, calls, events, transcripts, review items, voice consent and suppression), permissions, agent editor, call log, all behind a feature flag, no provider | V0; Phase 9 knowledge | Migrations, RLS and cross-tenant tests pass; the UI shows "voice is off" states; no network call is possible |
| V2 Inbound (sandbox) | Provider adapter, turn endpoint, event receivers, disclosure, knowledge answers, take a message, transfer; test numbers only | V1; a provider sandbox account (owner) | Simulated and sandbox calls; the disclosure is always spoken; forged webhooks rejected; turn latency measured against a target |
| V3 After the call | Transcript, summary, outcomes, review queue, links to contact, deal, conversation and appointment; automation triggers; booking during the call | V2 | Every side effect idempotent under replayed events; nothing changes CRM data without review unless allowed |
| V4 Outbound, single | One call from a contact or an automation; consent proof, opt-out, window, caps, caller ID, kill switch; verified test numbers | V3; legal sign-off | Every check fails closed; a call without consent is impossible (tested); an in-call opt-out suppresses at once |
| V5 Campaigns | Audience, pacing, per-campaign approval, cancel, outcomes, reporting | V4 | No double dial under duplicate jobs; approval required; plan caps enforced |
| V6 Metering and launch | Usage events, entitlements, budgets, reconciliation, reporting and CSV, operator alerts, the health check, a launch review | V5; Phase 11 billing for resale | Usage matches provider billing in a reconciliation test; production enablement only by the owner |

## 11. Owner decisions (P15-V, 2026-11-03)

| # | Decision | Outcome | Follow-up |
| --- | --- | --- | --- |
| 1 | Voice direction | **Approved**: Phase 15V stays as a planned post-launch capability | Not reopened |
| 2 | MVP scope K5 | **Unchanged**: voice outside the MVP | Only an explicit owner decision changes it |
| 3 | Providers | **Deferred** | `VOICE-PROVIDER-COMPARISON.md`; no accounts, no purchases |
| 4 | Legal review | **Required** before production implementation or activation | `VOICE-LEGAL-REVIEW.md` (DPIA requirements, questions for counsel); §7 is not a final legal determination |
| 5 | Pricing and plan limits | Cost model only, no commercial prices | `VOICE-COST-MODEL.md` |
| 6 | SaaS-OS | Proposal only; no SaaS-OS, release or pin change | `SAAS-OS-REALTIME-PROPOSAL.md` |
| 7 | Recording and retention | **No recording** as the design default until an approved policy and legal review; transcript and metadata retention documented separately | `VOICE-LEGAL-REVIEW.md` §3 |
| 8 | Outbound consent | **Explicit, demonstrable consent** for AI outbound calls as the initial policy; no outbound calling until the legal interpretation and operational controls are reviewed | Slices V4 and V5 wait for that review |

Also required by the owner for both directions: human handoff, selectable
voices, agent configuration, call summaries, transcripts where permitted,
outcome classification, usage metering, tenant isolation, campaign approval,
opt-outs, rate limits, budget limits and emergency stop controls
(`VOICE-THREAT-MODEL.md` §6 for the emergency stop).

### Original list of decisions (kept for the record)

1. Approve the direction and workstream 15V (this brief).
2. When, if ever, to change K5 to bring a voice slice into a release.
3. The voice platform and telephony providers, and who holds the accounts
   (LeadStack, the agency, or the business).
4. Commissioning a legal review and DPIA (cost).
5. Plan limits, prices and agency resale.
6. Whether to ask SaaS-OS for streaming inference (and audio), alongside
   the GET egress change already proposed.
7. The recording policy and retention periods.
8. Whether outbound AI calls are offered at all, or only to contacts with
   explicit consent to AI calls (the cautious default above).

## 12. Sources

- Reference template: `leadstack-crm-main.zip` (read in place, 2026-11-03).
- GoHighLevel: help.gohighlevel.com articles 155000004107, 155000003911,
  155000006598, 155000006679, 155000006680, 155000005900, 155000004693,
  155000006379, 155000006652, 155000008422, 155000003906, 155000008039;
  the ideas.gohighlevel.com changelog entries "Voice AI outbound calling"
  and "Voice pricing updates effective October 13, 2026".
- Law: AI Act Art. 50 (ai-act-service-desk.ec.europa.eu/en/ai-act/article-50);
  Regulation 2026/1744 (data.europa.eu/eli/reg/2026/1744/oj, not read
  directly); Telecommunicatiewet (wetten.overheid.nl/BWBR0009950/2026-08-15);
  Wetboek van Strafrecht Art. 139a and 139c (wetten.overheid.nl/BWBR0001854);
  ACM telemarketing guidance (acm.nl); Autoriteit Persoonsgegevens on
  recording calls and its DPIA list (Stcrt. 2019, 64418); EDPB guidelines
  02/2021 on virtual voice assistants; Directive 2002/58/EC; Regulation
  2016/679; Directive 2018/1972; Directive 2005/29/EC.
