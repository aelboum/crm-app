# LeadStack CRM — Master Product Roadmap

**Status:** Phase 1 complete (CI passed on the pushed commit, 2026-10-21); Phase 2 complete (2026-10-24, see §7). Current state: `docs/project/PROGRESS.md`
**Product name:** LeadStack CRM (internal provisional name only; see decision K4)
**Architecture:** New product consuming SaaS-OS as an external package
**SaaS-OS pin:** `b03d87a5272924d1e413c144dc5c3b41ac430580` (v0.5.0; decisions K3, K3.1 and K3.2)
**Product approach:** Modular monolith initially
**Database:** PostgreSQL
**Identity:** ZITADEL, subject to compatibility verification
**Frontend design:** Claude Design prototype, inspected read-only on 2026-10-21 as a design reference (`docs/project/DESIGN-INSPECTION.md`); not finalized
**Reference ZIP:** AgentStack CRM template (PolyForm Perimeter 1.0.0, noncompete); feature-idea reference only, no reuse of code, schemas, business rules, text, or assets (decision K1)

Decisions are recorded in `docs/project/DECISIONS.md`; the verified current
state is recorded in `docs/project/PROGRESS.md`.
**Primary objective:** Build a production-ready, multi-tenant CRM and marketing platform with a coherent user experience and reliable backend.

---

# 1. Product Vision

Build a new SaaS product combining the most valuable capabilities identified in:

1. The reference ZIP `leadstack-crm-main.zip` (a snapshot of the AgentStack CRM template), used for feature ideas only.
2. GoHighLevel's relevant CRM, sales, marketing, automation, communication, and agency-management capabilities.
3. The screens and workflows designed in Claude Design.
4. Shared platform capabilities provided by SaaS-OS.

The goal is not to reproduce every feature of either reference product.

We will build a cohesive product that provides real, secure, tested functionality behind its interface.

The product must be independently implemented, maintainable, and capable of evolving without compromising SaaS-OS.

## Core principles

* Build a new product repository.
* Consume SaaS-OS as an external, explicitly version-pinned dependency.
* Never modify SaaS-OS to satisfy product-specific requirements.
* Keep CRM business logic in the product.
* Reuse verified platform capabilities rather than duplicating them.
* Use PostgreSQL for product data.
* Use ZITADEL for identity where supported by verified integration contracts.
* Keep the application a modular monolith unless evidence justifies a different architecture.
* Make backend functionality match the approved frontend.
* Implement tenant isolation and authorization from the beginning.
* Require automated tests and security checks for every meaningful feature.
* Keep the initial design and product name provisional until approved.
* Do not introduce unnecessary infrastructure or microservices.
* Do not ship decorative controls that imply nonexistent functionality.

---

# 2. How to Use This Roadmap

This document is the project's master plan.

At every stage, Claude Code must:

1. Read this roadmap and the repository's `CLAUDE.md`.
2. Inspect the current Git state and identify existing user changes.
3. Identify the current phase and its acceptance criteria.
4. Review previous progress reports and recorded decisions.
5. Determine which tasks are complete, incomplete, blocked, or unverified.
6. Continue from the earliest incomplete task within the currently authorized scope.
7. Implement and test in small, coherent increments.
8. Update the project's progress record when authorized.
9. Run relevant quality and security checks.
10. Report evidence, failures, risks, and the next recommended action.

**Never mark a phase complete because its code exists.** Completion requires the specified tests, acceptance criteria, and evidence.

If work stops unexpectedly, resume from the recorded state rather than repeating completed work or inventing progress.

If the actual repository state contradicts this roadmap, investigate and report the discrepancy before proceeding.

---

# 3. Project Governance and Approval Boundaries

## 3.1 Work Claude Code may perform autonomously

Within an explicitly approved phase, Claude Code may:

* Inspect code and documentation.
* Develop a detailed implementation plan.
* Implement approved features.
* Add product-owned tests and migrations.
* Run linters, type checkers, tests, security checks, and builds.
* Fix defects introduced by its own changes.
* Audit its implementation.
* Update progress documentation.
* Prepare the next unblocked task.
* Report completed work and outstanding risks.

Avoid unnecessary pauses between routine tasks within the approved scope.

## 3.2 Actions requiring explicit approval

Claude Code must stop and request approval before:

* Creating or selecting a fundamentally different architecture.
* Changing the SaaS-OS dependency pin.
* Modifying SaaS-OS.
* Expanding the approved product scope substantially.
* Performing destructive database operations.
* Changing production infrastructure.
* Deploying to production.
* Committing, pushing, merging, tagging, or releasing.
* Publishing packages or making a public release.
* Incurring new external service costs.
* Performing actions that could expose user data or secrets.
* Making irreversible changes.
* Resolving a material licensing or intellectual-property uncertainty by assumption.

A previously approved phase does not automatically authorize these actions.

## 3.3 Preserve user work

Before making changes:

* Inspect `git status`.
* Identify staged, unstaged, and untracked user files.
* Never discard or overwrite unrelated changes.
* Never use destructive Git commands as a cleanup shortcut.
* Do not reset, rebase, or rewrite history without explicit approval.

---

