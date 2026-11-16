# SlotSpot MJ API

API del sistema de administracion de parqueadero SlotSpot MJ. El frontend vive en [slotspot-mj-frontend](https://github.com/MariaJoseMontepequeZet/slotspot-mj-frontend).

**Desarrolladora:** Maria Jose Montepeque Zet  
**Tecnologias:** Python 3.12, FastAPI, PostgreSQL 16, Docker, Docker Compose

---

## Estado actual

Esta es la base del backend. Hoy expone un solo endpoint y sirve para validar el despliegue automatico. Los demas endpoints se agregan por etapas.

| Metodo | Ruta | Descripcion |
|--------|------|-------------|
| GET | `/salud` | Devuelve `{"estado": "ok"}`. Lo usa el healthcheck de Docker |

En el servidor, Caddy publica la API bajo `/api/*`, por lo que desde el navegador la ruta es `/api/salud`.

## Estructura

```
slotspot-mj/
├── app/
│   └── main.py                 # Aplicacion FastAPI
├── db/
│   ├── schema.sql              # Tablas, restricciones, indices y triggers
│   ├── seed.sql                # Roles, tipos de vehiculo y 20 slots
│   ├── probar.sh               # Crea una base temporal y ejecuta las pruebas
│   └── tests/
│       └── restricciones.sql   # 55 pruebas de las reglas del negocio
├── ops/
│   ├── respaldar.sh            # Respaldo diario de PostgreSQL con retencion
│   ├── restaurar.sh            # Restauracion desde un respaldo, con confirmacion
│   ├── docker-compose.yml      # Compose de referencia con limites y rotacion de logs
│   └── tests/
│       └── probar_respaldos.sh # Prueba de respaldo y restauracion
├── docs/
│   └── diagrama-er.md          # Diagrama entidad-relacion
├── tests/
│   └── test_salud.py           # Pruebas con pytest
├── .github/workflows/
│   ├── ci.yml                  # Ruff, pytest, base de datos, respaldos y compose
│   └── desplegar.yml           # Despliegue automatico al hacer push a main
├── Dockerfile                  # Imagen de la API
├── requirements.txt            # Dependencias de ejecucion
├── requirements-dev.txt        # Dependencias de desarrollo (pytest, ruff)
├── pyproject.toml              # Configuracion de ruff y pytest
└── .env.example                # Nombres de las variables de entorno
```

## Ejecutar en local

```bash
python -m venv .venv
.venv/Scripts/activate        # En Linux o macOS: source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

La API queda en `http://127.0.0.1:8000`. La documentacion interactiva de FastAPI esta en `/docs`.

## Calidad del codigo

| Comando | Descripcion |
|---------|-------------|
| `pytest` | Ejecuta las pruebas |
| `ruff check .` | Revisa el codigo |
| `ruff format --check .` | Verifica el formato |
| `bash db/probar.sh` | Prueba el esquema de la base de datos (requiere `psql` y un servidor PostgreSQL) |
| `bash ops/tests/probar_respaldos.sh` | Prueba el respaldo y la restauracion (requiere `psql`, `pg_dump` y `gzip`) |

El workflow `.github/workflows/ci.yml` ejecuta todos, ademas de revisar la sintaxis de los scripts y validar el compose de referencia, en cada pull request hacia `dev` o `main`, contra un PostgreSQL 16 real. Corre en los servidores de GitHub, no en el servidor propio.

## Base de datos

El esquema de PostgreSQL esta en `db/schema.sql` y el diagrama en [docs/diagrama-er.md](docs/diagrama-er.md).

| Tabla | Contenido |
|-------|-----------|
| `roles` | `admin` y `operador` |
| `usuarios` | Cuentas, con el hash de la contrasena y su rol |
| `tipos_vehiculo` | Codigo, prefijo de placa y tarifa por hora |
| `slots` | Los 20 espacios del parqueo |
| `servicios` | Cada ingreso de un vehiculo, activo o finalizado |
| `pagos` | El cobro de un servicio finalizado |
| `auditoria` | Bitacora de acciones, solo de altas |

Las reglas del negocio las vigila la propia base de datos, no solo la aplicacion: una placa o un slot no pueden tener dos servicios activos, el formato y el prefijo de la placa se validan, la tarifa no puede ser negativa, un servicio finalizado no se modifica y el total de un pago debe ser horas por tarifa. La tabla completa esta en el diagrama.

`db/seed.sql` carga los datos iniciales y se puede repetir sin duplicar. **No crea ningun usuario**: la cuenta de administrador se creara desde la API con la contrasena cifrada.

### Probar el esquema

`db/probar.sh` crea una base temporal, aplica `schema.sql` y `seed.sql`, ejecuta `db/tests/restricciones.sql` y borra la base al terminar. Usa las variables estandar de PostgreSQL:

```bash
export PGHOST=localhost PGUSER=postgres PGPASSWORD=su_contrasena
bash db/probar.sh
```

Cada prueba imprime `OK` y el script termina con un error si alguna regla no se cumple.

### Aplicarlo en el servidor

El esquema se aplica una sola vez sobre la base vacia del contenedor `slotspot-db`, desde la carpeta del repositorio:

```bash
docker exec -i slotspot-db sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < db/schema.sql
docker exec -i slotspot-db sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < db/seed.sql
```

`schema.sql` no es repetible: si las tablas ya existen, falla. Los cambios futuros se haran con migraciones.

## Operacion en el servidor

Los scripts de `ops/` se ejecutan en el servidor, fuera del contenedor, y hablan con `slotspot-db` mediante `docker exec`. Tras cada despliegue a `main` quedan en `~/slotspot/slotspot-mj/ops/`.

### Respaldos

`ops/respaldar.sh` hace un `pg_dump` comprimido en `~/slotspot/respaldos` con el nombre `slotspot_AAAAMMDD_HHMMSS.sql.gz`.

- Escribe primero en un archivo temporal y lo verifica (gzip valido y volcado completo) antes de darlo por bueno. Si algo falla, no deja nada.
- Los archivos quedan con permisos privados, porque contienen los datos y los hashes de las contrasenas.
- Conserva los ultimos 7 respaldos y borra los anteriores. El conteo es por cantidad y no por antiguedad, de modo que si el respaldo diario dejara de correr nunca se borrarian todos.

Variables opcionales: `RESPALDOS_DIR`, `RESPALDOS_CANTIDAD` (por defecto 7) y `DB_CONTENEDOR` (por defecto `slotspot-db`).

Para programarlo cada dia a las 08:30 hora del servidor (UTC), que son las 02:30 en Guatemala:

```bash
mkdir -p ~/slotspot/respaldos
crontab -e
```

y agregar la linea:

```
30 8 * * * bash $HOME/slotspot/slotspot-mj/ops/respaldar.sh >> $HOME/slotspot/respaldos/respaldar.log 2>&1
```

Un respaldo guardado solo en el servidor se pierde si el servidor se pierde. Conviene copiar el ultimo archivo a otro equipo o a la nube con regularidad.

### Restaurar

```bash
bash ~/slotspot/slotspot-mj/ops/restaurar.sh ~/slotspot/respaldos/slotspot_AAAAMMDD_HHMMSS.sql.gz
```

Reemplaza **todos** los datos de la base por los del respaldo. Antes de tocar nada comprueba que el archivo sea un gzip valido y pide escribir `RESTAURAR`. La restauracion corre en una sola transaccion: si algo falla, la base queda como estaba.

### Limites de recursos y logs

`ops/docker-compose.yml` es el compose de referencia del servidor. Respecto al original agrega:

| Servicio | Memoria | CPU |
|----------|---------|-----|
| `db` | 512 MB | 1.0 |
| `api` | 256 MB | 0.5 |
| `web` | 128 MB | 0.5 |

y rotacion de logs de Docker (3 archivos de 10 MB por contenedor). Con el uso actual cada servicio consume unos 30 a 40 MB, asi que los limites dejan margen amplio y protegen a los demas proyectos del servidor. Para aplicarlo, compararlo con `~/slotspot/docker-compose.yml`, copiarlo y ejecutar `docker compose up -d`. Nunca usar `docker compose down -v`: borra el volumen de la base de datos.

## Variables de entorno

Los nombres estan en `.env.example`. Los valores reales viven en el archivo `.env` del servidor y **nunca se suben al repositorio**.

| Variable | Uso |
|----------|-----|
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Credenciales de la base de datos |
| `JWT_SECRET` | Firma de los tokens de sesion |
| `ALLOWED_ORIGINS` | Origenes permitidos por CORS |

## Despliegue

Cada push a `main` despliega la API en el servidor propio mediante un runner self-hosted de GitHub Actions (etiqueta `slotspot`).

1. El workflow copia el codigo a `~/slotspot/slotspot-mj` con `rsync`, excluyendo `.git`, `.env` y `.venv`.
2. Ejecuta `~/slotspot/desplegar.sh api`, que reconstruye el servicio con Docker Compose y espera a que el healthcheck de `/salud` quede sano.

El servidor ejecuta tres servicios: `db` (PostgreSQL con volumen), `api` (esta aplicacion) y `web` (Caddy, que sirve el frontend y envia `/api/*` a la API).

Flujo de ramas: una rama por tarea, pull request hacia `dev` y de `dev` a `main` al cerrar cada entrega. Solo el merge a `main` despliega.

## Licencia

Proyecto academico desarrollado por Maria Jose Montepeque Zet.
