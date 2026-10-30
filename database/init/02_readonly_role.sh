#!/bin/bash
# Creates the READ-ONLY database role used by the Streamlit app and the
# LangGraph AI workflow. The password comes from an environment variable,
# so no credential is hardcoded here.
#
# Layer 1 of SQL security: even if a malicious query got past the Python
# validator, PostgreSQL itself would refuse to write.
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
     -v ro_user="$RO_DB_USER" -v ro_pass="$RO_DB_PASSWORD" -v db="$POSTGRES_DB" <<'EOSQL'
CREATE ROLE :"ro_user" LOGIN PASSWORD :'ro_pass'
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT CONNECTION LIMIT 20;

GRANT CONNECT ON DATABASE :"db" TO :"ro_user";
GRANT USAGE ON SCHEMA public TO :"ro_user";
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO :"ro_user";

-- Every session of this role is read-only and time-limited.
ALTER ROLE :"ro_user" SET default_transaction_read_only = on;
ALTER ROLE :"ro_user" SET statement_timeout = '5s';
ALTER ROLE :"ro_user" SET idle_in_transaction_session_timeout = '30s';
EOSQL
echo "Read-only role '$RO_DB_USER' created."
