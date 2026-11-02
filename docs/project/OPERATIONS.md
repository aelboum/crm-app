# Operations: processes and scheduled commands (decision 13-O1)

What a deployment of LeadStack runs, in one place. Each command prints
counts or identifiers only (never personal data), is safe to run twice
(idempotent), and validates its settings at start-up. SaaS-OS v0.6.0
schedules system jobs only through a queue outside its public surface, so
periodic work runs as commands from the deployment's scheduler (gap 9 in
`saas-os-gaps.md`).

## Long-running processes

| Process | Command | Notes |
| --- | --- | --- |
| API and app | the ASGI app `crm_app.app:create_app` (factory) | Serves `/v1` and the built frontend at `/app` |
| Worker | `crm-app-worker` | Runs queued jobs: email sends, automation steps, import commits, inbound processing |

## Deployment steps

| When | Command | Notes |
| --- | --- | --- |
| Before the app and worker start | `crm-app-migrate` | Product migrations; idempotent; never against production without approval |

## Scheduled commands

| Command | Every | Does | If it stops |
| --- | --- | --- | --- |
| `python -m crm_app.email_maintenance` | 1–5 minutes | Queues due reminders (P5-D); retries lost or deferred email (P6-E); processes received mail (P6-I); re-checks custom domains daily (P12-D); releases unverified sending-domain claims after 7 days (13-H3) | Reminders and retries stop, received mail waits, domains are not re-checked |
| `python -m crm_app.automation_maintenance` | 1 minute | Enqueues automation runs that are due, including after waits (P8-A) | Automations stall after their first step or wait |
| `python -m crm_app.signup_maintenance` | a few minutes | Signup housekeeping (S-1; signup is off in production) | Pending signups are not cleaned up |
| `python -m crm_app.import_maintenance` | about hourly | Deletes CSV import staging rows 7 days after an import (P3-F 7) | Staged personal data is kept longer than promised |

Run each from one scheduler only, or tolerate overlap: every command claims
its work with row locks or `SKIP LOCKED`, so two at once do no harm, only
waste.

## Operator commands (never scheduled)

| Command | Purpose | Guard |
| --- | --- | --- |
| `python -m crm_app.provision` | Create a workspace with its roles and first Owner | `--dry-run`; `--confirm-production` |
| `python -m crm_app.role_upgrade` | Grant older workspaces new template permissions | Dry run by default; production needs `--confirm-production` and `--expect` (`ROLE-UPGRADE-RUNBOOK.md`) |

## Health to watch

- **Command exit codes:** non-zero means it did not finish. Any command failing
  twice in a row needs attention.
- **The `failed` counts** in `email_maintenance` output: one workspace failing
  repeatedly is isolated (13-H5) but should be looked at.
- **Queue age:** `python -m crm_app.health_check` (every few minutes from
  monitoring) prints `emails_overdue`, `automation_runs_overdue` and
  `imports_overdue` and exits 1 when any is above zero: email retries or
  automation runs overdue by more than 15 minutes, or import clean-ups by
  more than 3 hours, mean the worker or a scheduled command is not running.
- **Logs:** carry workspace ids and error types only; never message bodies,
  tokens or addresses.
