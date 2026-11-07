# Decision brief: hosting and first deployment

Status: **for the owner's decision.** Prepared 2026-11-07. Nothing has been
selected, no account exists, nothing was bought or deployed. Hosting
selection, paid accounts, infrastructure purchases and deployment need the
owner's explicit approval (CLAUDE.md §9).

Legend: **[V]** verified on 2026-11-07 against the cited source; **[E]**
estimate or arithmetic from verified unit prices; **[U]** not verified.
Prices exclude VAT; monthly = hourly × 730. AWS, ZITADEL, Sentry and Better
Stack bill in USD.

## 1. What the deployment must satisfy

### 1.1 SaaS-OS v0.10.0 (the pinned release, decision K3.9)

The request named SaaS-OS v0.6.0; the product now pins v0.10.0, so its
requirements are the ones that apply. Sources are SaaS-OS paths at
`0f9bf4d`.

| # | Requirement | Source |
| --- | --- | --- |
| S1 | Overall verdict "not production-ready"; gate 12 (deployment) blocked because no deployment was ever run; each product qualifies its own | `docs/PRODUCTION-READINESS.md` |
| S2 | Target: Docker containers with Docker Compose on a VPS. Kubernetes not implemented | ADR-0010 |
| S3 | **PostgreSQL and Redis in production are external, operator-managed, TLS endpoints.** The bundled `db`/`redis` services are for development only; SaaS-OS does not provision or rotate their certificates | ADR-0028 D1 |
| S4 | PostgreSQL: `sslmode=verify-full`; three roles (migration owner; application role `NOSUPERUSER NOBYPASSRLS`; `saas_os_platform_config` NOLOGIN, never given to the app or worker); a separate database for ZITADEL | RUNBOOKS "Production external PostgreSQL and Redis", CONSUMER-GUIDE §5 |
| S5 | Redis: `rediss://`, `maxmemory-policy noeviction`, AOF. The chain is verified, the hostname is not; a private CA needs `SSL_CERT_FILE` mounted into the worker | RUNBOOKS Redis §3–4 |
| S6 | ZITADEL and its Login V2 v4.19.5, pinned together; master key as a file; same-origin login (Topology A); operators with `forceMfa` | RUNBOOKS "Self-hosted identity operations", "Platform operators" |
| S7 | Edge: Caddy terminating TLS, the single origin `PUBLIC_APP_ORIGIN` (https); only the app and frontend reachable | ADR-0024 |
| S8 | Worker egress only through a proxy (Squid, CONNECT on 443) and its own resolver; the worker has no direct Internet route | ADR-0059 |
| S9 | Secrets: the process environment only (`.env` in development). No Vault/KMS adapter; host compromise exposing secrets is an accepted risk | ADR-0012 |
| S10 | Encrypted off-host backups (`age`) of the app and ZITADEL databases, plus one restore drill into an isolated target | `docs/BACKUP-RESTORE.md` |
| S11 | Audit digests: the worker's log shipped to an append-only store whose administrators hold no tier-0 credential; alert on ~80 min without an `audit_digest` line | RUNBOOKS "Audit digests" |
| S12 | No error tracker may capture local variables (frames can hold webhook secrets) | CONSUMER-GUIDE §15 |
| S13 | Observability vendor undecided; no metrics exporter or alerting shipped | ADR-0009 |
| S14 | Scheduled host jobs: app DB backup 03:00, ZITADEL DB backup 03:15, billing-event retention 03:30, session cleanup hourly | `deploy/` systemd timers |
| S15 | Staging host reference: Linux x86-64, 4 vCPU, 8 GB RAM, 60 GB disk, Compose ≥ 2.17, two DNS names, ports 80/443, an S3-compatible bucket, a second host for the restore drill | `docs/STAGING.md` §1 |

### 1.2 LeadStack

- Components: FastAPI app (`crm_app.app:create_app`) serving the built SPA
  at `/app`; worker `crm-app-worker`; migrations `crm-app-migrate` before
  start; scheduled `crm_app.email_maintenance` (1–5 min),
  `automation_maintenance` (1 min), `signup_maintenance` (few min),
  `import_maintenance` (hourly), `health_check` (from monitoring)
  (`OPERATIONS.md`).
