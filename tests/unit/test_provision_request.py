"""The provisioning command refuses a bad request before it touches the
database."""

from __future__ import annotations

from dataclasses import replace

import pytest

from crm_app.provision import ProvisioningRefusedError, Request, validate_request


def _request(**changes: str) -> Request:
    return replace(
        Request(name="Acme Ltd", owner_issuer="https://id.example", owner_subject="1234"),
        **changes,
    )


def test_a_plain_request_is_accepted() -> None:
    validate_request(_request())


@pytest.mark.parametrize("field", ["name", "owner_issuer", "owner_subject"])
@pytest.mark.parametrize("bad", ["\x00", "\n", "\x1f", "\x7f"])
def test_control_characters_are_refused(field: str, bad: str) -> None:
    with pytest.raises(ProvisioningRefusedError, match="control characters"):
        validate_request(_request(**{field: f"a{bad}b"}))


def test_an_empty_or_long_name_is_refused() -> None:
    with pytest.raises(ProvisioningRefusedError, match="empty"):
        validate_request(_request(name="  "))
    with pytest.raises(ProvisioningRefusedError, match="255"):
        validate_request(_request(name="a" * 256))
