#!/usr/bin/env bash
set -euo pipefail

raiz="$(cd "$(dirname "$0")/../.." && pwd)"
tmp="$(mktemp -d)"
base="slotspot_respaldo_$$"

limpiar() {
    psql -q -d postgres -c "DROP DATABASE IF EXISTS ${base} WITH (FORCE)" > /dev/null 2>&1 || true
    rm -rf "$tmp"
}
trap limpiar EXIT

ok() { echo "OK    $1"; }

fallar() {
    echo "FALLO $1" >&2
    exit 1
}

esperar() {
    [ "$3" = "$2" ] || fallar "$1 - se esperaba '$2' y se obtuvo '$3'"
    ok "$1"
}

sql() { psql -d "$base" -v ON_ERROR_STOP=1 -q -At -c "$1"; }

conteos() {
    sql "SELECT (SELECT count(*) FROM usuarios) || ',' || (SELECT count(*) FROM servicios) || ',' || (SELECT count(*) FROM pagos) || ',' || (SELECT count(*) FROM auditoria) || ',' || (SELECT count(*) FROM tipos_vehiculo) || ',' || (SELECT count(*) FROM slots)"
}

tarifa_auto() { sql "SELECT tarifa_hora FROM tipos_vehiculo WHERE codigo = 'AUT'"; }

archivos() { ls -1 "$tmp/resp" | wc -l | tr -d ' '; }

mkdir -p "$tmp/bin" "$tmp/resp"
cat > "$tmp/bin/docker" << SHIM
#!/usr/bin/env bash
[ "\$1" = "exec" ] || { echo "docker simulado: solo admite exec" >&2; exit 1; }
shift
[ "\$1" = "-i" ] && shift
if [ "\$1" != "slotspot-db" ]; then
    echo "Error: No such container: \$1" >&2
    exit 1
fi
if [ -n "\${SHIM_TRUNCAR:-}" ]; then
    echo "-- dump parcial"
    exit 0
fi
shift 3
POSTGRES_USER="\${PGUSER:-postgres}" POSTGRES_DB="$base" exec sh -c "\$1"
SHIM
chmod +x "$tmp/bin/docker"
export PATH="$tmp/bin:$PATH"
export RESPALDOS_DIR="$tmp/resp"

psql -v ON_ERROR_STOP=1 -q -d postgres -c "CREATE DATABASE ${base}"
psql -v ON_ERROR_STOP=1 -q -d "$base" -f "$raiz/db/schema.sql" -f "$raiz/db/seed.sql"
sql "INSERT INTO usuarios (nombre, email, password_hash, rol_id) SELECT 'Prueba', 'prueba@slotspotmj.com', 'hash', id FROM roles WHERE nombre = 'admin'"
sql "INSERT INTO servicios (placa, tipo_id, slot_numero, estado, entrada, salida, registrado_por) SELECT 'P-111AAA', t.id, 1, 'finalizado', now() - interval '3 hours', now(), u.id FROM tipos_vehiculo t, usuarios u WHERE t.codigo = 'AUT'"
sql "INSERT INTO pagos (servicio_id, horas, tarifa_hora, total, registrado_por) SELECT id, 3, 15.00, 45.00, registrado_por FROM servicios"
sql "INSERT INTO auditoria (usuario_id, accion, entidad) SELECT id, 'cobro', 'servicio' FROM usuarios"
esperar "datos de prueba cargados" "1,1,1,1,5,20" "$(conteos)"

bash "$raiz/ops/respaldar.sh" > /dev/null
esperar "respaldo: se crea un archivo" "1" "$(archivos)"
archivo="$(ls -1 "$tmp/resp"/slotspot_*.sql.gz | head -n 1)"
gzip -t "$archivo" || fallar "respaldo: el archivo no es un gzip valido"
ok "respaldo: gzip valido"
contenido="$(gzip -dc "$archivo")"
[[ "$contenido" == *"CREATE TABLE public.pagos"* ]] || fallar "respaldo: no contiene la tabla pagos"
ok "respaldo: contiene el esquema y los datos"