- Single EU region (K5, K5.1). Production email sending and receiving stay
  **off**; start-up refuses every email switch in production.
- Launch gates already recorded and still open: 13-H1 F2
  (`TRUST_PROXY_HEADERS` behind an edge that overwrites `X-Forwarded-For`,
  an edge request-size cap), SIGNUP LG-1 to LG-5 and LG-9/10, the email
  gates in `EMAIL-ARCHITECTURE.md` §6, brief 4 (custom-domain on-demand TLS
  needs a shared certificate store), brief 6 (parent sending domain).
- Missing in the repository today: a production container image, a
  production Compose file and Caddyfile, systemd units, backup
  configuration, an edge size cap, a production role-provisioning script.

### 1.3 What this rules out

- **S3 + S8** together favour a Compose host for the app, worker, edge,
  egress proxy and ZITADEL, next to **managed PostgreSQL and Redis**.
  Self-hosting PostgreSQL and Redis with TLS means owning a CA,
  certificates, rotation and failover: the project SaaS-OS declined.
- Developer PaaS (Render, Fly.io) cannot give the worker an egress proxy
  with no direct route (S8), their internal TLS for `verify-full` is
  unconfirmed [U], and both are US companies. They are listed for cost
  only and not recommended.

## 2. Options

### A — Hetzner Cloud (Germany/Finland), everything self-managed

Compose on VMs; PostgreSQL (primary + streaming standby, pgBackRest to a
Storage Box), Redis and ZITADEL on their own VMs, TLS from a private CA.

- Unit prices [V]: CX23 2 vCPU/4 GB €5.99, CX33 4/8 €8.99, CX43 8/16
  €16.49, LB11 €7.49, Storage Box 1 TB €3.20 (hetzner.com, 2026-11-07).
  Backups +20 %, IPv4 €0.50 [U, third-party].
- **Availability:** the research found the EU shared plans marked
  "currently unavailable" and two price rises in 2026 [V for the page
  text, U for duration]. Confirm capacity before choosing.
- Fits S2, S8, S15 exactly. Fails S3's intent: the TLS endpoints, failover,
  PITR, patching and the Redis private-CA mount (S5) are ours.

### B — Scaleway (Paris), Compose host + managed PostgreSQL and Redis (recommended)

Compose on an Instance (app, worker, Caddy, Squid + resolver, ZITADEL and
its login); Managed Database for PostgreSQL holding the app and ZITADEL
databases; Managed Database for Redis; Object Storage; Secret Manager;
private network.

- Unit prices [V] (Scaleway public product catalogue API): Instance
  BASIC2-A2C-8G €0.0345/h (€25.19), BASIC2-A4C-8G €0.0517/h (€37.74);
  PostgreSQL DB-DEV-S €11.39, DB-PLAY2-PICO €17.01 (HA adds a node and a
  multi-AZ management fee, ≈ €34 [E]); storage €0.099/GB, backups
  €0.029/GB; Redis RED1-MICRO €35.04, extra node €19.71; LB-S €16.79;
  flexible IPv4 €3.65; Object Storage ≈ €0.008–0.016/GB; Secret Manager
  ≈ €0.044 per version-month.
- Fits S2, S3, S8, S15. French, EU-headquartered.
- To verify before purchase: Redis `noeviction` is settable [U]; the Redis
  certificate's CA (a private CA needs the worker mount, S5) [U]; the
  PostgreSQL admin user can create roles with `NOBYPASSRLS` and the schema
  owner role, and ZITADEL's init works without superuser [U]; PITR
  availability and retention [U].

### C — AWS Frankfurt, ECS Fargate + RDS + ElastiCache

- Unit prices [V] (AWS Price List API, eu-central-1, 2026-10-29): Fargate
  ARM 0.5 vCPU/1 GB $16.58; RDS db.t4g.micro $13.87 Single-AZ, t4g.small
  Multi-AZ $54.02; ElastiCache Valkey t4g.micro $10.51; ALB $19.71 + LCUs;
  public IPv4 $3.65 each; Secrets Manager $0.40/secret; CloudWatch logs
  $0.63/GB. NAT gateway ≈ $38 + per GB [U for Frankfurt].
