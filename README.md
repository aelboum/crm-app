# crm-app

A multi-tenant CRM and marketing product for small agencies and SMBs in the
Netherlands and the EU. "LeadStack CRM" is an internal, provisional working
name only (decision K4 in `docs/project/DECISIONS.md`).

The product consumes [SaaS-OS](https://github.com/aelboum/saas-os) as an
external package pinned to commit
`b0809eeb3448956a4dc85a5541514823ec9ceae7` (release v0.1.2). SaaS-OS supplies
the platform: application bootstrap, OIDC sign-in, tenancy, authorization,
Row-Level Security helpers, jobs and health checks. This repository owns the
CRM domain, its schema and migrations, and its configuration. See
`docs/architecture/saas-os-integration.md`.

**Status:** Phase 1 (product foundation). There are no CRM features yet and
no frontend; see `ROADMAP.md` and `docs/project/PROGRESS.md`.

## Proprietary notice

Copyright © 2026 the repository owner. All rights reserved. This software is
proprietary and confidential. No licence, express or implied, is granted to
use, copy, modify or distribute it. It must not be published or distributed
until its licensing and ownership position has been confirmed.

## Requirements

- Python 3.13 and [uv](https://docs.astral.sh/uv/)
- Docker with Compose, for the local services

## Local development

```bash
cp .env.example .env            # then replace every change-me value
docker compose -f deploy/local/compose.yaml --env-file .env up -d --wait db redis
uv sync --locked
set -a; . ./.env; set +a        # PUBLIC_APP_ORIGIN and APP_DB_USER are read from the process environment
uv run crm-app-migrate          # SaaS-OS migrations, then this product's
uv run uvicorn crm_app.app:create_app --factory --host 127.0.0.1 --port 8000
uv run crm-app-worker           # in a second terminal
```

`/healthz` and `/readyz` report liveness and readiness. All local services
listen on `127.0.0.1` only.

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
`http://localhost:8000/auth/login` then signs in through ZITADEL. The
administrator's login name is
`<ZITADEL_FIRSTINSTANCE_ADMIN_USERNAME>@crm-app-local.zitadel.localhost`.
There is no frontend yet, so after sign-in the browser lands on a 404 page
at `/`; `/auth/me` shows the signed-in user.

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
| Secret scan | `git ls-files -z \| xargs -0 uv run detect-secrets-hook --baseline .secrets.baseline` |

The integration tests use their own database (`crm_app_test`) and Redis
database 1. CI (`.github/workflows/ci.yml`) runs the same checks. It is not
active until the repository is pushed.

## Layout

```text
src/crm_app/        application, worker and migration entrypoints; settings
src/crm_app/migrations/   this product's Alembic history (schema crm_app)
src/crm_app/domains/      product domain modules (none yet)
tests/unit/         no services needed
tests/integration/  PostgreSQL and Redis
tests/identity/     opt-in OIDC login against local ZITADEL
deploy/local/       local development services only
docs/project/       decisions, progress, plans, discovery
docs/architecture/  platform boundary and integration notes
```

## Limitations

- No CRM features, no tenant data tables and no frontend.
- No metrics: SaaS-OS v0.1.2 has none. Tracing goes to the console exporter only.
- No production deployment, hosting or TLS configuration.
- CI has not run on GitHub; the repository has no remote yet.
