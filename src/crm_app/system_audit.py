"""Audit entries for actions no member performs (decision K3.5).

SaaS-OS v0.7.0 added `record_system_action_in_transaction`: an entry whose
actor is a system component (`SystemActor`), with no member named. This
module is the product's one way to write such an entry, so every system
component has a fixed, named actor:

- the actor's `kind` is SaaS-OS's closed list (`SystemActorKind`);
- its `name` is one of `COMPONENTS` below, never an id;
- `initiated_by` is left out, which SaaS-OS records as `"unavailable"`;
  no member's id is ever stored there (SaaS-OS refuses a user initiator).

An entry is written inside the caller's tenant transaction, so the change
and its evidence commit or roll back together. Metadata follows the same
rules as member entries: ids, codes and counts only, never an address, a
message body or a provider text.

Paths whose entries name a member under an approved decision (bookings,
forms, consent confirmation, automation steps, emails a member queued)
are unchanged.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping

from saas_os.core.audit_log import record_system_action_in_transaction
from saas_os.core.authority import SystemActor, SystemActorKind
from saas_os.infra.db import Session

# Component name -> its SaaS-OS kind. A name not listed here is refused, so
# the set of system actors in the audit trail stays reviewable.
COMPONENTS: Mapping[str, SystemActorKind] = {
    "crm_app.unsubscribe_link": SystemActorKind.PUBLIC_LINK,
    "crm_app.email_send": SystemActorKind.WORKER_JOB,
    "crm_app.email_events": SystemActorKind.PROVIDER_EVENT_PROCESSOR,
    "crm_app.sending_domain_events": SystemActorKind.PROVIDER_EVENT_PROCESSOR,
    "crm_app.inbound_process": SystemActorKind.INBOUND_PROCESSOR,
    "crm_app.automation_run": SystemActorKind.WORKER_JOB,
    "crm_app.domain_maintenance": SystemActorKind.MAINTENANCE,
    "crm_app.import_maintenance": SystemActorKind.MAINTENANCE,
}


def actor(component: str) -> SystemActor:
    """The `SystemActor` of a listed component; `KeyError` otherwise."""
    return SystemActor(kind=COMPONENTS[component], name=component)


def record(  # noqa: PLR0913 - mirrors the SaaS-OS writer, all keyword-only
    session: Session,
    *,
    workspace: uuid.UUID,
    component: str,
    action: str,
    resource_type: str,
    resource_id: str | None,
    metadata: Mapping[str, object] | None = None,
) -> None:
    """Append one system entry for `workspace` inside `session`, which must
    be that workspace's tenant session (RLS refuses any other)."""
    record_system_action_in_transaction(
        session,
        tenant_id=workspace,
        actor=actor(component),
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        metadata=dict(metadata or {}),
    )