# 4. Phase 0 — Discovery and Baseline Audit

**Status:** Evidence complete. Task 0.3 completed 2026-10-21 from an owner-supplied file export rather than the MCP workflow (`docs/project/DESIGN-INSPECTION.md`). Findings: `docs/project/PHASE0-DISCOVERY.md`.

## Objectives

Understand the actual starting point before selecting the repository, dependency pin, or implementation architecture.

## Tasks

### 0.1 Inspect the product repository

* Identify the repository root and Git state.
* Inspect existing files and project instructions.
* Identify existing source code, dependencies, tests, and CI.
* Determine whether the repository is empty, initialized, or contains prior work.
* Record constraints and existing changes.

### 0.2 Locate and inspect the LeadStack ZIP

* Find the previously uploaded archive.
* Inventory its source tree and major features.
* Identify its stack, data models, integrations, and security boundaries.
* Separate implemented functionality from advertised functionality.
* Inspect its actual licence and provenance.
* Record which ideas are useful as references.
* Flag uncertain reuse rights.

The ZIP is a feature reference, not the foundation of the new product.

Do not copy restricted source code or assets.

### 0.3 Import and inspect Claude Design

Import the supplied project through the supported Claude Design MCP workflow.

Inspect the available screens, design notes, shared styles, mock data, and interactions.

Identify:

* Existing pages and navigation.
* Reusable UI patterns.
* User workflows.
* Missing states.
* Required backend operations.
* Layout inconsistencies.
* Opportunities for improvement.

Do not implement the frontend yet.

### 0.4 Audit SaaS-OS

Identify the actual package source and intended immutable pin.

Inspect the package's documented public contracts, tests, examples, and runtime requirements.

Verify support for:

* Application bootstrap.
* Identity integration.
* Tenant context and authorization.
* PostgreSQL-related responsibilities.
* Background jobs.
* Billing and entitlements.
* Secrets.
* Observability.
* AI/inference.
* Webhooks.
* Health and readiness.
* Consumer testing.

Record every capability as verified, partially available, unavailable, or unverified.

### 0.5 Compare product requirements

Compare:

* LeadStack reference features.
* Relevant GoHighLevel features.
* Claude Design screens.
* SaaS-OS capabilities.

Create a feature-to-backend traceability matrix.

### Deliverables

* Discovery report.
* ZIP feature and licence assessment.
* Claude Design screen inventory.
* SaaS-OS compatibility matrix.
* Initial security risk register.
* Proposed product architecture.
* MVP recommendation.
* Open-decision list.

## Exit criteria

Phase 0 is complete when the evidence is sufficient to decide the product repository, source-control approach, dependency pin, and initial architecture.

**No product implementation should be considered authorized merely because Phase 0 is complete.**

---

# 5. Phase 0.5 — Resolve Foundational Decisions

**Status:** K1–K5 and the workspace/tenant decision approved by the owner on 2026-10-20 and recorded in `docs/project/DECISIONS.md`. The recommended directions below are retained for context; the decision log is authoritative.

Record the following decisions before creating the product foundation.

## K1. Product base

Choose the starting point for the product.

**Recommended direction:** A new product built from scratch, with no fork or dependency on the LeadStack CRM application source.

Use the ZIP for feature discovery only, subject to licence review.

## K2. Repository strategy

Choose the repository in which the new product will live.

**Recommended direction:** A separate, clean Git repository, independent of the SaaS-OS repository.

Preserve the original LeadStack ZIP and SaaS-OS repository unchanged.

Do not select a repository based solely on its name. Inspect its current state first.

## K3. SaaS-OS pin

Choose the exact immutable SaaS-OS commit that the new product will consume.

**Recommended direction:** Use the verified, approved package commit and keep it fixed for the initial implementation.

Do not assume an old commit is still the correct choice. Verify the actual current package state and compatibility.

## K4. Product name

Keep `leadstack-crm` as a provisional working name.

Record the eventual name separately from technical package and repository names.

Do not delay the technical foundation solely to brainstorm branding, provided no naming or licensing issue blocks the project.

## K5. Initial market and scope

Confirm the initial target users, deployment model, and first-release feature priorities.

Keep these decisions documented so that later feature requests do not silently expand the MVP.

## Exit criteria

* K1–K5 are recorded.
* The repository strategy is confirmed.
* The SaaS-OS pin is verified.
* The ZIP's permitted use is understood.
* The initial MVP scope is approved.

---

# 6. Phase 1 — Product Foundation

**Status:** Complete. Implemented and verified locally (2026-10-20); CI passed on the exact pushed commit `dbb1560` (GitHub Actions run 39652641595, 2026-10-21). Evidence: `docs/project/PROGRESS.md`.

## Objectives

Create a clean, maintainable product foundation that consumes SaaS-OS correctly.

## Tasks

### 1.1 Repository and project structure

* Establish the approved product repository.
* Configure the selected language and framework.
* Define application, domain, infrastructure, and test boundaries.
* Add development instructions and project documentation.
* Configure formatting, linting, type checking, and test tooling.
* Configure CI without publishing or deploying.

### 1.2 SaaS-OS integration

