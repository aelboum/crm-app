# Staging end-to-end test report (2026-11-08)

Part of the staging acceptance audit (`STAGING-ACCEPTANCE-REPORT.md`).
Run against `https://crm-staging.auravox.nl` at commits `a3685cd` to
`bb90ab8` with disposable data only.

## 1. Test accounts and workspaces

| Item | How | Result |
| --- | --- | --- |
| Users `alice@crm-staging.auravox.nl`, `bob@crm-staging.auravox.nl` | ZITADEL v2 user API with the stack's bootstrap token; e-mail marked verified; random passwords in `.local/test-users.env` (0600, VPS only) | created |
| Workspaces "Staging Alpha" (alice Owner), "Staging Beta" (bob Owner) | `python -m crm_app.provision --confirm-production` | created; Owner, Admin, Member and Read-only roles with 65/63/31/16 permissions; the Owner role assigned last |

Signup (steps 1–2 of the brief) cannot be exercised: production mode
refuses `SIGNUP_ENABLED` until launch gates LG-1 to LG-10 pass (decision
S-1), and no email may be sent. Workspaces were therefore created with the
operator command, as the runbook prescribes.

API workflows ran inside the app image against the public origin, as the
owner, with a session minted by SaaS-OS's `issue_session` (the method the
integration tests use). The sign-in itself was tested separately in the
browser (§4).

## 2. Workflow results (API, workspace Alpha)

| # | Step | Result | Evidence |
| --- | --- | --- | --- |
| 3 | Create a workspace | **Pass** | §1 |
| 4 | Create a contact | **Pass** | 201; also in the browser with validation (§4) |
| 5 | Create a company | **Pass** | 201 |
| 6 | Link contact and company | **Pass** | PATCH 200; contact shows the company; the company's people list includes it |
| — | Tags | **Pass** | tag 201; set on the contact 200 |
| — | Custom field | **Pass** | definition 201; value "Gold" saved and returned |
| 7 | Pipeline and deal | **Pass** | pipeline read 200; deal 201 with contact, company, amount, stage |
| 8 | Move through stages | **Pass** | two moves 200; outcome "won" 200; 4 history entries; a stale `If-Match` 409 |
| 9 | Conversation | **Pass** | created 201; internal note 201; email reply 201, shown as `queued` (never "sent"); closed 200 |
| 10 | Appointment | **Pass** | created 201; replay with the same idempotency key returns the same appointment; double booking 409; confirmed 200; cancelled 200 |
| 11 | Automation | **Pass**, note S-16 | created and activated; a new contact got the tag from the worker (run "completed", step `add_tag: done`); the first run started 67 s after the contact, on the minute sweep |
| — | Email template | **Pass** | created 201; rendered for the contact: subject "Hi Dana" |
| — | Reports | **Pass** | contacts, deals, tasks 200 with a 30-day period; CSV export 200, `no-store` (without a period: 422 `invalid_period`, as designed) |
| 12 | Export contacts and companies | **Pass** | both 200, `text/csv`, `Cache-Control: no-store` |
| 13 | Switch workspaces | **Pass** | alice opening Beta's address in the browser: "This workspace does not exist, or you are not a member of it." (S-15) |
| 14 | Data isolation | **Pass** | §3 |
| 15 | Sign out | **Pass** (app and provider, after ZIT-1) | §4 |

## 3. Cross-workspace isolation (API)

Alice's session against Bob's records (contacts, companies, deals, tasks,
conversations, appointments), each addressed through Alpha's path and
through Beta's path:

| Attempt | Result |
| --- | --- |
| GET, PATCH, DELETE via Alpha's path (24 requests) | all 404 |
| GET, DELETE via Beta's path (12 requests) | 404; conversations DELETE 405 (no delete route) |
| Beta's lists: contacts, companies, opportunities, tasks, conversations, members, automations, reports, settings | all 404 |
| Search in Alpha for Bob's contact's name | 0 results |
| Bob's contact in Alpha's list | absent |
| Bob's six records afterwards (as Bob) | all 200, unchanged |
| No credentials | 401 |

The restored backup repeats the check at database level: through the
runtime role, Alpha's context sees 4 of its own role rows and 0 of Beta's;
no context sees 0 (`STAGING-BACKUP-RESTORE-REPORT.md`).

## 4. Browser checks (Chrome, desktop 1280 px)

| Check | Result |
| --- | --- |
| Sign-in | **Pass**: `/app` → ZITADEL Login V2 on the same origin → password → back to "Your workspaces", which lists only Staging Alpha |
| Contact form validation | **Pass**: empty submit shows "First name is required" and "Add an email or phone number" |
| Create a contact | **Pass**: toast "Contact created · Elena", preview opens |
| Home, Opportunities, Inbox | **Pass**: load with data; no console errors |
| Another workspace by address | **Pass**: refused with a plain message |
| Sign out | app session ended ("Your session has ended"); ZITADEL then shows its account-choice page; choosing "Sign in" without that click signs straight back in (S-7) |
| Login branding | ZITADEL's default look, not LeadStack's (S-13) |
| Rate-limited sign-in | raw JSON page (S-14) |

## 5. Findings

### S-15 Low — An inaccessible workspace still shows the full frame (fixed, `bf163ea`)
- The refusal message appears inside the normal frame, with the
  workspace's navigation and disabled Import/Export controls. Remediation:
  show the refusal without the workspace frame. Owner decision: no.

### S-16 Informational — Automations start on the next minute's sweep
- By design (decision P8-A, D-STG.3) runs are enqueued by
  `automation_maintenance` every minute; each sweep starts a fresh
  container, so the first step runs 60–100 s after the trigger.

### S-13 Low — Login pages are unbranded (fixed, decision ZIT-1)
- `identity_local.py` does not apply `ZITADEL_LOCAL_BRANDING`; the
  login showed ZITADEL's default look. Since decision ZIT-1 staging runs
  LeadStack's login build: its own layout and one-page form.

## 6. Not tested

- Signup and e-mail verification (refused in production mode; no email).
- Mobile layout in a browser: the Chrome window could not be resized to
  390 px (the frontend's own tests cover narrow layouts).
- User and role management in the browser (inviting members needs either
  email or the manual link flow; not exercised).
- Accessibility on staging (axe runs in CI on every commit).
- A real outbound email (sending is not authorized).
