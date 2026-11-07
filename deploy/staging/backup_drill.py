"""Back up the local staging stack and restore it into a separate instance.

    uv run python deploy/staging/backup_drill.py

The brief's exit criterion E8 as far as a local run can take it (decision
D-STG.2). Everything goes through SaaS-OS's own backup pipeline
(`python -m saas_os.infra.db.backup.orchestrator`, docs/BACKUP-RESTORE.md
at the pinned commit), run on this host as its systemd timer would run it:

1. Back up the app database and ZITADEL's, each to its own staging
   directory under `.local/backups/`, encrypted with `age` to a key pair
   made once in `.local/backups/` (the identity is the owner's offline
   secret on a real host; brief H section 6).
2. Start a separate, empty PostgreSQL ("the drill instance") on its own
   internal network, with the same roles prepared as an operator would
   (`init/01-roles.sh`), and restore both backups into it.
3. Check the restored copies: every RLS table still forces RLS and has a
   policy; the app role is still a safe role; every table's row count and
   both migration versions match the live databases; through the app role,
   one workspace's context sees none of the other's rows; and
   `saas_os.ops.audit_digest verify` passes against the worker's exported
   `audit_digest` log lines (the stand-in for the external log store).
4. Remove the drill instance and its network. The backups stay.

Stand-in limits (written down, not hidden):
- The app database is dumped as the stand-in's superuser. `pg_dump` refuses
  a table whose RLS would hide rows from it, and every tenant table forces
  RLS on its owner, so the non-superuser migration owner cannot take this
  backup (SaaS-OS gap 18). On a managed service this needs the provider's
  backups, or an admin with BYPASSRLS (decision D-STG.2).
- The orchestrator only reaches a database through `docker exec`, which a
  managed service has no container for (SaaS-OS gap 17).
- No off-provider copy: that needs a bucket (an owner decision).
- The drill instance runs on the same host. A real drill uses a second
  host or instance (brief H section 7.2).

Prints one line per check and exits 1 if any fails. Every command is a
fixed `docker` or orchestrator invocation built here; no secret is printed.
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOCAL = HERE / ".local"
BACKUPS = LOCAL / "backups"
DOCKER = shutil.which("docker") or "docker"
AGE_KEYGEN = shutil.which("age-keygen") or "age-keygen"
PROJECT = "crm-app-staging"
LIVE = f"{PROJECT}-postgres-1"
WORKER = f"{PROJECT}-worker-1"
DRILL = f"{PROJECT}-restore-drill"
DRILL_NETWORK = f"{PROJECT}_restore-drill"
IMAGE = "crm-app:staging"
POSTGRES_IMAGE = (
    "postgres:16-alpine@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea"
)
results: list[tuple[str, bool, str]] = []

# Exact row counts of every table, as the superuser (whom RLS never limits).
_COUNTS = r"""
SELECT format('SELECT %L, count(*) FROM %I.%I', n.nspname || '.' || c.relname, n.nspname, c.relname)
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'p') AND n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND n.nspname NOT LIKE 'pg_toast%'
ORDER BY 1
\gexec
"""

# Row-Level Security, table by table: enabled, forced, number of policies.
_RLS = """
SELECT n.nspname || '.' || c.relname, c.relrowsecurity, c.relforcerowsecurity,
       (SELECT count(*) FROM pg_policy p WHERE p.polrelid = c.oid)
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'p') AND n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY 1
"""

# Run in the product image against the restored app database.
_VERIFY = """
import json, os
from sqlalchemy import text
from saas_os.infra.db import DatabaseConfig, build_engine, validate_application_role
from saas_os.infra.db.backup import verify_restored_database

admin = build_engine(DatabaseConfig(url=os.environ["DRILL_ADMIN_URL"]))
checked = verify_restored_database(admin)
app = build_engine(DatabaseConfig(url=os.environ["DATABASE_URL"]))
safe = True
try:
    validate_application_role(app)
except Exception:
    safe = False
# Two workspaces with roles, then that table read through the app role in
# the first workspace's context, and with no context at all.
with admin.connect() as c:
    tenants = c.execute(text("SELECT array_agg(DISTINCT tenant_id::text) FROM core.roles")).scalar()
tenants = tenants or []
isolation = None
if len(tenants) >= 2:
    with app.begin() as c:
        c.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenants[0]})
        own = c.execute(text("SELECT count(*) FROM core.roles")).scalar()
        foreign = c.execute(
            text("SELECT count(*) FROM core.roles WHERE tenant_id <> CAST(:t AS uuid)"),
            {"t": tenants[0]},
        ).scalar()
    with app.begin() as c:
        none = c.execute(text("SELECT count(*) FROM core.roles")).scalar()
    isolation = {"workspaces": len(tenants), "own": own, "foreign": foreign, "no_context": none}
