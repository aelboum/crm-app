"""The tenant-table guard's decision rules (`tests/catalog_rules.py`)."""

from __future__ import annotations

from dataclasses import replace

from tests.catalog_rules import (
    CHECKED_PRIVILEGES,
    FORBIDDEN_PRIVILEGES,
    REQUIRED_PRIVILEGES,
    Policy,
    classification_violations,
    policy_violations,
    privilege_violations,
    purge_violations,
    rls_violations,
)

GOOD_POLICY = Policy(
    name="contacts_tenant_isolation",
    command="*",
    permissive=True,
    roles=("public",),
    using="(tenant_id = (NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid)",
    with_check=None,
)
CRUD_ONLY = {p: p in REQUIRED_PRIVILEGES for p in CHECKED_PRIVILEGES}


def test_exactly_crud_passes() -> None:
    assert privilege_violations("contacts", CRUD_ONLY) == []


def test_each_forbidden_privilege_fails() -> None:
    for privilege in FORBIDDEN_PRIVILEGES:
        held = {**CRUD_ONLY, privilege: True}
        assert privilege_violations("contacts", held) == [
            f"contacts: runtime role holds forbidden {privilege}"
        ]


def test_each_missing_crud_privilege_fails() -> None:
    for privilege in REQUIRED_PRIVILEGES:
        held = {**CRUD_ONLY, privilege: False}
        assert privilege_violations("contacts", held) == [
            f"contacts: runtime role lacks {privilege}"
        ]


def test_an_unchecked_privilege_fails_instead_of_passing() -> None:
    assert privilege_violations("contacts", {}) == [
        f"contacts: privilege {p} was not checked" for p in CHECKED_PRIVILEGES
    ]


def test_rls_must_be_enabled_and_forced() -> None:
    assert rls_violations("t", enabled=True, forced=True) == []
    assert len(rls_violations("t", enabled=True, forced=False)) == 1
    assert len(rls_violations("t", enabled=False, forced=False)) == 2


def test_the_platform_policy_shape_passes() -> None:
    assert policy_violations("contacts", [GOOD_POLICY]) == []


def test_no_policy_or_an_extra_policy_fails() -> None:
    assert policy_violations("contacts", []) != []
    extra = replace(GOOD_POLICY, name="contacts_extra")
    assert policy_violations("contacts", [GOOD_POLICY, extra]) != []


def test_each_policy_deviation_fails() -> None:
    deviations = [
        replace(GOOD_POLICY, name="contacts_open"),
        replace(GOOD_POLICY, command="r"),
        replace(GOOD_POLICY, permissive=False),
        replace(GOOD_POLICY, roles=("crm_app_runtime",)),
        replace(GOOD_POLICY, using="(true)"),
        replace(GOOD_POLICY, using=None),
        replace(GOOD_POLICY, with_check="(true)"),
    ]
    for policy in deviations:
        assert len(policy_violations("contacts", [policy])) == 1, policy


def test_purge_coverage_names_every_uncovered_table() -> None:
    assert purge_violations({"a", "b"}, {"a"}) == ["b: not covered by tenant purge"]
    assert purge_violations({"a"}, {"a", "b"}) == []
    assert purge_violations(set(), set()) == []


def test_every_product_table_must_be_tenant_owned_or_declared_global() -> None:
    assert classification_violations({"contacts", "currencies"}, {"contacts"}, {"currencies"}) == []
    assert classification_violations({"notes"}, set(), set()) == [
        "notes: has no tenant_id and is not declared global"
    ]
    assert classification_violations({"contacts"}, {"contacts"}, {"contacts"}) == [
        "contacts: declared global but has a tenant_id"
    ]
