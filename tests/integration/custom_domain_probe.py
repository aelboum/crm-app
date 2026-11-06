"""Drives custom domains (decision P12-D) and prints one `RESULT <json>` line.

Run in a fresh interpreter by `tests/integration/test_custom_domains.py`.
DNS answers come from a test double in this process, never from the
network. Seeds throwaway workspaces. Refuses to run unless ENVIRONMENT=test.
"""

from __future__ import annotations

import json
import os
import secrets
import uuid
from typing import Any

from fastapi.testclient import TestClient
from saas_os.core.authority import SystemAuthority, SystemCaller, UserCaller
from saas_os.core.identity import issue_session
from saas_os.core.platform_authority import (
    PlatformPermission,
    enroll_operator,
    grant_platform_permission,
)
from saas_os.core.tenancy import TenantStatus, transition_tenant_status
from saas_os.infra.db import tenant_session_scope
from sqlalchemy import text

from crm_app import custom_domains
from crm_app.app import create_app
from crm_app.records import Scope
from crm_app.roles import Role
from tests.integration.opportunity_route_probe import _member
from tests.integration.workspace_route_probe import _new_user, _new_workspace


class FakeDns:
    """TXT records by name; `fail` makes every lookup fail."""

    def __init__(self) -> None:
        self.records: dict[str, list[str]] = {}
        self.fail = False

    def txt(self, name: str) -> list[str]:
        if self.fail:
            raise custom_domains.ResolverError("timeout")
        return list(self.records.get(name, []))


def _age(workspace: uuid.UUID, domain_id: str, column: str, interval: str) -> None:
    with tenant_session_scope(workspace) as session:
        session.execute(
            text(
                f"UPDATE crm_app.custom_domain SET {column} = now() - interval '{interval}'"  # noqa: S608 - constants from this probe
                " WHERE tenant_id = :t AND id = :d"
            ),
            {"t": workspace, "d": domain_id},
        )