sleep 1
for i in 1 2 3 4 5 6 7 8 9; do : > "$tmp/resp/slotspot_2020010${i}_000000.sql.gz"; done
RESPALDOS_CANTIDAD=3 bash "$raiz/ops/respaldar.sh" > /dev/null
esperar "retencion: quedan solo 3 respaldos" "3" "$(archivos)"
[ -f "$archivo" ] || fallar "retencion: se borro un respaldo reciente"
ok "retencion: se conserva el respaldo reciente"
[ ! -f "$tmp/resp/slotspot_20200101_000000.sql.gz" ] || fallar "retencion: no se borro el mas antiguo"
ok "retencion: se elimina el mas antiguo"

if RESPALDOS_CANTIDAD=0 bash "$raiz/ops/respaldar.sh" > /dev/null 2>&1; then fallar "cantidad 0 debe rechazarse"; fi
ok "respaldo: rechaza una cantidad invalida"

antes="$(archivos)"
if DB_CONTENEDOR=inexistente bash "$raiz/ops/respaldar.sh" > /dev/null 2>&1; then fallar "un contenedor inexistente debe fallar"; fi
esperar "respaldo fallido: no deja archivos nuevos ni temporales" "$antes" "$(archivos)"

antes="$(archivos)"
if SHIM_TRUNCAR=1 bash "$raiz/ops/respaldar.sh" > /dev/null 2>&1; then fallar "un respaldo incompleto debe descartarse"; fi
esperar "respaldo incompleto: se descarta sin dejar archivos" "$antes" "$(archivos)"

sql "DROP SCHEMA public CASCADE; CREATE SCHEMA public"
esperar "base vaciada" "0" "$(sql "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'")"
bash "$raiz/ops/restaurar.sh" "$archivo" --confirmar > /dev/null
esperar "restauracion: vuelven los datos" "1,1,1,1,5,20" "$(conteos)"
esperar "restauracion: vuelven las 7 tablas" "7" "$(sql "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'")"
esperar "restauracion: vuelven los 5 triggers" "5" "$(sql "SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal")"
if sql "UPDATE servicios SET placa = 'P-999ZZZ'" > /dev/null 2>&1; then fallar "el servicio finalizado debe seguir protegido"; fi
ok "restauracion: los triggers siguen protegiendo los datos"
esperar "restauracion: la secuencia sigue despues del ultimo id" "2" "$(sql "INSERT INTO usuarios (nombre, email, password_hash, rol_id) SELECT 'Otro', 'otro@slotspotmj.com', 'hash', id FROM roles WHERE nombre = 'operador' RETURNING id")"

sql "UPDATE tipos_vehiculo SET tarifa_hora = 99 WHERE codigo = 'AUT'"
if printf 'no\n' | bash "$raiz/ops/restaurar.sh" "$archivo" > /dev/null 2>&1; then fallar "sin confirmar no debe restaurar"; fi
esperar "sin confirmar: no se modifica nada" "99.00" "$(tarifa_auto)"
printf 'RESTAURAR\n' | bash "$raiz/ops/restaurar.sh" "$archivo" > /dev/null || fallar "confirmando por teclado no restauro"
esperar "confirmando por teclado: restaura" "15.00" "$(tarifa_auto)"

echo "no es gzip" > "$tmp/malo.sql.gz"
if bash "$raiz/ops/restaurar.sh" "$tmp/malo.sql.gz" --confirmar > /dev/null 2>&1; then fallar "un archivo que no es gzip debe rechazarse"; fi
ok "restauracion: rechaza un archivo que no es gzip"
if bash "$raiz/ops/restaurar.sh" "$tmp/no-existe.sql.gz" --confirmar > /dev/null 2>&1; then fallar "un archivo inexistente debe rechazarse"; fi
ok "restauracion: rechaza un archivo inexistente"
if bash "$raiz/ops/restaurar.sh" > /dev/null 2>&1; then fallar "sin archivo debe mostrar el uso"; fi
ok "restauracion: exige el archivo"

printf 'UPDATE tipos_vehiculo SET tarifa_hora = 77;\nSELECT 1/0;\n' | gzip > "$tmp/roto.sql.gz"
if bash "$raiz/ops/restaurar.sh" "$tmp/roto.sql.gz" --confirmar > /dev/null 2>&1; then fallar "un respaldo con errores debe fallar"; fi
esperar "restauracion fallida: la transaccion se revierte" "15.00" "$(tarifa_auto)"

echo "TODAS LAS PRUEBAS DE RESPALDO PASARON"
