#!/usr/bin/env bash
set -euo pipefail
umask 077

export PATH="${PATH:-/usr/bin:/bin}:/usr/local/bin:/usr/bin:/bin"

carpeta="${RESPALDOS_DIR:-$HOME/slotspot/respaldos}"
cantidad="${RESPALDOS_CANTIDAD:-7}"
contenedor="${DB_CONTENEDOR:-slotspot-db}"

case "$cantidad" in
    '' | *[!0-9]* | 0)
        echo "RESPALDOS_CANTIDAD debe ser un entero mayor que 0" >&2
        exit 1
        ;;
esac

mkdir -p "$carpeta"
archivo="$carpeta/slotspot_$(date +%Y%m%d_%H%M%S).sql.gz"
temporal="${archivo}.tmp"
trap 'rm -f "$temporal"' EXIT

docker exec "$contenedor" sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --clean --if-exists' | gzip > "$temporal"

gzip -t "$temporal"
cola="$(gzip -dc "$temporal" | tail -n 5)"
case "$cola" in
    *"dump complete"*) ;;
    *)
        echo "El respaldo quedo incompleto y se descarto" >&2
        exit 1
        ;;
esac

mv "$temporal" "$archivo"
echo "Respaldo creado: $archivo ($(du -h "$archivo" | cut -f1))"

ls -1 "$carpeta"/slotspot_*.sql.gz | sort -r | tail -n "+$((cantidad + 1))" | while IFS= read -r viejo; do
    rm -f -- "$viejo"
    echo "Respaldo antiguo eliminado: $viejo"
done
