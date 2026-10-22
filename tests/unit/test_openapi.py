"""The committed OpenAPI schema, from which the frontend's typed client is
generated, matches the API (`crm_app.openapi`, decision P-6.1).

When this fails, regenerate both files:

    python -m crm_app.openapi frontend/openapi.json
    (cd frontend && npm run gen:api)
"""

from __future__ import annotations

from pathlib import Path

from tests.support import PLACEHOLDER_SETTINGS, REPO_ROOT, clean_environment, run_module

COMMITTED = REPO_ROOT / "frontend" / "openapi.json"


def test_the_committed_schema_is_current(tmp_path: Path) -> None:
    generated = tmp_path / "openapi.json"
    result = run_module(
        "crm_app.openapi",
        [str(generated)],
        clean_environment(PLACEHOLDER_SETTINGS),
        tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert generated.read_text(encoding="utf-8") == COMMITTED.read_text(encoding="utf-8")
