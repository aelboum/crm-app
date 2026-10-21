"""This product's own Alembic environment (SaaS-OS ADR-0016).

It has its own script directory and the default `alembic_version` table,
applied after SaaS-OS's own history (`alembic_version_saas_os`) in the same
database; `crm_app.migrate` runs both in that order. The connection is the
privileged migration role (`MIGRATIONS_DATABASE_URL`, resolved by the
installed `saas-os` package), so a migration never runs as the application.
"""

from alembic import context
from saas_os.infra.db import get_migrations_database_config
from sqlalchemy import engine_from_config, pool

config = context.config
target_metadata = None


def run_migrations_offline() -> None:
    context.configure(
        url=get_migrations_database_config().url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_migrations_database_config().url
    connectable = engine_from_config(configuration, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
