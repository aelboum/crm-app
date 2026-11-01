"""Text search over conversations (Phase 6 slice 6C.1, decision P6-C1).

Revision ID: 0023_conversation_search
Revises: 0022_conversations
Create Date: 2026-11-01

The Inbox searches a workspace's threads by subject and message text
(`crm_app.conversations.list_conversations`) with PostgreSQL's built-in
full-text search, `simple` configuration (no stemming, no stop words, no
extension). Each table gains a stored generated `search_vector` column and
a GIN index on it. The product reaches SQL only through `saas_os.infra.db`,
which exposes no function constructor or cast, and binds text as
`varchar`; so the search uses the operator `crm_app.@@` (`tsvector @@
varchar`), a plain SQL function that PostgreSQL inlines into
`vector @@ to_tsquery('simple', terms)`, which the GIN index serves. The
product builds `terms` from letters and digits only
(`crm_app.conversations.search_terms`). The columns are derived from text
already stored; nobody writes them. Downgrade drops the operator, function,
indexes and columns.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0023_conversation_search"
down_revision: str | Sequence[str] | None = "0022_conversations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "crm_app"

TABLES = (("conversation", "subject"), ("conversation_message", "body"))


FUNCTION = f"{SCHEMA}.search_matches(tsvector, varchar)"


def upgrade() -> None:
    op.execute(
        f"CREATE FUNCTION {SCHEMA}.search_matches(vector tsvector, terms varchar) "
        "RETURNS boolean LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE "
        "AS $$ SELECT vector @@ to_tsquery('simple'::regconfig, terms::text) $$"
    )
    op.execute(
        f"CREATE OPERATOR {SCHEMA}.@@ (LEFTARG = tsvector, RIGHTARG = varchar, "
        f"FUNCTION = {SCHEMA}.search_matches)"
    )
    for table, source in TABLES:
        op.execute(
            f"ALTER TABLE {SCHEMA}.{table} ADD COLUMN search_vector tsvector "
            f"GENERATED ALWAYS AS (to_tsvector('simple'::regconfig, {source})) STORED"
        )
        op.execute(f"CREATE INDEX {table}_search_idx ON {SCHEMA}.{table} USING gin (search_vector)")


def downgrade() -> None:
    for table, _ in TABLES:
        op.execute(f"DROP INDEX {SCHEMA}.{table}_search_idx")
        op.execute(f"ALTER TABLE {SCHEMA}.{table} DROP COLUMN search_vector")
    op.execute(f"DROP OPERATOR {SCHEMA}.@@ (tsvector, varchar)")
    op.execute(f"DROP FUNCTION {FUNCTION}")
