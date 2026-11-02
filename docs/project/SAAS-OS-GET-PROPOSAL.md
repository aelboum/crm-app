# Proposal to SaaS-OS: GET (and DELETE) on the strict egress client

**Status:** a proposal for review, prepared on 2026-11-02 under the owner's
instruction "Prepare the SaaS-OS GET change as a separate reviewable
proposal. Do not change the SaaS-OS pin or release SaaS-OS." It is written
for the SaaS-OS maintainers. Nothing in this repository changes because of
it: the pin stays at v0.6.0
(`d980e73b0313ed63f2a59fd4a991a89f75791c0e`), and SaaS-OS is not edited,
forked or released from here. Background: DECISION-BRIEFS brief 1,
`EMAIL-ARCHITECTURE.md` section 1.

## 1. The gap

`saas_os.infra.egress.StrictEgressClient` (v0.6.0) exposes one request
method:

```python
async def post(self, url: str, *, headers: Mapping[str, str],
               content: bytes, deadline: Deadline) -> EgressResponse
```

The exchange itself sends the fixed verb `"POST"`. Resend's receiving API,
which returns the content of an inbound email after its webhook arrives, is
`GET /emails/receiving/{id}`. A consumer therefore cannot read received
mail through platform egress, and a consumer-owned HTTP client would bypass
the platform's destination allowlist, address validation, proxy tunnel and
limits. LeadStack has refused that route (brief 1, option c).

Consequence today, in LeadStack: inbound webhooks are verified, stored and
routed, but `crm_app.inbound.configured_client()` returns `None`, so
received emails wait as `received` and members never see their content.

## 2. Proposed interface

Add two methods beside `post`, sharing its whole pipeline:

```python
async def get(self, url: str, *, headers: Mapping[str, str],
              deadline: Deadline) -> EgressResponse

async def delete(self, url: str, *, headers: Mapping[str, str],
                 deadline: Deadline) -> EgressResponse
```

Implementation sketch for the maintainers (their design governs):

- turn the fixed verb in the exchange into a parameter restricted to a
  closed set, `Literal["GET", "POST", "DELETE"]`; no caller-supplied verb
  string;
- `get` and `delete` send no body; a `Content-Length` or
  `Transfer-Encoding` header from the caller is refused, as forbidden
  headers already are;
- `post` keeps its exact signature and behaviour.

`DELETE` is included so that a consumer can remove provider-side copies
where a provider offers that (keeping retention short); whether Resend's
receiving API offers it has not been verified here. `get` alone unblocks
LeadStack, and the maintainers may prefer to add only that.

## 3. Guarantees that must hold for every verb

Each of these exists for `post` in v0.6.0 and must apply unchanged:

1. Destination allowlist from `StrictEgressPolicy`; URL length, ASCII and
   hostname checks.
2. DNS resolution validated against private, loopback, link-local and other
   non-public ranges, with the existing trusted-address rule; at most
   `max_addresses_tried` addresses.
3. TLS verification required (the client already refuses a context without
   it).
4. The `CONNECT` tunnel when an egress proxy is configured (ADR-0059).
5. Redirects never followed (`EgressRedirectError`).
6. `max_response_bytes` enforced while streaming the body.
7. Connect, read and total deadlines, with the same `EgressTimeoutError`
   phases and the `request_may_have_been_sent` flag.
8. Forbidden caller headers refused.

Retry semantics, for callers: `GET` is safe to retry; `DELETE` is
idempotent at the provider; neither changes `post`.

## 4. Tests the change should carry (in SaaS-OS)

- `get` and `delete` send the right verb and no body, through the default
  transport and through the proxied transport.
- Every guarantee in section 3 is tested once per verb: a disallowed host, a
  private address, a redirect, an oversized response, each timeout phase,
  a forbidden header.
- A `Content-Length` or `Transfer-Encoding` header on `get` or `delete` is
  refused.
- `post`'s existing tests pass unchanged.
- The public-surface contract (the `saas_os.infra.egress` `__init__`
  exports) lists the new methods.

## 5. LeadStack's side, after a release that has it

Not started; listed so the size is known. Each step needs the owner's
approval of the pin move first (CLAUDE.md section 3).

1. Move the pin to the release, with the full re-test (unit, integration,
   frontend, consumer clean install), recorded as a K3.x decision.
2. Add a `ResendReceiving` adapter (about 40 lines) behind the existing
   `ReceivingClient` protocol in `crm_app.inbound`: a policy allowing only
   the Resend API host, `get` on `/emails/receiving/{id}`, the provider's
   JSON returned to the existing parser, `EgressError` mapped to
   `FetchError`. A `delete` after a successful store only if the provider
   offers it and the owner wants it.
3. `configured_client()` returns it only when inbound processing is enabled
   by configuration; it stays off until the owner authorises inbound
   receiving in production.
4. Tests with a transport double: success, provider 404, timeout, an
   oversized answer, a disallowed host; then the existing pipeline tests
   (routing, quarantine, review) run with the real adapter type.

Untouched by all of this: inbound content stays untrusted (text only,
attachments listed and never fetched), and logs keep ids and codes only.

## 6. Reversibility

High. The adapter is selected by configuration; switching it off returns
LeadStack to metadata-only inbound. The SaaS-OS change is additive and does
not alter `post`.
