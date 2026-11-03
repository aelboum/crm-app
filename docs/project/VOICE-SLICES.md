# AI voice agents: implementation slices V0–V6

**Status:** a plan, 2026-11-03. It refines roadmap workstream 15V. No slice
is authorised. Each slice starts only after an explicit owner approval (its
gate) and keeps the Definition of Done, negative authorisation tests and the
usual quality gates. Requirement ids refer to `VOICE-SPEC.md`; screens to
`VOICE-UX-SPEC.md`. K5 is unchanged: voice stays outside the MVP.

## Safe now, without any provider, account, purchase or scope change

Documentation, research and specifications only:
- These specifications.
- Test specifications for the gate, the state machine and the prompt
  builder (§T below).
- Provider research from public documentation.
- Legal question lists.
- The threat model.

Not done now, because each is V1 code that needs the V1 gate:
- E.164 normalisation of contact phones;
- the voice tables;
- the pure gate and state machine modules;
- the screens.

---

## V0 — Owner decisions and requirements

| Item | Content |
| --- | --- |
| Scope | Decisions only: a K5 scope change for voice (or not); the provider bake-off (sandbox accounts, cost in `VOICE-ACTIVITY-COSTS.md`); the legal review and DPIA; plan limits and prices; recording policy (stays "none"); SaaS-OS #205/#206 outcomes |
| Dependencies | Owner |
| Database / API / screens | None |
| Security | The decisions recorded in DECISIONS |
| Tests | None |
| Acceptance | Each decision recorded with its date and text |
| Rollback | Not applicable |
| **Approval gate** | The owner approves a K5 change that brings V1 into a release, or approves V1 as non-release work behind a switch |

## V1 — Data model, permissions and UI behind a feature switch, no provider

| Item | Content |
| --- | --- |
| Scope | E.164 normalisation and `contact.phone_e164`; the voice tables (`VOICE-SPEC.md` §B2); `domains.voice` (gate, state machine, outcome rules, prompt builder, all pure); permissions (§C2); the agent editor (S1, S2 without the Test call), call log (S6) and review queue (S7) on `FakeVoicePlatform` data only; the workspace switch and platform flag (§C8) |
| Dependencies | V0 gate; Phase 9 knowledge for the Knowledge tab (otherwise shown as "Knowledge comes later") |
| Database | Migration 00xx_voice: the tables, RLS, grants, purge order, test manifests; `contact.phone_e164` with a backfill (by a command, dry run first, never destructive) |
| API | `GET/POST /v1/workspaces/{ws}/voice-agents`, `GET/PATCH /voice-agents/{id}`, `POST /voice-agents/{id}/activate`, `/pause`, `/archive`; `GET /voice-calls`, `GET /voice-calls/{id}`; `GET /voice-review`, `POST /voice-review/{id}/approve`, `/reject`; `GET/PUT /voice-settings` |
| Screens | S1, S2 (no Test call), S6, S7, banners and "off" states |
| Security | RLS and cross-tenant tests; permission tests per role; no network call possible (there is no adapter except the fake one; an import-linter contract forbids provider SDKs) |
| Tests | Unit: gate, state machine, outcomes, prompt builder, E.164. Integration: migrations, isolation, routes. Frontend: every screen state, axe |
| Acceptance | All tests pass; the feature switch off hides voice; no call can be placed (proved by test); full suites and CI green |
| Rollback | The switch off. The migration is additive; down-migration tested on a copy only |
| **Approval gate** | Owner approves V1; then a provider choice for V2 |

## V2 — Inbound calls in a provider test environment

