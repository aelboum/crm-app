# Progress Record

The verified current state of the project. `ROADMAP.md` defines the
destination; this file records what is actually true. Do not record
anything here that was not verified.

**Last updated:** 2026-10-24 (Phase 2 complete, decisions P2-F and P2-G).
Earlier: 2026-10-23 (SaaS-OS pin moved to v0.5.0, decision K3.2); 2026-10-21 (SaaS-OS pin moved to v0.3.0, decision K3.1;
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
