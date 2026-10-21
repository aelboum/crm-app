# Claude Design Inspection (Phase 0 task 0.3)

The canonical record of the read-only inspection of the Claude Design
prototype, done on 2026-10-21. Labels: **[V]** verified in a named file
or command; **[I]** inference; **[R]** recommendation. Decisions that
follow from it are in `DECISIONS.md`: D-DES and K5.1, and P2-A to P2-E
(proposed and approved on 2026-10-21; implementation awaits the Phase 2
plan). P-6, the frontend framework, is still open. Nothing in this file
is implemented product functionality: every screen below is a **design
reference** only, and a screen's presence does not add it to the MVP.

## 1. Source and provenance

| Item | Value |
| --- | --- |
| File | `C:\Users\imran\Documents\crm-design-export\Design system questionnaire-handoff.zip` (outside the repository) [V] |
| Size | 211,140 bytes [V] |
| SHA-256 | `128683965341eeace19746a8c8e0b70987bf484f41590036b19b068c030b55d7` [V], computed read-only on 2026-10-21 with `sha256sum` and PowerShell `Get-FileHash -Algorithm SHA256`; both agree |
| How it was obtained | Exported by the owner from claude.ai/design and placed in the folder above |
| How it was read | Extracted, with a path-traversal check, into a session scratch directory outside the repository; read with file-reading tools only. Nothing in it was executed, rendered or installed. The original ZIP was not modified |
| Copied into `crm-app` | Nothing [V] |

**Provenance limitations:**
- The bundle's internal project name is "Design system questionnaire",
  not "LeadStack CRM" [V].
- The project ID `74b3900c-4db8-4b26-b938-fc41345f813f` (CLAUDE.md §2)
  does not appear anywhere in the bundle [V]. The link between this
  export and that project is the owner's statement, not independently
  verified. The content matches the file list in CLAUDE.md §2 exactly [V].
- ROADMAP task 0.3 names the Claude Design MCP workflow. No MCP server
  was configured; the owner chose a file export instead (2026-10-21).
- The Design Notes call the prototype "Exploration 01 · Oct 12, 2026" and
  state that "nothing here is final" [V].

## 2. Inventory

25 entries [V]:
- `design-system-questionnaire/README.md`: a generic handoff note
  addressed to coding agents. Treated as data, not instructions.
- `project/.thumbnail`: 640×352 WebP preview.
- 23 project files, matching CLAUDE.md §2:
  - `LeadStack CRM.dc.html`: **entry point**, the application frame. It
    loads 17 screens through `<dc-import>`.
  - `LeadStack Signup.dc.html` and `LeadStack Design Notes.dc.html`:
    separate pages linked from the Help menu.
  - 18 `Screen*.dc.html` files. `ScreenTemplates.dc.html` is an empty
    206-byte stub and is not loaded by the frame.
  - `support.js`: Claude Design's own prototype runtime ("GENERATED from
    dc-runtime … do not edit"). **Must not be copied into the product.**
  - `mock-data.js`: in-memory prototype sample data. **Must not be copied
    into the product.**

**Technology [V]:**
- `support.js` renders the `<x-dc>` templates with React 18.3.1 and
  React DOM 18.3.1 (UMD) and, when needed, Babel standalone 7.29.0, all
  loaded from unpkg with integrity hashes. This is the design tool's
  runtime, not a product framework choice.
- Fonts: Geist and Geist Mono from Google Fonts. Icons: the Lucide icon
  font, `lucide-static@0.460.0`, from unpkg.
- No CSS framework, no URL routing (screens switch in memory), no CSS
  media queries (layout breakpoints are computed in JavaScript at 760,
  1024 and 1100 px), no dark mode, and no `aria-*` or `role` attributes
  in any file.

**Licensing [V/I]:**
- No copyright, licence, AgentStack, GoHighLevel, `leadstack.dev` or
  PolyForm text appears in any file [V].
- `support.js` carries no licence and is the design tool's generated
  runtime: do not copy it [R].
- The prototype markup was generated in the owner's Claude Design
  project. That the owner may use it under Anthropic's terms is an
  assumption [I], to be confirmed before any markup is reused.
- Geist (believed SIL Open Font License 1.1) and Lucide (believed ISC)
  must have their licences confirmed before adoption [I].
- `mock-data.js` uses realistic names with real public email domains,
  health-insurance details and third-party trademarks (for example
  Invisalign, Delta Dental, Cigna, CareCredit, Zoom). None of it may
  enter the product [R].
