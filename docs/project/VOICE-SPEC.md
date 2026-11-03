# AI voice agents: implementation-readiness specification

**Status:** specification only, 2026-11-03. Prepared under the owner's
instruction to make voice implementation-ready without building it.

Boundaries:
- Voice is approved product direction (decision P15-V) but stays outside the
  K5 MVP.
- Nothing here is built, enabled or bought.
- Recording is off by default.
- No outbound calling until the legal interpretation and operational
  controls are reviewed.

Companion documents:
- `VOICE-AGENTS-BRIEF.md`: the decision brief.
- `VOICE-UX-SPEC.md`: the screens.
- `VOICE-SLICES.md`: the slices.
- `VOICE-THREAT-MODEL.md`: the threats.
- `VOICE-LEGAL-REVIEW.md`: the legal questions.
- `VOICE-PROVIDER-COMPARISON.md`: the providers.
- `VOICE-COST-MODEL.md`: the costs.

Every statement about SaaS-OS is marked:
- **[Exists]**: verified in the pinned v0.6.0 package.
- **[Proposed]**: requested upstream and not available. #205 is GET egress;
  #206 is streaming inference and governed audio.
- **[Product]**: to be built in LeadStack.

---

# A. Product requirements

Each requirement has an id used by the slices and tests.

## A1. Inbound AI receptionist

| Id | Requirement | Acceptance |
| --- | --- | --- |
| A1.1 | An agent answers a workspace's number in one of three modes: **always**; **outside business hours** (5B hours); or **when no person answers within N seconds** (the business's own line rings first) | Mode chosen per number; calls inside the rule reach the agent, others ring through |
| A1.2 | The greeting starts with the **AI disclosure**, which the business cannot remove; the rest of the greeting is configurable | Every call's events record "disclosure spoken" before any other agent speech |
| A1.3 | The agent answers from the workspace's knowledge, business hours, services and booking pages; it says it does not know rather than guessing | Answers cite a knowledge source in the turn log; a question outside knowledge gets the configured fallback |
| A1.4 | The caller's number is an **unverified claim** (decision P7-V). A match on a contact unlocks no personal data and makes no CRM change on its own | A matched inbound call never reads out contact data |
| A1.5 | The caller can always ask for a person; the agent transfers or takes a message | "Speak to someone" triggers handoff in tests |
| A1.6 | Calls end gracefully at the maximum length or on silence | The call ends with a closing line at the limit |

## A2. Outbound AI calls to eligible contacts

| Id | Requirement | Acceptance |
| --- | --- | --- |
| A2.1 | An outbound AI call is placed only to a contact with **explicit, demonstrable consent to AI calls** (P15-V point 8) that is not suppressed, inside the calling window, under caps and budget, with no emergency stop active | The gate refuses each failing case and records the reason. It fails closed when any check cannot be read |
| A2.2 | Single calls from a contact record, by a member with `voice_call:place` | Button disabled with the reason when the gate would refuse |
| A2.3 | Calls from an automation action, subject to the same gate | An automation-triggered call to a non-consenting contact is skipped with a reason |
| A2.4 | Campaigns (A2.5–A2.7) are created by `voice_campaign:manage` and **approved** by `voice_campaign:approve` before any call | No call without approval; the approval is audited with the audience snapshot |
| A2.5 | Campaign pacing: per-minute rate, daily cap, per-number frequency cap, window | Throughput never exceeds the configured limits |
| A2.6 | Cancel: stop queued calls; optionally end live calls | Cancel takes effect within one minute |
| A2.7 | Caller ID is always a verified workspace number; never withheld | Calls without a verified number are refused |

## A3. Lead qualification

| Id | Requirement | Acceptance |
| --- | --- | --- |
| A3.1 | An agent version defines **qualification questions** (up to 10) and the fields they map to (contact fields, custom fields, deal value, deal stage) | The configured questions appear in the agent's instructions; answers are extracted after the call |
| A3.2 | Extracted answers become **proposed changes** in the review queue, never direct writes, unless a field is marked auto-apply by an administrator | A proposed change waits for review; an auto-apply field is written and audited |
| A3.3 | Qualification outcome: qualified, not qualified, needs follow-up, with a reason | The outcome is stored on the call and shown in the review queue |

