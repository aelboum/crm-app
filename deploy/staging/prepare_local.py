"""Prepare a local run of the staging stack (`deploy/staging/compose.yaml`).

    uv run python deploy/staging/prepare_local.py

Writes, under `deploy/staging/.local/` (ignored by git, never committed):

- a throwaway certificate authority and server certificates for the
  stand-in PostgreSQL (`postgres`) and Redis (`redis`), so the application
  connects with `sslmode=verify-full` and `rediss://` exactly as it would to
  a managed service (SaaS-OS ADR-0028), and for the edge
  (`leadstack.localhost`), so the app verifies its identity provider's
  certificate (`OIDC_CA_BUNDLE`) as it would a public one;
- `compose.env` (the stand-in services' passwords, for `docker compose
  --env-file`), `app.env` (the app's and the worker's settings) and
  `migrate.env` (the migration owner's URL, for `migrate` only), with fresh
  random passwords and ZITADEL's master key.

`OIDC_CLIENT_ID` stays a placeholder until `identity_local.py` creates the
OIDC application in the stack's ZITADEL and writes its ID into `app.env`.

Run it again with `--force` to replace everything (the stand-in databases
must then be recreated: `docker compose ... down -v`). Nothing here is for
a real deployment: a real host gets its certificates from the managed
services and its secrets from the secret store (DECISION-BRIEF-HOSTING.md).
"""

from __future__ import annotations

import base64
import secrets
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

HERE = Path(__file__).resolve().parent
OUT = HERE / ".local"
DAYS = 30
ORIGIN = "https://leadstack.localhost:8443"
EDGE_HOST = "leadstack.localhost"


def _key() -> ec.EllipticCurvePrivateKey:
    return ec.generate_private_key(ec.SECP256R1())


def _pem_key(key: ec.EllipticCurvePrivateKey) -> bytes:
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


def _name(common: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common)])


def _authority(now: datetime) -> tuple[ec.EllipticCurvePrivateKey, x509.Certificate]:
    key = _key()
    cert = (
        x509.CertificateBuilder()
        .subject_name(_name("LeadStack local staging CA"))
        .issuer_name(_name("LeadStack local staging CA"))
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=DAYS))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        # Python 3.13 verifies strictly (VERIFY_X509_STRICT): key identifiers
        # on the authority and on every certificate it signs.
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )
    return key, cert


def _server(
    host: str, ca_key: ec.EllipticCurvePrivateKey, ca: x509.Certificate, now: datetime
) -> tuple[ec.EllipticCurvePrivateKey, x509.Certificate]:
    key = _key()
    cert = (
        x509.CertificateBuilder()
        .subject_name(_name(host))
        .issuer_name(ca.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=DAYS))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(host)]), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False
        )
        .sign(ca_key, hashes.SHA256())
    )
    return key, cert


def _files(passwords: dict[str, str]) -> dict[str, str]:
    """The three settings files. Each process gets only what it needs: the
    app and the worker never see the migration owner's or the database
    admin's credentials."""
    owner, runtime, redis = passwords["owner"], passwords["runtime"], passwords["redis"]
    zitadel = passwords["zitadel_db"]
    tls = "sslmode=verify-full&sslrootcert=/certs/ca.crt"
    head = "# Local staging only (deploy/staging/prepare_local.py). Never commit.\n"
    compose = [
        # Read by `docker compose --env-file` for the stand-in services only.
        "POSTGRES_PASSWORD=" + passwords["admin"],
        "CRM_APP_OWNER_PASSWORD=" + owner,
        "APP_DB_USER=crm_app_runtime",
        "APP_DB_PASSWORD=" + runtime,
        "REDIS_PASSWORD=" + redis,
        "ZITADEL_DB_PASSWORD=" + zitadel,
        # Exactly 32 characters; encrypts ZITADEL's keys at rest.
        "ZITADEL_MASTERKEY=" + passwords["masterkey"],
        "ZITADEL_ADMIN_PASSWORD=" + passwords["zitadel_admin"],
        "ZITADEL_LOGIN_SESSION_COOKIE_SECRET=" + passwords["login_cookie"],
    ]
    app = [
        "ENVIRONMENT=production",
        "APP_DB_USER=crm_app_runtime",
        f"DATABASE_URL=postgresql+psycopg://crm_app_runtime:{runtime}@postgres:5432/crm_app?{tls}",
        f"REDIS_URL=rediss://:{redis}@redis:6380/0",
        # Redis's certificate comes from the local CA (SaaS-OS RUNBOOKS,
        # Redis section 4): Python verifies the chain against this file.
        "SSL_CERT_FILE=/certs/ca.crt",
        "PUBLIC_APP_ORIGIN=" + ORIGIN,
        # ZITADEL on the app's own origin (SaaS-OS ADR-0025), reached by the
        # app through the edge and verified against the local CA only.
        "OIDC_ISSUER_URL=" + ORIGIN,
        "OIDC_CA_BUNDLE=/certs/ca.crt",
        "OIDC_END_SESSION_ENDPOINT=" + ORIGIN + "/oidc/v1/end_session",
        # Replaced by identity_local.py with the ID ZITADEL assigns.
        "OIDC_CLIENT_ID=staging-placeholder",  # pragma: allowlist secret
        "AUTH_POST_LOGIN_PATH=/app",
        "TRUST_PROXY_HEADERS=true",
        # SaaS-OS keeps webhook signing secrets encrypted with this key
        # (decision P12-H); on a host it comes from the secret store.
        "FIELD_ENCRYPTION_ACTIVE_KEY_VERSION=v1",
        "FIELD_ENCRYPTION_KEY_V1=" + passwords["field_key"],
    ]
    migrate = [
        f"MIGRATIONS_DATABASE_URL=postgresql+psycopg://crm_app_owner:{owner}@postgres:5432/crm_app?{tls}",
    ]
    return {
        "compose.env": head + "\n".join(compose) + "\n",
        "app.env": head + "\n".join(app) + "\n",
        "migrate.env": head + "\n".join(migrate) + "\n",
    }


def main(argv: list[str]) -> int:
    force = argv == ["--force"]
    if argv and not force:
        print("usage: prepare_local.py [--force]", file=sys.stderr)
        return 2
    if OUT.exists() and not force:
        print(f"{OUT} exists; use --force to replace it", file=sys.stderr)
        return 1
    OUT.mkdir(exist_ok=True)
    now = datetime.now(UTC)
    ca_key, ca = _authority(now)
    (OUT / "ca.crt").write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    for name, host in (("postgres", "postgres"), ("redis", "redis"), ("edge", EDGE_HOST)):
        key, cert = _server(host, ca_key, ca, now)
        (OUT / f"{name}.crt").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        (OUT / f"{name}.key").write_bytes(_pem_key(key))
    # The CA key is not kept: nothing else is ever signed with it.
    names = ("admin", "owner", "runtime", "redis", "zitadel_db", "masterkey", "login_cookie")
    # token_urlsafe(24) is 32 characters: ZITADEL's master key length.
    passwords = {name: secrets.token_urlsafe(24) for name in names}
    # ZITADEL's default password policy: upper, lower, digit and symbol.
    passwords["zitadel_admin"] = "Aa1!" + secrets.token_urlsafe(18)
    # 32 random bytes, standard base64: SaaS-OS's field-encryption key format.
    passwords["field_key"] = base64.b64encode(secrets.token_bytes(32)).decode("ascii")
    for name, text in _files(passwords).items():
        (OUT / name).write_text(text, encoding="utf-8")
    print(f"wrote {OUT} (certificates valid {DAYS} days)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
