"""The permission grant migrations (`crm_app.permission_grants`): append-only,
tied to the role templates, never authority-changing, administrative ones
held back (PERMISSION-GRANT-MIGRATIONS-PLAN.md, step A)."""

from __future__ import annotations

import pytest
from saas_os.core.permission_grants import (
    PermissionGrantMigration,
    permission_grant_migration_digest,
    validate_permission_grant_migrations,
)
from saas_os.core.rbac import is_authority_changing

from crm_app import permission_grants as pg
from crm_app.role_upgrade import GUARDED
from crm_app.roles import GRANTED, ROLE_TEMPLATES, Role

ALL = pg.PERMISSION_GRANT_MIGRATIONS + pg.ADMINISTRATIVE_MIGRATIONS

# The role templates before the first permission was added after Phase 2
# (`crm_app/roles.py` at commit `3bce9b6^`). Fixed: never edit.
BASELINE: dict[str, frozenset[str]] = {
    "Owner": frozenset(
        {
            "crm_app.activity:create",
            "crm_app.activity:delete",
            "crm_app.activity:read",
            "crm_app.activity:update",
            "crm_app.audit:read",
            "crm_app.company:create",
            "crm_app.company:delete",
            "crm_app.company:read",
            "crm_app.company:update",
            "crm_app.contact:create",
            "crm_app.contact:delete",
            "crm_app.contact:read",
            "crm_app.contact:update",
            "crm_app.crm_data:export",
            "crm_app.member_profile:read",
            "crm_app.opportunity:create",
            "crm_app.opportunity:delete",
            "crm_app.opportunity:read",
            "crm_app.opportunity:update",
            "crm_app.owner:manage",
            "crm_app.pipeline:manage",
            "crm_app.pipeline:read",
            "crm_app.task:create",
            "crm_app.task:delete",
            "crm_app.task:read",
            "crm_app.task:update",
            "crm_app.workspace:read",
            "crm_app.workspace:update",
            "crm_app.workspace_security:update",
            "invitation:create",
            "invitation:read",
            "invitation:revoke",
            "membership:reactivate",
            "membership:read",
            "membership:revoke",
            "membership:suspend",
            "membership_role:create",
            "membership_role:delete",
            "tenant:read_status",
        }
    ),
    "Admin": frozenset(
        {
            "crm_app.activity:create",
            "crm_app.activity:delete",
            "crm_app.activity:read",
            "crm_app.activity:update",
            "crm_app.audit:read",
            "crm_app.company:create",
            "crm_app.company:delete",
            "crm_app.company:read",
            "crm_app.company:update",
            "crm_app.contact:create",
            "crm_app.contact:delete",
            "crm_app.contact:read",
            "crm_app.contact:update",
            "crm_app.crm_data:export",
            "crm_app.member_profile:read",
            "crm_app.opportunity:create",
            "crm_app.opportunity:delete",
            "crm_app.opportunity:read",
            "crm_app.opportunity:update",
            "crm_app.pipeline:manage",
            "crm_app.pipeline:read",
            "crm_app.task:create",
            "crm_app.task:delete",
            "crm_app.task:read",
            "crm_app.task:update",
            "crm_app.workspace:read",
            "crm_app.workspace:update",
            "invitation:create",
            "invitation:read",
            "invitation:revoke",
            "membership:reactivate",
            "membership:read",
            "membership:revoke",
            "membership:suspend",
            "membership_role:create",
            "membership_role:delete",
            "tenant:read_status",
        }
    ),
    "Member": frozenset(
        {
            "crm_app.activity:create",
            "crm_app.activity:read",
            "crm_app.company:create",
            "crm_app.company:read",
            "crm_app.company:update",
            "crm_app.contact:create",
            "crm_app.contact:read",
            "crm_app.contact:update",
            "crm_app.member_profile:read",
            "crm_app.opportunity:create",
            "crm_app.opportunity:read",
            "crm_app.opportunity:update",
            "crm_app.pipeline:read",
            "crm_app.task:create",
            "crm_app.task:delete",
            "crm_app.task:read",
            "crm_app.task:update",
            "crm_app.workspace:read",
            "membership:read",
            "tenant:read_status",
        }
    ),
    "Read-only": frozenset(
        {
            "crm_app.activity:read",
            "crm_app.company:read",
            "crm_app.contact:read",
            "crm_app.member_profile:read",
            "crm_app.opportunity:read",
            "crm_app.pipeline:read",
            "crm_app.task:read",
            "crm_app.workspace:read",
            "membership:read",
            "tenant:read_status",
        }
    ),
}

