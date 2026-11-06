"""The product's system actors (decision K3.5): a fixed, reviewable list."""

from __future__ import annotations

import pytest
from saas_os.core.authority import SystemActor, SystemActorKind

from crm_app import system_audit


def test_every_component_is_a_valid_saas_os_system_actor() -> None:
    for name, kind in system_audit.COMPONENTS.items():
        actor = system_audit.actor(name)
        assert isinstance(actor, SystemActor)
        assert (actor.kind, actor.name) == (kind, name)
        assert name.startswith("crm_app.")


def test_an_unlisted_component_is_refused() -> None:
    with pytest.raises(KeyError):
        system_audit.actor("crm_app.somebody_else")


def test_no_component_claims_billing() -> None:
    # Billing goes through SaaS-OS only (CLAUDE.md, section 5).
    assert SystemActorKind.BILLING_PROCESS not in system_audit.COMPONENTS.values()