## A4. Appointment booking and rescheduling

| Id | Requirement | Acceptance |
| --- | --- | --- |
| A4.1 | The agent offers times from a chosen booking page's availability (P5-C rules: business hours, conflicts, limits) | Offered times are always bookable at the moment of booking |
| A4.2 | Booking uses the same service as public booking, with the P7-V rule: a caller matched only by number is an unverified claim (the booking is kept and attached; no automations from the match) | The booking appears in the calendar; the booking-limit and conflict rules apply |
| A4.3 | Rescheduling and cancelling **only on an outbound call LeadStack placed to that contact**, or after the caller confirms a code sent to the contact's email | An inbound caller cannot move another person's appointment |
| A4.4 | Confirmation by email (when email sending is enabled) | The confirmation is queued; nothing is sent while sending is off |

## A5. Human handoff and escalation

| Id | Requirement | Acceptance |
| --- | --- | --- |
| A5.1 | Transfer targets per agent: a member's number, a team number or the business's main line; warm (announce, then connect) or cold | A transfer reaches the target, or falls back |
| A5.2 | Escalation triggers: caller asks; configured keywords (complaint, emergency, legal); low confidence two turns in a row; a tool fails twice; a complaint about the AI | Each trigger leads to transfer or message-taking |
| A5.3 | Fallback when nobody answers: take a message, create a task for the assigned owner, end politely | A task with the caller's message exists after the call |
| A5.4 | Emergency wording ("112") is never handled by the agent: it tells the caller to hang up and dial 112 | Fixed response tested |

## A6. Business knowledge

| Id | Requirement | Acceptance |
| --- | --- | --- |
| A6.1 | Each agent version selects knowledge sources from the Phase 9 knowledge module (not yet built; a dependency) | Only selected sources are retrieved |
| A6.2 | Retrieval per turn is bounded (§B7) and logged by source id | The turn log lists source ids, never the text |
| A6.3 | Knowledge text is untrusted: it can inform answers, never change the agent's rules or tools | Injection tests (§C11) pass |

## A7. Agent personalities and voices

