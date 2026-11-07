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
  -f deploy/staging/compose.yaml --profile stateful-local up -d --build
uv run python deploy/staging/verify_local.py       # the exit criteria a local run can prove
```

The app answers at `https://leadstack.localhost:8443` (Caddy's local CA;
`/app` is the frontend). Stop with `... down`; `down -v` also removes the
databases. `prepare_local.py --force` replaces the certificates and
passwords; recreate the databases afterwards (`down -v`).

| Service | Role |
| --- | --- |
| `edge` | Caddy 2.11.4: TLS, body caps (6 MB, 64 KB for `/v1/public/*`), `X-Forwarded-For` replaced, admin API off. Only published port: `127.0.0.1:8443` |
| `app` | the API (`uvicorn crm_app.app:create_app --factory`), read-only filesystem, no capabilities |
| `worker` | `crm-app-worker`; no route out except `egress-proxy`, own resolver |
| `migrate` | `crm-app-migrate` before `app` and `worker`; the only service with the migration owner's URL |
| `egress-proxy`, `dns-resolver` | Squid (CONNECT to public IPv4 on 443 only) and Unbound |
| `postgres`, `redis` (`stateful-local`) | stand-ins for the managed services: TLS from the local CA, hostssl only, a non-superuser owner, `noeviction`, AOF |

Settings are split so each process holds only what it needs:
`compose.env` (stand-in passwords), `app.env` (app and worker),
`migrate.env` (migration owner URL). All three are in `.local/`, which git
ignores.

## Not covered yet

Sign-in (ZITADEL in the stack), backups and the restore drill, the
scheduled maintenance commands, monitoring and alerting: exit criteria E4,
E5, E8 and E9 in the brief. A real public certificate, DNS and the managed
services' own behaviour can only be proven on the chosen host.