- Managed PostgreSQL and Redis with publicly trusted or bundled CAs: S3–S5
  are the best understood here.
- Off SaaS-OS's reference shape (S2): no Compose host, so the egress proxy,
  resolver and timers must be rebuilt as tasks and scheduled tasks, and the
  worker needs a NAT or proxy path. US parent company.

### D — Render or Fly.io (for comparison only)

Not recommended (section 1.3). Render: web/worker from $7, Postgres from
$19, Key Value from $10 [V]. Fly: 1 GB machine $7.73 in `fra`, Managed
Postgres from $38 with HA included [V]; availability in `fra`/`ams` [U].

### ZITADEL: self-hosted or Cloud

- Self-hosted in the Compose stack is what SaaS-OS documents and what the
  product's same-origin login (Topology A) assumes. Resource need ≈ 512 MB
  and under one core, with spikes for password hashing [V,
  zitadel.com/docs]. Its database is a second database on the managed
  cluster.
- ZITADEL Cloud (Free: 100 DAU, EU residency; Pro $100/month) [V] would
  change the identity architecture, which needs its own approval. Not
  priced into the recommendation.

## 3. Monthly cost

### 3.1 Staging (1 app, 1 worker, smallest databases, free monitoring)

| Option | Line items | Total |
| --- | --- | --- |
| A Hetzner | CX33 with every service €8.99, backups €1.80, IPv4 €0.50, Storage Box €3.20 | **≈ €15** (not production-shaped: databases in Compose) |
| **B Scaleway** | BASIC2-A2C-8G €25.19; PostgreSQL DB-DEV-S €11.39 + 10 GB €0.99 + backups ≈ €0.30; Redis RED1-MICRO €35.04; IPv4 €3.65; Object Storage ≈ €0.20; Secret Manager ≈ €0.50 | **≈ €77** |
| C AWS | 2 Fargate tasks + ZITADEL task $41.45; RDS t4g.micro + 20 GB $16.61; Valkey micro $10.51; ALB + 1 LCU $25.55; IPv4 $18.25; secrets, logs, registry ≈ $6 | **≈ $119** |
| D Render / Fly | as researched | ≈ $46 / $61–71 |

Restore drill: a second instance for a few hours, under €1 [E].

### 3.2 Early production (≤ 50 workspaces, a few hundred users, database < 20 GB)

| Option | Line items | Total |
| --- | --- | --- |
| A Hetzner | 2× CX33 app/worker, CX43 PG primary, CX33 standby, CX23 Redis, CX23 ZITADEL, LB11, backups, volume, IPv4, Storage Box | **≈ €82** + monitoring |
| **B Scaleway, one host** | BASIC2-A4C-8G €37.74; IPv4 €3.65; PostgreSQL PLAY2-PICO HA ≈ €34 + 2 × 20 GB €3.97 + backups €1.17; Redis MICRO + replica €54.75; Object Storage ≈ €1; secrets, logs ≈ €2.50 | **≈ €139** + monitoring |
| B Scaleway, two hosts | the above + second BASIC2-A4C-8G €37.74 + LB-S €16.79 + IP €3.65 | **≈ €197** + monitoring |
| C AWS | 2 app, 2 worker, 2 ZITADEL tasks; RDS t4g.small Multi-AZ; Valkey with replica; ALB; NAT; CloudWatch | **≈ $260** + monitoring |
| D Render / Fly | as researched | ≈ $315–371 / $171–200 |

Monitoring for every option: Sentry Team $26–29 (EU data residency [V];
local-variable capture off, S12) and Better Stack Responder $29–34 for
on-call, or their free tiers until launch [V].

Off-provider backup copy: Backblaze B2 $6.95/TB or a Hetzner Storage Box
€3.20/TB [V]; at < 20 GB, under €1–4.

**Growth** (≈ 200 workspaces, database ≈ 100 GB): for B, a larger
PostgreSQL node (PRO2-XXS ≈ €80 single, ≈ €160 HA [E]) and storage
≈ €10, so ≈ €300–350 a month [E]. The Compose hosts scale vertically
first.

