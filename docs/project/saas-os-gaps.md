# SaaS-OS gaps found by LeadStack

Status: 2026-11-06. Against the pinned SaaS-OS v0.8.0
(`140d9dd2e724357cf54e74fb3be9dadb8943a238`), verified in the installed
package. These are capabilities SaaS-OS does not provide that LeadStack
needs. LeadStack does not change, fork or patch SaaS-OS; each gap has a
product-side workaround or keeps a feature blocked until SaaS-OS ships it
and the owner approves a pin move.

## Blocking a feature now

| # | Area | Gap | Blocks | Ask of SaaS-OS |
| --- | --- | --- | --- | --- |
| 1 | `saas_os.core.email` | No custom headers except `Message-ID`: no `List-Unsubscribe` / `List-Unsubscribe-Post` (RFC 8058) | Sending campaigns (bulk-sender requirements); `crm_app.campaigns.SENDING_AVAILABLE` stays false | Let `EmailMessage` carry an allow-listed set of headers, at least the unsubscribe pair, `In-Reply-To` and `References`, validated against header injection |
| 2 | `saas_os.infra.egress` | `StrictEgressClient` sends only POST | Real inbound email: Resend's receiving API (`GET /emails/receiving/{id}`, attachments) needs GET; `crm_app.inbound.configured_client()` returns none | GET (and DELETE for item 3) with the same destination, TLS, size and timeout rules |
| 3 | `saas_os.core.email` | No Resend Domains API (create, verify, read, delete a domain and its DNS records) | Customer-owned sending domains per workspace: create and verify are built on the egress client's POST (P6-D); reading and deleting a domain are not possible | A domain-management interface on the provider, Resend first, returning the provider's exact records |

## Worked around in LeadStack

| # | Area | Gap | LeadStack's workaround |
| --- | --- | --- | --- |
| 4 | `saas_os.core.email` | `validate_email_address` refuses whitespace, so no display name in `From` | Senders are bare addresses (`team@mail.<parent>`) |
| 5 | `saas_os.core.email` | No `In-Reply-To` / `References` (see 1) | Replies are threaded by a per-conversation routing address |
| 6 | `saas_os.core.email` | No attachments, tags, scheduling or batch send | Outbound mail is text only; one message per send |
| 7 | `saas_os.core.email` | No inbound (receiving) support and no Resend/Svix webhook verification | Product webhooks with their own Svix signature check (`crm_app.domains.emails.signature_valid`) |
| 8 | `saas_os.infra.jobs` | Retries are plain exponential backoff: no jitter, provider `Retry-After` ignored | `email_message.next_attempt_at` and `inbound_email.next_attempt_at` with jitter and `Retry-After` |
| 9 | `saas_os.infra.jobs` | System jobs take no payload; no cron scheduling on the public surface | Due-row batches with `SKIP LOCKED`; maintenance commands run by the deployment's scheduler |
| 10 | `saas_os.core.rbac` | No sanctioned way to grant a newly added permission to existing tenants' roles (saas-os #88). **v0.7.0 adds one:** declared permission grant migrations applied by `saas-os-operator apply-permission-grants` (ADR 0060); not adopted (decision K3.4, needs owner approval) | Operator command `crm_app.role_upgrade` using `SystemCaller(PROVISIONING)` beyond its documented purpose (decision P2-G7) |
| 11 | `saas_os.core.audit_log` / `authority` | No system caller for audit entries when no member acts (a worker, an unsubscribe link, inbound mail). **v0.7.0 adds** `record_system_action_in_transaction` with a `SystemActor`: adopted for every path that had no entry (decision K3.5) | System-actor entries through `crm_app.system_audit`; bookings, forms, consent confirmations, automation steps and member-queued emails still act as a member under their approved decisions |
| 12 | `saas_os.infra.db` | No SQL function constructor or cast exported | Full-text search via a stored generated column and an inlined product operator `crm_app.@@` (migration 0023) |
| 13 | `saas_os.inference` | No embeddings API | Phase 9 knowledge retrieval not built (decision P9-0) |
| 14 | `saas_os.core.email` | `EmailOutcomeUnknownError` (with `retry_within`) and `EmailNotSentError` exist since v0.7.0 but are not exported from `saas_os.core.email`; the public `EmailProviderError` fields cannot tell an unknown outcome from a plain transient failure | `crm_app.emails` keeps retrying every non-permanent failure up to `MAX_ATTEMPTS`, so an SMTP send whose outcome is unknown may be delivered twice (Resend is de-duplicated by the `Message-ID` key). Production sending is not authorized (decision K3.4) |

## Suggested order for SaaS-OS

1. Egress GET (2): unblocks inbound email and domain status reads.
2. Email headers (1, 5): unblocks campaigns and header threading.
3. Domains API (3): unblocks customer-owned domains.
4. Job retry controls (8) and the system audit caller (11).
5. Permission upgrade for existing tenants (10, saas-os #88).
6. Display names (4), attachments (6), DB functions (12), embeddings (13).
7. Export the email outcome errors (14): small, and lets products stop retrying an unknown outcome.

Adopting any SaaS-OS release that closes a gap needs the owner's approval
of a pin move (decision K3 and its amendments).
