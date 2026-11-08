# Staging backup and restore report (2026-11-08)

Part of the staging acceptance audit (`STAGING-ACCEPTANCE-REPORT.md`).
Real backups of the staging databases, restored into a separate, empty
PostgreSQL on its own network on the same VPS, with
`deploy/staging/backup_drill.py` (SaaS-OS's backup orchestrator at the
pinned v0.10.0). Run three times; the last run had data in two
workspaces.

## 1. Measured results (final run, 14:31 UTC)

| Check | Result |
| --- | --- |
| App database backed up (`pg_dump` through the orchestrator) | **Pass**: 0.8 s; 668 KB |
| ZITADEL database backed up | **Pass**: 0.7 s |
| Both artifacts encrypted | **Pass**: `age` ciphertexts (`age-encryption.org/v1` header), recipient from a key pair kept in `.local/backups/` (identity 0600, root) |
| Separate, empty PostgreSQL on its own internal network | **Pass** |
| App backup restored | **Pass**: 3.4 s |
| ZITADEL backup restored | **Pass**: 2.3 s |
| Row counts table by table | **Pass**: app 127 tables / 1,050 rows; ZITADEL 144 tables / 2,207 rows |
| RLS restored (enabled, forced, policies) | **Pass**: 107 tables force RLS, 60 of them in `crm_app` |
| Migration versions | **Pass**: SaaS-OS `e2b7c4d9a1f6`, product `0043_business_hours_wait` |
| `verify_restored_database` | **Pass**: control_plane, core, self_learning |
| App role still safe | **Pass** |
| Tenant isolation in the copy, through the app role | **Pass**: `{"workspaces": 2, "own": 4, "foreign": 0, "no_context": 0}` |
| Audit digest verifies against the copy | **Fail**: no digest record available (S-10) |
| Whole drill | 22 s wall clock (backup, restore, checks, clean-up) |

Recovery time objective as measured: about 6 s to restore both databases,
22 s including verification, for this data size. The drill instance is
removed afterwards; the backups stay.

Earlier runs: 13:41 (empty staging) 13 of 15; the isolation check needs
two workspaces and the digest check failed on a file-permission bug in the
drill (S-11, fixed in `4470baf`).

## 2. Findings

### S-9 Medium — Backups are local, unscheduled, and leave plaintext copies (open)
- **Evidence:** `.local/backups/app/` holds each `crm_app-…pgdump.age`
  next to its plaintext `crm_app-…pgdump` (mode 0644, inside the 0700
  `.local/`); three runs left three of each; no backup timer is installed
  (the runbook's step 8 waits for the bucket decision).
- **Impact:** losing the VPS loses the data and its backups; the plaintext
  dumps make the encryption at rest moot on this host; local backups grow
  without limit.
- **Root cause:** SaaS-OS's orchestrator in "local-only" mode
  (`BACKUP_OFF_SITE_ENABLED=false`) keeps the plaintext and applies
  retention only to an off-site destination (its documented behaviour);
  no bucket is chosen.
- **Remediation:** the owner chooses an off-host bucket; then a nightly
  `leadstack-backup.timer` with off-site upload (SaaS-OS uploads only the
  verified ciphertext and applies retention there), and a local clean-up
  of plaintext dumps after each run. SaaS-OS is not changed.
- **Owner decision: yes** (bucket and its cost).

### S-10 Medium — Audit digests live only in container logs (open)
- **Evidence:** the worker's digest job runs every minute and emits a
  digest once an hourly window has settled (1 h + 15 min); the 13:00–14:00
  digest was written around 14:15 into the log of a worker container that
  was replaced at 14:26, so the drill found none.
- **Impact:** the tamper-evidence for audit rows (SaaS-OS ADR-0053) is lost
  whenever the worker is recreated (every deploy).
- **Root cause:** no external log store (gap S11 in the hosting brief).
- **Remediation:** ship container logs to an external store, or at least
  append the worker's `audit_digest` lines to a file on the host before a
  redeploy. **Owner decision: yes** (log store).

### S-11 Low — The drill could not read its own audit log on Linux (fixed)
- `NamedTemporaryFile` kept mode 0600 under `sudo`, unreadable by the
  verifying container's non-root user; Docker Desktop had hidden it. Fixed
  in `4470baf`; the drill now reaches the digest check.

## 3. Not tested

- An off-host copy and a restore on a second host (no bucket, no second
  host).
- Persistent files: the stack keeps no user files on disk (no uploads are
  stored), so only the two databases, the Caddy certificate store and the
  `.local/` settings matter; `.local/` and `caddy-data` are not backed up
  (losing them means new secrets and a new certificate; existing data
  would need the old field-encryption key, which must be kept offline).
- Retention over time.
