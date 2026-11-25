#!/usr/bin/env bash
set -euo pipefail

# Create the isolated test database configured by POSTGRES_TEST_DB if absent.
TEST_DB="${POSTGRES_TEST_DB:-vcraft_test}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --set="test_db=${TEST_DB}" <<'EOSQL'
SELECT format('CREATE DATABASE %I', :'test_db')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'test_db')\gexec
EOSQL
