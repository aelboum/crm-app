"""Writes the API's OpenAPI schema, from which the frontend's typed client
is generated (decision P-6.1).

    python -m crm_app.openapi frontend/openapi.json

Builds the application without contacting any service (configuration is
validated, nothing is connected) and writes the schema with sorted keys, so
the committed file changes only when the API does. A unit test fails when
the committed file is stale.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def render() -> str:
    from crm_app.app import create_app  # noqa: PLC0415 - configuration is read at import

    return json.dumps(create_app().openapi(), indent=2, sort_keys=True) + "\n"


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: python -m crm_app.openapi <output.json>", file=sys.stderr)
        return 2
    Path(argv[0]).write_text(render(), encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
