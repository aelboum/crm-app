"""The tenant-table guard's decision rules (`tests/catalog_rules.py`)."""

from __future__ import annotations

from dataclasses import replace

from tests.catalog_rules import (
    CHECKED_PRIVILEGES,
    FORBIDDEN_PRIVILEGES,
    REQUIRED_PRIVILEGES,
    Policy,
    classification_violations,
    global_policy_violations,
    global_reference_violations,
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


def test_an_append_only_table_must_lack_update_and_hold_the_rest() -> None:
    append_only = {**CRUD_ONLY, "UPDATE": False}
    assert privilege_violations("activity", append_only, append_only=True) == []
    assert privilege_violations("activity", CRUD_ONLY, append_only=True) == [
        "activity: runtime role holds forbidden UPDATE"
    ]
    for privilege in ("SELECT", "INSERT", "DELETE"):
        held = {**append_only, privilege: False}
        assert privilege_violations("activity", held, append_only=True) == [
            f"activity: runtime role lacks {privilege}"
        ]
    # Without the flag, the same grants are a missing UPDATE.
    assert privilege_violations("activity", append_only) == ["activity: runtime role lacks UPDATE"]


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


# --- Global tables (decision S-1, option A) ---------------------------------

_USER = (
    "((user_id)::text = NULLIF(current_setting('crm_app.signup_user_id'::text, true), ''::text))"
)
_MAINTENANCE = (
    "(NULLIF(current_setting('crm_app.signup_maintenance'::text, true), ''::text) = 'on'::text)"
)
EXCLUSION = Policy(
    name="signup_no_tenant_context",
    command="*",
    permissive=True,
    roles=("public",),
    using="(NULLIF(current_setting('app.tenant_id'::text, true), ''::text) IS NULL)",
    with_check=None,
)
OWNER = (
    Policy("signup_owner_read", "r", False, ("public",), f"({_USER} OR {_MAINTENANCE})", None),
    Policy("signup_owner_insert", "a", False, ("public",), None, _USER),
    Policy("signup_owner_update", "w", False, ("public",), _USER, _USER),
    Policy("signup_owner_delete", "d", False, ("public",), _USER, None),
)


def test_a_person_scoped_global_table_with_exactly_its_policies_passes() -> None:
    assert global_policy_violations("signup", (EXCLUSION, *OWNER), person_scoped=True) == []


def test_a_plain_global_table_needs_only_the_exclusion_policy() -> None:
    attempt = replace(EXCLUSION, name="signup_attempt_no_tenant_context")
    assert global_policy_violations("signup_attempt", (attempt,), person_scoped=False) == []
    assert global_policy_violations("signup_attempt", (), person_scoped=False) == [
        "signup_attempt: missing policy signup_attempt_no_tenant_context"
    ]


def test_a_missing_or_extra_policy_fails() -> None:
    assert global_policy_violations("signup", (EXCLUSION, *OWNER[:3]), person_scoped=True) == [
        "signup: missing policy signup_owner_delete"
    ]
    extra = replace(GOOD_POLICY, name="signup_anything")
    assert "signup: unexpected policy signup_anything" in global_policy_violations(
        "signup", (EXCLUSION, *OWNER, extra), person_scoped=True
    )


def test_an_owner_policy_must_be_restrictive_and_scoped_by_the_person() -> None:
    permissive = replace(OWNER[3], permissive=True)
    assert global_policy_violations(
        "signup", (EXCLUSION, *OWNER[:3], permissive), person_scoped=True
    ) == ["signup: signup_owner_delete is permissive, not restrictive"]
    unscoped = replace(OWNER[2], using="true")
    assert global_policy_violations(
        "signup", (EXCLUSION, OWNER[0], OWNER[1], unscoped, OWNER[3]), person_scoped=True
    ) == ["signup: signup_owner_update USING is not scoped by the person"]


def test_the_maintenance_flag_may_never_widen_a_write() -> None:
    widened = replace(OWNER[3], using=f"({_USER} OR {_MAINTENANCE})")
    assert global_policy_violations(
        "signup", (EXCLUSION, *OWNER[:3], widened), person_scoped=True
    ) == ["signup: signup_owner_delete lets the maintenance flag write"]


def test_the_exclusion_policy_must_require_an_empty_tenant() -> None:
    tenant = replace(EXCLUSION, using=GOOD_POLICY.using)
    assert global_policy_violations("signup", (tenant, *OWNER), person_scoped=True) == [
        "signup: exclusion policy does not require an empty app.tenant_id"
    ]


def test_a_global_table_naming_a_workspace_must_be_purged_without_a_foreign_key() -> None:
    assert (
        global_reference_violations(
            "signup", names_workspace=True, references_tenants=False, purge_covered=True
        )
        == []
    )
    assert global_reference_violations(
        "signup", names_workspace=True, references_tenants=True, purge_covered=False
    ) == [
        "signup: references core.tenants, which would block tenant purge",
        "signup: names a workspace but is not covered by tenant purge",
    ]
    assert (
        global_reference_violations(
            "signup_attempt", names_workspace=False, references_tenants=False, purge_covered=False
        )
        == []
    )
