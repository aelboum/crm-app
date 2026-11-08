# Staging infrastructure report (2026-11-08)

Part of the staging acceptance audit (`STAGING-ACCEPTANCE-REPORT.md`).
Every result below was measured on the host on 2026-11-08 unless marked
otherwise. Finding IDs (`S-n`) are shared across the five staging reports.

## 1. What existed at the start

The owner reported staging as ready. Inspection found an empty host:

| Item | Found |
| --- | --- |
| Host | OVHcloud VPS `vps-043f68cc` (SSH alias `ovh-vps-ai-pbx`), public IPv4 51.91.249.26 |
| OS | Debian 13 (trixie), kernel 6.12.100+deb13-cloud-amd64; 6 vCPU, 11 GiB RAM, 99 GB disk |
| Uptime | 18 minutes (freshly provisioned) |
| Docker / Compose | **not installed** |
| LeadStack, database, proxy | **none** |
| Firewall | ufw active: deny incoming, allow 22/tcp (rate-limited) |
| Listening publicly | sshd (22); systemd-resolved LLMNR (5355, blocked by ufw) |
| DNS | `crm-staging.auravox.nl` did not exist; a proxied Cloudflare wildcard answered instead |

Nothing in `docs/project/` recorded the choice of OVHcloud: the hosting
brief recommended Scaleway with managed PostgreSQL and Redis. The owner
approved deploying everything on this one VPS on 2026-11-08 (decision
D-STG.5).

## 2. What was set up (decision D-STG.5)

