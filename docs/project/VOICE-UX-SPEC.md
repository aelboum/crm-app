# AI voice agents: screen specifications

**Status:** specification only, 2026-11-03; nothing is built. Screens follow
LeadStack's existing design system:
- the AI group in the sidebar (Assistants, Knowledge, AI activity), today
  marked "soon";
- the Claude Design Assistants screen: a list, then a detail page with
  instructions, tone, reply language, guardrails, channels (including
  "Phone"), CRM-access levels ("No access / Read / Read & update"),
  knowledge sources, a sandbox labelled "Simulated replies · nothing is
  sent", and an activity log;
- the existing components in `frontend/src/components`: `ui/DataTable`,
  `ui/Badge`, `ui/Button`, `ui/Dialog`, `ConfirmDialog`, `StateNotice`
  (loading, empty, error), `ui/Toast`;
- the list → side drawer → full record pattern;
- 13 px base text, a 4 px grid, the tenant accent colour, flat cards.

Requirement ids refer to `VOICE-SPEC.md`.

**Rule while voice is off (every screen):** the "Voice agents" entry stays
under AI with the existing "soon" treatment (`nav.soon`). A screen reached
directly shows a `StateNotice` "Voice calling is not available in this
workspace yet" and no working control. Nothing ever fakes a call or a
result.

## Common states (all screens)

| State | Treatment |
| --- | --- |
| Loading | `StateNotice` loading row in the content area |
| Empty | A short sentence and the main action, if the role allows it |
| Validation error | Inline under the field, plus an `aria-live` summary at the top of the form |
| Permission denied | 403: "You don't have access to voice agents" without data; controls a role lacks are hidden, or disabled with a tooltip giving the reason |
| Server error | `StateNotice` error with "Try again"; no stack traces |
| Voice off or emergency stop | A top banner in the warning colour: "Calls are stopped for this workspace" with the reason and who stopped it (for administrators) |

Accessibility on every screen:
- labels on every control;
- focus order follows the layout;
- dialogs trap focus and restore it on close;
- status uses text and colour, never colour alone;
- the transcript viewer is a list with speaker labels;
- usable at 390 px wide;
- axe checks in the component tests.

## S1. Voice agent list (`/w/<ws>/voice-agents`)