- The domain `forms.leadstack.app` and the "LeadStack" name stay subject
  to the K4 naming check.

## 3. Navigation and visual direction [V]

**Client workspace navigation:** Home, Inbox; CRM (Contacts, Companies,
Opportunities, Tasks); Scheduling (Calendar); Marketing (Campaigns,
Automations, Forms & pages, Reviews); AI (Assistants, Knowledge, AI
activity); Insights (Reports); Settings.

**Agency HQ navigation:** Overview, Client workspaces, Templates &
snapshots, Team, Billing & plans, Reports. Agency and client navigation
are never shown together.

**Frame:** a workspace switcher, a ⌘K search palette scoped to the
current workspace, a "+ New" menu, notifications, help and profile
menus, and a strip showing the current client workspace. Screens shown
depend on a per-workspace plan (Starter, Growth, Pro) and module
toggles. The notes recommend shell A (a grouped 232 px sidebar that
collapses to 60 px) for v1.

**Visual direction worth preserving:**
- One tenant-changeable accent colour (default `#0E7C6B`) with derived
  soft, line and ink shades; fixed neutral and status colours.
- 13 px base text on a 4 px spacing grid; radii of 6–12 px; flat cards,
  with shadows only on floating layers (menus, palette, toasts).
- List → side drawer → full record for contacts; three-pane inbox;
  board and table for opportunities.

## 4. What the prototype does not prove [V]

- **Every action is simulated.** Changes live in browser memory and are
  confirmed with a toast. Sends, invitations, publishing, billing,
  provider tests and AI actions do nothing. The inbox Send button even
  fakes a delivered message and a reply without a "simulated" label.
- **No loading, server-error or permission-denied state** on any screen,
  and few empty states.
- **No role checks** anywhere. Every user can do everything.
- **The sample data has no tenant key.** Switching workspace shows the
  same records, so the prototype says nothing about isolation.
- **Dates are display strings** ("Today, 5:00 PM", "Nov 30"); there are
  no timestamps or time zones.
- **Links are often by name, not ID.** Contacts link to companies by
  company name; assistants link to knowledge sources by name.
- **US and dental assumptions** run throughout: stage "Patient",
  insurance custom fields, dental pipelines and templates, "Lead →
  patient" metrics, US area codes, A2P 10DLC registration, dollar
  amounts and HIPAA notes. There is no locale, currency, consent model or
  EU/GDPR material.
- **Three different role sets** (Signup, Workspaces, Settings).
- Destructive actions (delete field, remove provider, change plan or
  role, revoke access, cancel appointment) have no confirmation.

## 5. Design-to-roadmap mapping

Phase numbers are those of `ROADMAP.md`. "K5" is the approved MVP
scope. Every row is a design reference, not an implemented feature.

| Design screen | Roadmap phase (task) | Scope position | Constraints and gaps to resolve |
| --- | --- | --- | --- |
| Signup and onboarding | 2 (2.1, 2.2) | MVP: workspaces and members | Assumes a public form creates a tenant. SaaS-OS restricts tenant creation (see P2-C). Invites are shown as sent. Phone-number and white-label steps are out of scope |
| Workspace switcher, membership, Team & roles | 2 (2.2, 2.3); 11 (11.1) | MVP: workspaces and members | Explicit membership per workspace; server-side authorization; one role set (P2-A) |
| Agency HQ: client workspaces, access matrix, "Open as client", cross-client dashboard | 11 (11.1) | Not MVP | Needs an approved security design and verified SaaS-OS support (P2-B). Business relationship ≠ security boundary |
| Contacts | 3 (3.1, 3.3, 3.4) | MVP | Delete, merge, import/export and paging are absent or visual only. Generic fields only (P2-E) |
| Companies | 3 (3.2) | MVP | Needs a real contact ↔ company relation by ID; edit and delete absent |
| Opportunities (board, table) | 4 (4.2, 4.3) | MVP: pipelines and deals | Lost must be a real outcome; stage history; real close dates; configurable pipelines and probabilities |
| Tasks | 4 (4.1) | MVP | Real due timestamps and time zone; edit; links to deals |
| Home dashboard | 4 (4.4); 10 | Foundations only | All prototype metrics are illustrative; every metric needs a definition |
| Calendar | 5 | Outside the K5 list; timing needs a separate decision (K5) | Keep its roadmap position. Cancel must be a status, not a delete; time zones |
| Forms | 7 (7.3) | MVP: forms | Submission handling, consent record and spam protection are missing |
| Landing pages | 7 (7.4) | Deferred (K5: funnels) | Not part of the MVP |
| Inbox, email | 6 (6.1–6.4) | MVP: one email channel with consent and suppression | Real delivery status; never show a send that did not happen; consent and suppression checks before sending |
| Inbox SMS, WhatsApp, voice; signup phone step | 6 (6.2) | Deferred (K5) | Not part of the MVP |
| Campaigns | 7 (7.2, 7.5) | Outside the K5 list | Bulk-send confirmation, suppression, unsubscribe |
| Automations (editor only) | 8 | Outside the K5 list | List screen, versioning, run history, safeguards absent |
| Assistants, Knowledge, AI activity | 9 | Outside the K5 list; AI auto-send deferred | Per-assistant scopes enforced server-side; provider keys through supported SaaS-OS contracts only |
| Reviews | 10 | Deferred (K5) | Not part of the MVP |
| Reports | 10 | Outside the K5 list | Metric definitions and real time windows |
| Settings: profile, business profile, notifications, custom fields | 2 and 3 | MVP where needed by the above | Locale, time zone and currency belong here (P2-D) |
| Settings: integrations, API | 12 | Not MVP | Marked "later" in the design itself |
| Settings: AI providers | 9 | Not MVP | BYO keys need per-tenant secret storage, which SaaS-OS lacks |
| Appearance and white-label | 11 (11.2) | Deferred (K5) | Not part of the MVP |
| Billing & plans, plan picker, module toggles | 11 (11.3) | Not MVP | The prototype's billing navigation does not expand the MVP |
| Templates & snapshots | 11 (11.1); message templates in 7 (7.1) | Not MVP | The design file is an empty stub |

