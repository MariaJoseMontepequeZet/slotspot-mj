#!/usr/bin/env bash
set -euo pipefail

# Crea o actualiza el rol de PostgreSQL con el que se conecta la API.
# Uso: APP_DB_PASSWORD=... bash ops/crear_rol_app.sh
# Es seguro repetirlo: si el rol existe, solo cambia la contrasena y reaplica los permisos.

export PATH="${PATH:-/usr/bin:/bin}:/usr/local/bin:/usr/bin:/bin"

raiz="$(cd "$(dirname "$0")/.." && pwd)"
contenedor="${DB_CONTENEDOR:-slotspot-db}"
export APP_DB_USER="${APP_DB_USER:-slotspot_app}"

if [ -z "${APP_DB_PASSWORD:-}" ]; then
    echo "Define APP_DB_PASSWORD con la contrasena del rol de la aplicacion" >&2
    exit 1
fi

case "$APP_DB_USER" in
    '' | [!a-z]* | *[!a-z0-9_]*)
        echo "APP_DB_USER solo admite minusculas, numeros y guion bajo, y empieza con una letra" >&2
        exit 1
        ;;
esac

case "$APP_DB_PASSWORD" in
    *[!A-Za-z0-9]*)
        echo "APP_DB_PASSWORD solo debe llevar letras y numeros (por ejemplo: openssl rand -hex 24)" >&2
        exit 1
        ;;
esac

if [ "${#APP_DB_PASSWORD}" -lt 24 ]; then
    echo "APP_DB_PASSWORD debe tener al menos 24 caracteres" >&2
    exit 1
fi

# La contrasena viaja por el entorno del contenedor, no por la linea de comandos.
docker exec -i -e APP_DB_PASSWORD -e APP_DB_USER "$contenedor" sh -c \
    'psql -v ON_ERROR_STOP=1 -q -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v "rol=$APP_DB_USER" -v "clave=$APP_DB_PASSWORD"' \
    < "$raiz/db/roles.sql"

echo "Rol $APP_DB_USER listo en el contenedor $contenedor"
