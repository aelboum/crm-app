# Proposal — Public Purge-Participant Registration in SaaS-OS (gate G1)

**Status:** technical proposal, 2026-10-22. Summarised as a comment on #87
(see §6); no pull request or other communication. Upstream issue
aelboum/saas-os#87 (opened 2026-10-22 from `PHASE2-PLAN.md` Appendix A)
is **open with no response**; checked 2026-10-22. The latest release is
still v0.3.0 and there are no commits after it.

Gate G1 stays closed:
- no tenant-owned CRM table or migration;
- no import of `saas_os.core.tenancy.purge_participants`;
- no pin change.

## 1. Facts at the pinned v0.3.0 (`5905156`), read from the installed package

**The contract** (`core/tenancy/purge_participants.py`, a module that is
not exported):
- `TenantPurgeParticipant` is a `@runtime_checkable Protocol` with
  `name: str` and `purge_tenant_data(tenant_id: uuid.UUID) -> None`.
- `TenantPurgeParticipantRegistry` has `register(participant) ->
  participant` and `list()`. Duplicate names raise
  `DuplicateTenantPurgeParticipantError`.
- `default_registry()` returns the single registry for the process.

**Semantics** (module docstring):
- Participants run after Core's steps, while the tenant is held in
  `PURGING` under the purge row lock.
- They receive only `tenant_id` and do their own data access, with the
  documented pattern `tenant_session_scope(tenant_id)`.
- They must be idempotent: every retry runs every participant again.
- They report failure by raising. Core records an opaque
  `participant_error` (the type name only) and does not move the tenant
  to `PURGED`.

**`purge_tenant(..., registry=None)`:**
- It is public.
- The `registry=` override is documented as being for test isolation
  only.
- Without participants, product rows remain: "A product that registers
  no participant leaves its rows behind a purged tenant" (consumer
  guide §11).

**`saas-os-operator purge-tenant`:**
- It requires `--setup module:function` (called to register
  participants in that process) or an explicit
  `--no-product-participants`.
- It refuses if `--setup` ran and registered nothing.
- It imports `default_registry` itself (`ops/operator_cli.py:84`).

**The conflict:**
- The consumer guide (§9, §11) and the reference consumer tell products
  to register participants.
- The module is not in `saas_os.core.tenancy.__all__`.
- The update policy (`infra/update/policy.py`) classifies everything
  under `saas_os/core/*` except `__init__.py` as INTERNAL.
- A consumer following the public-surface rule therefore cannot
  register. Even SaaS-OS's own consumer scaffold registers through the
  internal module: `examples/consumer-scaffold/my_product/purge.py`
  L21-24 imports `default_registry` from
  `saas_os.core.tenancy.purge_participants`. The guide's
  `register_purge_participant()` (§9) is that scaffold's own function,
  not a SaaS-OS API.

## 2. Requirements from this product (G1 acceptance, `PHASE2-PLAN.md` §9.4)

1. Registration through a documented public API.
2. Registration guaranteed in **every** process that can purge: the
   application, the worker and the operator command.
3. Fail closed: if a participant fails, the tenant is not `PURGED` and the
   failure is audited.
4. A product participant can prove completeness: it re-reads every table
   and raises if rows remain.
5. Bypass only by an explicit operator flag, never by omission.

## 3. Proposed API

**Neither option below exists in SaaS-OS v0.3.0 or on its `main` branch as
of 2026-10-22.** Both are proposals for the maintainers. The names are
suggestions.

### 3.1 Option A (minimum, recommended for the next release): public re-export

In `saas_os/core/tenancy/__init__.py`:

```python
from saas_os.core.tenancy.purge_participants import (
    DuplicateTenantPurgeParticipantError,
    TenantPurgeParticipant,
)


def register_purge_participant(participant: TenantPurgeParticipant) -> TenantPurgeParticipant:
    """Register a Product participant with this process's registry.
    Idempotent for the same object; a different object with the same name
    raises DuplicateTenantPurgeParticipantError."""


def registered_purge_participant_names() -> tuple[str, ...]:
    """Names registered in this process, in run order (for startup checks
    and tests; no participant objects are exposed)."""
```

