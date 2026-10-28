"""The product's purge participant and its registration (`crm_app.purge`).

Registration cases run in a fresh interpreter with placeholder settings:
SaaS-OS resolves configuration at import, and the registry is per process.
No service is contacted. Deletion itself is tested against PostgreSQL in
`tests/integration/test_purge.py`.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

import pytest

from crm_app.purge import (
    CRM_DATA_PURGE_PARTICIPANT,
    EXPECTED_PURGE_PARTICIPANTS,
    PARTICIPANT_NAME,
    PURGE_GLOBAL_REFERENCES,
    PURGE_TABLES,
    CrmDataPurgeParticipant,
)
from tests.support import (
    GLOBAL_TABLES,
    PLACEHOLDER_SETTINGS,
    PRODUCT_TABLES,
    PURGE_COVERED_TABLES,
    clean_environment,
    run_python,
)

# SaaS-OS's participant-name grammar (CONSUMER-GUIDE §11).
SAAS_OS_NAME = re.compile(r"[a-z0-9][a-z0-9._-]{0,99}")


def _run(code: str, tmp_path: Path) -> str:
    result = run_python(code, clean_environment(PLACEHOLDER_SETTINGS), tmp_path)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_the_participant_name_is_valid_and_product_prefixed() -> None:
    assert SAAS_OS_NAME.fullmatch(PARTICIPANT_NAME)
    assert PARTICIPANT_NAME.startswith("crm_app.")
    assert EXPECTED_PURGE_PARTICIPANTS == (PARTICIPANT_NAME,)
    assert CRM_DATA_PURGE_PARTICIPANT.name == PARTICIPANT_NAME


def test_the_manifest_is_what_the_table_guard_checks() -> None:
    assert CRM_DATA_PURGE_PARTICIPANT.tables == PURGE_TABLES
    assert frozenset(PURGE_TABLES) == PURGE_COVERED_TABLES
    assert len(set(PURGE_TABLES)) == len(PURGE_TABLES)


def test_every_approved_product_table_is_purged_children_first() -> None:
    assert frozenset(PURGE_TABLES) == PRODUCT_TABLES - GLOBAL_TABLES
    order = PURGE_TABLES.index
    assert order("activity") < order("note") < order("contact") < order("company")
    assert order("consent_record") < order("form_submission") < order("form")
    assert order("form") < order("contact") < order("tag")
    assert order("appointment") < order("contact")
    assert order("booking") < order("booking_page")
    assert order("booking") < order("appointment") < order("contact")


def test_the_manifest_resolves_to_the_mapped_tables_in_a_fresh_process(tmp_path: Path) -> None:
    """What the installed operator process does: no application is built, so
    the participant itself must make the product tables known."""
    out = _run(
        "from crm_app.purge import CRM_DATA_PURGE_PARTICIPANT as p\n"
        "print([p._table(t).fullname for t in p.tables])\n",
        tmp_path,
    )
    assert out == repr([f"crm_app.{t}" for t in PURGE_TABLES])


@pytest.mark.parametrize("bad", ["Contacts", "contacts;drop", "1contacts", "", "crm.contacts"])
def test_a_table_name_that_is_not_a_plain_identifier_is_refused(bad: str) -> None:
    with pytest.raises(ValueError, match="plain SQL identifier"):
        CrmDataPurgeParticipant((bad,))


def test_an_empty_manifest_purges_nothing_without_touching_the_database() -> None:
    CrmDataPurgeParticipant(()).purge_tenant_data(uuid.uuid4())


def test_importing_the_module_reads_no_configuration(tmp_path: Path) -> None:
    result = run_python("import crm_app.purge", clean_environment(), tmp_path)
    assert result.returncode == 0, result.stderr


def test_registration_is_idempotent_and_exact(tmp_path: Path) -> None:
    out = _run(
        "from crm_app.purge import register_purge_participants\n"
        "from saas_os.core.tenancy import registered_purge_participant_names\n"
        "register_purge_participants()\n"
        "register_purge_participants()\n"
        "print(registered_purge_participant_names())\n",
        tmp_path,
    )
    assert out == repr(EXPECTED_PURGE_PARTICIPANTS)


def test_another_participant_under_the_products_name_is_refused(tmp_path: Path) -> None:
    out = _run(
        "from crm_app.purge import CrmDataPurgeParticipant, register_purge_participants\n"
        "from saas_os.core.tenancy import (\n"
        "    DuplicateTenantPurgeParticipantError, register_purge_participant)\n"
        "register_purge_participants()\n"
        "try:\n"
        "    register_purge_participant(CrmDataPurgeParticipant())\n"
        "except DuplicateTenantPurgeParticipantError:\n"
        "    print('refused')\n",
        tmp_path,
    )
    assert out == "refused"


def test_an_unexpected_participant_in_the_process_is_refused(tmp_path: Path) -> None:
    out = _run(
        "from crm_app.purge import (\n"
        "    CrmDataPurgeParticipant, PurgeRegistrationError, register_purge_participants)\n"
        "from saas_os.core.tenancy import register_purge_participant\n"
        "register_purge_participant(CrmDataPurgeParticipant((), name='crm_app.stray'))\n"
        "try:\n"
        "    register_purge_participants()\n"
        "except PurgeRegistrationError:\n"
        "    print('refused')\n",
        tmp_path,
    )
    assert out == "refused"


def test_the_worker_registers_the_participant_before_it_starts(tmp_path: Path) -> None:
    out = _run(
        "import saas_os.api.worker as platform_worker\n"
        "from saas_os.core.tenancy import registered_purge_participant_names\n"
        "seen = []\n"
        "platform_worker.main = lambda argv, extra_functions: seen.append(\n"
        "    registered_purge_participant_names()) or 0\n"
        "from crm_app.worker import run\n"
        "run([])\n"
        "print(seen[0])\n",
        tmp_path,
    )
    assert out.splitlines()[-1] == repr(EXPECTED_PURGE_PARTICIPANTS)


def test_create_app_registers_the_participant(tmp_path: Path) -> None:
    out = _run(
        "from crm_app.app import create_app\n"
        "from saas_os.core.tenancy import registered_purge_participant_names\n"
        "create_app()\n"
        "create_app()\n"
        "print(registered_purge_participant_names())\n",
        tmp_path,
    )
    assert out.splitlines()[-1] == repr(EXPECTED_PURGE_PARTICIPANTS)


def test_global_tables_naming_a_workspace_are_removed_by_the_participant() -> None:
    """`signup` (decision S-1) and `import_expiry` (decision P3-F) name a
    workspace without a key into `core.tenants`; the participant removes
    those rows."""
    assert PURGE_GLOBAL_REFERENCES == ("signup", "import_expiry")
    assert frozenset(PURGE_GLOBAL_REFERENCES) <= GLOBAL_TABLES


def test_a_participant_refuses_a_global_table_it_has_no_step_for() -> None:
    with pytest.raises(ValueError, match="No purge step"):
        CrmDataPurgeParticipant(global_references=("signup_attempt",))