- **Header:** "Voice agents"; a one-line explanation ("Voice agents answer
  and place calls for <workspace>. They always say they are an AI and hand
  off to your team when needed."); a "New voice agent" button
  (`voice_agent:manage`).
- **Table (`DataTable`):**
  - name;
  - purpose;
  - status `Badge` (Draft, Active, Paused, Archived);
  - direction (Inbound, Outbound, Both);
  - number;
  - language and voice;
  - calls in the last 7 days;
  - last call;
  - a row action "Open".
- **Filters:** status, direction.
- **Empty:** "No voice agents yet." with "New voice agent" for
  administrators.
- **Create dialog:**
  - name (required, 1–80 characters);
  - start from a template: Receptionist, Lead qualifier, Appointment
    follow-up, or Blank;
  - "Create draft" creates a draft and opens S2. Nothing goes live.

## S2. Agent configuration (`/w/<ws>/voice-agents/<id>`)

**Layout:**
- A header with the name, status `Badge`, version ("Draft v3", "Active
  v2"), and the buttons "Activate" (`voice_agent:manage`; confirm dialog),
  "Pause" and "Archive".
- Tabs: **Overview, Behaviour, Voice & language, Knowledge, Actions &
  handoff, Calls, Test**.
- Unsaved changes show a sticky "Save draft" bar. Activating a draft shows
  a diff summary of what changes.

| Tab | Fields (validation) | Requirement |
| --- | --- | --- |
| Overview | Purpose; key figures (calls, booked, transferred, opted out, last 30 days); recent calls | A8 |
| Behaviour | Instructions (plain language, at most 4,000 characters, counter); tone (Warm & concise / Professional / Calm & clear); Dutch form of address (u / je); maximum reply length (short / normal); qualification questions (up to 10, each mapped to a field or "note only"); fixed rules shown read-only ("Always says it is an AI first", "Stops calling when asked", "Never handles emergencies") | A3, A7.1, C11 |
| Voice & language | Language (Dutch / English / match the caller); voice from the vetted list with a "Play sample" button; greeting text after the fixed disclosure, with the full spoken greeting previewed; the disclosure is shown locked | A1.2, A7 |
| Knowledge | Knowledge sources to use (from Knowledge, Phase 9); business hours and booking pages it may use; "What this agent can read": contacts, appointments, deals each "No access / Read" (the design's control; "Read & update" is not offered: updates go through review) | A6, B7 |
| Actions & handoff | Allowed actions (book, reschedule, cancel, take a message, transfer, end call), each a toggle with an explanation; transfer targets (member, team or business number, warm or cold); escalation keywords; fallback when nobody answers (take a message → task for the owner) | A4, A5, B7 |
| Calls | This agent's calls (S6 filtered) | A8 |
| Test | Sandbox like the design's: "Simulated replies · nothing is sent" for text testing against the draft; a "Test call" button only for numbers the member has verified, disabled while voice is off, with the reason | C7 |

## S3. Inbound call settings (`/w/<ws>/settings?section=voice-numbers`)

- **Numbers table:**
  - number (E.164 shown in Dutch format);
  - verified `Badge`;
  - agent;
  - mode;
  - business-hours summary;
  - "Edit".
- **Edit drawer:**
  - mode: Always / Outside business hours / When nobody answers within N
    seconds (10–60);
  - agent (active agents only);
  - fallback number (the business line);
  - after-hours message;
  - maximum call length;
  - transcripts kept (on or off; retention shown, read-only).
- **Add number** (`voice_number:manage`): shows "Numbers are provided by
  your phone provider under your own account" and the verification steps.
  Disabled until a provider is approved. +3197 numbers are refused with an
  explanation.

## S4. Outbound call settings (`/w/<ws>/settings?section=voice-outbound`)

- **Status card:** "Outbound AI calls are off" until the legal review and
  the owner's approval (P15-V point 8). It shows the checklist that turns
  it on: consent wording, calling window, caps and budget.
- **Fields, when on:**
  - calling window per weekday (default 09:00–20:00, Monday to Friday; no
    Sundays or public holidays; cannot be widened beyond the platform
    maximum);
  - per-number frequency cap;
  - daily call cap;
  - caller number;
  - countries allowed (NL first).
- **Consent:** the wording used for AI-call consent (read-only text from
  the legal review); a link to contacts with consent; and the suppression
  list of numbers (S4b: add with a reason, search, and "remove" only for
  administrators with a confirm dialog; in-call opt-outs cannot be
  removed).
- **Single-call button** on the contact record: "Call with AI agent", shown
  for `voice_call:place`. Disabled with the gate's reason, for example
  "No consent to AI calls" or "Outside calling hours".
- **Campaigns** (`/w/<ws>/voice-campaigns`), when allowed:
  - audience (tag, pipeline stage, list), with the eligible count after the
    gate;
  - agent;
  - pacing;
  - schedule;
  - "Request approval", then "Approve" (`voice_campaign:approve`), showing
    the audience snapshot;
  - a live progress table (queued, dialled, done, skipped with reasons);
  - "Cancel" (queued only, or also end live calls).

## S5. Knowledge and voice selection

Inside S2:
- **Knowledge:** a picker of sources with type, size, last indexed and
  status. Only indexed sources are selectable; failed sources are shown
  with the error.
- **Voices:** a list grouped by language. Each voice shows its name, a
  style description, a "Play sample" control (keyboard-operable,
  stop-on-escape) and the provider. Unavailable voices are hidden. Premium
  voices are marked with their cost class (from the cost model) and need an
  entitlement.

## S6. Call history and transcripts (`/w/<ws>/voice-calls`)

- **Table:**
  - time;
  - direction icon with text;
  - other party (contact name if matched, else the masked number; a
    "claimed" `Badge` when matched by number only);
  - agent;
  - duration;
  - outcome `Badge`;
  - "Needs review" marker.
- **Filters:** date, direction, agent, outcome, needs review.
- **Detail drawer:**
  - a summary card;
  - the outcome, with "Change" (review permission);
  - linked contact, deal and appointment;
  - actions taken (booked, transferred, message);
  - the transcript, if kept, where `voice_transcript:read` allows: speaker
    labels, times, "Transcript deleted after 90 days" when expired;
  - a timeline of events (disclosure spoken, transfer, opt-out).
- **No recording player:** recording is not available.
- The call also appears in the Inbox conversation (channel "Phone") and on
  the contact and company timelines.

## S7. Call outcome and review queue (`/w/<ws>/voice-review`)

- **List of open items:**
  - kind (proposed field update, deal stage move, flagged call:
    complaint, opt-out, low confidence, failed disclosure);
  - the contact or deal;
  - the proposed value, compared with the current value;
  - the call link;
  - age.
- **Actions:**
  - "Approve" (applies once);
  - "Reject";
  - "Edit and approve";
  - bulk approve and reject for selected items of the same kind, with a
    confirm dialog.
- **Flagged calls** need a note when closed.
- **Empty:** "Nothing to review."

## S8. Usage and cost dashboard (`/w/<ws>/voice-usage`, `voice_settings:manage`)

- **Cards:**
  - minutes this month (inbound and outbound) against the plan limit;
  - calls;
  - estimated cost against the budget, with a progress bar and text;
  - concurrent calls at peak.
- **Charts:** minutes per day and outcomes per week. Each has a data table
  alternative, and a CSV export as in reports.
- **Budget settings:**
  - daily and monthly budget;
  - alerts at 50%, 80% and 100%;
  - "Stop calls at 100%" (always on; shown read-only).
- **Emergency stop:** a destructive-style button "Stop all calls now" with
  a confirm dialog asking for a reason; it also offers "End live calls".
  Resuming needs the same permission and is audited.

## Routes and permissions summary

| Screen | Route | View | Act |
| --- | --- | --- | --- |
| S1 | `/w/<ws>/voice-agents` | `voice_agent:read` | `voice_agent:manage` |
| S2 | `/w/<ws>/voice-agents/<id>` | `voice_agent:read` | `voice_agent:manage` |
| S3 | settings `voice-numbers` | `voice_agent:read` | `voice_number:manage` |
| S4 | settings `voice-outbound`, `/w/<ws>/voice-campaigns` | `voice_agent:read` | `voice_settings:manage`, `voice_campaign:manage`, `voice_campaign:approve`, `voice_call:place` |
| S6 | `/w/<ws>/voice-calls` | `voice_call:read` (+ `voice_transcript:read`) | `voice_review:decide` |
| S7 | `/w/<ws>/voice-review` | `voice_call:read` | `voice_review:decide` |
| S8 | `/w/<ws>/voice-usage` | `voice_settings:manage` | `voice_settings:manage` |
