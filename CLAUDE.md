# CLAUDE.md --- LeadStack CRM (Temporary Product Name)

## 1. Mission

Build a **fresh product from scratch**, temporarily named
"LeadStack CRM". The name is an internal, provisional working name only
(decision K4); technical package, import, and repository names are
neutral and recorded in `docs/project/DECISIONS.md`.

The product should combine the useful features and workflows found in
the reference ZIP (`leadstack-crm-main.zip`) with the strongest relevant
features of GoHighLevel, using the supplied Claude Design project as the
initial UI/UX reference. This is an exploratory starting point: the
layout, brand, information architecture, and feature priorities are not
final.

The reference ZIP is a snapshot of the **AgentStack** CRM template
(© AgentStack.Dev), licensed under PolyForm Perimeter 1.0.0, which
includes a noncompete clause. It is feature-idea reference material
only (decision K1): do not copy its code, schemas, business rules,
text, or assets. Treat it and GoHighLevel as feature/workflow
references, not permission to copy proprietary code, branding, or
assets. Independently implement the product.

Do not reuse code from any other existing CRM repository (including the
owner's earlier `aelboum/leadstack` repository) until its ownership and
permission are confirmed and recorded in the decision log.

The goal is a cohesive, maintainable, multi-tenant CRM and marketing
platform---not a collection of disconnected mock screens.

## 2. Claude Design project

Use the Claude Design MCP at `https://api.anthropic.com/v1/design/mcp`;
authenticate using its supported `/design-login` flow if required. Never
put credentials, tokens, cookies, or secrets in source code, logs,
commits, prompts, or documentation.

Import and inspect:
`https://claude.ai/design/p/74b3900c-4db8-4b26-b938-fc41345f813f?file=LeadStack+CRM.dc.html`

Focus on all accessible files: - `LeadStack CRM.dc.html` -
`LeadStack Design Notes.dc.html` - `LeadStack Signup.dc.html` -
`mock-data.js` - `ScreenAIActivity.dc.html` -
`ScreenAssistants.dc.html` - `ScreenAutomation.dc.html` -
`ScreenCalendar.dc.html` - `ScreenCampaigns.dc.html` -
`ScreenCompanies.dc.html` - `ScreenContacts.dc.html` -
`ScreenConversations.dc.html` - `ScreenDashboard.dc.html` -
`ScreenForms.dc.html` - `ScreenKnowledge.dc.html` -
`ScreenPipeline.dc.html` - `ScreenReports.dc.html` -
`ScreenReviews.dc.html` - `ScreenSettings.dc.html` -
`ScreenTasks.dc.html` - `ScreenTemplates.dc.html` -
`ScreenWorkspaces.dc.html` - `support.js`

Inspect the full design, shared styles, mock data, interactions, and
notes. Reimplement the design using the product's chosen application
stack and reusable components. Do not ship disconnected static HTML
screens as the production application unless the repository's
established architecture explicitly requires that.

The design is a reference, not an unchangeable specification. Preserve
its visual direction while identifying missing states, design/backend
mismatches, confusing workflows, and useful improvements. Do not
silently make major product or architecture decisions.

## 3. SaaS-OS is an external package

The product must consume SaaS-OS as an external (https://github.com/aelboum/saas-os.git), versioned dependency.
SaaS-OS is not part of this repository.

Non-negotiable boundaries: - Do not edit, fork, copy, vendor, or commit
SaaS-OS source into this repository. - Do not add CRM-specific logic to
SaaS-OS. - Do not change the approved SaaS-OS package source, version,
Git SHA, dependency pin, or installation method without explicit
authorization. - Do not bypass its public contracts with undocumented
imports, private implementation access, direct database writes, or
parallel platform implementations. - Inspect the exact pinned package,
public APIs, documentation, examples, and tests before integrating it. -
Do not assume a capability exists just because it is desirable. If a
required capability is absent or unclear, document the gap and propose
options; do not modify SaaS-OS or change its pin as a workaround. - Keep
CRM/product-domain entities and workflows in this product. Reuse SaaS-OS
for shared platform capabilities it actually exposes.

At project start, record the exact dependency source and pin in project
documentation. Treat the pin as immutable unless the owner explicitly
authorizes a change.

Approved pin (decision K3, fixed through Phase 1):
`saas-os @ git+https://github.com/aelboum/saas-os@b0809eeb3448956a4dc85a5541514823ec9ceae7`
(release v0.1.2). Import only from the `saas_os` public surface:
`saas_os.api.*`, `saas_os.inference`, `saas_os.contracts`, and the
`__init__` exports of `saas_os.core.*`, `saas_os.infra.*`, and
`saas_os.control_plane.*`. Start from SaaS-OS's
`examples/consumer-scaffold/` at that commit. See
`docs/project/DECISIONS.md` and `docs/project/PHASE1-PLAN.md`.

### Intended technical direction

-   Database: PostgreSQL.
-   Identity/authentication: ZITADEL, integrated using supported
    OIDC/OAuth contracts and SaaS-OS capabilities where available.
-   Shared platform: SaaS-OS package through public contracts.
-   Product backend: product-owned API, domain services, schema, and
    migrations.
-   Frontend: follow the imported design and the repository's
    established stack; inspect before selecting or adding frameworks.
-   Application structure: prefer a modular monolith initially; do not
    split into microservices without demonstrated need and explicit
    approval.
-   Background jobs, billing, observability, secrets, and AI/inference:
    reuse SaaS-OS only where supported by the pinned version.

These are intended foundations, not proof that every integration is
already available. Verify them before implementation.

## 4. Required first step: read-only discovery

Before code changes:

1.  Inspect the repository, branch, working tree, existing files,
    manifests, runtime versions, and instructions.
2.  Search accessible current conversation files and the user's file
    library for the previously uploaded LeadStack ZIP. If it is
    unavailable after checking, report that; do not invent findings.
3.  Import and inspect all accessible Claude Design files listed above.
4.  Inspect the exact pinned SaaS-OS package, public contracts,
    examples, dependencies, and extension points.
5.  Identify the existing frontend/backend stack and choose no new
    framework until the current state is understood.
6.  Map features, screens, user journeys, entities, permissions,
    integrations, and external-service dependencies.
7.  Map every major UI capability to a backend use case/API, persistence
    model, authorization rule, asynchronous work, and tests.
8.  Identify licensing/provenance questions, security risks, missing
    design states, contradictions, and architecture gaps.
9.  Produce a phased plan with dependencies and measurable acceptance
    criteria.

The report must distinguish verified facts, inferences, assumptions,
recommendations, and blockers. Do not start broad implementation before
discovery and the plan are complete. Safe, reversible setup may proceed
only if it does not pre-empt a meaningful decision.

The Phase 0 baseline is recorded in `docs/project/PHASE0-DISCOVERY.md`.
Do not repeat completed discovery; re-verify only what may have changed
and complete the outstanding Claude Design inspection.

## 5. Candidate product capability map

This is a candidate map, not a commitment to build everything in the
first release. Refine it using the uploaded ZIP, design screens,
GoHighLevel feature research, and implementation dependencies.

### CRM

-   Contacts and companies; relationships, tags, custom fields, notes,
    and activity history.
-   Ownership, assignment, search, filtering, sorting, bulk actions.
-   Import/export with validation and actionable error reporting.
-   Tasks, reminders, and follow-up activities.

### Sales

-   Configurable pipelines and stages.
-   Opportunities/deals linked to contacts and companies.
-   Deal value, owner, expected close date, and activity history.
-   Kanban and table views; stage-change history and reporting.

### Communications

-   Unified inbox with contact context.
-   Assignment, status, internal notes, reply composer, and conversation
    history.
-   Email, SMS, WhatsApp, voice, and other channels only through
    identified and approved provider integrations.
-   Never represent a message as sent if only a mock interaction
    occurred.

### Marketing

-   Campaigns, reusable templates, forms, lead capture, and
    segmentation.
-   Landing pages where justified by scope.
-   Reporting, consent, unsubscribe, suppression, and delivery-status
    handling appropriate to each channel and jurisdiction.

### Automation

-   Trigger/condition/action workflows.
-   Draft, validation, activation, pause, and execution history.
-   Idempotency, retries, auditability, safe limits, and failure
    visibility.
-   Safeguards against loops, duplicate actions, and accidental bulk
    sends.

### Calendar and booking

-   Day/week/month views, appointments, availability, assignment,
    status, cancellation, and reminders.
-   External calendar integration only after providers and requirements
    are identified.

### AI

-   Assistant configuration and lifecycle.
-   Knowledge sources and indexing status.
-   Conversation/activity history, usage visibility, and failure states.
-   Provider/model configuration only through supported SaaS-OS
    inference contracts, if available.
-   No secrets in frontend code, browser storage, logs, or user-visible
    responses.
-   AI retrieval and actions must respect tenant isolation and
    authorization.

### Agency/workspaces

-   Agency and client-workspace experience if validated by the product
    model.
-   Clear current-workspace context, memberships, and roles.
-   Strict tenant isolation for every API and data-access path.

### Reporting, reviews, administration

-   Operational and campaign reports with defined metrics and time
    windows.
-   Review-management features only after source integrations are known.
-   Team, workspace, role, integration, notification, and custom-field
    settings.
-   Billing/plan enforcement only through supported SaaS-OS
    capabilities; do not create a parallel billing system.

Prioritize a coherent end-to-end vertical slice before expanding scope.
Do not implement every candidate feature in one unreviewed pass.

## 6. The backend must fit the layout

A page is not complete merely because it looks like the design. Every
implemented control must correspond to defined behavior and appropriate
backend enforcement.

Maintain a feature map containing: - Screen/component and user action. -
API endpoint or application use case. - Request/response schema. -
Domain service and persistence operations. - Tenant and permission
checks. - Loading, empty, success, validation-error, permission-denied,
and server-error states. - Background job/provider dependency, if
applicable. - Automated tests. - Status: design-only, planned,
implemented, or verified.

### UI rules

-   Preserve the supplied visual direction and core information
    hierarchy.
-   Extract reusable components, design tokens, navigation, forms,
    tables, badges, dialogs, drawers, and feedback states.
-   Keep mock data isolated and easy to replace.
-   Never leave a production-looking control that silently does nothing.
-   If a capability is unimplemented, label it unavailable, disabled, or
    prototype-only; never fake success.
-   Handle loading, empty, error, validation, and permission-denied
    states.
-   Build deliberate responsive behavior and support keyboard
    navigation, semantic labels, focus, and accessible contrast.
-   Never expose another tenant's records, secrets, or unauthorized
    operational details.

### Backend rules

-   Design APIs around product use cases and domain boundaries, not
    merely around visual components.
-   Validate all inputs server-side.
-   Enforce authorization and tenant isolation on every request and
    data-access path.
-   Use database constraints and transactions for invariants.
-   Use versioned migrations; never rely on manual production database
    edits.
-   Paginate large lists.
-   Define stable error responses without leaking sensitive internals.
-   Make retried jobs and external side effects idempotent where
    appropriate.
-   Put external providers behind explicit adapters/contracts.
-   Test successful flows and denied/cross-tenant access.
-   Avoid speculative features, unnecessary dependencies, and premature
    abstractions.

## 7. Security, privacy, and tenancy

Security and tenant isolation are release-blocking: - Resolve identity
through the approved identity/platform integration. - Derive active
tenant/workspace context from trusted, validated context. A
client-supplied tenant ID is not sufficient authorization. - Enforce
authorization in backend services and data access, not only in the
frontend. - If PostgreSQL row-level security is used, test
transaction/session context and connection reuse carefully. - Prevent
cross-tenant access through APIs, exports, jobs, search, caches, and AI
retrieval. - Apply least privilege to credentials and integrations. -
Store secrets only through the approved secret-management approach;
never commit them or expose them in frontend bundles. - Avoid logging
tokens, passwords, sensitive customer data, full message bodies, or
provider payloads unnecessarily. - Audit relevant security-sensitive and
administrative actions. - Clarify and implement applicable consent,
retention, deletion, and export requirements. - Treat AI prompts,
retrieved documents, imported content, and external messages as
untrusted. - Do not claim legal/regulatory compliance without evidence
and a defined verification process.

## 8. Quality gates

Use existing repository checks and SaaS-OS consumer contracts. Never
invent results or silently skip failures.

Define appropriate gates for: - Formatting and linting. - Static type
checking. - Import/dependency boundary checks, where available. - Unit
and API/integration tests. - Migration validation. - Authorization and
cross-tenant isolation tests. - Frontend component and critical
user-flow tests. - Accessibility checks for primary workflows. -
Dependency and secret scanning. - Production build. - Clean
installation/build as a consumer of the exact pinned SaaS-OS package.

Run narrow checks during implementation and broader gates at phase
boundaries. Report exact commands and actual results. Never weaken
tests, lint, typing, security checks, or build configuration just to
obtain a green result. Propose and seek approval for any exception
before introducing it.

## 9. Autonomy and approval boundaries

Within an explicitly approved phase, execute autonomously through
**Inspect → Plan → Implement → Test → Audit → Report**. Do not ask for
routine permission for safe, reversible steps already in scope. Prepare
the next unblocked task after reporting when it remains within the
approved scope.

Stop and request explicit approval before: - Material product-scope
changes or consequential architecture decisions not covered here. -
Changing the SaaS-OS dependency pin/source/contract or editing
SaaS-OS. - Adding a major framework, database, identity system, or
external service not already approved. - Accepting a material
licensing/IP risk. - Destructive data operations or removing user
work. - Risky production configuration, secrets, or access-control
changes. - Committing, pushing, opening a PR, merging, tagging,
releasing, publishing, or deploying. - Running migrations or tests
against a real production system. - Spending money or enabling paid
services.

Authorization to implement/test does not imply authorization to commit
or push.

### Protect existing work

-   Inspect `git status`, branch, and diff before editing.
-   Preserve all pre-existing user changes.
-   Do not reset, discard, overwrite, or reformat unrelated changes.
-   Avoid unrelated refactors and destructive cleanup.
-   Keep temporary/generated artifacts controlled.
-   If unexpected changes or concurrent processes appear, inspect and
    protect the work before continuing.

## 10. Delivery phases

`ROADMAP.md` is authoritative for phase numbering, scope, and exit
criteria. Always refer to phases by the roadmap's numbers:

| Roadmap phase | Scope |
| --- | --- |
| 0 | Discovery and baseline audit |
| 0.5 | Foundational decisions (K1–K5) |
| 1 | Product foundation |
| 2 | Identity, workspaces, and tenant isolation |
| 3 | Core CRM (contacts, companies) |
| 4 | Sales, tasks, and pipelines |
| 5 | Calendar and appointment booking |
| 6 | Conversations and communications |
| 7 | Marketing, forms, and campaigns |
| 8 | Marketing automation |
| 9 | AI assistants and knowledge |
| 10 | Reviews, reporting, and business insights |
| 11 | Agency management, white label, and billing |
| 12 | Integrations and API platform |
| 13 | Production hardening |
| 14 | Release preparation and launch |
| 15 | Post-launch improvement |

The approved MVP scope (decision K5) is recorded in
`docs/project/DECISIONS.md`; features outside it are deferred even when
a roadmap phase mentions them.

Do not attempt the whole product in one unreviewed pass. Each phase
requires acceptance criteria, test evidence, known limitations, and an
explicit status. Phase completion does not authorize commits, pushes,
releases, or deployment.

## 11. Documentation and reporting

Maintain concise, current documentation: - `README.md`: product purpose,
setup, development, testing, limitations. - Architecture overview:
product/platform boundary and module responsibilities. - SaaS-OS
integration note: exact pin, public APIs used, verified capabilities. -
Feature map: UI → use case/API → data → authorization → tests. - Data
model/migration notes. - Security and tenancy assumptions. - Roadmap and
acceptance criteria. - Decision log for consequential decisions. -
Implementation report after each phase.

Project records live in `docs/project/`: `DECISIONS.md` (decision log),
`PROGRESS.md` (verified current state), `PHASE0-DISCOVERY.md` (baseline
findings), and `PHASE1-PLAN.md` (repository and scaffold plan).

Reports must separate code written from behavior actually tested and
verified. Include failing checks, untested paths, external-service
dependencies, unresolved questions, and repository/commit state where
relevant.

## 12. Definition of done

A feature is done only when: 1. Its behavior matches the approved design
or a documented improvement. 2. Its controls perform the advertised
actions. 3. Backend behavior and data persistence are implemented. 4.
Server-side validation, authentication, authorization, and tenant
isolation are enforced. 5. Loading, empty, success, and failure states
are handled. 6. Relevant tests pass, including negative authorization
tests. 7. It respects SaaS-OS package boundaries. 8. Documentation and
feature map are updated. 9. No unapproved scope, dependency,
architecture, or release changes occurred. 10. The report clearly states
what is verified and what remains unverified.

**North star:** Build a cohesive, secure, independently implemented CRM
and marketing platform whose backend genuinely supports the Claude
Design interface, consuming SaaS-OS as a stable external platform
dependency. Keep the product name, visual layout, and feature priorities
open to informed refinement.
