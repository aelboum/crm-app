#!/bin/sh
# Runs once, on the first start of an empty `db` volume (the postgres
# image's /docker-entrypoint-initdb.d mechanism), and in CI against a fresh
# service container. Creates:
#
# - the restricted runtime role APP_DB_USER: LOGIN, NOSUPERUSER, NOBYPASSRLS,
#   NOCREATEDB, NOCREATEROLE, NOREPLICATION. SaaS-OS refuses to run the
#   application or the worker under a role that can bypass Row-Level Security;
# - the integration-test database `crm_app_test`, next to POSTGRES_DB.
#
# Values are passed to psql as variables and quoted by format(%I, %L), never
# interpolated into SQL text. Local development and CI only: production roles
# are created by the deployment, not by this script.
set -eu

: "${POSTGRES_USER:?POSTGRES_USER must be set}"
: "${POSTGRES_DB:?POSTGRES_DB must be set}"
: "${APP_DB_USER:?APP_DB_USER must be set}"
: "${APP_DB_PASSWORD:?APP_DB_PASSWORD must be set}"

psql -v ON_ERROR_STOP=1 \
    --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    -v app_user="$APP_DB_USER" -v app_password="$APP_DB_PASSWORD" <<'SQL'
SELECT format(
    'CREATE ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION',
    :'app_user', :'app_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'app_user')
\gexec

SELECT 'CREATE DATABASE crm_app_test'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'crm_app_test')
\gexec

SELECT format('GRANT CONNECT ON DATABASE %I TO %I', datname, :'app_user')
FROM pg_database WHERE datname IN (current_database(), 'crm_app_test')
\gexec

SELECT format('REVOKE CONNECT ON DATABASE %I FROM PUBLIC', datname)
FROM pg_database WHERE datname IN (current_database(), 'crm_app_test')
\gexec
SQL