* Add the approved immutable package dependency.
* Follow the documented consumer installation process.
* Use supported public APIs and contracts.
* Verify the reference consumer's relevant integration patterns.
* Avoid importing internal modules that are not part of the supported public contract.
* Add consumer-level integration tests.

### 1.3 Configuration and secrets

* Define required environment variables.
* Provide safe example configuration.
* Validate configuration at startup.
* Keep secrets outside source control.
* Redact credentials and sensitive data from logs.

### 1.4 Observability

* Establish structured logging.
* Integrate the tracing the pinned SaaS-OS supports (OpenTelemetry with a console exporter at v0.5.0).
* Metrics: SaaS-OS v0.5.0 does not provide metrics. Record this as a known gap; do not build a parallel metrics platform without an approved decision.
* Add health and readiness checks where appropriate.
* Ensure logs identify failures without leaking customer information.

### 1.5 Quality gates

Configure and run appropriate checks, including:

* Formatting.
* Linting.
* Static type checking.
* Import or architecture boundary checks.
* Unit tests.
* Integration tests.
* Dependency security auditing.
* Secret scanning.
* Build verification.

Use the actual language and tooling selected after discovery.

## Exit criteria

* The new product builds successfully.
* The SaaS-OS dependency resolves to the approved pin.
* The application starts using supported platform contracts.
* CI passes on the exact code being evaluated.
* No SaaS-OS source code has been modified.
* The repository is clean of unintended changes.

---

# 7. Phase 2 — Identity, Workspaces, and Tenant Isolation

**Status:** Complete (2026-10-24): integration suite, ZITADEL sign-in test and browser sign-in from the LeadStack start page passed on current code; CI passed on the final code commit `5c06d48` (run 40094376772); every security finding fixed or dispositioned by the owner (`PHASE2-SECURITY-REVIEW.md`). Plan: `docs/project/PHASE2-PLAN.md`. Decisions P2-A to P2-E, Q6 (role matrix) and Q-purge approved 2026-10-21 in `docs/project/DECISIONS.md`.