# Each shipped migration's SaaS-OS digest. An applied migration must never
# change (SaaS-OS refuses the whole run); a new one is added here when it is
# appended. Hex digests, not secrets.
# In declaration order, one per migration of each list.
STANDARD_DIGESTS: tuple[str, ...] = (
    "be81231b1c57f6a38b3c4e43cf44544f84d997dfecf9026c5bd269ec0adb9ddf",  # pragma: allowlist secret
    "60d29edbb8278f93164865a97a36be4c561ea93532ba7ad92d4eb6725248add4",  # pragma: allowlist secret
    "c4c4261233b154aa830d9e4ba33dee83d3c32085a8f8e77a5a288b9b672db92a",  # pragma: allowlist secret
    "12e785f78113dba4fe7524d8a4e31b83b20429c939987727a57f40f871b15032",  # pragma: allowlist secret
    "8781b3e58e4b0b263e530c66c4d1c054d287a376ca4bcc7868aafa87df4394a0",  # pragma: allowlist secret
    "1b5b0d35fd30f80af8b99718e63cd3ccd0c317ec5b6bc9402843efba4716c86b",  # pragma: allowlist secret
    "500f4e7f895e22e1911358335840d0ef9c8e207d88ae8107495e8e229e29afc2",  # pragma: allowlist secret
    "f7834151721e2978b10de2601829f2fd08e21758eb01a3f251ef86f8ea2577d4",  # pragma: allowlist secret
    "594023c1c2537add1d47f0788318715980ba81546b6573f0ba4ab104f2ac0e65",  # pragma: allowlist secret
    "c6fac8ac367264eda28dcf588de534c00115ca9e257bec24a2538f54d546e26e",  # pragma: allowlist secret
    "9b5bafc3f0a440b78d73415a8a69cd09b831312da9f70e72005a3f0f8b1a346e",  # pragma: allowlist secret
    "c05bc4ba8f53b74f1a4e7dda947d2a2756616d27ec310ded6f5133c9939ab662",  # pragma: allowlist secret
    "0ba06f831d4877e9012335782cb149a728c549bc627c546f1fc341ba28a06d52",  # pragma: allowlist secret
    "841e3c28938bc1c141bd851941fbe290540e4cb644c03ce14931266f1abec152",  # pragma: allowlist secret
    "242b4664dc478fe3590c0c2f0a73c3e8d00115f2a4e06ad4c97aedd15fd02157",  # pragma: allowlist secret
    "c8911d4019d825c790936c55b625c088ef3b56271cdf310ca6cef3bf7a428c10",  # pragma: allowlist secret
    "5d2ba9f9c9367e7d6576df0683eacbac4fc311c686b228342992f38ec5552515",  # pragma: allowlist secret
    "39f4a40b8b8c15e40041b4083be8143eb9dd4fb50c8e7453c653316b570e7885",  # pragma: allowlist secret
    "ced7c427dbdcbf3048e18173e4e08d44c399e8346d576139b9cb1ea541f1ec71",  # pragma: allowlist secret
    "98e86babc58992b78df20691aba56427990e0cdfdb3dfec62497ad89cd5fa0c5",  # pragma: allowlist secret
    "573cdc44ce37adea113901d8c236303532ac0d0273226e8abd2df198b91f3047",  # pragma: allowlist secret
    "c653b7de49f0fd623c1e25329172f2dc76f08cbc3c015a5ef9725e788cd2a41b",  # pragma: allowlist secret
    "c1f82c205253ecc7055312788ce2c3f8d1461c7a6be3a99a793f643ce97c0531",  # pragma: allowlist secret
    "61f8ffaaf17f5edc6cf6b4c885b436b0b0b4186ae35dfc5191a325d4f9121706",  # pragma: allowlist secret
    "3b9d3b3612f8c3023f660ac34df07896e51a5d62aeada5ad00654ae6fac59337",  # pragma: allowlist secret
    "68b04085ec3ed7a7d64fbb36a826dfb90655a3abd342aa363b01deae91510f72",  # pragma: allowlist secret
    "5032f3b3adab8c4ac9bd1f9ad640da392fde9a65854d0d59b4246411486c6642",  # pragma: allowlist secret
)
ADMINISTRATIVE_DIGESTS: tuple[str, ...] = (
    "77c647223d6c367e137d7a550b479922738a16b4bdfe87ea54c6798e862fa3d0",  # pragma: allowlist secret
    "3b0e441cc19939e4c24d63f05cebae9deb0beb0db26f37b3ac2acf9a756f13dd",  # pragma: allowlist secret
    "17d4570262df94f14b11e55b17a9dd1853878c20ba53d8cd4089b61633ab2f9d",  # pragma: allowlist secret
    "8ce9ee11356c12b58ce199726119fb884ac61dc1746451a7728b7bf29c965913",  # pragma: allowlist secret
    "9838e042ef157a9e8216ece34a314f4a275c5cd40fd11614a5da6a7792536af5",  # pragma: allowlist secret
    "1b85b65533d40c6fb4d57665fdc70a4ce40df60e3303362aa305c3ab85aadb07",  # pragma: allowlist secret
    "93a9623a15dade742062b4464400e623258f67aff07713bbb3a4faa131626146",  # pragma: allowlist secret
    "ac007f93738aed4384bfb304532ad7781f9249ae757c5acf09f37573d478e4e7",  # pragma: allowlist secret
    "cbbb5380bc1ad00155e296cda0562b53fb58c7d2ee9c66bb2bda939d46d8b1db",  # pragma: allowlist secret
    "a203c11cbddf458bdf27f45e9e6b1b4f2adf7c8b18271f47d902717d50fe3921",  # pragma: allowlist secret
    "a236e42a0b2b928e6af8fe0ba53aa02b76b0e7746c49cba090c05d9444c227d2",  # pragma: allowlist secret
    "6e78ea6f7a397e561ef61ca3e093e196a21875f29748b08cc460b238ab3c3320",  # pragma: allowlist secret
)


