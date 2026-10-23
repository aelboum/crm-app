"""How `crm_app.records` maps database errors (pre-push review findings).

The race between linking a contact to a company and deleting that company
can end with the contact's foreign-key check failing after the company
pre-check passed; that must be the same 422 `company_not_found`, not a 500.
PostgreSQL resolving a deadlock or serialization failure must become the
retryable 409 `conflict`, and nothing else may. Against a real database
these paths depend on timing, so the mapping itself is pinned here,
deterministically, with stand-in driver errors. Runs in a fresh interpreter
with placeholder settings (SaaS-OS reads configuration at import); no
service is contacted.
"""

from __future__ import annotations

from pathlib import Path

from tests.support import PLACEHOLDER_SETTINGS, clean_environment, run_python

_PROBE = """
import uuid
from types import SimpleNamespace
from saas_os.infra.db import IntegrityError, OperationalError
from crm_app import records

scope = records.Scope(workspace=uuid.uuid4(), actor=uuid.uuid4())

def integrity(constraint):
    orig = SimpleNamespace(diag=SimpleNamespace(constraint_name=constraint))
    return IntegrityError("statement", {}, orig)

def operational(sqlstate):
    return OperationalError("statement", {}, SimpleNamespace(sqlstate=sqlstate))

link = records._duplicate_or(integrity("contact_company_fkey"), records.CONTACT, scope, None)
print("link", type(link).__name__, link.code, link.status)
other = integrity("contact_email_or_phone_check")
print("other", records._duplicate_or(other, records.CONTACT, scope, None) is other)
company = integrity("contact_company_fkey")
print("company", records._duplicate_or(company, records.COMPANY, scope, None) is company)
for state in ("40P01", "40001", "57014", None):
    error = operational(state)
    mapped = records._conflict_or(error)
    print("state", state, type(mapped).__name__, getattr(mapped, "status", None), mapped is error)
"""


def test_database_errors_map_to_the_documented_responses(tmp_path: Path) -> None:
    result = run_python(_PROBE, clean_environment(PLACEHOLDER_SETTINGS), tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines() == [
        "link InvalidReferenceError company_not_found 422",
        "other True",
        "company True",
        "state 40P01 TransactionConflictError 409 False",
        "state 40001 TransactionConflictError 409 False",
        "state 57014 OperationalError None True",
        "state None OperationalError None True",
    ]
