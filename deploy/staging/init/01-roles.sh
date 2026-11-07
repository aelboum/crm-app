#!/bin/sh
# Stand-in for a managed PostgreSQL's setup (stateful-local profile only;
# decision D-STG). Run once by the official image as its admin user, the way
# an operator would run it with a managed service's admin account:
#
# - `crm_app_owner`: owns the `crm_app` database and runs the migrations
#   (SaaS-OS's and the product's). NOT a superuser and cannot bypass RLS, as
#   on a managed service, so migrations are proven to work without either.
# - the application role (`APP_DB_USER`): NOSUPERUSER NOBYPASSRLS; the
#   migrations grant it exactly its table privileges.
# - `saas_os_platform_config`: created NOLOGIN here so the owner needs no
#   CREATEROLE (SaaS-OS RUNBOOKS, platform configuration role); its URL is
#   never given to the app or the worker.
# - `zitadel`: owns the separate `zitadel` database (ZITADEL keeps its own,
#   SaaS-OS ADR-0023), NOT a superuser; ZITADEL's init finds its role and
#   database already there and only creates its schemas.
# - Only TLS connections are accepted from the network.
set -eu

: "${CRM_APP_OWNER_PASSWORD:?}"
: "${APP_DB_USER:?}"
: "${APP_DB_PASSWORD:?}"
: "${ZITADEL_DB_PASSWORD:?}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    -v owner_password="$CRM_APP_OWNER_PASSWORD" \
    -v app_user="$APP_DB_USER" -v app_password="$APP_DB_PASSWORD" \
    -v zitadel_password="$ZITADEL_DB_PASSWORD" <<'SQL'
SELECT format(
    'CREATE ROLE crm_app_owner LOGIN PASSWORD %L NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION',
    :'owner_password')
\gexec
SELECT format(
    'CREATE ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION',
    :'app_user', :'app_password')
\gexec
CREATE ROLE saas_os_platform_config NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION;
CREATE DATABASE crm_app OWNER crm_app_owner;
REVOKE CONNECT ON DATABASE crm_app FROM PUBLIC;
SELECT format('GRANT CONNECT ON DATABASE crm_app TO %I', :'app_user')
\gexec
SELECT format(
    'CREATE ROLE zitadel LOGIN PASSWORD %L NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION',
    :'zitadel_password')
\gexec
CREATE DATABASE zitadel OWNER zitadel;
REVOKE CONNECT ON DATABASE zitadel FROM PUBLIC;
GRANT CONNECT ON DATABASE zitadel TO zitadel;
SQL

# Network clients must use TLS; the image's default rule allows plain TCP.
sed -i 's/^host all all all /hostssl all all all /' "$PGDATA/pg_hba.conf"