- These are added to `__all__`.
- `default_registry` and the registry class stay internal.
- The update policy reclassifies the new names as `PUBLIC_API`.
- **Re-registering the same object is idempotent.** Today a second
  `register()` with the same name always raises. Idempotent registration
  of the same object makes "register in `create_app()`, the worker
  entry and `--setup`" safe when one process calls more than one of
  them.
- **Compatibility:** the internal module stays, and existing imports keep
  working.

### 3.2 Option B (follow-up, recommended): entry-point discovery

Products declare participants in packaging metadata:

```toml
[project.entry-points."saas_os.purge_participants"]
crm_app = "crm_app.purge:participant"
```

`purge_tenant()` (default registry only) and `saas-os-operator
purge-tenant` load every entry point in the group before running.

**This closes requirements 2 and 5 by construction:**
- the installed product's participants are present in every process that
  has the product installed, with no `--setup` to forget;
- `--no-product-participants` stays the only explicit bypass.

**Discovery failure is fail-closed:** an entry point that cannot be
imported or does not satisfy the protocol aborts the purge before Core's
steps, with an audited reason.

### 3.3 Not proposed

- Handing participants a session or connection. Core rightly does not
  know product tables.
- Making `registry=` a supported production path. It is documented as a
  test override.
- An internal-import exception in this product. It was rejected by the
  owner (decision Q-purge).

## 4. Tests we would expect upstream

- The public names import from `saas_os.core.tenancy` and are listed in
  `__all__`; the public-surface classification test treats them as
  `PUBLIC_API`.
- A participant registered through `register_purge_participant` runs
  during `purge_tenant()` and `saas-os-operator purge-tenant --setup`.
- Registering the same object twice is a no-op; a different object with
  the same name raises.
- A failing participant leaves the tenant in `PURGING` with a
  `tenant.purge_failed` audit row naming it; a re-run completes.
- **Option B:** an entry-point participant runs without `--setup`; a
  broken entry point aborts before any Core step; `--no-product-participants`
  still bypasses explicitly.

## 5. Product adoption once released (after the owner approves the pin move)

1. **S0:** the pin moves to the release (a new K3 decision, with upgrade
   checks).
2. **`crm_app/purge.py`:** one participant, `crm_app.crm_data`, that:
   - uses `tenant_session_scope(tenant_id)`;
   - deletes in the order of `PHASE3-PLAN.md` §5;
   - re-reads every table in its manifest and raises if any row
     remains.
3. **Registration:**
   - **Option A:** in `create_app()`, the worker entry and the operator
     `--setup` (`crm_app.purge:register`). A startup check fails if
     `registered_purge_participant_names()` lacks `crm_app.crm_data`.
   - **Option B:** the entry point replaces the three call sites; the
     startup check stays.
4. **Tests:**
   - purging a test tenant with data in every table leaves zero rows;
   - another tenant is untouched;
   - a failing participant leaves PURGING with an audit row;
   - a re-run completes;
   - the schema guard lists every tenant table as covered.
5. **Only then:** the first tenant-owned tables (`PHASE3-PLAN.md` S1).

## 6. Status and next step

- **Outcome (2026-10-23):** SaaS-OS v0.5.0 shipped Option A (#94; #87
  closed). Option B was not adopted: registration stays explicit. The
  pin moved to v0.5.0 (K3.2) and the participant of §5 is in
  `crm_app/purge.py`; G1 passed (`DECISIONS.md` G1). §1–§4 are kept as
  the record of the request.
- **Blocker (historical):** G1 waited on an upstream release with a
  public registration API.
- **Posted 2026-10-22 with the owner's approval:**
  https://github.com/aelboum/saas-os/issues/87#issuecomment-6339887993.
  It is the owner's edited text, plus a reference to CONSUMER-GUIDE §11
  and a criterion naming `saas-os-operator purge-tenant`. It asks the
  maintainers whether they agree with the direction or prefer another
  contract. No other communication was sent.
