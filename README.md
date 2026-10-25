# crm-app

A multi-tenant CRM and marketing product for small agencies and SMBs in the
Netherlands and the EU. "LeadStack CRM" is an internal, provisional working
name only (decision K4 in `docs/project/DECISIONS.md`).

The product consumes [SaaS-OS](https://github.com/aelboum/saas-os) as an
external package pinned to commit
`b03d87a5272924d1e413c144dc5c3b41ac430580` (release v0.5.0). SaaS-OS supplies
the platform: application bootstrap, OIDC sign-in, tenancy, authorization,
Row-Level Security helpers, jobs and health checks. This repository owns the
CRM domain, its schema and migrations, and its configuration. See
`docs/architecture/saas-os-integration.md`.

**Status:** Phase 1 (product foundation) complete. There are no CRM features
yet and no frontend; see `ROADMAP.md` and `docs/project/PROGRESS.md`.

## Proprietary notice

Copyright © 2026 the repository owner. All rights reserved. This software is
proprietary and confidential. No licence, express or implied, is granted to
use, copy, modify or distribute it. It must not be published or distributed
until its licensing and ownership position has been confirmed.

## Requirements

- Python 3.13 and [uv](https://docs.astral.sh/uv/)
- Node.js 22 or later with npm, to build the frontend (build time only)
- Docker with Compose, for the local services

## Local development

```bash
cp .env.example .env            # then replace every change-me value
docker compose -f deploy/local/compose.yaml --env-file .env up -d --wait db redis edge
uv sync --locked
set -a; . ./.env; set +a        # PUBLIC_APP_ORIGIN and APP_DB_USER are read from the process environment
uv run crm-app-migrate          # SaaS-OS migrations, then this product's
uv run uvicorn crm_app.app:create_app --factory --host 127.0.0.1 --port 8001
uv run crm-app-worker           # in a second terminal
(cd frontend && npm ci && npm run build)   # or `npm run dev` to rebuild on change
```

Open `http://localhost:8000/app`. The browser only ever talks to the `edge`
service on port 8000 (`deploy/local/Caddyfile`), which forwards to the
application on 127.0.0.1:8001 and, with the identity profile running, to
ZITADEL and its login UI on the same origin (decision D-IDL). The API
serves the built frontend itself (`crm_app.api.spa`).

`/healthz` and `/readyz` report liveness and readiness. All local services
listen on `127.0.0.1` only.

## Purging a workspace (operators)

Purging permanently deletes a workspace's data. There is no route for it;
an operator runs SaaS-OS's command, after the workspace was marked deleted
(`saas-os-operator delete-tenant`, by an enrolled platform operator):

```bash
uv run saas-os-operator purge-tenant --tenant <id> --actor <user id> \
    --setup crm_app.purge:register_purge_participants --confirm <id>
```

- **`--setup crm_app.purge:register_purge_participants` is required.** It
  registers this product's participant, `crm_app.crm_data`, which deletes
  the workspace's CRM data (`src/crm_app/purge.py`; decision G1).
- **Never use `--no-product-participants` for this product.** SaaS-OS
  offers it for products that keep no data of their own. Here it would
  purge the platform's records, mark the workspace purged and leave CRM
  rows behind, and a later run would not remove them (it reports the
  workspace as already purged). It is not a supported procedure, and
  nothing in this product can block it; the rule is procedural (decision
  Q-purge).
- If the purge fails, the workspace stays `PURGING` and a
  `tenant.purge_failed` audit entry records the failing step. Run the same
  command again.
- With `ENVIRONMENT=production`, SaaS-OS also requires
  `--confirm-production`. Purging a real workspace needs the owner's
  authorization.

### Local identity (ZITADEL)

```bash
docker compose -f deploy/local/compose.yaml --env-file .env --profile identity up -d --wait
set -a; . ./.env; set +a
uv run saas-os-local-identity --zitadel-url "$OIDC_ISSUER_URL" \
  --pat-path deploy/local/.bootstrap/bootstrap.pat \
  --public-app-origin "$PUBLIC_APP_ORIGIN" \
  --project-name "$OIDC_LOCAL_PROJECT_NAME" --application-name "$OIDC_LOCAL_APPLICATION_NAME"
```

Put the printed `OIDC_CLIENT_ID` in `.env` and restart the application.
Then apply the project's sign-in settings (no self-registration, no
username probing, lockout after 5 failures; decision D-IDL.1):
`uv run python deploy/local/configure-zitadel.py` (it also registers
`<PUBLIC_APP_ORIGIN>/app` as the post-sign-out address, so signing out ends
the ZITADEL session too; decision P2-G). A locked-out user is
unlocked in the ZITADEL console (`http://localhost:8000/ui/console`).
In Git Bash on Windows, export `MSYS2_ENV_CONV_EXCL=AUTH_POST_LOGIN_PATH`
before starting it: otherwise Git Bash rewrites `/app` into a Windows path
and `/auth/login` answers "Authentication is not configured".
`http://localhost:8000/auth/login` then signs in. The login screens are
ZITADEL's Login V2, served at `/ui/v2/login` on the application's own
origin, so no identity-provider hostname appears (SaaS-OS ADR-0025). The
administrator's login name is
`<ZITADEL_FIRSTINSTANCE_ADMIN_USERNAME>@crm-app-local.localhost`.
A sign-in left open for more than 10 minutes is refused at
`/auth/callback` (SaaS-OS's login-transaction lifetime); start again from
`/app`.

ZITADEL's issuer is fixed when its database is first created. Moving from
the earlier `http://zitadel.localhost:8081` setup therefore uses a new
volume (`zitadel-same-origin-data`); the old `zitadel-db-data` volume is
left unused and can be removed by hand. After the switch, rerun
`saas-os-local-identity` and put the new `OIDC_CLIENT_ID` in `.env`.
After sign-in the browser returns to `AUTH_POST_LOGIN_PATH` (`/app` in
`.env.example`). There is no list of workspaces yet: open one by its link
(`/app/w/<workspace id>`) or paste its ID on the start page.

**Self-service signup** (decisions S-1, S-1.2; `docs/project/SIGNUP-PLAN.md`).
`POST /v1/signups` and `GET /v1/signups/current` create a workspace for a
signed-in person with a verified email and make them its Owner. They
answer 404 unless `SIGNUP_ENABLED=true`, which also needs
`TRUST_PROXY_HEADERS=true` and is refused in production. There is no
signup screen yet (Stage D). Unfinished signups are resumed, expired and
cleaned up by a command the deployment runs every few minutes, whether or
not signup is on:

```bash
uv run python -m crm_app.signup_maintenance
```

**Testing ZITADEL's own registration locally** (Stage A4; local development
only, off unless you opt in). This is ZITADEL's registration and email
verification, not LeadStack's signup: `SIGNUP_ENABLED` stays off. Uncomment
the three `ZITADEL_LOCAL_*` lines of the Stage A4 block in `.env`, so every
later run keeps them, then:

```bash
set -a; . ./.env; set +a
docker compose -f deploy/local/compose.yaml --env-file .env --profile mail up -d mailpit
uv run python deploy/local/configure-zitadel.py
docker compose -f deploy/local/compose.yaml --env-file .env --profile identity up -d --wait zitadel-login
```

Login V2 then offers registration ("Register new user"; "Create one" on the
LeadStack login build), after one reload because it caches its settings
briefly, and refuses to finish a sign-in until the email is verified. Verification and password-reset emails arrive only in Mailpit at
`http://127.0.0.1:58025` (Mailpit listens on 127.0.0.1 alone and delivers
nothing). The script refuses registration without `ZITADEL_LOCAL_SMTP=mailpit`,
and says so whenever it turns registration on or off. To return to the
defaults, comment the three lines again, rerun the script and recreate
`zitadel-login`. The Mailpit provider stays configured in ZITADEL but only
matters while Mailpit runs.

**Trying LeadStack branding on the login pages** (local only; off unless you
opt in). Sets LeadStack's colours and logo (`deploy/local/branding/`), hides
ZITADEL's watermark and the login-name suffix, and replaces every English
Login V2 text that names Zitadel:

```bash
ZITADEL_LOCAL_BRANDING=leadstack uv run python deploy/local/configure-zitadel.py
```

`ZITADEL_LOCAL_BRANDING=default` restores ZITADEL's own branding and texts.
Only English is overridden; Login V2's other languages still name Zitadel.
The layout stays Login V2's centred card: its `NEXT_PUBLIC_THEME_*` layout
options are fixed when the published image is built and are ignored at run
time (tried with v4.19.5).

**LeadStack's own sign-in pages** (decision S-2). The `crm-app-login`
repository builds Login V2 with LeadStack's layout and a one-page sign-in
form. Build it there (`scripts/build.sh`, which makes the image
`crm-app-login:dev`), then run it here in place of ZITADEL's image:

```bash
ZITADEL_LOGIN_IMAGE=crm-app-login:dev docker compose -f deploy/local/compose.yaml \
  --env-file .env --profile identity up -d --wait zitadel-login
```

Without `ZITADEL_LOGIN_IMAGE` the published `zitadel-login` image runs, as
before. Opening `/app` without a session goes straight to the sign-in page,
except right after signing out in the same tab.

`deploy/local/.bootstrap/` holds ZITADEL's bootstrap token and is never
committed. `docker compose ... down -v` deletes every local volume, including
ZITADEL's, after which the client ID changes.

## Checks

| Check | Command |
| --- | --- |
| Lockfile current | `uv lock --check` |
| Format | `uv run ruff format --check .` |
| Lint | `uv run ruff check .` |
| Types | `uv run pyright` |
| Import boundaries | `uv run lint-imports` |
| Unit tests | `uv run pytest tests/unit` |
| Integration tests | `cp .env.test.example .env.test` (same passwords as `.env`), then `set -a; . ./.env.test; set +a; uv run pytest tests/integration` |
| OIDC login (opt-in) | with the identity profile running and `.env` exported: `CRM_APP_IDENTITY_TEST=1 uv run pytest tests/identity` |
| Dependency audit | see the `security` job in `.github/workflows/ci.yml` |
| Frontend | `cd frontend && npm ci && npm run typecheck && npm run lint && npm test && npm run build` |
| API schema for the frontend | `python -m crm_app.openapi frontend/openapi.json`, then `cd frontend && npm run gen:api` (a unit test fails when stale) |
| Secret scan | `git ls-files -z \| xargs -0 uv run detect-secrets-hook --baseline .secrets.baseline` |

The integration tests use their own database (`crm_app_test`) and Redis
database 1. CI (`.github/workflows/ci.yml`) runs the same checks on every
push to `main` and every pull request in `aelboum/crm-app`.

## Layout

```text
src/crm_app/        application, worker and migration entrypoints; settings
src/crm_app/migrations/   this product's Alembic history (schema crm_app)
src/crm_app/domains/      product domain modules (none yet)
tests/unit/         no services needed
tests/integration/  PostgreSQL and Redis
tests/identity/     opt-in OIDC login against local ZITADEL
frontend/           React single-page app (decision P-6.1), served under /app
deploy/local/       local development services only
docs/project/       decisions, progress, plans, discovery
docs/architecture/  platform boundary and integration notes
```

## Limitations

- No CRM features and no tenant data tables. The frontend covers sign-in,
  opening a workspace and managing its members only; members are shown by
  ID because no member profile is stored yet.
- No metrics: SaaS-OS v0.5.0 has none. Tracing goes to the console exporter only.
- No production deployment, hosting or TLS configuration.