## 4. Recommendation

**Option B, Scaleway Paris:** one Compose host plus managed PostgreSQL (HA
in production) and managed Redis, with self-hosted ZITADEL in the Compose
stack, Better Stack for uptime, heartbeats and the audit-digest log store,
Sentry (EU) for errors, and an encrypted second backup copy at another
provider.

Why:
1. It is SaaS-OS's reference shape (S2, S8) with the managed external TLS
   endpoints ADR-0028 chose (S3). We own no database certificates,
   failover or PITR.
2. EU-headquartered provider, EU region, no US parent; it matches K5/K5.1.
3. Staging and production have the same shape; production adds HA and a
   Redis replica, then a second host behind a load balancer.
4. Every part is standard (PostgreSQL 16, Redis protocol, Compose,
   S3-compatible storage), so moving to Hetzner or AWS later is a
   redeploy and a database restore.

Choose A instead if the lowest cost outweighs operating databases
yourself and Hetzner capacity is confirmed. Choose C if certifications or
an enterprise customer's procurement require AWS.

## 5. Risks

| Risk | Option | Mitigation |
| --- | --- | --- |
| Managed Redis refuses `noeviction` or uses a private CA | B | Verify first (V2, V3); otherwise mount the CA for the worker, or run Redis on a dedicated instance with TLS |
| Managed PostgreSQL admin cannot create the three roles as required | B, C | Verify (V4) on a DB-DEV-S before committing |
| Single Compose host is a single point of failure | A, B | Accepted for staging; production adds the second host when uptime needs it |
| Host compromise exposes every secret (env only) | all | Accepted by ADR-0012; least-privilege database roles, rotation runbook, SSH by key from known addresses |
| Audit log store administered by the same people as the database | all | Better Stack in a separate account with separate admins (S11) |
| Topology A login not fully verified upstream (ADR-0025, SaaS-OS row 1037) | all | Staging exit criterion E4 is a real browser sign-in |
| Custom-domain on-demand TLS needs a shared certificate store (brief 4) | B two hosts, C | Single host first; shared storage before a second host serves custom domains |
| Price or capacity changes | A especially | Re-check prices at order time; keep the setup portable |
| CLOUD Act exposure | C, D | Not applicable to B |

## 6. Migration considerations

- No data exists yet: the first deployment starts from empty databases.
  `crm-app-migrate` runs SaaS-OS's and the product's migrations to head.
- Moving providers later: `pg_dump`/`pg_restore` of both databases
  (encrypted with `age`), ZITADEL master key and keys moved out of band,
  DNS switched with a short TTL, Redis drained (jobs are re-enqueued by
  the sweepers).
- The ZITADEL master key and the backup decryption identity are kept
  offline by the owner; losing them makes backups useless.
- Keep the deployment portable: one image, one Compose file, settings by
  environment, no provider SDK in the application.

## 7. First staging deployment plan

### 7.1 Repository work that needs no account (can start now, local only)

1. A production image for the app and worker (multi-stage: frontend
   build, then Python with the locked dependencies, non-root user).
   **Done 2026-11-07** (`Dockerfile`, decision D-IMG; built in CI).
2. `deploy/staging/`: a Compose file shaped on SaaS-OS
   `docker-compose.prod.yml` (Caddy, app, worker, Squid + resolver,
   ZITADEL + login), with no `db`/`redis` services.
3. A production Caddyfile: TLS, request-size cap, `X-Forwarded-For`
   overwritten, only `/` and `/app` routed (13-H1 F2).
4. systemd units for the product's maintenance commands and SaaS-OS's
   timers (S14).
5. An environment template listing every setting and secret by name, with
   no values, and a role-provisioning script for an external PostgreSQL
   (S4).
6. A staging runbook: deploy, roll back, rotate secrets, restore.

All of this is checked locally (image builds, Compose config validates,
the stack starts against local PostgreSQL and Redis with TLS).

### 7.2 After the owner's approval of provider, account and budget

1. Owner creates the account (billing, MFA, a budget alert at €100/month)
   and approves a staging hostname under a domain the owner holds.