print("RESULT " + json.dumps({
    "schemas": sorted(checked.schemas_present),
    "force": checked.every_rls_table_has_force_rls,
    "policies": checked.every_rls_table_has_a_policy,
    "safe_app_role": safe,
    "isolation": isolation,
}))
"""


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}{(' - ' + detail) if detail else ''}")


def run(
    args: list[str], env: dict[str, str] | None = None, stdin: str | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed docker and orchestrator commands built here
        args, env=env, input=stdin, capture_output=True, text=True, timeout=600, check=False
    )


def _last_line(done: subprocess.CompletedProcess[str]) -> str:
    text = done.stdout.strip() or done.stderr.strip()
    return text.splitlines()[-1][:200] if text else ""


def _env_file(name: str) -> dict[str, str]:
    lines = (LOCAL / name).read_text(encoding="utf-8").splitlines()
    return dict(line.split("=", 1) for line in lines if "=" in line and not line.startswith("#"))


def _keys() -> tuple[str, str]:
    """The age key pair for these local backups: (recipient, identity)."""
    BACKUPS.mkdir(parents=True, exist_ok=True)
    key = BACKUPS / "age-identity.txt"
    if not key.exists():
        made = run([AGE_KEYGEN, "-o", str(key)])
        if made.returncode != 0:
            raise SystemExit("age-keygen failed; is age installed?")
    lines = key.read_text(encoding="utf-8").splitlines()
    recipient = next(x.split(":", 1)[1].strip() for x in lines if x.startswith("# public key:"))
    # The key line alone: SaaS-OS expects exactly `AGE-SECRET-KEY-1...`.
    identity = next(x.strip() for x in lines if x.startswith("AGE-SECRET-KEY-1"))
    return recipient, identity


def _orchestrator(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return run([sys.executable, "-m", "saas_os.infra.db.backup.orchestrator", *args], env)


def _newest(directory: Path) -> tuple[Path, Path]:
    metadata = sorted(directory.glob("*.json"), key=lambda p: p.stat().st_mtime)[-1]
    encrypted = sorted(directory.glob("*.age"), key=lambda p: p.stat().st_mtime)[-1]
    return metadata, encrypted


def _psql(container: str, password: str, database: str, sql: str) -> str:
    done = run(
        [
            DOCKER,
            "exec",
            "-i",
            "-e",
            "PGPASSWORD",
            container,
            "psql",
            "-h",
            "127.0.0.1",
            "-U",
            "postgres",
            "-d",
            database,
            "-At",
            "-v",
            "ON_ERROR_STOP=1",
        ],
        {**os.environ, "PGPASSWORD": password},
        sql,
    )
    if done.returncode != 0:
        raise RuntimeError(f"psql on {container}/{database} failed: {done.stderr[-300:]}")
    return done.stdout


def _counts(container: str, password: str, database: str) -> dict[str, str]:
    rows = _psql(container, password, database, _COUNTS).splitlines()
    return dict(row.split("|", 1) for row in rows if "|" in row)


def _wait_for_drill() -> bool:
    """The image runs its init scripts on a temporary server, then restarts
    for real: ready only after that second start."""
    for _ in range(60):
        logs = run([DOCKER, "logs", DRILL])
        text = logs.stdout + logs.stderr
        ready = run([DOCKER, "exec", DRILL, "pg_isready", "-h", "127.0.0.1", "-U", "postgres"])
        if "PostgreSQL init process complete" in text and ready.returncode == 0:
            return True
        time.sleep(2)
    return False


def _backups(base: dict[str, str]) -> dict[str, tuple[Path, Path]] | None:
    made: dict[str, tuple[Path, Path]] = {}
    for name, var in (
        ("app", "APP_BACKUP_DATABASE_URL"),
        ("zitadel", "ZITADEL_BACKUP_DATABASE_URL"),
    ):
        directory = BACKUPS / name
        directory.mkdir(parents=True, exist_ok=True)
        env = {**base, "BACKUP_STAGING_DIR": str(directory)}
        done = _orchestrator(env, "run", "--container", LIVE, "--admin-database-url-var", var)
        check(f"E8 {name} database backed up and encrypted", done.returncode == 0, _last_line(done))
        if done.returncode != 0:
            return None
        made[name] = _newest(directory)
        header = made[name][1].read_bytes()[:21]
        check(f"E8 the {name} artifact is an age ciphertext", header == b"age-encryption.org/v1")
    return made


def _start_drill(stand_in: dict[str, str], password: str) -> bool:
    run([DOCKER, "rm", "-f", DRILL])
    run([DOCKER, "network", "rm", DRILL_NETWORK])
    run([DOCKER, "network", "create", "--internal", DRILL_NETWORK])
    names = ("CRM_APP_OWNER_PASSWORD", "APP_DB_USER", "APP_DB_PASSWORD", "ZITADEL_DB_PASSWORD")
    passed = [flag for name in ("POSTGRES_PASSWORD", *names) for flag in ("-e", name)]
    # Shaped like the live stand-in (compose.yaml): TLS from the local CA and
    # hostssl only, under the name its certificate carries, so the checks
    # below connect with verify-full exactly as the app does.
    serve = (
        "install -m 600 -o postgres -g postgres /certs/postgres.key /var/lib/postgresql/server.key"
        " && install -m 644 -o postgres -g postgres /certs/postgres.crt"
        " /var/lib/postgresql/server.crt"
        " && exec docker-entrypoint.sh postgres -c ssl=on"
        " -c ssl_cert_file=/var/lib/postgresql/server.crt"
        " -c ssl_key_file=/var/lib/postgresql/server.key"
        " -c ssl_min_protocol_version=TLSv1.2"
    )
    started = run(
        [
            DOCKER,
            "run",
            "-d",
            "--name",
            DRILL,
            "--network",
            DRILL_NETWORK,
            "--network-alias",
            "postgres",
            *passed,
            "-v",
            f"{HERE / 'init' / '01-roles.sh'}:/docker-entrypoint-initdb.d/01-roles.sh:ro",
            "-v",
            f"{LOCAL / 'postgres.crt'}:/certs/postgres.crt:ro",
            "-v",
            f"{LOCAL / 'postgres.key'}:/certs/postgres.key:ro",
            "--entrypoint",
            "sh",
            POSTGRES_IMAGE,
            "-c",
            serve,
        ],
        {**os.environ, "POSTGRES_PASSWORD": password, **{n: stand_in[n] for n in names}},
    )
    ok = started.returncode == 0 and _wait_for_drill()
    check("E8 a separate, empty PostgreSQL started on its own network", ok, started.stderr[-200:])
    return ok


def _verify_app_copy(drill_admin: str, runtime: str) -> None:
    # The app's own settings (production, TLS required), pointed at the
    # restored copy; the drill network reaches nothing else.
    probe = [
        "--env-file",
        str(LOCAL / "app.env"),
        "-e",
        "DRILL_ADMIN_URL",
        "-e",
        "DATABASE_URL",
        "-v",
        f"{LOCAL / 'ca.crt'}:/certs/ca.crt:ro",
    ]
    env = {**os.environ, "DRILL_ADMIN_URL": drill_admin, "DATABASE_URL": runtime}
    verified = run(
        [DOCKER, "run", "--rm", "-i", "--network", DRILL_NETWORK, *probe, IMAGE, "python", "-"],
        env,
        _VERIFY,
    )
    line = next((x for x in verified.stdout.splitlines() if x.startswith("RESULT ")), "")
    found = json.loads(line.removeprefix("RESULT ")) if line else {}
    check(
        "E8 every RLS table still forces RLS and has a policy",
        found.get("force") is True and found.get("policies") is True,
        ", ".join(found.get("schemas", [])) or verified.stderr.strip()[-200:],
    )
    check("E8 the app role is still a safe role", found.get("safe_app_role") is True)
    isolation = found.get("isolation") or {}
    check(
        "E8 a workspace's context sees none of another's rows",
        isolation.get("foreign") == 0
        and (isolation.get("own") or 0) > 0
        and isolation.get("no_context") == 0,
        json.dumps(isolation),
    )

    # The worker's audit_digest lines stand in for the external log store.
    exported = run([DOCKER, "logs", WORKER])
    lines = [
        x
        for x in (exported.stdout + exported.stderr).splitlines()
        if '"message": "audit_digest"' in x
    ]
    with tempfile.NamedTemporaryFile("w", suffix=".log", delete=False, encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
        log_path = handle.name
    try:
        digest = run(
            [
                DOCKER,
                "run",
                "--rm",
                "--network",
                DRILL_NETWORK,
                *probe,
                "-v",
                f"{log_path}:/tmp/audit.log:ro",
                IMAGE,
                "python",
                "-m",
                "saas_os.ops.audit_digest",
                "verify",
                "--partial",
                "/tmp/audit.log",  # noqa: S108 - a path inside the throwaway probe container
            ],
            env,
        )
    finally:
        os.unlink(log_path)
    check(
        f"E8 audit_digest verify passes on the restored copy ({len(lines)} records)",
        digest.returncode == 0 and bool(lines),
        _last_line(digest),
    )


def main() -> int:
    if not (LOCAL / "compose.env").exists():
        print("run prepare_local.py and start the stack first", file=sys.stderr)
        return 2
    stand_in = _env_file("compose.env")
    app = _env_file("app.env")
    recipient, identity = _keys()
    base = {
        **os.environ,
        # The orchestrator's settings and secrets come from the environment
        # (SaaS-OS ADR-0012); nothing secret is passed as an argument.
        "ENVIRONMENT": "production",
        "BACKUP_ENCRYPTION_RECIPIENT": recipient,
        "BACKUP_OFF_SITE_ENABLED": "false",
        # The stand-in's superuser for the app database (gap 18, above);
        # ZITADEL's own role for its database. Used over the container's
        # loopback by `docker exec`.
        "APP_BACKUP_DATABASE_URL": (
            f"postgresql+psycopg://postgres:{stand_in['POSTGRES_PASSWORD']}@postgres:5432/crm_app"
        ),
        "ZITADEL_BACKUP_DATABASE_URL": (
            f"postgresql+psycopg://zitadel:{stand_in['ZITADEL_DB_PASSWORD']}@postgres:5432/zitadel"
        ),
    }
    made = _backups(base)
    if made is None:
        return 1

    drill_password = secrets.token_urlsafe(24)
    try:
        if not _start_drill(stand_in, drill_password):
            return 1
        tls = "sslmode=verify-full&sslrootcert=/certs/ca.crt"
        drill = f"postgres:{drill_password}@postgres:5432"
        restore_env = {
            **base,
            "BACKUP_ENCRYPTION_IDENTITY": identity,
            # Used over the drill container's loopback by `docker exec`.
            "DRILL_ADMIN_DATABASE_URL": f"postgresql+psycopg://{drill}/postgres",
        }
        for name, target in (("app", "crm_app_restored"), ("zitadel", "zitadel_restored")):
            metadata, encrypted = made[name]
            env = {**restore_env, "BACKUP_STAGING_DIR": str(BACKUPS / name)}
            done = _orchestrator(
                env,
                "restore",
                "--container",
                DRILL,
                "--admin-database-url-var",
                "DRILL_ADMIN_DATABASE_URL",
                "--metadata",
                str(metadata),
                "--encrypted",
                str(encrypted),
                "--target-database",
                target,
                "--confirm-production-restore",
            )
            check(f"E8 {name} backup restored into it", done.returncode == 0, _last_line(done))
            if done.returncode != 0:
                return 1

        live_password = stand_in["POSTGRES_PASSWORD"]
        for name, live_db, target in (
            ("app", "crm_app", "crm_app_restored"),
            ("zitadel", "zitadel", "zitadel_restored"),
        ):
            live = _counts(LIVE, live_password, live_db)
            restored = _counts(DRILL, drill_password, target)
            differ = sorted(t for t in set(live) | set(restored) if live.get(t) != restored.get(t))
            rows = sum(int(v) for v in restored.values())
            detail = f"{len(restored)} tables, {rows} rows"
            check(
                f"E8 {name}: every table's row count matches",
                not differ and bool(live),
                detail + (f"; differ: {differ[:5]}" if differ else ""),
            )
        heads = (
            "SELECT (SELECT version_num FROM alembic_version_saas_os)"
            " || ' ' || (SELECT version_num FROM alembic_version)"
        )
        live_rls = _psql(LIVE, live_password, "crm_app", _RLS).splitlines()
        back_rls = _psql(DRILL, drill_password, "crm_app_restored", _RLS).splitlines()
        forced = sum(1 for row in back_rls if row.split("|")[2] == "t")
        product = sum(1 for row in back_rls if row.startswith("crm_app.") and "|t|t|" in row)
        check(
            "E8 RLS restored table by table (enabled, forced, policies), crm_app included",
            live_rls == back_rls and product > 0,
            f"{forced} tables force RLS, {product} of them in crm_app",
        )
        live_heads = _psql(LIVE, live_password, "crm_app", heads).strip()
        back = _psql(DRILL, drill_password, "crm_app_restored", heads).strip()
        check("E8 both migration versions restored", back == live_heads and bool(back), back)

        runtime = (
            f"postgresql+psycopg://{app['APP_DB_USER']}:{stand_in['APP_DB_PASSWORD']}"
            f"@postgres:5432/crm_app_restored?{tls}"
        )
        _verify_app_copy(f"postgresql+psycopg://{drill}/crm_app_restored?{tls}", runtime)
    finally:
        run([DOCKER, "rm", "-f", DRILL])
        run([DOCKER, "network", "rm", DRILL_NETWORK])

    failed = [name for name, ok, _ in results if not ok]
    print(f"\n{len(results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
