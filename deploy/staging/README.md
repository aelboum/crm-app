# Staging stack (decision D-STG)

The production-shaped stack from `docs/project/DECISION-BRIEF-HOSTING.md`
(section 7). It runs the one product image (`Dockerfile`) with
`ENVIRONMENT=production` behind Caddy, the worker sealed behind an egress
proxy, and PostgreSQL and Redis over TLS.

Nothing here selects a provider or deploys anything. Locally it is the
staging rehearsal; on a host it would run without the `stateful-local`
profile, against the managed PostgreSQL and Redis, once the owner chooses.

## Run it locally

```sh
uv run python deploy/staging/prepare_local.py      # certificates and secrets in .local/
docker compose --env-file deploy/staging/.local/compose.env \
  -f deploy/staging/compose.yaml --profile stateful-local up -d --build --wait
uv run python deploy/staging/identity_local.py     # OIDC application in ZITADEL (decision D-STG.1)
uv run python deploy/staging/verify_local.py       # the exit criteria a local run can prove
uv run python deploy/staging/backup_drill.py       # backup, restore drill, checks (D-STG.2; needs age)
uv run python deploy/staging/schedule_local.py     # scheduled commands and the heartbeat (D-STG.3)
```

The app answers at `https://leadstack.localhost:8443` (a certificate from
the local CA in `.local/ca.crt`; `/app` is the frontend). ZITADEL's
administrator is `admin@crm-app-staging.leadstack.localhost`, its password
`ZITADEL_ADMIN_PASSWORD` in `.local/compose.env`. Stop with `... down`; `down -v` also removes the
databases. `prepare_local.py --force` replaces the certificates and
passwords; recreate the databases afterwards (`down -v`).

| Service | Role |
| --- | --- |
| `edge` | Caddy 2.11.4: TLS, body caps (6 MB, 64 KB for `/v1/public/*`), `X-Forwarded-For` replaced, provider cookies stripped before the app, admin API off. Only published port: `127.0.0.1:8443` |
| `zitadel`, `zitadel-login` | ZITADEL v4.20.1 and Login V2 (LeadStack's build on the staging VPS) on the app's own origin (SaaS-OS ADR-0025); own database over `verify-full` as a non-superuser; internal network only |
| `app` | the API (`uvicorn crm_app.app:create_app --factory`), read-only filesystem, no capabilities |
| `worker` | `crm-app-worker`; no route out except `egress-proxy`, own resolver |
| `migrate` | `crm-app-migrate` before `app` and `worker`; the only service with the migration owner's URL |
| `egress-proxy`, `dns-resolver` | Squid (CONNECT to public IPv4 on 443 only) and Unbound |
| `postgres`, `redis` (`stateful-local`) | stand-ins for the managed services: TLS from the local CA, hostssl only, a non-superuser owner, `noeviction`, AOF |

Every setting a host needs is named, without values, in `env.template`;
the steps to deploy, update, roll back, rotate secrets and restore are in
`docs/project/STAGING-RUNBOOK.md` (decision D-STG.4).

Settings are split so each process holds only what it needs:
`compose.env` (stand-in passwords), `app.env` (app and worker),
`migrate.env` (migration owner URL). All three are in `.local/`, which git
ignores.

## Not covered yet

A browser sign-in with MFA (the rest of E4), the off-provider backup copy
and a second host for the restore drill (the rest of E8), and the
monitoring service raising the alert (the rest of E9). The host timers are
in `systemd/` (decision D-STG.3); `heartbeat.sh` pings the monitor only
while the worker and the queues are healthy. `backup_drill.py`
dumps the app database as the stand-in's superuser: a non-superuser owner
cannot (SaaS-OS gap 18). A real public certificate, DNS and the managed
services' own behaviour can only be proven on the chosen host.
