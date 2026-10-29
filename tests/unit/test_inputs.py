"""Shared request inputs (`crm_app.api.inputs`, security review 13-H1): a
small JSON body is refused when too large, declared or actual, and a body
nested too deeply is a 422 like any other non-JSON body, not a 500; a time
outside 1900-2999, including one Python cannot convert, is a 422.

Run in a fresh interpreter with placeholder settings, because SaaS-OS
resolves configuration at import time; nothing is contacted.
"""

from __future__ import annotations

import json
from pathlib import Path

from tests.support import PLACEHOLDER_SETTINGS, clean_environment, run_python

_PROBE = (
    "import json\n"
    "from fastapi import FastAPI, Request\n"
    "from fastapi.testclient import TestClient\n"
    "from pydantic import BaseModel\n"
    "from crm_app.api.inputs import Instant, json_body\n"
    "app = FastAPI()\n"
    "class At(BaseModel):\n"
    "    at: Instant\n"
    "@app.post('/body')\n"
    "async def body(request: Request) -> dict:\n"
    "    return {'payload': await json_body(request, 16384)}\n"
    "@app.post('/at')\n"
    "def at(value: At) -> dict:\n"
    "    return {'at': value.at.isoformat()}\n"
    "client = TestClient(app)\n"
    "def body_status(content, headers=None):\n"
    "    return client.post('/body', content=content, headers=headers or {}).status_code\n"
    "def at_status(value):\n"
    "    return client.post('/at', json={'at': value}).status_code\n"
    "print('RESULT ' + json.dumps({\n"
    "    'small': client.post('/body', content=b'{\"a\": 1}').json(),\n"
    "    'large': body_status(b'[' + b'1,' * 9000 +b'1]'),\n"
    "    'declared': body_status(b'{}', {'content-length': '100000'}),\n"
    "    'deep': body_status(b'[' * 8000),\n"
    "    'not_json': body_status(b'nope'),\n"
    "    'usual': at_status('2026-10-29T09:30:00+01:00'),\n"
    "    'naive': at_status('2026-10-29T09:30:00'),\n"
    "    'earliest': at_status('0001-01-01T00:00:00+14:00'),\n"
    "    'latest': at_status('9999-12-31T23:59:59-14:00'),\n"
    "    'before': at_status('1899-12-31T23:59:59+00:00'),\n"
    "    'after': at_status('3000-01-01T00:00:00+00:00'),\n"
    "}))\n"
)


def _run(tmp_path: Path) -> dict[str, object]:
    result = run_python(_PROBE, clean_environment(PLACEHOLDER_SETTINGS), tmp_path)
    assert result.returncode == 0, result.stderr
    line = next(x for x in result.stdout.splitlines() if x.startswith("RESULT "))
    return json.loads(line.removeprefix("RESULT "))


def test_bodies_and_times_are_bounded(tmp_path: Path) -> None:
    result = _run(tmp_path)
    assert result["small"] == {"payload": {"a": 1}}
    assert result["large"] == 400
    assert result["declared"] == 400
    assert result["deep"] == 422
    assert result["not_json"] == 422
    assert result["usual"] == 200
    assert result["naive"] == 422
    assert result["earliest"] == 422
    assert result["latest"] == 422
    assert result["before"] == 422
    assert result["after"] == 422