def main() -> None:  # noqa: PLR0915 - one scenario script, read top to bottom
    if os.environ.get("ENVIRONMENT") != "test":
        raise SystemExit("custom_domain_probe runs only with ENVIRONMENT=test")
    a = _new_workspace("domain-a")
    b = _new_workspace("domain-b")
    _, member = _member(a, Role.MEMBER)
    _, reader = _member(a, Role.READ_ONLY)
    tokens = {
        "owner": issue_session(a.owner_id)[1],
        "member": member,
        "reader": reader,
        "other_owner": issue_session(b.owner_id)[1],
        "outsider": issue_session(_new_user())[1],
    }

    def auth(caller: str = "owner", version: int | None = None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {tokens[caller]}"}
        if version is not None:
            headers["If-Match"] = f'"{version}"'
        return headers

    host = f"forms-{secrets.token_hex(3)}.acme-shop.nl"
    scope_a = Scope(workspace=a.id, actor=a.owner_id)
    scope_b = Scope(workspace=b.id, actor=b.owner_id)
    dns = FakeDns()
    result: dict[str, Any] = {}
    with TestClient(create_app(), follow_redirects=False) as client:
        base = f"/v1/workspaces/{a.id}/domains"

        def add(hostname: str, caller: str = "owner", workspace: uuid.UUID = a.id) -> Any:
            return client.post(
                f"/v1/workspaces/{workspace}/domains",
                json={"hostname": hostname},
                headers=auth(caller),
            )

        made = add(f"  {host.upper()} ")
        claim = made.json()
        result["added"] = [
            made.status_code,
            claim.get("hostname") == host,
            claim.get("status"),
            claim.get("record_name") == f"_leadstack-challenge.{host}",
            claim.get("record_value", "").startswith("leadstack-verification="),
            claim.get("expires_at") is not None,
        ]
        app_origin = os.environ.get("PUBLIC_APP_ORIGIN", "http://localhost:8000")
        app_host = app_origin.split("//", 1)[1].split(":", 1)[0].split("/", 1)[0]
        result["refused"] = [
            add("localhost").status_code,
            add("*.acme-shop.nl").status_code,
            add("192.168.1.10").status_code,
            add("www.example.com").status_code,
            add(f"pages.{app_host}").status_code,
            add(host).status_code,
            add("other.acme-shop.nl", "member").status_code,
            add("other.acme-shop.nl", "other_owner").status_code,
        ]
        result["reader_lists"] = len(client.get(base, headers=auth("reader")).json()["items"])
        one = f"{base}/{claim['id']}"

        # Without a configured resolver nothing is verified.
        unchecked = client.post(f"{one}/check", headers=auth(version=1)).json()
        result["no_resolver"] = [unchecked["status"], unchecked["last_error"]]
        result["member_check"] = client.post(f"{one}/check", headers=auth("member", 2)).status_code

        def check(scope: Scope, domain_id: str) -> dict[str, Any]:
            with tenant_session_scope(scope.workspace) as session:
                version = session.execute(
                    text(
                        "SELECT version FROM crm_app.custom_domain WHERE tenant_id = :t AND id = :d"
                    ),
                    {"t": scope.workspace, "d": domain_id},
                ).scalar_one()
            item = custom_domains.check(
                scope, uuid.UUID(domain_id), expected_version=version, resolver=dns
            )
            return {"status": item["status"], "error": item["last_error"]}

        def resolve(hostname: str) -> int | str:
            response = client.get("/v1/public/domains/resolve", headers={"Host": hostname})
            if response.status_code != 200:
                return response.status_code
            return str(response.json()["workspace_id"])

        result["missing_record"] = check(scope_a, claim["id"])
        result["resolve_pending"] = resolve(host)
        dns.records[claim["record_name"]] = [f'"{claim["record_value"]}"', "v=spf1 -all"]
        result["verified"] = check(scope_a, claim["id"])
        result["resolve_verified"] = resolve(host) == str(a.id)
        result["resolve_with_port"] = resolve(f"{host.upper()}:443") == str(a.id)
        result["resolve_unknown"] = resolve("nobody.acme-shop.nl")

        # Another workspace claims the same host and publishes its own token:
        # it stays pending while A holds the host.
        b_claim = add(host, "other_owner", b.id).json()
        dns.records[b_claim["record_name"]] = [claim["record_value"], b_claim["record_value"]]
        result["claimed_elsewhere"] = check(scope_b, b_claim["id"])
        result["b_sees"] = [
            len(
                client.get(f"/v1/workspaces/{b.id}/domains", headers=auth("other_owner")).json()[
                    "items"
                ]
            ),
            client.post(
                f"/v1/workspaces/{b.id}/domains/{claim['id']}/check",
                headers=auth("other_owner", 1),
            ).status_code,
            client.delete(
                f"/v1/workspaces/{b.id}/domains/{claim['id']}", headers=auth("other_owner")
            ).status_code,
        ]

        # The domain changes hands: its record now holds only B's token. A
        # failing lookup lapses nothing; the daily re-check lapses A's claim,
        # and then B can verify.
        dns.records[claim["record_name"]] = [b_claim["record_value"]]
        _age(a.id, claim["id"], "checked_at", "2 days")
        dns.fail = True
        result["recheck_failing_dns"] = custom_domains.recheck_due(dns, limit=100000)["lapsed"]
        dns.fail = False
        _age(a.id, claim["id"], "checked_at", "2 days")
        custom_domains.recheck_due(dns, limit=100000)
        result["a_after"] = client.get(base, headers=auth()).json()["items"][0]["status"]
        result["resolve_after_lapse"] = resolve(host)
        result["b_takes_over"] = check(scope_b, b_claim["id"])
        result["resolve_b"] = resolve(host) == str(b.id)

        # 13-H3: a suspended workspace's domain resolves to nothing, and
        # again once the workspace is reactivated.
        bootstrap = SystemCaller(SystemAuthority.PLATFORM_BOOTSTRAP)
        operator_user = _new_user()
        operator = enroll_operator(operator_user, caller=bootstrap, reason="crm-app domain test")
        for permission in (PlatformPermission.TENANT_SUSPEND, PlatformPermission.TENANT_REACTIVATE):
            grant_platform_permission(
                operator.id, permission, caller=bootstrap, reason="crm-app domain test"
            )
        transition_tenant_status(b.id, TenantStatus.SUSPENDED, caller=UserCaller(operator_user))
        result["resolve_suspended"] = resolve(host)

        def allowed(hostname: str) -> int:
            return client.get("/v1/public/domains/allowed", params={"domain": hostname}).status_code

        result["allowed_suspended"] = allowed(host)
        transition_tenant_status(b.id, TenantStatus.ACTIVE, caller=UserCaller(operator_user))
        result["resolve_reactivated"] = resolve(host) == str(b.id)
        allowed_response = client.get("/v1/public/domains/allowed", params={"domain": host})
        result["allowed"] = [
            allowed_response.status_code,
            allowed_response.text,
            allowed(host.upper()),
            allowed("nobody.acme-shop.nl"),
            allowed(""),
            allowed("x" * 400),
        ]

        # Removing frees the host at once.
        result["removed"] = [
            client.delete(
                f"/v1/workspaces/{b.id}/domains/{b_claim['id']}", headers=auth("other_owner")
            ).status_code,
            resolve(host),
        ]

        # An expired claim cannot be verified and is cleared by the re-check.
        late = add(f"late-{secrets.token_hex(3)}.acme-shop.nl").json()
        _age(a.id, late["id"], "expires_at", "1 hour")
        result["expired_check"] = client.post(
            f"{base}/{late['id']}/check", headers=auth(version=1)
        ).json()["detail"]
        custom_domains.recheck_due(dns, limit=100000)
        result["expired_cleared"] = late["id"] not in [
            item["id"] for item in client.get(base, headers=auth()).json()["items"]
        ]
        result["outsider"] = client.get(base, headers=auth("outsider")).status_code
        # The re-check's own entries (K3.5): one lapse, one expiry, no member.
        with tenant_session_scope(a.id) as session:
            result["recheck_audit"] = sorted(
                [row[0], row[1], row[2]]
                for row in session.execute(
                    text(
                        "SELECT resource_id, metadata->>'status', actor_user_id IS NULL"
                        " FROM core.audit_log WHERE tenant_id = :t"
                        " AND action = 'crm_app.custom_domain.status_changed'"
                        " AND metadata->'system_actor'->>'name' = 'crm_app.domain_maintenance'"
                    ),
                    {"t": a.id},
                )
            )
        result["recheck_expected"] = sorted(
            [[claim["id"], "lapsed", True], [late["id"], "expired", True]]
        )
    print("RESULT " + json.dumps(result, default=str))


if __name__ == "__main__":
    main()
