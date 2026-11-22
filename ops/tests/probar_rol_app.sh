#!/usr/bin/env bash
set -euo pipefail

# Requiere un contenedor PostgreSQL real (DB_CONTENEDOR, por defecto slotspot-db) ya listo.

raiz="$(cd "$(dirname "$0")/../.." && pwd)"
contenedor="${DB_CONTENEDOR:-slotspot-db}"
export DB_CONTENEDOR="$contenedor"
export APP_DB_USER="slotspot_app"
export APP_DB_PASSWORD="0123456789abcdef0123456789abcdef"

ok() { echo "OK    $1"; }

fallar() {
    echo "FALLO $1" >&2
    exit 1
}

admin() { docker exec -i "$contenedor" sh -c 'psql -v ON_ERROR_STOP=1 -q -At -U "$POSTGRES_USER" -d "$POSTGRES_DB"'; }

como_app() {
    docker exec -i -e PGPASSWORD="$APP_DB_PASSWORD" "$contenedor" sh -c \
        'psql -h "$(hostname -i)" -v ON_ERROR_STOP=1 -q -At -U slotspot_app -d "$POSTGRES_DB"'
}

docker exec -i "$contenedor" sh -c 'psql -v ON_ERROR_STOP=1 -q -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < "$raiz/db/schema.sql"
docker exec -i "$contenedor" sh -c 'psql -v ON_ERROR_STOP=1 -q -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < "$raiz/db/seed.sql"

bash "$raiz/ops/crear_rol_app.sh" > /dev/null
ok "el script crea el rol"

bash "$raiz/ops/crear_rol_app.sh" > /dev/null
ok "el script se puede repetir"

[ "$(echo "SELECT count(*) FROM tipos_vehiculo" | como_app)" = "5" ] || fallar "el rol no puede leer"
ok "el rol entra con su contrasena y lee"

if echo "DROP TABLE usuarios" | como_app > /dev/null 2>&1; then
    fallar "el rol pudo borrar una tabla"
fi
ok "el rol no puede borrar tablas"

if echo "DELETE FROM auditoria" | como_app > /dev/null 2>&1; then
    fallar "el rol pudo borrar la bitacora"
fi
ok "el rol no puede borrar la bitacora"

if APP_DB_PASSWORD="corta" bash "$raiz/ops/crear_rol_app.sh" > /dev/null 2>&1; then
    fallar "acepto una contrasena corta"
fi
ok "rechaza una contrasena corta"

if APP_DB_PASSWORD="0123456789abcdef0123456789abcdef'; DROP" bash "$raiz/ops/crear_rol_app.sh" > /dev/null 2>&1; then
    fallar "acepto una contrasena con caracteres especiales"
fi
ok "rechaza una contrasena con caracteres especiales"

[ "$(echo "SELECT rolsuper::text FROM pg_roles WHERE rolname = 'slotspot_app'" | admin)" = "false" ] || fallar "el rol es superusuario"
ok "el rol no es superusuario"

echo "TODAS LAS PRUEBAS DEL ROL PASARON"