* **Done and CI-verified** (commit `a069a6a1675802139e8862d0f639388d521b95c7`, GitHub Actions run 39675570028): the four role templates and permission catalogue; registration of the granted permissions in the migration step (no roles created or granted anywhere); structural guards that keep tenant-owned tables out and fix the RLS, privilege and purge-coverage rules for future ones; two read-only routes, `GET /v1/workspaces/{id}` and `GET /v1/workspaces/{id}/members`, with backend permission checks.
* **Frontend (F1, 2026-10-22, decision P-6.1):** React single-page app served by the API under `/app`: sign-in, opening a workspace, and member management with Owner confirmations and refusal messages (`PHASE2-PLAN.md` §11.3). Not yet exercised in a real browser against ZITADEL.
* **Done since (2026-10-24, decision P2-F; all CI-verified):** the workspace directory (`5f8e475`, run 40085049780), workspace settings (`d833deb`, run 40086027721), invitations in Q4 manual-link mode with SaaS-OS acceptance and Q5 role confirmation, email delivery behind `INVITATION_DELIVERY` (`b3bf1d4`, run 40087539620), the review fixes (`8e00048`, run 40087955496), and the Phase 2 security review, owner-reviewed, with a second review of this work: no critical or high finding open (`PHASE2-SECURITY-REVIEW.md`). **Final verification (2026-10-24):** full integration suite against `crm_app_test`, 229 passed (before and after the sign-out fix); ZITADEL sign-in test (`tests/identity`, through ZITADEL's session API, P2-F), 1 passed; browser sign-in by the owner from `/app` through ZITADEL's login and back, `/auth/me` 200 with the user ID only, sign-out ending the session. That check found sign-out leaving the ZITADEL session alive: reduced by decision P2-G (`5c06d48`, run 40094376772), residual accepted as Low for Phase 13. The production email provider (Q3) is a launch task.
* **Branded sign-in (2026-10-24, owner-approved before slice 3C):** the signed-out `/app` and invitation screens follow the sign-in parts of the design's `LeadStack Signup.dc.html` (`DESIGN-FIDELITY.md` §4e). The one action still starts the existing ZITADEL OIDC flow at `/auth/login`; sign-out (P2-G) is unchanged. Commit `04a4bb6`, CI run 40097066377 green. The rest of that prototype, self-service signup and public workspace creation, stays unimplemented (excluded by P2-C at the time; now planned under S-1, below). Known gap: a failed or cancelled sign-in ends on SaaS-OS's plain JSON answer at `/auth/callback` (owner decision pending, `PROGRESS.md`).
* **Self-service signup (decision S-1, approved 2026-10-24 for implementation planning; supersedes P2-C's exclusion):** plan, launch gates and the audit in `docs/project/SIGNUP-PLAN.md`. Stages: A security and configuration → B shared provisioning service → C signup backend (signup record, `POST /v1/signups`, recovery) → D frontend (Create account, workspace name) → E verification and release readiness. **Status:** planned; stage A started: the `SIGNUP_ENABLED` kill switch (default off, refused in production until launch gates LG-1 to LG-10 pass) and limit settings are implemented with unit tests; L4 investigated and reduced, not closed (closes at LG-5 on the production edge). Exit criterion: every launch gate has evidence; until then signup stays off in production.
* **Blocked by gates** (`PHASE2-PLAN.md` §14):
  * **G1:** passed 2026-10-23 (`DECISIONS.md` G1): SaaS-OS v0.5.0's public registration API is pinned (K3.2) and the product's purge participant is registered and tested. Each tenant-owned table still needs its own approval, manifest entry and RLS tests.
  * **G2:** the provisioning command is implemented and validated against the test database (commit `19e7dce`, CI run 39742030028 green); provisioning any real workspace needs owner authorization.
  * **G-LOCK:** Owner-, role- and membership-changing routes are implemented with a per-workspace lock; local concurrency tests against the test database show the last active Owner is never removed (commit `19e7dce`). Paths outside the product are covered by an operator rule only (`PHASE2-PLAN.md` §5.4). CI run 39742030028 green.
  * **G3/G4:** real invitation delivery needs an email provider (Q3); Q4 and Q5 were decided 2026-10-22, but the flow also needs G1 for its product table.
* **External dependencies:** two upstream SaaS-OS requests were opened on 2026-10-22: purge-participant registration (aelboum/saas-os#87, blocks G1) and adding permissions to existing workspaces (aelboum/saas-os#88).
* **Proven since (slice 3A, 2026-10-23):** runtime RLS isolation of product data on the first tenant-owned tables (`contact`, `company`): as the runtime role, no rows without or with another workspace set, no writes into another workspace, composite foreign keys refusing cross-workspace links with RLS bypassed, every record route answering another workspace's IDs with 404, and the operator purge removing exactly one workspace's rows (`tests/integration/test_crm_tables.py`, `test_record_routes.py`, `test_record_lists.py`). Phase 2 security review: done read-only on 2026-10-24 (`docs/project/PHASE2-SECURITY-REVIEW.md`): no critical or high finding; its two evidence gaps and two defects are fixed; it awaits the owner's review and does not complete Phase 2.

## Objectives

Establish secure identity and tenant boundaries before implementing business data.

## Tasks

### 2.1 Identity integration

* Integrate ZITADEL using verified OIDC/OAuth contracts.
* Establish login, logout, and session handling.
* Validate tokens server-side.
* Handle unauthorized and expired sessions.
* Define the application identity model.
* Avoid creating a second identity system unnecessarily.

### 2.2 Workspace and tenant model

Determine which responsibilities are owned by SaaS-OS and which belong to the product.

Implement only the product-owned parts.

Define:

* Workspace ownership.
* Membership.
* User roles and permissions.
* Workspace selection.
* Tenant context propagation.
* Workspace lifecycle.

### 2.3 Authorization

* Enforce authorization on the server.
* Define permissions for sensitive operations.
* Deny access by default.
* Prevent client-controlled tenant identifiers from becoming trusted authorization evidence.

### 2.4 PostgreSQL security

* Establish the product database connection.
* Define migration ownership.
* Design transaction boundaries.
* Evaluate and implement RLS where appropriate.
* Test isolation across workspaces.
* Ensure background jobs preserve the same tenant boundaries.

### 2.5 Security tests

Test that:

* One tenant cannot access another tenant's contacts.
* Cross-tenant searches and exports are blocked.
* Unauthorized users cannot perform privileged operations.
* Tenant context cannot be forged.
* Jobs cannot accidentally process another tenant's data.

## Exit criteria

* Authentication works against the intended identity provider.
* Workspace context is trustworthy.
* Authorization is enforced server-side.
* Tenant-isolation tests pass.
* Database migrations are reproducible.
* No known critical cross-tenant access vulnerability remains.

---

# 8. Phase 3 — Core CRM

**Status:** In progress. Slice 3A backend (stages 3A.1–3A.3: contact and company tables, record API, lists) is done and CI-verified (commits `2a6ea5b`, `dad9132`, `58cb900`, `8724359`; GitHub Actions run 40036417310 on `b288a4b`, all four jobs green). Decision P3-A; plan `docs/project/PHASE3-PLAN.md` §19. Slice 3A.4 (Contacts and Companies screens) is done and CI-verified (commits `77f2c29`, `d20f743`, hardening `8787e6c`; run 40042487578 on `5288398`, all four jobs green); flows checked in Chrome at desktop width after a ZITADEL sign-in on 2026-10-24 (phone width not yet). Slice 3B (notes and activity, decision P3-B, `PHASE3-PLAN.md` §21) is done: increments 3B.1-3B.5 CI-verified, security review without critical or high findings, browser-checked at desktop width (§21.4). Exports (3E1, 3E2) and tags (3C, decision P3-C) are done and CI-verified. Custom fields (3D, decision P3-D) are done. Import (3F, decision P3-F) is done. Phase 3 is complete; work proceeds under the owner's autonomous-development mandate (decision M1).

## Objectives

Build the first genuinely useful CRM experience.

## Modules

### 3.1 Contacts

* Create, view, edit, and archive contacts.
* Search and filter.
* Pagination and sorting.
* Tags.
* Custom fields.
* Assigned team members.
* Notes.
* Activity history.
* Import and export, subject to security requirements.

### 3.2 Companies

* Create, view, edit, and archive companies.
* Associate contacts with companies.
* Search and filter.
* Show relevant company activity.

### 3.3 Contact details

Connect the UI to actual backend operations.

Support:

* Contact information.
* Related companies.
* Notes.
* Tasks.
* Activity timeline.
* Associated opportunities.
* Communication history when that module becomes available.

### 3.4 Data integrity

* Validate input server-side.
* Enforce tenant boundaries.
* Handle duplicate records deliberately.
* Use pagination for large datasets.
* Provide clear error and empty states.
* Record appropriate audit events.

## Exit criteria

* Contacts and companies are persisted in PostgreSQL.
* UI actions use real backend operations.
* CRUD, search, filters, and pagination work.
* Authorization tests pass.
* Cross-tenant tests pass.
* Automated tests cover important business rules.

---

# 9. Phase 4 — Sales, Tasks, and Pipelines

**Status:** Done (decisions P4, P4-B, P4-C): 4A pipeline and stages, 4B deals and 4C tasks are built, tested and pushed.

## Objectives

Implement the daily sales-management workflow.

## Tasks

### 4.1 Tasks

* Create and edit tasks.
* Assign users.
* Set due dates.
* Track completion.
* Associate tasks with contacts and opportunities.
* Filter overdue and upcoming tasks.

### 4.2 Opportunities

* Create and edit opportunities.
* Associate contacts and companies.
* Assign owners.
* Store values and expected closing dates.
* Track opportunity status.

### 4.3 Pipelines

* Define pipelines and stages.
* Display Kanban and table views.
* Move opportunities between stages.
* Validate stage changes.
* Track relevant history.
* Support filtering and sorting.

### 4.4 Dashboard foundations

Add real metrics for:

* Total contacts.
* Active opportunities.
* Pipeline value.
* Tasks due.
* Recent activity.

Only show metrics whose definitions are documented and whose calculations are correct.

## Exit criteria

* Sales workflows persist correctly.
* Stage transitions enforce business rules.
* Users cannot access other tenants' sales records.
* Dashboard metrics reconcile with stored data.
* Important operations have automated tests.

---

# 10. Phase 5 — Calendar and Appointment Booking

**Status:** In progress (decision P5-A, started by the owner on 2026-10-28). Slice 5A built: appointments, views, status, cancel, rescheduling, conflict detection, time zones, contact association, team assignment. Slice 5B built: business hours, availability, the outside-hours warning (decision P5-B). Slice 5C built: public booking pages with the visitor's own link to cancel (decision P5-C). Reminders and notifications (need a delivery channel) remain.

## Objectives

Provide reliable scheduling and appointment management.

## Tasks

* Calendar views.
* Appointment creation and editing.
* Contact association.
* Team member assignment.
* Appointment status.
* Availability management.
* Conflict detection.
* Time-zone handling.
* Notifications and reminders.
* Cancellation and rescheduling.

Before implementing external calendar synchronization, evaluate its complexity and business value.

## Exit criteria

* Appointments persist correctly.
* Time zones are handled consistently.
* Scheduling conflicts are detected.
* Tenant isolation is enforced.
* Notifications are reliable and appropriately retried.
* Important scheduling edge cases are tested.

---

# 11. Phase 6 — Conversations and Communications

**Status:** Not started.

## Objectives

Create the foundations of a unified customer communications experience.

## Tasks

### 6.1 Conversation model

* Conversations.
* Messages.
* Contact association.
* Assignment.
* Conversation status.
* Internal notes.
* Message history.
* Search and filtering.

### 6.2 Provider integration architecture

Design provider adapters for supported channels.

Potential channels include:

* Email.
* SMS.
* WhatsApp.
* Voice.

Do not assume every provider or channel is available in the initial release.

Select providers based on market requirements, cost, reliability, legal requirements, and technical compatibility.

### 6.3 Delivery and reliability

* Verify inbound webhook signatures.
* Make message processing idempotent.
* Track delivery states.
* Retry transient failures safely.
* Prevent duplicate message processing.
* Redact secrets and sensitive data.
* Handle provider outages.

### 6.4 User interface

Implement:

* Conversation list.
* Active conversation.
* Contact context.
* Reply composer.
* Assignment controls.
* Status changes.
* Loading, empty, error, and delivery states.

## Exit criteria

* At least one approved communication channel works end to end.
* Provider credentials are managed securely.
* Message processing is idempotent.
* Webhooks are verified.
* Tenant boundaries are tested.
* The interface reflects real delivery and error states.

---

# 12. Phase 7 — Marketing, Forms, and Campaigns

**Status:** In progress. 7.3 Forms built (slice 7A, decision P7-A); 7.5 consent and suppression management built (slice 7B, decision P7-B); 7.4 landing pages deferred; templates, campaigns, unsubscribe processing and the remaining safeguards wait for the email channel (Phase 6).

## Objectives

Build useful marketing capabilities on top of the CRM.

## Tasks

### 7.1 Templates

* Email templates.
* Reusable message templates.
* Editing and preview.
* Validation and versioning where appropriate.

### 7.2 Campaigns

* Campaign creation.
* Audience selection.
* Scheduling.
* Sending.
* Delivery tracking.
* Campaign status.
* Basic performance metrics.

### 7.3 Forms

* Form configuration.
* Field validation.
* Submission handling.
* Contact creation or update.
* Spam protection.
* Consent capture where required.

### 7.4 Landing pages

Evaluate the business case and architecture before building a complete page builder.

A limited initial form or landing-page experience may be more appropriate than replicating a full visual website builder.

### 7.5 Marketing safeguards

* Consent and suppression management.
* Unsubscribe processing.
* Rate limiting.
* Bounce and complaint handling where supported.
* Tenant-specific sender configuration.
* Auditability.
* Provider compliance requirements.

## Exit criteria

* Approved campaign flows work end to end.
* Contact segmentation is tenant-safe.
* Suppression rules are enforced.
* Sending operations are retry-safe.
* Campaign metrics are based on real provider events or clearly defined internal events.

---

# 13. Phase 8 — Marketing Automation

**Status:** Not started.

## Objectives

Build a reliable automation engine that supports the automation UI.

## Tasks

### 8.1 Workflow definition

* Triggers.
* Conditions.
* Actions.
* Branches.
* Workflow versions.
* Activation and deactivation.

### 8.2 Execution engine

* Persistent execution state.
* Background processing.
* Retry policies.
* Idempotency.
* Failure tracking.
* Cancellation where appropriate.
* Execution history.
* Operational visibility.

### 8.3 Initial automation actions

Start with a limited set, such as:

* Add a tag.
* Assign a contact.
* Create a task.
* Update an approved field.
* Send an approved communication.
* Wait until a specified time.

Add further actions only after the initial engine is reliable.

### 8.4 Visual builder

Connect the automation screen to real workflow definitions.

Validate workflows before activation.

The UI must not imply that unsupported nodes or actions are executable.

## Exit criteria

* Workflows can be created, validated, activated, and deactivated.
* Executions are durable and observable.
* Retries do not cause unintended duplicate actions.
* Failures can be diagnosed.
* Tenant isolation and permissions are enforced.
* Workflow behavior is tested.

---

# 14. Phase 9 — AI Assistants and Knowledge

**Status:** Not started.

**Dependency:** Verified SaaS-OS inference capabilities or an explicitly approved product-side integration strategy.

## Objectives

Introduce AI functionality without weakening tenant isolation or platform boundaries.

## Tasks

### 9.1 AI provider integration

Verify which inference capabilities SaaS-OS actually provides.

Determine how the product should handle:

* Provider selection.
* Model selection.
* Credentials.
* Custom endpoints.
* Usage limits.
* Cost accounting.
* Timeouts.
* Retries.
* Provider failures.

Do not invent unsupported SaaS-OS APIs.

### 9.2 Assistants

* Assistant configuration.
* Instructions and behavior.
* Activation controls.
* Execution history.
* Usage visibility.
* Error handling.

### 9.3 Knowledge

* Knowledge-source management.
* Document ingestion.
* Parsing and indexing.
* Retrieval.
* Access control.
* Re-indexing and deletion.
* Source attribution where appropriate.

### 9.4 AI security

* Enforce tenant-safe retrieval.
* Treat retrieved content as untrusted input.
* Defend against prompt injection.
* Restrict tools and external actions.
* Avoid leaking secrets into prompts or logs.
* Apply usage limits.
* Make consequential actions subject to appropriate authorization.

### 9.5 Initial AI use cases

Prioritize measurable use cases, such as:

* Drafting a contact response.
* Summarizing a conversation.
* Suggesting follow-up tasks.
* Answering questions using authorized knowledge sources.

Avoid building a general autonomous agent platform before the core CRM and security foundations are proven.

## Exit criteria

* At least one useful AI workflow works end to end.
* Provider failures are handled.
* Usage is measured where feasible.
* Knowledge retrieval respects tenant boundaries.
* AI operations have appropriate authorization and observability.
* Security tests cover the main failure modes.

---

# 15. Phase 10 — Reviews, Reporting, and Business Insights

**Status:** Not started.

## Objectives

Provide reliable reporting and business-management capabilities.

## Tasks

* CRM activity reporting.
* Pipeline performance.
* Sales conversion metrics.
* Campaign performance.
* Task and appointment reporting.
* Review management, where supported by selected providers.
* Date-range filtering.
* Export controls.
* Role-appropriate access.

Define each metric precisely before displaying it.

Avoid misleading charts based on incomplete or synthetic data.

## Exit criteria

* Metrics have documented definitions.
* Aggregations respect tenant boundaries.
* Reports are tested against known datasets.
* Exports are permission-checked and bounded.
* Large reports do not block ordinary application operations.

---

# 16. Phase 11 — Agency Management, White Label, and Billing

**Status:** Not started.

## Objectives

Support agencies and businesses managing multiple client workspaces.

## Tasks

### 11.1 Agency and workspace experience

* Workspace selector.
* Client workspace management.
* Membership administration.
* Roles and permissions.
* Workspace-specific configuration.
* Clear workspace context throughout the interface.

Determine how agency relationships fit with SaaS-OS tenancy before implementing the data model.

A product workspace is the user-facing representation of a SaaS-OS tenant, not a second security boundary (decision D-WS in `docs/project/DECISIONS.md`). An agency may relate to multiple client workspaces, but every cross-tenant access path must be explicitly authorized and enforced through SaaS-OS contracts. A workspace listing or membership index must never bypass SaaS-OS authorization or tenant isolation.

### 11.2 White-label configuration

Evaluate:

* Branding.
* Logos.
* Colors.
* Custom domains.
* Email branding.
* Workspace-level appearance settings.

Implement only after defining the security and operational implications.

### 11.3 Billing

Use verified SaaS-OS billing capabilities where available.

If the product requires additional billing behavior, implement it in the product or through an approved adapter without modifying SaaS-OS.

Define:

* Plans.
* Entitlements.
* Usage limits.
* Subscription state.
* Upgrade and downgrade behavior.
* Failed payment behavior.
* Account suspension and recovery.

Do not grant paid entitlements solely because a checkout flow was initiated.

## Exit criteria

* Workspace switching is secure.
* Membership and permissions are tested.
* Billing state is reconciled reliably.
* Entitlements are enforced server-side.
* White-label configuration cannot cross workspace boundaries.

---

# 17. Phase 12 — Integrations and API Platform

**Status:** Not started.

## Objectives

Make the product extensible without introducing uncontrolled complexity.

## Tasks

* Define supported integration patterns.
* Implement required external provider adapters.
* Securely store integration credentials.
* Define webhook behavior.
* Add appropriate API authentication and authorization.
* Apply rate limits.
* Document supported integration contracts.
* Provide observability and failure diagnostics.

Evaluate third-party integrations according to actual user demand.

Do not build a large public integration marketplace before core integration patterns are stable.

## Exit criteria

* Supported integrations have documented behavior.
* Credentials are securely managed.
* Webhooks and retries are tested.
* API access is scoped and authorized.
* Integration failures are observable.

---

# 18. Phase 13 — Production Hardening

**Status:** Not started as a phase. Brought forward under M1: the security review of the public routes (decision 13-H1, 2026-10-29), with its fixes done and a proxy-header launch gate recorded.

## Objectives

Demonstrate that the product can be operated safely and reliably.

## Tasks

### Security

* Authentication and authorization review.
* Tenant-isolation review.
* Dependency audit.
* Secret scanning.
* Input validation.
* API abuse controls.
* Webhook security.
* File-upload security where applicable.
* Data-retention and deletion review.
* AI security review if AI is enabled.

### Reliability

* Database backup and restore drills.
* Migration safety.
* Background-job recovery.
* Idempotency verification.
* Provider outage handling.
* Readiness and health checks.
* Graceful shutdown.
* Operational alerting.

### Performance

* Database query review.
* Index review.
* Pagination and bounded queries.
* Load testing.
* Slow-operation monitoring.
* Resource limits.

### Privacy and compliance

Evaluate applicable obligations for the target markets and selected providers.

The product is a global SaaS (decision K5.1). For each market the product launches in, assess the applicable data-protection, electronic-marketing, consent, retention and data-subject requirements, with qualified guidance where needed. For example, a Netherlands/EU launch requires a GDPR and EU electronic-marketing assessment; if Morocco becomes a market, its data-protection law (including Law 09-08) applies. No single jurisdiction defines the product, and localisation alone is not compliance.

Hosting stays in a single region (decision K5); multi-region hosting and data residency outside that region need a separate decision.

Do not claim legal compliance without the required assessment and evidence.

### Operational documentation

* Deployment procedure.
* Rollback procedure.
* Backup and recovery.
* Incident response.
* Monitoring.
* Secret rotation.
* Support procedures.

## Exit criteria

* Production security review has no unresolved critical findings.
* Backup and restore procedures have been tested.
* Deployment and rollback procedures are documented and validated.
* CI passes.
* Operational monitoring is working.
* Privacy and legal requirements have been assessed.
* Known risks are explicitly accepted or mitigated.

---

# 19. Phase 14 — Release Preparation and Launch

**Status:** Not started.

## Objectives

Prepare an approved release without skipping final verification.

## Tasks

* Freeze the intended release scope.
* Review the full acceptance criteria.
* Run the complete test suite.
* Run dependency and security audits.
* Verify database migrations.
* Verify production configuration.
* Test critical user journeys.
* Validate backup and recovery.
* Confirm billing and entitlement behavior.
* Verify logging and alerts.
* Prepare support and incident procedures.
* Document known limitations.
* Prepare release notes.

## Release gates

A release cannot be declared ready solely because the application builds.

Require evidence for:

* Functional correctness.
* Security and tenant isolation.
* Migration safety.
* Performance and reliability.
* Production configuration.
* Monitoring and recovery.
* Required legal and privacy reviews.
* Approved deployment authorization.

**Production deployment requires separate explicit approval.**

## Exit criteria

* All mandatory release gates pass.
* No unresolved critical or high-severity issue remains without explicit risk acceptance.
* Release artifacts and test results are traceable to the exact release candidate.
* The release has been explicitly authorized.

---

# 20. Phase 15 — Post-Launch Improvement

**Status:** Not started.

## Objectives

Improve the product using actual customer feedback and operational evidence.

## Tasks

* Monitor reliability and performance.
* Track onboarding and activation.
* Measure feature adoption.
* Gather customer feedback.
* Identify usability problems.
* Prioritize support issues.
* Review infrastructure and provider costs.
* Improve the most important workflows.
* Refine documentation.
* Plan future features using evidence rather than assumptions.

Potential later features include:

* Advanced workflow branches.
* More communication providers.
* Voice and conversational AI.
* Advanced attribution.
* Website and funnel builders.
* Expanded white-label functionality.
* Additional integrations.
* Advanced analytics.

These features are not automatically part of the MVP.

## Exit criteria

Post-launch development is continuous. Each feature follows the same planning, implementation, testing, and release controls.

---

# 21. Mandatory Definition of Done

Every feature must satisfy the following applicable requirements before it is considered complete.

## Product behavior

* The feature meets documented acceptance criteria.
* The UI is connected to real backend functionality where required.
* Loading, empty, success, and error states are handled.
* Unsupported actions are not presented as functional capabilities.

## Backend

* Business rules are enforced server-side.
* Input is validated.
* Data integrity is protected.
* Errors are handled consistently.
* Relevant operations are observable.

## Security

* Authentication is enforced where required.
* Authorization is enforced server-side.
* Tenant isolation is tested.
* Secrets are not exposed.
* Sensitive data is appropriately protected.

## Testing

* Relevant unit tests pass.
* Integration tests pass where applicable.
* API tests pass where applicable.
* Cross-tenant tests cover sensitive data access.
* Type checking, linting, and build checks pass.

## Architecture

* SaaS-OS is consumed through approved public contracts.
* Product-specific logic remains in the product.
* Dependency pins are unchanged unless separately approved.
* No unrelated refactoring is introduced.

## Documentation

* Relevant interfaces and configuration are documented.
* Important decisions are recorded.
* Known limitations are reported.
* The roadmap and progress record are updated as authorized.

---

# 22. Progress Tracking

Maintain a separate progress record, for example:

`docs/project/PROGRESS.md`

This file should record:

* Current phase.
* Current task.
* Completed work.
* Work in progress.
* Blockers.
* Open decisions.
* Test results.
* Security findings.
* Relevant commits and CI results.
* Files changed.
* Next authorized action.

Do not invent commit hashes, test results, or deployment status.

The roadmap defines the intended destination. The progress record describes the verified current state.

Keep architectural decisions in separate ADRs when appropriate.

---

# 23. Recovery Protocol: When We Lose Track

If a conversation or coding session is interrupted, use this recovery sequence.

1. Read `CLAUDE.md`.
2. Read `ROADMAP.md`.
3. Read `docs/project/PROGRESS.md`, if it exists.
4. Inspect Git status and the current commit.
5. Inspect the most recent relevant test and CI evidence.
6. Identify the earliest incomplete acceptance criterion.
7. Compare the repository state against the recorded progress.
8. Report any discrepancies.
9. Continue from the earliest unblocked task within the current authorization.

Do not restart the project merely because the conversation context was lost.

Do not mark tasks complete based on previous assistant messages alone.

The current repository state and verifiable evidence are authoritative.

If an important decision was never recorded, return to the relevant decision section rather than guessing.

---

# 24. Immediate Next Actions

The project must proceed in this order. Current status of each item is tracked in `docs/project/PROGRESS.md` (as of 2026-10-20: items 1–6 and the MVP scope in item 8 are recorded; item 7 is blocked on Claude Design access; the architecture in item 8 and item 9 await owner approval of `docs/project/PHASE1-PLAN.md`. Update 2026-10-21: item 7 is complete, see `docs/project/DESIGN-INSPECTION.md`).

1. Complete the read-only Phase 0 discovery report.
2. Resolve K1: confirm the product is built independently from scratch.
3. Resolve K2: select the clean product repository.
4. Resolve K3: verify and approve the exact SaaS-OS dependency pin.
5. Confirm the LeadStack ZIP is being used only as an authorized reference.
6. Confirm `leadstack-crm` is a provisional name or select another working name.
7. Import and inspect the Claude Design project before frontend implementation.
8. Approve the product architecture and MVP scope.
9. Authorize Phase 1 implementation.
10. Complete Phase 1 acceptance criteria before progressing to Phase 2.

Backend foundation work may begin before the design is finalized only after the repository, dependency pin, architecture, and scope decisions are resolved.

Frontend implementation must wait until the Claude Design project has been successfully inspected and the initial UI-to-backend traceability is established.

---

# 25. Project Success Criteria

The product is successful when it has:

* A coherent, polished, and usable interface.
* A reliable backend supporting its advertised functionality.
* Secure multi-tenant data access.
* A clean integration with SaaS-OS.
* PostgreSQL persistence.
* Verified identity integration.
* Maintainable product-owned business modules.
* Automated tests and enforceable quality gates.
* Reliable background processing and external integrations.
* Clear operational documentation.
* A repeatable deployment and recovery process.
* A roadmap that reflects the actual state of the project.

The objective is not to maximize the number of features.

The objective is to build the right features, in the right order, with the right architectural boundaries, and to make them work reliably.

**End of master roadmap.**
