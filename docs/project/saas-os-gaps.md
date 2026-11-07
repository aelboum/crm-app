# SaaS-OS gaps found by LeadStack

Status: 2026-11-07. Against the pinned SaaS-OS v0.10.0
(`0f9bf4d67e13aff284af9f30505b7f256ea49801`, decision K3.9), verified in
the installed package. These are capabilities SaaS-OS does not provide that LeadStack
needs. LeadStack does not change, fork or patch SaaS-OS; each gap has a
product-side workaround or keeps a feature blocked until SaaS-OS ships it
and the owner approves a pin move.

## Blocking a feature now

| # | Area | Gap | Blocks | Ask of SaaS-OS |
| --- | --- | --- | --- | --- |
| 1 | `saas_os.core.email` | No custom headers except `Message-ID`: no `List-Unsubscribe` / `List-Unsubscribe-Post` (RFC 8058) | Sending campaigns (bulk-sender requirements); `crm_app.campaigns.SENDING_AVAILABLE` stays false | Let `EmailMessage` carry an allow-listed set of headers, at least the unsubscribe pair, `In-Reply-To` and `References`, validated against header injection. Filed as aelboum/saas-os#224 (2026-11-06). **v0.10.0 adds** `list_unsubscribe`, `list_unsubscribe_post`, `in_reply_to` and `references` on `EmailMessage` and `InvalidEmailHeaderError`; not adopted yet (needs its own slice; production sending stays unauthorized) |
| 2 | `saas_os.infra.egress` | `StrictEgressClient` sends only POST | Real inbound email: Resend's receiving API (`GET /emails/receiving/{id}`, attachments) needs GET; `crm_app.inbound.configured_client()` returns none | GET (and DELETE for item 3) with the same destination, TLS, size and timeout rules. **v0.10.0 adds** `StrictEgressClient.get` with `post`'s policy; `delete` not shipped (issue #205 open). Not adopted yet (needs its own slice; inbound receiving stays unauthorized) |
| 3 | `saas_os.core.email` | No Resend Domains API (create, verify, read, delete a domain and its DNS records) | Customer-owned sending domains per workspace: create and verify are built on the egress client's POST (P6-D); reading and deleting a domain are not possible | A domain-management interface on the provider, Resend first, returning the provider's exact records. Filed as aelboum/saas-os#225 (2026-11-06) |

| 17 | `saas_os.infra.db.backup.orchestrator` | The production pipeline (`run`, `restore`) requires `--container` and reaches the database only through `docker exec`; the endpoint transport for an operator-managed PostgreSQL (ADR-0028 D4-B) exists in `create_backup`/`restore_backup` but the orchestrator never uses it | Encrypted logical backups of a managed PostgreSQL through SaaS-OS's pipeline; the local drill uses the stand-in's container (decision D-STG.2) | Make `container` optional in the orchestrator and its CLI, passing `None` to the endpoint transport. Not filed upstream yet |
| 18 | `saas_os.infra.db.backup` (and the schema's FORCE RLS) | `pg_dump` refuses a table whose RLS would hide rows ("query would be affected by row-level security policy"), and SaaS-OS's own tables (first: `control_plane.ai_inference_attempts`) force RLS on their owner, so the non-superuser migration owner cannot back up the database; a managed admin usually cannot create a BYPASSRLS role (decision M-RLS) | Logical backups on a managed PostgreSQL unless its admin has BYPASSRLS; the local drill dumps as the stand-in's superuser | Document the role a logical backup needs on a managed service and how to obtain it, or a supported alternative. Not filed upstream yet |

## Worked around in LeadStack

| # | Area | Gap | LeadStack's workaround |
| --- | --- | --- | --- |
| 4 | `saas_os.core.email` | `validate_email_address` refuses whitespace, so no display name in `From` | Senders are bare addresses (`team@mail.<parent>`) |
| 5 | `saas_os.core.email` | No `In-Reply-To` / `References` (see 1) | Replies are threaded by a per-conversation routing address. v0.10.0 adds the two fields; not adopted yet |
| 6 | `saas_os.core.email` | No attachments, tags, scheduling or batch send | Outbound mail is text only; one message per send |
| 7 | `saas_os.core.email` | No inbound (receiving) support and no Resend/Svix webhook verification | Product webhooks with their own Svix signature check (`crm_app.domains.emails.signature_valid`) |
| 8 | `saas_os.infra.jobs` | Retries are plain exponential backoff: no jitter, provider `Retry-After` ignored | `email_message.next_attempt_at` and `inbound_email.next_attempt_at` with jitter and `Retry-After` |
| 9 | `saas_os.infra.jobs` | System jobs take no payload; no cron scheduling on the public surface | Due-row batches with `SKIP LOCKED`; maintenance commands run by the deployment's scheduler |
| 10 | `saas_os.core.rbac` | No sanctioned way to grant a newly added permission to existing tenants' roles (saas-os #88). **v0.7.0 adds one:** declared permission grant migrations applied by `saas-os-operator apply-permission-grants` (ADR 0060); declared and trialled locally (decision K3.7); production runs await approval | Operator command `crm_app.role_upgrade` using `SystemCaller(PROVISIONING)` beyond its documented purpose (decision P2-G7) |
| 11 | `saas_os.core.audit_log` / `authority` | No system caller for audit entries when no member acts (a worker, an unsubscribe link, inbound mail). **v0.7.0 adds** `record_system_action_in_transaction` with a `SystemActor`: adopted for every path that had no entry (decision K3.5) | System-actor entries through `crm_app.system_audit` (K3.5, K3.6); only emails a member queued, and appointment reminders, still name a member |
| 12 | `saas_os.infra.db` | No SQL function constructor or cast exported | Full-text search via a stored generated column and an inlined product operator `crm_app.@@` (migration 0023) |
| 13 | `saas_os.inference` | No embeddings API | Phase 9 knowledge retrieval not built (decision P9-0) |
| 14 | `saas_os.core.email` | `EmailOutcomeUnknownError` (with `retry_within`) and `EmailNotSentError` exist since v0.7.0 but are not exported from `saas_os.core.email`; the public `EmailProviderError` fields cannot tell an unknown outcome from a plain transient failure | `crm_app.emails` keeps retrying every non-permanent failure up to `MAX_ATTEMPTS`, so an SMTP send whose outcome is unknown may be delivered twice (Resend is de-duplicated by the `Message-ID` key). Production sending is not authorized (decision K3.4). Filed as aelboum/saas-os#223 (2026-11-06). **v0.9.0 exports both classes; adopted in `crm_app.emails` (decision E-R1, 2026-11-07)** |
| 16 | `docker-compose.prod.yml` (deployment asset) | The `egress-proxy` healthcheck runs `exec 3<>/dev/tcp/127.0.0.1/3128` through `CMD-SHELL`; the Squid image's `/bin/sh` is dash, which has no `/dev/tcp`, so the check always fails (seen 2026-11-07 with the same image digest) | `deploy/staging/compose.yaml` runs the same check through `bash -c` (decision D-STG). Not filed upstream yet |
| 15 | `saas_os.core.notifications` | The `in_app` channel stores only subject and body text: no type or record reference, no read state, an unpaged and unordered `list_notifications()`, and no link from a row to the outbox event that made it | A product-owned inbox, `crm_app.member_notification`, written in the change's own transaction (decision N-1). Filed as aelboum/saas-os#230 (2026-11-06) |

## Suggested order for SaaS-OS

1. Egress GET (2): unblocks inbound email and domain status reads.
2. Email headers (1, 5): unblocks campaigns and header threading.
3. Domains API (3): unblocks customer-owned domains.
4. Job retry controls (8) and the system audit caller (11).
5. Permission upgrade for existing tenants (10, saas-os #88).
6. Display names (4), attachments (6), DB functions (12), embeddings (13).
7. Export the email outcome errors (14): small, and lets products stop retrying an unknown outcome.
8. An in-app inbox (15): a type, a reference, read state and a paged list would let LeadStack move its inbox to SaaS-OS.

Adopting any SaaS-OS release that closes a gap needs the owner's approval
of a pin move (decision K3 and its amendments).