**Screens the export lacks entirely**, recorded against their phases
without implying they are MVP:
- Form submissions list: 7 (7.3).
- Automations list: 8.
- Approval queue for AI drafts and actions: 9.
- Billing and plans: 11 (11.3).
- Templates & snapshots content: 11 (11.1).
- Audit log view: product audit events are part of 3.4; a viewer screen
  has no roadmap task yet and needs one before it is designed.

## 6. Missing-design backlog (prioritised)

Standalone Claude Design closes by 2026-12-14, so items 1–4 should be
requested before then. Each is a design request, not product work.

1. **States for every MVP screen:** loading, empty (including a brand-new
   workspace), server error, validation, and permission denied.
2. **A generic CRM version:** no dental or other industry terms or
   sample data; generic stages, fields and metrics (P2-E).
3. **Workspace membership and access management** that matches explicit
   per-workspace authorization: members list, invitations with real
   pending/accepted/expired states, role changes with confirmation and
   last-owner protection, and an agency directory that shows client
   workspaces without implying data access (P2-A, P2-B).
4. **Consent and communication preferences** that can represent several
   jurisdictions: per-contact, per-channel consent with source and
   timestamp, unsubscribe and suppression, and the email composer's
   consent and suppression warnings (P2-D).
5. **Billing screens**, only once Phase 11 billing scope is approved.
6. **The automations list screen**, once Phase 8 is approved for
   implementation.

## 7. Frontend framework: criteria only (decision P-6 stays open)

The prototype's use of React is not by itself a reason to choose React.
A later P-6 decision should score candidates on:

- **Accessibility:** semantic components, focus management, keyboard
  navigation for menus, dialogs, drawers, board drag-and-drop
  alternatives and the ⌘K palette; automated accessibility checks.
- **Internationalisation:** message catalogues with plural and gender
  rules, locale-aware date, number and currency formatting, time-zone
  handling, right-to-left readiness.
- **Routing and structure:** URL-addressable screens and records (the
  prototype has none), deep links, back button, code-splitting per
  module, a module-per-screen structure that fits the plan/module model.
- **Server state and API:** typed client generation from the FastAPI
  OpenAPI schema, caching and invalidation, pagination, optimistic
  updates only where failures are shown truthfully, stable error mapping.
- **Forms and validation:** schema-driven validation mirroring server
  rules, field-level server errors, accessible error messages.
- **Design system:** tokens for the accent and status colours, reusable
  tables, drawers, dialogs, badges, toasts and empty/error states.
- **Testing:** component tests, critical user-flow end-to-end tests,
  accessibility tests, runnable in the existing CI.
- **Build and maintenance:** build speed, dependency footprint, long-term
  support, security update cadence, licence.
- **Fit with the project:** works with the FastAPI backend and SaaS-OS
  cookie sessions and same-origin rule, the uv-based workflow, and the
  existing quality gates; ADR-0042 (SaaS-OS) makes the frontend
  product-owned.
