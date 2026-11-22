#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

base="slotspot_prueba_$$"
rol="slotspot_app_prueba_$$"
psql -v ON_ERROR_STOP=1 -q -d postgres -c "CREATE DATABASE ${base}"
trap 'psql -q -d postgres -c "DROP DATABASE IF EXISTS ${base} WITH (FORCE)"; psql -q -d postgres -c "DROP ROLE IF EXISTS ${rol}"' EXIT

psql -v ON_ERROR_STOP=1 -q -d "$base" -f schema.sql -f seed.sql
psql -v ON_ERROR_STOP=1 -q -d "$base" -f tests/restricciones.sql
psql -v ON_ERROR_STOP=1 -q -d "$base" -v "rol=${rol}" -v "clave=clave-de-prueba" -f roles.sql
psql -v ON_ERROR_STOP=1 -q -d "$base" -v "rol=${rol}" -f tests/permisos.sql