2. Provision: private network, one Instance BASIC2-A2C-8G (ports 80/443
   public, SSH by key from known addresses), PostgreSQL DB-DEV-S
   (PostgreSQL 16), Redis RED1-MICRO, a backup bucket, Secret Manager.
3. Verify V1–V5 (below) before going further.
4. Create the roles and the two databases; download the CA certificates;
   configure `verify-full` and `rediss://`.
5. Deploy the image; run `crm-app-migrate`; start the stack; bootstrap
   ZITADEL; enrol two platform owners with MFA.
6. Install the timers; configure Better Stack heartbeats for
   `crm_app.health_check` and the audit digest, and an uptime check on
   `/readyz`.
7. Run the backup once; restore it on a temporary second instance; delete
   that instance.

### 7.3 Verification before relying on the provider

| # | Check |
| --- | --- |
| V1 | Instance capacity and the prices above, at order time |
| V2 | Redis accepts `maxmemory-policy noeviction` |
| V3 | Redis TLS certificate chain is publicly trusted, or the CA can be mounted for the worker |
| V4 | PostgreSQL admin can create the owner, application (`NOBYPASSRLS`) and NOLOGIN roles and the ZITADEL database |
| V5 | PostgreSQL backups and PITR retention as documented |

### 7.4 Staging exit criteria

| # | Criterion |
| --- | --- |
| E1 | `/healthz` and `/readyz` 200 over HTTPS on the staging hostname |
| E2 | The app refuses to start with a non-`verify-full` database URL or a non-`rediss` Redis URL (negative check) |
| E3 | Migrations at head (SaaS-OS `e2b7c4d9a1f6`, product current head) |
| E4 | A real-browser sign-in through ZITADEL with MFA, and sign-out ending both sessions |
| E5 | Two workspaces created; cross-workspace access refused through the API |
| E6 | Every email switch refused at start-up; no email leaves the host (egress log) |
| E7 | The worker reaches the Internet only through the proxy (a direct connection fails) |
| E8 | Backup encrypted, copied off-provider, restored on a separate instance, `saas_os.ops.audit_digest verify` passes |
| E9 | Heartbeat alert fires when the worker is stopped |
| E10 | Edge size cap and `X-Forwarded-For` overwrite proven |

The evidence goes into `PROGRESS.md`. Passing staging authorizes nothing
further: production, email activation and signup each keep their own
approval.

## 8. Decisions for the owner

1. Choose a provider: **B Scaleway (recommended)**, A Hetzner or C AWS.
2. Approve creating the account and a monthly budget (staging ≈ €77; a
   ceiling such as €100 with an alert).
3. Name the staging hostname and the domain it lives under.
4. Confirm self-hosted ZITADEL (as documented by SaaS-OS) rather than
   ZITADEL Cloud.
5. Approve the monitoring accounts (Better Stack, Sentry) on free tiers
   for staging.
6. Approve an off-provider backup location (Backblaze B2 EU or a Hetzner
   Storage Box).

Section 7.1 can start without any of these and stays local.

## Sources

Hetzner: hetzner.com/cloud/cost-optimized, /regular-performance,
/general-purpose, /load-balancer, /storage/storage-box. Scaleway:
api.scaleway.com/product-catalog/v2alpha1/public-catalog/products;
scaleway.com/en/docs/managed-databases-for-postgresql-and-mysql/faq/.
AWS: pricing.us-east-1.amazonaws.com offers for AmazonRDS,
AmazonElastiCache, AmazonECS, AWSELB, AmazonVPC, AWSSecretsManager,
AmazonCloudWatch (eu-central-1); aws.amazon.com/vpc/pricing/. Render:
render.com/pricing. Fly: docs.fly.io/about/pricing, docs.fly.io/postgres.
ZITADEL: zitadel.com/pricing, zitadel.com/docs/self-hosting/manage/production.
Monitoring and storage: betterstack.com/pricing, grafana.com/pricing,
sentry.io/pricing, backblaze.com/cloud-storage/pricing. SaaS-OS documents
as cited in section 1.1, at commit `0f9bf4d`.
