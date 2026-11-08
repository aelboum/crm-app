# Staging runbook (decision D-STG.4)

How to deploy, update, roll back, rotate secrets and restore LeadStack's
staging. Provider-neutral in general; the staging VPS chosen on 2026-11-08 is in
section 1a (decision D-STG.5). Elsewhere `<staging-hostname>`,
`<registry>` and `<host>` are placeholders. Every step names what it was checked with. "Rehearsed"
means run locally against `deploy/staging/` (decisions D-STG to D-STG.3);
"not yet run" means it needs the real host.

Production email sending and receiving stay off throughout: the app
refuses every email switch in production (`deploy/staging/env.template`).

## 0. Before the first deployment (owner decisions)

- Provider, account with MFA and a budget alert, staging hostname and DNS.
- Self-hosted ZITADEL or ZITADEL Cloud.
- A monitoring service for the heartbeat (`HEARTBEAT_URL`) and an
  off-provider backup bucket.
- How the app database is backed up on that provider: an admin with
  BYPASSRLS (then SaaS-OS's encrypted `pg_dump` works), or the provider's
  own backups, exportable for an off-provider copy (SaaS-OS gaps 17, 18).

## 1. First deployment

1. **Databases** (not yet run). On the managed PostgreSQL, as its admin,
   create the roles and databases the way `deploy/staging/init/01-roles.sh`
   does (rehearsed): `crm_app_owner` owning `crm_app`, the runtime role, the
   `saas_os_platform_config` role NOLOGIN, `zitadel` owning `zitadel` when
   self-hosted. None is a superuser or has BYPASSRLS. Require TLS.
2. **Secrets** (not yet run). Fill every name in `deploy/staging/env.template`
   in the host's secret store. Generate the ZITADEL master key and the
   field-encryption key on a trusted machine and keep copies offline with
   the backup identity (`[offline]`); losing them loses data.
3. **Image** (built in CI; push not yet run). Build `Dockerfile`, tag it
   with the commit, push it to `<registry>`, and pin that tag on the host.
4. **Migrate** (rehearsed). `docker compose -f deploy/staging/compose.yaml
   run --rm migrate`. It runs as the non-superuser owner; data changes in
   migrations go through `all_rows` (decision M-RLS).
5. **Start** (rehearsed). `docker compose -f deploy/staging/compose.yaml up
   -d --wait`, without the `stateful-local` profile. Check
   `https://<staging-hostname>/readyz` answers 200.
6. **Identity** (rehearsed with bootstrap tokens; the host's way not yet
   run). Self-hosted: ZITADEL's first instance, then the OIDC application on
   the app's origin; on a host use a system-user key, not bootstrap tokens
   (SaaS-OS ADR-0025 section 7). Put the client ID in `OIDC_CLIENT_ID` and
   restart `app`. Enrol two platform owners with MFA.
7. **Timers and heartbeat** (rehearsed: `schedule_local.py`; systemd not yet
   run). Install `deploy/staging/systemd/`, set `HEARTBEAT_URL` in
   `heartbeat.env`, `systemctl enable --now leadstack-*.timer
   saas-os-*.timer`. Stop the worker once and see the monitor alert (E9).
8. **Backups** (rehearsed: `backup_drill.py`, 15 of 15). Per section 0's
   decision; then restore once into a second instance (E8) before calling
   staging ready.
9. **Exit checks.** The brief's E1 to E10; `verify_local.py` shows what each
   proves locally.

## 1a. The staging VPS as built (decision D-STG.5, 2026-11-08)

Run on the VPS (`ssh ovh-vps-ai-pbx`, user `debian`, passwordless sudo).
Checkout `/srv/leadstack/crm-app` (read-only deploy key), settings in
`deploy/staging/.local/` (0700; never copied off the host). Let `C` be:

```sh
C="sudo docker compose --env-file deploy/staging/.local/compose.env   -f deploy/staging/compose.yaml -f deploy/staging/compose.host.yaml   --profile stateful-local"
```

- **First time** (done 2026-11-08): install `docker.io docker-compose
  docker-buildx git age python3-venv`; clone; build the image (below);
  `prepare_local.py --host crm-staging.auravox.nl --days 365 --public-ca
  /etc/ssl/certs/ca-certificates.crt` inside the image as uid 1000; start
  everything but `edge`; once DNS answers the VPS, `$C up -d --wait edge`;
  `identity_local.py --origin https://crm-staging.auravox.nl --no-restart`
  inside the image on the `crm-app-staging_edge` network; `$C up -d --wait
  --force-recreate app worker`; install `deploy/staging/systemd/` (not the
  heartbeat until `HEARTBEAT_URL` exists) with `/opt/leadstack` linked to
  the checkout and `deploy/staging/.env` to `.local/compose.env`.
- **Deploy a commit:** `git fetch && git checkout <commit>`; `sudo docker
  build -t crm-app:staging -t crm-app:<commit> .`; set `VERSION=<commit>`
  in `.local/app.env`; `$C up -d --wait` (runs `migrate` first);
  `curl https://crm-staging.auravox.nl/readyz` → 200.
- **Roll back code:** `sudo docker tag crm-app:<previous> crm-app:staging`
  and `$C up -d --wait app worker`.
- **Backup and restore drill:** `sudo .venv/bin/python
  deploy/staging/backup_drill.py` (a project environment in `.venv`, made
  with uv). Backups stay on this host only (no bucket yet).
- **Test accounts:** disposable users and their passwords are in
  `.local/test-users.env`; never reuse them anywhere else.

## 2. Deploying a new version

1. CI green on the commit.
2. Read the release's migrations: a migration that changes data must use
   `all_rows` (the unit guard enforces it).
3. Take a backup (section 5) if any migration changes data.
4. Pin the new image tag; `docker compose run --rm migrate`; then
   `docker compose up -d --wait app worker`.
5. `/readyz` 200, the heartbeat keeps arriving, and one sign-in works.

## 3. Rolling back

- **Code only** (no migration in the release): pin the previous image tag
  and `up -d --wait app worker`.
- **With a migration**: migrations are applied forward only on staging and
  production; downgrades exist for development and tests only. If the new
  schema is the problem, restore the backup taken before the release
  (section 5) into a fresh database, point `DATABASE_URL` and
  `MIGRATIONS_DATABASE_URL` at it, and start the previous image. Changes
  made after the backup are lost; record them.

## 4. Rotating secrets

| Secret | How | Effect |
| --- | --- | --- |
| Database role passwords | `ALTER ROLE ... PASSWORD` as the admin, update the secret store, restart the processes that use it | Brief reconnect |
| `REDIS_URL` password | The provider's rotation, update the store, restart `app` and `worker` | Queued jobs stay (AOF, `noeviction`) |
| `ZITADEL_LOGIN_SESSION_COOKIE_SECRET` | New value, restart `zitadel-login` | Open sign-ins start again |
| Field-encryption key | Add `FIELD_ENCRYPTION_KEY_V2` and set `FIELD_ENCRYPTION_ACTIVE_KEY_VERSION=v2`; new signing keys use V2. Keep V1 as long as any webhook address added before exists (or add those addresses again) | Not yet rehearsed; never remove V1 first |
| An integration's API key | The workspace's Owner or Admin issues a second key, switches the tool, revokes the old one (Settings > Integrations) | No gap: two live keys are allowed |
| A webhook signing key | Add the address again (new key), switch the receiver, remove the old address | Both receive events meanwhile |
| Backup identity (`age`) | New key pair; new backups use the new recipient; keep the old identity for old backups | Old backups still need the old identity |
| `HEARTBEAT_URL` | Regenerate it at the monitor, update `heartbeat.env` | One missed ping possible |

## 5. Backing up and restoring

- **Backup**: the timers in section 1 step 8, or by hand `python -m
  saas_os.infra.db.backup.orchestrator run ...`, as `backup_drill.py` runs
  it.
- **Restore** (rehearsed: `backup_drill.py`): always into a fresh database
  on a separate instance prepared with the same roles. Then check, as the
  drill does: row counts, migration versions, RLS forced on every table,
  the app role still safe, tenant isolation through the app role, and
  `python -m saas_os.ops.audit_digest verify` against the exported digest
  log (windows after the backup are expected to differ; record the restore
  time). Only then point the app at it.

## 6. When something goes wrong

| Signal | Likely cause | First step |
| --- | --- | --- |
| Heartbeat missing | Worker stopped, or work overdue | `docker compose ps`; `python -m crm_app.health_check` |
| A timer failed | Its command exited non-zero | `systemctl --failed`; `journalctl -u leadstack-job@<module>` |
| Webhook "Gave up" | The receiver refused or is down | Ask the workspace to fix its receiver; given-up deliveries are not resent |
| Sign-in fails | ZITADEL or its database | `docker compose logs zitadel zitadel-login`; `/.well-known/openid-configuration` |
| `/readyz` not 200 | Database or Redis unreachable, or TLS refused | The managed services' status and CA; `SSL_CERT_FILE` |