| Id | Requirement | Acceptance |
| --- | --- | --- |
| A7.1 | Personality: tone (as in the design: warm and concise, professional, calm and clear), formality (u or je for Dutch), verbosity limit | Saved per version |
| A7.2 | Language: Dutch, English, or match the caller (the provider's language detection) | The chosen language is used from the greeting |
| A7.3 | Voice: chosen from a **vetted list** per provider and language; no cloning of real people (`VOICE-AGENTS-BRIEF.md` §4) | Only listed voices selectable |
| A7.4 | Preview: a short sample per voice (provider-generated, cached) | Plays in the editor |

## A8. After the call

| Id | Requirement | Acceptance |
| --- | --- | --- |
| A8.1 | **Summary** generated once per call | Present on every completed call |
| A8.2 | **Transcript** kept only where permitted: per workspace setting, default on for inbound, retention per `VOICE-LEGAL-REVIEW.md` §3 (90 days proposed); **no recording** | With transcripts off, only the summary and outcome remain |
| A8.3 | **Outcome** from a fixed list (§B4.3), set by rules and the model, confirmable in review | Every call has exactly one outcome |
| A8.4 | **Review queue** for proposed changes and flagged calls | Approving applies the change once; rejecting changes nothing |

## A9. Integration

| Area | Integration | Existing LeadStack basis |
| --- | --- | --- |
| Contacts | Call history on the contact; voice consent and opt-out; proposed field updates | `contact`, `consent_record`, `suppression`, `activity` |
| Companies | Through the contact's company; shown on the company timeline | `company`, `activity` |
| Deals | Link a call to a deal; proposed stage and value changes through review | `opportunity`, `opportunity_event` |
| Appointments | Book, reschedule and cancel under §A4 | `appointment`, `booking_page`, `booking` |
| Conversations | Each call is a conversation message on channel `voice` (summary and transcript); notes and assignment as today | `conversation`, `conversation_message` (channel check allows `email`, `other` today) |
| Automations | Triggers: call completed, outcome set, missed call, opted out. Action: place an AI call | `automation`, `automation_run` (8A/8B safeguards) |
| Knowledge | Sources per agent version | Phase 9 (not built) |
| Reporting | Calls, minutes, outcomes, bookings, transfers, opt-outs, cost; CSV export | `reports` (10A/10B) |

---

# B. Technical architecture

## B1. Components

```
voice platform ──(turn: HTTPS, signed)──▶ edge ─▶ API: voice turn endpoint ─▶ SaaS-OS run_inference [Exists]
voice platform ──(events: HTTPS, signed)─▶ edge ─▶ API: voice event receiver ─▶ voice_event (stored first)
worker: voice_post_call, voice_campaign_step, voice_retention, voice_usage_reconcile jobs
API: voice agents, numbers, calls, review, campaigns, usage (member routes)
```

- **[Product]** `crm_app.voice` (service), `crm_app.domains.voice` (pure
  rules), `crm_app.api.voice` (routes), `crm_app.voice_adapters` (provider
  adapters).
- **[Exists]** SaaS-OS uses:
  - `saas_os.inference.run_inference` (non-streaming);
  - `saas_os.infra.egress.StrictEgressClient.post`;
  - `saas_os.infra.secrets`;
  - `saas_os.infra.jobs` (worker jobs);
  - `saas_os.core.usage` (`ingest_event`, `consume_quota`);
  - `saas_os.core.billing.get_entitlements`;
  - `saas_os.core.feature_flags.evaluate_flag`;
  - `saas_os.core.webhooks` (signature and replay primitives);
  - `saas_os.core.audit_log`;
  - `saas_os.infra.ratelimit` (as used by the forms routes).
- **[Proposed]**:
  - streaming inference (#206): optional, for lower latency;
  - GET egress (#205): needed for fetching call details where a provider
    exposes them by GET only.

## B2. Data model ([Product], migration in slice V1; names are proposals)

All tables are tenant tables: `tenant_id`, forced RLS, composite foreign
keys on `(tenant_id, id)` as elsewhere. They go into the purge order and the
test manifests.

| Table | Purpose | Notes |
| --- | --- | --- |
| `voice_agent` | An agent: name, purpose, status (`draft`, `active`, `paused`, `archived`), current version | Optimistic version like automations |
| `voice_agent_version` | Immutable configuration snapshot: instructions, greeting (after the fixed disclosure), language, voice id, personality, qualification questions, allowed tools, CRM access levels, knowledge source ids, transfer targets, escalation rules, max call seconds, transcript setting | Validated by `domains.voice`; a call always records the version it used |
| `voice_number` | A workspace number: E.164, provider, provider number id, verified flag, inbound mode, agent id, calling window | Unique per tenant on E.164; **global** `voice_number_index` (number → tenant) for routing, ids and times only (like `conversation_route_index`) |
| `voice_call` | One call: direction, status (§B4), number, other party E.164, contact id (nullable, with `match` = none/claimed/verified), agent version id, deal id, appointment id, conversation message id, outcome, started/answered/ended, duration, provider call id (unique per tenant), campaign recipient id | `provider call id` unique: idempotency anchor |
| `voice_event` | Append-only provider and internal events: kind, provider event id (unique per tenant), occurred at, small payload (ids and codes only) | No transcript text, no audio |
| `voice_transcript_segment` | Append-only: call id, sequence, speaker (agent/caller), text, start ms | Deleted by retention (§C10) |
| `voice_review_item` | A proposed change or a flag: call id, kind, target (contact/deal/appointment), field, proposed value, status (`open`, `approved`, `rejected`, `applied`), decided by and at | Applying is idempotent (status transition) |
| `voice_consent` | Consent to AI calls: contact id, E.164, status (granted/withdrawn), method (`web_form`, `manual`, `verbal_in_call` withdrawal only), wording, evidence reference, recorded at | Append-only like `consent_record`; or a `channel = 'voice_ai'` extension of `consent_record`, decided in V1 |
| `voice_suppression` | Numbers never to call: E.164, reason (`opt_out_in_call`, `manual`, `complaint`), origin, created at | Unique per tenant on E.164; the gate checks it |
| `voice_campaign`, `voice_campaign_recipient` | Campaign definition, audience snapshot, approval, pacing; recipient status (`queued`, `dialled`, `done`, `skipped`), reason, attempts | Recipient row lock for dialling |

Existing tables extended in V1 (each an additive migration):
- `contact` gains `phone_e164` (normalised, nullable, indexed per tenant).
  Phones are stored as entered today; E.164 normalisation of Dutch numbers
  is a prerequisite.
- `conversation.channel` gains `voice`; `conversation_message` links to
  `voice_call`.
- `activity.kind` gains `call`.
- `automation` triggers and actions gain the voice kinds.

## B3. Agent configuration and lifecycle

- `draft → active → paused → active … → archived`. Only `active` agents
  answer or call.
- Editing creates a new draft version. Activation validates it and switches
  `voice_agent.current_version` atomically.
- A call in progress keeps its version.
- Activation requires `voice_agent:manage`, a verified number for any
  outbound use, and the workspace feature switch (§C8) on.
- Pausing stops new calls at once. Live calls finish, or are ended if the
  emergency stop is used.

## B4. Call session lifecycle

### B4.1 States

```
inbound:  ringing → answered → in_progress ⇄ transferring → ended
outbound: queued → dialling → (no_answer | busy | failed | voicemail | answered → in_progress ⇄ transferring) → ended
any live state → ended (hang-up, max length, emergency stop, provider failure)
```

- Transitions come from provider events (verified, §C4) or internal actions.
- Each transition is stored in `voice_event`.
- Invalid transitions (for example `ended → in_progress`) are ignored and
  logged by code, so out-of-order events cannot reopen a call.

### B4.2 Timeouts

| Timeout | Default | Effect |
| --- | --- | --- |
| Ring | 30 s | Outbound becomes `no_answer` |
| Turn | 6 s to a first answer | Fallback line; after 2 in a row, handoff |
| Silence | 20 s | Closing line, end |
| Maximum length | 600 s (per agent, at most 1,800 s) | Closing line, end |
| Stale call | 2 h without an end event | The reconcile job ends it as `failed` |

### B4.3 Outcomes (exactly one per call)

`answered_by_person`, `voicemail`, `no_answer`, `busy`, `failed`,
`transferred`, `booked`, `rescheduled`, `qualified`, `not_qualified`,
`callback_requested`, `message_taken`, `not_interested`, `opted_out`.

Rules set the technical outcomes (no answer, busy, voicemail, failed,
transferred, opted out). The model proposes the business outcomes, and a
person confirms them in review where they change CRM data.

## B5. Provider-neutral interfaces ([Product], `crm_app.voice_adapters`)

```python
class VoicePlatform(Protocol):
    async def configure_agent(
        self, workspace: UUID, version: AgentVersionSpec
    ) -> ProviderAgentRef: ...
    async def place_call(
        self, workspace: UUID, request: PlaceCall, idempotency_key: str
    ) -> ProviderCallRef: ...
    async def end_call(self, workspace: UUID, provider_call_id: str) -> None: ...
    async def transfer(
        self, workspace: UUID, provider_call_id: str, target_e164: str, warm: bool
    ) -> None: ...
    def verify_event(
        self, headers: Mapping[str, str], body: bytes, secret: Secret
    ) -> VerifiedEvent: ...
    def parse_turn(
        self, headers: Mapping[str, str], body: bytes, secret: Secret
    ) -> TurnRequest: ...


class Telephony(Protocol):
    async def verify_number(self, workspace: UUID, e164: str) -> NumberStatus: ...
```

- Normalised types (`TurnRequest`, `VerifiedEvent`, `ProviderCallRef`) keep
  provider fields out of the domain.
- One adapter per approved provider, plus `FakeVoicePlatform` for tests,
  which is the only adapter in V1.
- All network calls go through `StrictEgressClient.post` **[Exists]**.
- A provider that needs GET for reads waits for #205 **[Proposed]**, or uses
  push events only.
- No provider SDK is imported outside its adapter (an import-linter contract
  to add).

## B6. Streaming, turns and interruption

- **[Exists]** path, used first:
  1. The platform calls the turn endpoint with the transcript so far.
  2. LeadStack calls `run_inference` with the voice deadline (§B4.2) and a
     60-token output cap.
  3. LeadStack returns the reply text in one response (if the platform
     requires a streamed format, one chunk).
  4. Latency is measured in V2 against a target of 1.5 s from the end of
     the caller's speech to the first audio.
- **[Proposed]** path (#206): `stream_inference`, forwarding text deltas as
  they arrive. It is switched on by configuration only after a SaaS-OS
  release and a pin approval.
- **Interruption (barge-in):** the platform detects speech over the agent
  and stops speaking. On LeadStack's side:
  - the in-flight turn is abandoned when the platform sends the next turn
    or a cancel signal (the format depends on the provider:
    `VOICE-PROVIDER-COMPARISON.md`);
  - an abandoned non-streaming `run_inference` still completes and is
    metered, and its reply is discarded;
  - with streaming, leaving the `async with` cancels it (contract §6.3).
- **Turn idempotency:** the platform's turn id (or call id plus sequence) is
  the key. A repeated turn returns the cached reply for 60 s and is not sent
  to the model twice.

## B7. Tools during calls

Tools available to a version: `book_appointment`, `reschedule_appointment`,
`cancel_appointment`, `find_times`, `take_message`, `transfer`,
`lookup_business_info`, `end_call`.

For every tool call:
1. Check that the tool is in the version's allowed list.
2. Re-check the workspace permission held by the agent's acting member (the
   member who activated it, as for automations). If that member is no
   longer active, the agent pauses.
3. Validate the arguments with the same validators as the API.
4. Execute through the existing service function (for example the booking
   service), in its own transaction.
5. Return a short result to the model.

Rules:
- Writes that would change contact or deal data are not tools. They become
  review items (§A3.2) after the call.
- At most 3 tool calls per turn and 15 per call. A tool that fails twice
  escalates (§A5.2).
- Context limits per turn:
  - fixed rules and the disclosure (not editable);
  - the version's instructions, at most 4,000 characters;
  - at most 3 knowledge snippets of 800 characters each;
  - the last 12 turns or 3,000 tokens of history, whichever is smaller;
  - verified contact context only: first name and the next appointment, and
    only for an outbound call LeadStack placed.
  - The prompt is built by code; the model never sees secrets or other
    contacts.

## B8. Durable events and idempotency

- **Receive:**
  1. Verify the signature (§C4).
  2. Insert into `voice_event` with the unique provider event id, in the
     same transaction as resolving the tenant.
  3. Answer 2xx. A duplicate insert answers 2xx without reprocessing.
- **Process:** the `voice_post_call` job runs at most once per call and
  kind, keyed by call id and kind. It produces the summary, the outcome
  proposal, the review items, the activity, the conversation message, the
  automation triggers and the usage events.
- **Outbound dial:**
  1. Lock the recipient row.
  2. Set it to `dialled` before the provider call.
  3. Use the recipient id as the provider idempotency key.
  4. A timeout is reconciled by status and never re-dialled automatically.
- **Usage:** one `core.usage` event per call and metric, keyed by call id
  (`consume_quota_idempotent` **[Exists]**).

## B9. Failure recovery and handoff

| Failure | Behaviour |
| --- | --- |
| Model timeout or error | Fallback line; after 2 in a row, handoff (§A5) |
| Tool failure | Tell the caller, offer handoff; after 2, escalate |
| Turn endpoint unreachable | The provider's own fallback message (configured at agent set-up) and a transfer to the business line |
| Provider outage | Campaigns pause automatically; inbound falls back to the business line (carrier routing); operators alerted |
| Missing end event | The reconcile job ends the call as `failed` after 2 h |
| LeadStack database unavailable | The turn endpoint answers with the fallback and handoff; nothing is written; reconciliation on recovery |

## B10. Usage metering and isolation

- **Metrics [Exists, any metric name]:** `voice_minutes_inbound`,
  `voice_minutes_outbound`, `voice_calls`, `voice_campaign_recipients`,
  `voice_numbers`.
- **Entitlements [Exists]:** minutes a month, concurrent calls, campaign
  size, numbers.
- **Before each call:** `consume_quota` for at least one minute (hard
  stop), a concurrency check, and the budget (§C7).
- **Isolation:**
  - The tenant comes only from the global number index (inbound) or the
    call row (events) via the provider call id.
  - All reads and writes go through `tenant_session_scope`.
  - The turn endpoint resolves the tenant once per turn and never accepts a
    tenant id from the request.

---

# C. Security and permissions

## C1. Tenant isolation
- Forced RLS on every voice table.
- The global index tables hold only ids, the E.164 key and times.
- Cross-tenant tests for every route, receiver and job (§C12).

## C2. Permissions (proposed, in `crm_app.roles`)

| Permission | Kind | Read-only | Member | Admin | Owner |
| --- | --- | --- | --- | --- | --- |
| `voice_agent:read` | normal | ✓ | ✓ | ✓ | ✓ |
| `voice_call:read` | normal | ✓ | ✓ | ✓ | ✓ |
| `voice_transcript:read` | normal | — | ✓ | ✓ | ✓ |
| `voice_call:place` | normal | — | ✓ | ✓ | ✓ |
| `voice_review:decide` | normal | — | ✓ | ✓ | ✓ |
| `voice_campaign:manage` | normal | — | ✓ | ✓ | ✓ |
| `voice_agent:manage` | administrative | — | — | ✓ | ✓ |
| `voice_number:manage` | administrative | — | — | ✓ | ✓ |
| `voice_campaign:approve` | administrative | — | — | ✓ | ✓ |
| `voice_settings:manage` (emergency stop, budgets, retention) | administrative | — | — | ✓ | ✓ |

Existing workspaces receive these through the role-upgrade command
(13-R1), with the administrative ones held back as today.

## C3. Secrets
- Provider API keys and per-workspace webhook secrets are stored through
  `infra.secrets` **[Exists]** and referenced by name.
- They are never in the database in clear, never in the frontend, never in
  logs.
- Secrets are rotated with an overlap window: two secrets are valid for
  24 h.

## C4. Webhook and turn authentication
- An HMAC signature over the timestamp and body, in a header, with a
  per-workspace secret, a constant-time compare and a 5-minute timestamp
  window.
- A replay ledger keyed by the provider event id (and
  `core.webhooks.verify_and_record_webhook_delivery` **[Exists]** where its
  envelope fits).
- No secret in a URL.
- Where a provider only supports its own scheme, the adapter verifies that
  scheme, and the workspace is still resolved from LeadStack's mapping,
  never from the payload.

## C5. Outbound call authorisation (the gate, `domains.voice.may_call`)

The gate is pure and returns either allowed or the first failing reason, in
this order:
1. Platform emergency stop.
2. Workspace emergency stop.
3. Voice feature switch.
4. The member's or automation's permission.
5. The agent is active.
6. A verified caller number.
7. The destination is a valid E.164 number and allowed for the country
   (NL first).
8. Not in `voice_suppression`.
9. Consent to AI calls granted and not withdrawn.
10. Inside the calling window in the callee's local time, and not on a
    public holiday.
11. The per-number frequency cap (proposal: 1 a day, 3 in 14 days).
12. The workspace daily cap.
13. The budget.
14. The quota.

Any exception counts as "refused: check unavailable".

## C6. Consent and suppression
- Consent comes from a web form with double opt-in (the P7-V mechanism,
  wording specific to AI calls) or is recorded manually with evidence.
- Saying "stop", "bel me niet meer" or similar during a call:
  1. The agent confirms.
  2. The number is written to `voice_suppression` with reason
     `opt_out_in_call`.
  3. Consent is withdrawn.
  4. Every agent and campaign of the workspace respects it from the next
     dial.
- Opt-outs never expire.

## C7. Rate and spending limits
- Edge rate limits on the turn and event endpoints per provider source.
- Per-workspace concurrent calls (from the entitlement).
- A daily spend cap per workspace and per agency, with alerts at 50%, 80%
  and 100%.
- A maximum call length.
- At most 3 test calls a day per member, to verified numbers only.

## C8. Emergency stop
- **Platform level:** a SaaS-OS feature flag
  (`voice_platform_enabled`, `evaluate_flag` **[Exists]**) checked at every
  dial and campaign step. When off, inbound falls back to the business
  line.
- **Workspace level:** `voice_settings.stopped` set by
  `voice_settings:manage`, which also offers "end live calls".
- **Agency level:** with Phase 11.
- **Speed:** a stop takes effect within one minute. Every stop is audited
  with its reason.

## C9. Audit trail
Audited in `core.audit_log` **[Exists]**:
- agent version activation and pause;
- number changes;
- campaign approval;
- emergency stop on and off;
- consent changes;
- review decisions;
- settings changes (budgets, retention, transcripts on or off);
- every refused outbound call (reason code only).

Audit entries carry ids and codes, never transcript text.

## C10. Retention and deletion

Per `VOICE-LEGAL-REVIEW.md` §3:
- No recordings.
- Transcripts: 90 days proposed, configurable shorter.
- Summaries, outcomes and metadata: as CRM history.

Deletion:
- The `voice_retention` job deletes transcript segments past their date in
  batches.
- Deleting a contact deletes its transcripts and links: calls keep
  anonymised metadata for usage and billing.
- Workspace purge (`crm_app.purge`) covers every voice table.
- Provider-side copies: zero-retention settings where offered; otherwise the
  provider's deletion API through the adapter (it may need #205 or DELETE,
  **[Proposed]**).

## C11. Prompt injection through calls and knowledge
- System rules, the disclosure, the opt-out handling, the tool allowlist and
  the emergency wording are enforced in code. The model cannot change them.
- Caller speech and knowledge snippets are placed in delimited untrusted
  sections.
- Tool arguments are validated, and identifiers are resolved by LeadStack,
  never taken from model output.
- The model has no tool that reads another contact, lists data, exports,
  changes settings or sends messages.
- An injection test corpus (Dutch and English) runs in CI against the
  prompt builder and the tool gate, using the fake provider. Expected
  results: no forbidden tool executes, no other contact's data appears in a
  prompt, and the disclosure is always first.

## C12. Tests required before each slice is accepted
- Unit tests:
  - the gate (`may_call`): every reason, in order, failing closed;
  - the call state machine: valid and invalid transitions, out-of-order
    events;
  - the prompt builder: context limits, untrusted sections, no secrets;
  - outcome rules;
  - E.164 normalisation of Dutch numbers.
- Integration tests:
  - migrations, RLS and cross-tenant isolation for every table, route,
    receiver and job;
  - signature, timestamp and replay rejection;
  - idempotent event processing and post-call side effects under replay;
  - a single dial under concurrent jobs;
  - review apply exactly once;
  - retention deletion;
  - purge.
- Frontend tests: every screen's loading, empty, error and denied states;
  accessibility checks (axe); disabled controls with reasons while voice is
  off.
- Operations tests: the emergency stop within a minute; the health check
  covering voice queues.
