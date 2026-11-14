#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

base="slotspot_prueba_$$"
psql -v ON_ERROR_STOP=1 -q -d postgres -c "CREATE DATABASE ${base}"
trap 'psql -q -d postgres -c "DROP DATABASE IF EXISTS ${base} WITH (FORCE)"' EXIT

psql -v ON_ERROR_STOP=1 -q -d "$base" -f schema.sql -f seed.sql
psql -v ON_ERROR_STOP=1 -q -d "$base" -f tests/restricciones.sql
