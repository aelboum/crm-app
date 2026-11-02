# Role-upgrade dry run: report for review

**Status:** for review, prepared on 2026-11-02 under the owner's instruction
"Prepare the role-upgrade dry-run report for review. Do not apply it to
real workspaces." Nothing was applied. The run was a dry run (no `--apply`)
against the local **test** database (`ENVIRONMENT=test`), whose workspaces
are all created by the automated test suites. No real or production
workspace was read or changed. Procedure: `ROLE-UPGRADE-RUNBOOK.md`;
decision brief 7.

## 1. Command

```
python -m crm_app.role_upgrade --all --json
```

Exit code 0; `"applied": false`; fingerprint `89e1319df6264bab`. The
fingerprint describes this test database only and would not match any other
database; a production run takes its own dry run and fingerprint.

## 2. What it found

| Count | Workspaces |
| --- | --- |
| 17,107 | Seen |
| 11,689 | Skipped: not a product workspace (none of the four product roles; SaaS-OS-level test fixtures) |
| 1 | Skipped: not a product workspace (missing Member and Read-only) |
| 76 | Skipped: status is `pending` (not yet activated) |
| 5,341 | Product workspaces checked |
| 1,196 | Already up to date: nothing to grant |
| 4,145 | Missing at least one permission, because tests created them before the features that added it |

Custom grants already present on roles are kept: 10 in total. The upgrade
never removes a grant.

## 3. What an apply would grant (default run)

Per role, the number of workspaces that would receive each permission (all
in the `crm_app.` namespace):

| Permission | Owner | Admin | Member | Read-only |
| --- | --- | --- | --- | --- |
| `appointment:read` | 2,746 | 2,746 | 2,746 | 2,746 |
| `appointment:create`, `appointment:update` | 2,746 | 2,746 | 2,746 | — |
| `appointment:delete` | 2,746 | 2,746 | — | — |
| `automation:read` | 3,810 | 3,810 | 3,810 | 3,810 |
| `booking_page:read` | 2,999 | 2,999 | 2,999 | 2,999 |
| `campaign:read` | 4,137 | 4,137 | 4,137 | 4,137 |
| `campaign:manage` | 4,137 | 4,137 | 4,137 | — |
| `conversation:read` | 3,952 | 3,952 | 3,952 | 3,952 |
| `conversation:reply` | 3,952 | 3,952 | 3,952 | — |
| `form:read` | 2,624 | 2,624 | 2,624 | 2,624 |
| `suppression:read` | 3,128 | 3,128 | 3,128 | — |

These match the role definitions in `src/crm_app/roles.py` (Read-only,
Member and Admin sets); nothing beyond a role's definition is granted.

## 4. What is held back (administrative)

The default run never grants administrative permissions; they need a
separately approved run with `--include-administrative` and its own dry run.
Held back here, for Owner and Admin only:

| Permission | Workspaces |
| --- | --- |
| `campaign:approve` | 4,137 |
| `automation:manage` | 3,810 |
| `suppression:manage` | 3,128 |
| `booking_page:manage` | 2,999 |
| `form:manage` | 2,624 |
| `crm_data:import` | 1,868 |

## 5. Points for the reviewer

1. **Member receives `campaign:manage` and `conversation:reply`.** That is
   the current role definition (members draft campaigns and reply to
   conversations; approving a campaign stays administrative). If the owner
   wants otherwise, the role definition changes first, in its own decision,
   before any production run.
2. **Owners and Admins without the held-back permissions** keep working but
   cannot manage forms, booking pages, automations or the suppression list,
   approve campaigns or import until an administrative run is approved.
   That is the decision in brief 7.
3. **Pending workspaces are skipped**; they receive the current role set
   when activated.
4. **Production:** when a production workspace needs this, the runbook
   applies: dry run, review of that output,
   `--apply --confirm-production --expect <fingerprint>`, then a second dry
   run that must show nothing to grant.

## 6. Not done

- No `--apply`, against this or any database.
- No run with `--include-administrative`.
- The full JSON output (about 13 MB, one entry per test workspace) is not
  committed; it is reproducible with the command in section 1.
