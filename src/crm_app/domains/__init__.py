"""Product domain modules (contacts, companies, pipelines, ...).

Phase 1 has none. Domain code does not import the HTTP framework, the
entrypoints, `sqlalchemy` or `psycopg` (import-linter contracts in
`pyproject.toml`); it reaches the database only through
`saas_os.infra.db.tenant_session_scope`, with a tenant id taken from a
verified request or job context.
"""