def _names(keys: frozenset[tuple[str, str]] | set[tuple[str, str]]) -> set[str]:
    return {f"{resource}:{action}" for resource, action in keys}


def test_both_lists_are_valid_saas_os_declarations() -> None:
    validate_permission_grant_migrations(pg.PERMISSION_GRANT_MIGRATIONS, namespace=pg.NAMESPACE)
    validate_permission_grant_migrations(pg.ADMINISTRATIVE_MIGRATIONS, namespace=pg.NAMESPACE)
    # Ids are unique across both lists, which share one namespace and ledger.
    assert len({m.id for m in ALL}) == len(ALL)


def test_no_migration_holds_an_authority_changing_permission() -> None:
    assert not [m.id for m in ALL for key in m.permissions if is_authority_changing(*key)]


def test_administrative_permissions_are_only_in_the_held_back_list() -> None:
    for migration in pg.PERMISSION_GRANT_MIGRATIONS:
        assert not set(migration.permissions) & GUARDED, migration.id
    for migration in pg.ADMINISTRATIVE_MIGRATIONS:
        assert set(migration.permissions) <= GUARDED, migration.id


def test_every_permission_is_one_the_product_registers() -> None:
    registered = set(GRANTED)
    assert not [m.id for m in ALL for key in m.permissions if key not in registered]


def test_templates_are_the_baseline_plus_the_migrations() -> None:
    for role in Role:
        declared = {key for m in ALL if m.role_name == role.value for key in m.permissions}
        baseline = BASELINE[role.value]
        assert not _names(declared) & baseline, role
        assert _names(ROLE_TEMPLATES[role]) == baseline | _names(declared), (
            f"{role.value}: a template permission has no migration, or a migration"
            " grants what the template does not"
        )


def test_every_role_name_is_one_provisioning_creates() -> None:
    assert {m.role_name for m in ALL} <= {role.value for role in Role}


def test_shipped_migrations_never_change() -> None:
    def digests(migrations: tuple[PermissionGrantMigration, ...]) -> tuple[str, ...]:
        return tuple(permission_grant_migration_digest(m) for m in migrations)

    assert digests(pg.PERMISSION_GRANT_MIGRATIONS) == STANDARD_DIGESTS
    assert digests(pg.ADMINISTRATIVE_MIGRATIONS) == ADMINISTRATIVE_DIGESTS


def test_the_report_refuses_without_a_scope() -> None:
    with pytest.raises(SystemExit) as exit_info:
        pg.main(["--report"])
    assert exit_info.value.code == 2