| Item | Content |
| --- | --- |
| Scope | One provider adapter; the turn endpoint and event receivers; disclosure; knowledge answers; take a message; transfer; test numbers only (a sandbox account and a test number, never a customer number) |
| Dependencies | V1; an approved sandbox account; a Dutch local or national number (KvK and address; not +3197) |
| Database | `voice_number_index` (global); event uniqueness |
| API | `POST /v1/voice/{provider}/turn` (public route, signed); `POST /v1/voice/{provider}/events` (public route, signed); `POST /voice-numbers`, `PATCH /voice-numbers/{id}` |
| Screens | S3; the Test call in S2 for verified member numbers |
| Security | Signature and replay tests; the tenant resolved from the mapping only; injection corpus; secrets through `infra.secrets` |
| Tests | Simulated calls through the fake provider and the sandbox; latency measured (target 1.5 s to first audio); disclosure always first |
| Acceptance | Scripted test calls pass; forged requests rejected; latency recorded (a decision on #206 if over target) |
| Rollback | Number routed back to the business line; the agent paused; the switch off |
| **Approval gate** | Owner approves the sandbox account and number (cost) and V2 |

## V3 — Post-call processing and review

| Item | Content |
| --- | --- |
| Scope | Summary, outcome, review items, links to contact, deal, appointment and conversation (channel `voice`); automation triggers; booking and rescheduling tools (§A4); retention job |
| Dependencies | V2 |
| Database | `conversation.channel` gains `voice`; `activity.kind` gains `call`; automation trigger kinds |
| API | Review apply; call outcome change |
| Screens | S6 complete, S7 complete, timeline entries, Inbox "Phone" messages |
| Security | Every side effect idempotent under replayed events; P7-V rule for matched callers; review apply once |
| Tests | Replay tests; booking-limit and conflict tests through the tool; retention deletion |
| Acceptance | Nothing changes CRM data without review unless allowed; the replay suite passes |
| Rollback | Disable post-call processing (a setting); calls keep their raw events |
| **Approval gate** | Owner approves V3 |

## V4 — Individual outbound calls

| Item | Content |
| --- | --- |
| Scope | The single "Call with AI agent" action; the automation action; consent to AI calls (form with double opt-in, manual entry with evidence); voice suppression; the calling window, caps, budget and emergency stop; caller ID |
| Dependencies | V3; **the legal review** (P15-V points 4 and 8) |
| Database | `voice_consent`, `voice_suppression`, caps counters |
| API | `POST /voice-calls` (place one call), consent and suppression routes, the emergency stop |
| Screens | S4 (outbound settings, suppression), the contact action |
| Security | The gate fails closed (tests for every reason); an in-call opt-out suppresses at once; EEA origination enforced (cost test) |
| Tests | Gate, concurrency (no double dial), emergency stop within a minute, origination check |
| Acceptance | A call without consent is impossible (proved by test); counsel's conditions met |
| Rollback | Outbound off per workspace and platform-wide |
| **Approval gate** | Owner approves V4 after the legal review |

## V5 — Approved outbound voice campaigns

| Item | Content |
| --- | --- |
| Scope | Audience, approval, pacing, schedule, cancel, progress, outcomes, reporting |
| Dependencies | V4 |
| Database | `voice_campaign`, `voice_campaign_recipient` |
| API | Campaign create, request approval, approve, cancel, list recipients |
| Screens | S4 campaigns |
| Security | Approval by an administrative permission; the audience snapshot audited; the gate per recipient at dial time; caps per plan |
| Tests | No dial without approval; one dial per recipient under duplicate jobs; cancel within a minute |
| Acceptance | All of the above; a dry-run campaign on the fake provider matches its pacing |
| Rollback | Cancel all campaigns; outbound off |
| **Approval gate** | Owner approves V5 |

## V6 — Metering, operational controls and launch readiness

| Item | Content |
| --- | --- |
| Scope | Usage events and entitlements, budgets and alerts, reconciliation against the provider's billing, the usage dashboard (S8), the health check for voice queues, operations runbook, launch review |
| Dependencies | V5; Phase 11 billing for agency resale |
| Database | Usage reconciliation records |
| API | Usage read, budget settings |
| Screens | S8 |
| Security | Spend caps enforced before each call; alerts; the emergency stop at every level |
| Tests | Reconciliation test; budget stop; health check |
| Acceptance | Usage matches provider billing; operators can stop everything within a minute |
| Rollback | Platform flag off |
| **Approval gate** | Owner approves production enablement (a separate decision from every slice above) |

---

## §T Test specifications ready now (for V1)

Given and Then pairs the V1 unit tests will implement.

**Gate `may_call`:**
1. Platform flag off → refused `platform_stopped`.
2. Workspace stopped → `workspace_stopped`.
3. Switch off → `voice_off`.
4. A member without `voice_call:place` → `forbidden`.
5. Agent not active → `agent_inactive`.
6. No verified caller number → `no_caller_id`.
7. An invalid or non-allowed number → `bad_destination`.
8. A suppressed number → `suppressed`.
9. No consent or withdrawn → `no_consent`.
10. Outside the window or on a holiday → `outside_window`.
11. Frequency cap → `too_frequent`.
12. Daily cap → `daily_cap`.
13. Budget → `over_budget`.
14. Quota → `quota`.
15. Any lookup raising → `check_unavailable`.
16. Everything fine → allowed.

When several fail, the first in this order is reported.

**State machine:**
- Every valid transition in `VOICE-SPEC.md` §B4.1 is accepted.
- `ended → in_progress` and any transition out of `ended` are ignored.
- A duplicate event is a no-op.
- Out-of-order `answered` after `ended` is ignored.

**Prompt builder:**
- The disclosure is always first.
- Instructions are truncated at 4,000 characters.
- At most 3 snippets of 800 characters each.
- History is bounded at 12 turns or 3,000 tokens.
- Caller text and knowledge are inside untrusted delimiters.
- Secrets never appear (a canary test).
- Contact context only on a LeadStack-placed outbound call.

**E.164 (NL):**
- `06 12345678`, `+31 6 1234 5678` and `0031612345678` all become
  `+31612345678`.
- `020 123 4567` becomes `+31201234567`.
- `+3197…` is flagged as machine-to-machine.
- Invalid input is `None`, never an exception reaching the user.
