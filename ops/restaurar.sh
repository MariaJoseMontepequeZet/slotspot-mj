#!/usr/bin/env bash
set -euo pipefail

export PATH="${PATH:-/usr/bin:/bin}:/usr/local/bin:/usr/bin:/bin"

contenedor="${DB_CONTENEDOR:-slotspot-db}"
archivo="${1:-}"

if [ -z "$archivo" ]; then
    echo "Uso: restaurar.sh ARCHIVO.sql.gz [--confirmar]" >&2
    exit 1
fi

if [ ! -f "$archivo" ]; then
    echo "No existe el archivo: $archivo" >&2
    exit 1
fi

if ! gzip -t "$archivo" 2> /dev/null; then
    echo "El archivo no es un gzip valido: $archivo" >&2
    exit 1
fi

if [ "${2:-}" != "--confirmar" ]; then
    echo "Esto reemplaza TODOS los datos de la base de $contenedor con los de $archivo."
    printf 'Escribe RESTAURAR para continuar: '
    read -r respuesta || respuesta=""
    if [ "$respuesta" != "RESTAURAR" ]; then
        echo "Cancelado, no se modifico nada." >&2
        exit 1
    fi
fi

gzip -dc "$archivo" | docker exec -i "$contenedor" sh -c 'psql -v ON_ERROR_STOP=1 -q -1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
echo "Restauracion completada desde $archivo"