| Step | How | Verified |
| --- | --- | --- |
| Docker | Debian packages `docker.io` 26.1.5, `docker-compose` 2.26.1, `docker-buildx`, `git` | `docker version`, `docker compose version` |
| Source | Read-only GitHub deploy key (`staging VPS (OVH) read-only`), clone in `/srv/leadstack/crm-app`; GitHub's host key checked against `gh api meta` (SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU) | clone, `git log` |
| Image | Built on the VPS from the pinned commit (`crm-app:<commit>`, also `crm-app:staging`); no registry, nothing published | SaaS-OS `direct_url.json`: commit `0f9bf4d67e13aff284af9f30505b7f256ea49801`, v0.10.0, equal to the approved pin |
| Secrets | `prepare_local.py --host crm-staging.auravox.nl --days 365 --public-ca /etc/ssl/certs/ca-certificates.crt`, run on the VPS inside the image; `.local/` mode 0700, env files and keys 0600 | `ls -la`; no secret printed or copied off the host |
| Stack | `compose.yaml` + `compose.host.yaml`, profile `stateful-local` (PostgreSQL 16 and Redis 7 in containers, TLS from the stack's own CA) | `docker compose ps`: every service healthy |
| Edge | Caddy 2.11.9 (2.11.4 at first; D-STG.6), Let's Encrypt via HTTP-01, HSTS, HTTP→HTTPS 301 | certificate CN `crm-staging.auravox.nl`, issuer Let's Encrypt YE1, valid to 2027-02-06 |
| Identity | ZITADEL v4.19.5 + Login V2 on the app's origin; OIDC application created by `identity_local.py --origin … --no-restart` | discovery `issuer` = `https://crm-staging.auravox.nl`; browser sign-in works |
| Timers | `deploy/staging/systemd/` installed (all but the heartbeat); `/opt/leadstack` → checkout, `deploy/staging/.env` → `.local/compose.env` | `systemctl list-timers`; `automation_maintenance` ran: "queued 0, queue unreachable 0" |
| Host hardening | `X11Forwarding no` (`/etc/ssh/sshd_config.d/60-leadstack.conf`); LLMNR and mDNS off (`/etc/systemd/resolved.conf.d/60-leadstack.conf`); ufw allows 80/tcp and 443/tcp | `sshd -T`; port 5355 no longer listening |
| DNS | Owner: `crm-staging` A 51.91.249.26, DNS only | 1.1.1.1 and 8.8.8.8 answer 51.91.249.26 |

Repository changes that made this possible: `a3685cd` (host mode),
`1d537d0` (log rotation, log labels), `7aeddf6` and `1170b91` (restart
fixes), `bb90ab8` (image security updates).

## 3. Checks

| Area | Result | Evidence |
| --- | --- | --- |
| Public exposure | **Pass** | From outside: 22, 80, 443 open; 3000, 3128, 5432, 6379, 6380, 8000, 8080, 8443 closed |
| Published ports | **Pass** | Only `edge` publishes (80, 443); PostgreSQL, Redis, ZITADEL, app on internal networks |
| Firewall | **Pass**, note S-17 | ufw default deny; Docker-published ports bypass ufw by design (only 80/443 are published) |
| SSH | **Pass** | keys only, no root login, no keyboard-interactive, X11 off |
| Automatic updates | **Pass** | `unattended-upgrades` active, Debian-Security origin |
| Restart policies | **Pass after fix** (S-1) | every long-running service `unless-stopped` |
| Health checks | **Pass**, note S-12 | all but `edge` define one; all report healthy |
| Startup order | **Pass** | `depends_on` with `service_healthy`; `migrate` completes before `app`/`worker` |
| Reboot recovery | **Pass after fixes** (S-1, S-2) | third reboot: `/readyz` 200 after 32 s, every service healthy |
| Redeploy | **Pass** | new image deployed twice; data kept (contacts before = after) |
| Disk | **Pass**, note S-4 | 4.8 GB of 99 GB used; container logs now rotate (10 MB × 5) |
| Resources | **Pass** | idle: < 1 GiB of 11 GiB used; no container memory limits set (S-12) |
| Image provenance | **Pass** | built from a pinned commit on the host; base images pinned by digest |
| GHCR | **Not used** | owner chose build-on-host; no registry token on the host |

## 4. Findings

### S-1 High — PostgreSQL and Redis stayed down after a reboot (fixed)
- **Evidence:** first reboot: `/readyz` 502 after 245 s; `postgres` and
  `redis` "Exited (0)"; their restart policy `no`; app, worker, ZITADEL
  crash-looping.
- **Impact:** any host restart (kernel update, provider maintenance) took
  staging down until someone intervened.
- **Root cause:** the services were written as stand-ins for managed
  databases, without `restart:`.
- **Remediation:** `restart: unless-stopped` on both (`7aeddf6`).
- **Verification:** reboot: `/readyz` 200 after 31 s. **Owner decision:** no.

### S-2 Medium — The worker's resolver lost its address after a reboot (fixed)
- **Evidence:** second reboot: `dns-resolver` "Address already in use";
  the worker held 172.31.54.2.
- **Impact:** the worker had no DNS: provider calls (email, webhooks)
  would fail once enabled.
- **Root cause:** Docker starts containers in parallel; the worker took
  the resolver's fixed address from the network's dynamic pool.
- **Remediation:** dynamic pool limited to 172.31.54.8/29 (`1170b91`).
- **Verification:** third reboot: resolver healthy, worker on .9.
  **Owner decision:** no.

### S-3 Medium — Squid could not start on Debian 13 (fixed)
- **Evidence:** `FATAL: xcalloc: Unable to allocate 1073741816 blocks`.
- **Root cause:** Docker on Debian 13 leaves the open-file limit at about
  10⁹; Squid sizes a table from it.
- **Remediation:** `ulimits: nofile 65536` on `egress-proxy` (`a3685cd`).
- **Verification:** `egress-proxy` healthy. **Owner decision:** no.

### S-4 Medium — Container logs grew without bound (fixed)
- **Evidence:** one log reached 14 MB in about 45 minutes; no
  `daemon.json`; SaaS-OS's default `console` exporter printed every
  request's trace spans; log lines said `deployment_id: local`,
  `version: 0.0.0`.
- **Impact:** the disk would fill over weeks; logs mislabelled.
- **Remediation:** every service rotates its log (5 × 10 MB);
  `prepare_local.py --host` writes `DEPLOYMENT_ID`,
  `OBSERVABILITY_SERVICE_NAME`, `OBSERVABILITY_EXPORTER=none`; all named
  in `env.template` with `VERSION` (`1d537d0`).
- **Verification:** `LogConfig` `max-size:10m max-file:5`; 0 span lines
  per minute; lines say `deployment_id: staging, version: <commit>`.
  **Owner decision:** no (an exporter is a later decision, ADR-0009).

### S-12 Low — Edge without a health check, Redis as root, no memory limits (partly fixed)
- `edge` defines no health check; the Redis container runs as root (its
  command bypasses the image's privilege drop); no service has a memory
  limit, which matters if the voice PBX shares the host (owner,
  2026-11-08). **Remediation:** add an edge health check, run Redis as its
  user, set limits once the PBX's needs are known. **Owner decision:** the
  limits, with the PBX plan.
- **Update (`bf163ea`):** the edge checks its HTTPS port; Redis runs as
  `redis` (root only copies the key and owns `/data`); both healthy on
  staging. Memory limits remain open.

### S-17 Informational — Docker-published ports bypass ufw
- Docker inserts its own iptables rules, so ufw does not govern published
  ports. Only 80 and 443 are published, both intended. Any future
  `ports:` entry is public regardless of ufw.

### S-18 Informational — Cloudflare records outside staging
- `www.auravox.nl` points at this VPS (proxied) and gets no site;
  `_dmarc` is a proxied CNAME; SPF lists mijndomein's servers while MX is
  Google. None affects staging; all need review before any email is sent
  from `auravox.nl`.

### S-20 Informational — The hosting choice was not recorded
- OVHcloud and a single VPS with in-container databases differ from the
  hosting brief's recommendation (Scaleway, managed services). Recorded
  now as decision D-STG.5.

## 5. Not tested

- Failed deployment and rollback on the host (the runbook's rollback was
  not exercised).
- Behaviour under load and memory pressure.
- The voice PBX sharing the host (not deployed).
