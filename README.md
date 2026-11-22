# SlotSpot MJ API

API del sistema de administracion de parqueadero SlotSpot MJ. El frontend vive en [slotspot-mj-frontend](https://github.com/MariaJoseMontepequeZet/slotspot-mj-frontend).

**Desarrolladora:** Maria Jose Montepeque Zet  
**Tecnologias:** Python 3.12, FastAPI, PostgreSQL 16, Docker, Docker Compose

---

## Estado actual

La API ya tiene autenticacion: contrasenas cifradas con Argon2id, sesiones con tokens JWT y un formato de error uniforme. La aplicacion web todavia no la usa (se conecta en una etapa posterior).

| Metodo | Ruta | Acceso | Descripcion |
|--------|------|--------|-------------|
| GET | `/salud` | Publico | Devuelve `{"estado": "ok"}`. Lo usa el healthcheck de Docker |
| GET | `/salud/bd` | Publico | Comprueba que la base de datos responde |
| POST | `/auth/login` | Publico | Recibe `email` y `password` y devuelve un token de acceso |
| GET | `/auth/yo` | Sesion | Devuelve el usuario de la sesion |
| POST | `/usuarios` | Administrador | Crea un usuario con rol `admin` u `operador` |
| GET | `/usuarios` | Administrador | Lista los usuarios, sin datos secretos |

En el servidor, Caddy publica la API bajo `/api/*` y quita ese prefijo, por lo que desde el navegador las rutas son `/api/salud`, `/api/auth/login`, etc.

## Autenticacion

- **Contrasenas:** se guardan cifradas con Argon2id (19 MiB, 2 pasadas, 1 hilo, los minimos que recomienda OWASP). Nunca se guardan ni se devuelven en claro. Un hash con parametros mas debiles se actualiza solo en el siguiente inicio de sesion correcto.
- **Tokens:** JWT firmado con HS256 que lleva `sub`, `rol`, `iss`, `iat` y `exp`. Expira a los 60 minutos por defecto. Al verificarlo se exige el algoritmo, el emisor y las cuatro reclamaciones, de modo que un token con algoritmo `none`, otro emisor o una firma alterada se rechaza.
- **Cada peticion consulta la base de datos:** el rol y el estado activo salen de la base de datos y no del token. Si se desactiva a un usuario o se le cambia el rol, el cambio rige de inmediato.
- **Credenciales invalidas:** un correo inexistente, una contrasena incorrecta y un usuario inactivo dan exactamente la misma respuesta, y en los tres casos se hace el mismo trabajo de cifrado para que el tiempo de respuesta no delate si el correo existe.
- **Memoria acotada:** cada calculo de Argon2id reserva unos 19 MiB, asi que solo se permiten 4 a la vez; el resto de las peticiones espera su turno. Sin ese limite, una rafaga de inicios de sesion podria agotar la memoria del contenedor.
- **Sin registro abierto:** no hay ningun endpoint publico para crear cuentas. Los usuarios los crea un administrador, y el primero se crea con la linea de comandos.

Ejemplo de inicio de sesion y uso del token:

```bash
curl -X POST http://127.0.0.1:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "correo@ejemplo.com", "password": "su_contrasena"}'

curl http://127.0.0.1:8000/auth/yo -H "Authorization: Bearer EL_TOKEN"
```

### Formato de los errores

Todos los errores tienen la misma forma, sea una validacion, un permiso o una falla interna:

```json
{"error": {"codigo": "credenciales_invalidas", "mensaje": "Correo o contrasena incorrectos.", "detalle": null}}
```

| Estado | Codigo | Cuando |
|--------|--------|--------|
| 401 | `no_autenticado` | Falta el token |
| 401 | `credenciales_invalidas` | Correo o contrasena incorrectos |
| 401 | `token_invalido` / `token_expirado` | Token manipulado, de otro emisor, vencido o de un usuario desactivado |
| 403 | `prohibido` | Falta el rol de administrador |
| 404 / 405 | `no_encontrado` / `metodo_no_permitido` | Ruta o metodo inexistente |
| 409 | `conflicto` | Ya existe un usuario con ese correo |
| 422 | `validacion` | Datos invalidos; `detalle` lista cada campo con su mensaje |
| 503 | `bd_no_disponible` | La base de datos no responde |
| 500 | `error_interno` | Falla inesperada; el detalle solo se escribe en el log, nunca en la respuesta |

### Crear el primer administrador

Se hace desde la linea de comandos y la contrasena se pide sin mostrarla, asi no queda en el historial del terminal ni en ningun chat. En el servidor:

```bash
docker exec -it slotspot-api python -m app.cli crear-admin --nombre "Nombre Apellido" --email correo@ejemplo.com
```

Para automatizarlo existe `--password-stdin`, que lee la contrasena de la entrada estandar. La contrasena debe tener entre 8 y 128 caracteres.

## Estructura

```
slotspot-mj/
├── app/
│   ├── main.py                 # Aplicacion FastAPI y sus rutas de salud
│   ├── config.py               # Variables de entorno
│   ├── db.py                   # Pool de conexiones a PostgreSQL
│   ├── errores.py              # Errores de la aplicacion y manejadores
│   ├── seguridad.py            # Argon2id y tokens JWT
│   ├── esquemas.py             # Modelos de entrada y salida
│   ├── repositorio.py          # Consultas SQL de usuarios
│   ├── dependencias.py         # Sesion actual y control de rol
│   ├── cli.py                  # Linea de comandos (crear-admin)
│   └── routers/
│       ├── auth.py             # /auth/login y /auth/yo
│       └── usuarios.py         # /usuarios
├── db/
│   ├── schema.sql              # Tablas, restricciones, indices y triggers
│   ├── seed.sql                # Roles, tipos de vehiculo y 20 slots
│   ├── probar.sh               # Crea una base temporal y ejecuta las pruebas
│   └── tests/
│       └── restricciones.sql   # 55 pruebas de las reglas del negocio
├── ops/
│   ├── respaldar.sh            # Respaldo diario de PostgreSQL con retencion
│   ├── restaurar.sh            # Restauracion desde un respaldo, con confirmacion
│   ├── Caddyfile               # Servidor web: rutas, politica de seguridad y permiso de incrustacion
│   ├── docker-compose.yml      # Compose de referencia con limites y rotacion de logs
│   └── tests/
│       └── probar_respaldos.sh # Prueba de respaldo y restauracion
├── docs/
│   └── diagrama-er.md          # Diagrama entidad-relacion
├── tests/
│   ├── conftest.py             # Base de datos temporal por prueba
│   ├── test_seguridad.py       # Hash y tokens, sin base de datos
│   ├── test_auth.py            # Inicio de sesion y sesion actual
│   ├── test_usuarios.py        # Alta, validacion y lista de usuarios
│   ├── test_errores.py         # Formato de errores, CORS y documentacion
│   ├── test_cli.py             # Comando crear-admin
│   ├── test_caddyfile.py       # Politica de seguridad y rutas del Caddyfile
│   └── test_salud.py           # Ruta de salud
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

Necesita estas variables de entorno (los nombres estan en `.env.example`):

```bash
export DATABASE_URL=postgresql://usuario:contrasena@localhost:5432/slotspot
export JWT_SECRET=un_texto_aleatorio_de_al_menos_32_caracteres
export API_DOCS=1
```

La API queda en `http://127.0.0.1:8000`. Con `API_DOCS=1` la documentacion interactiva de FastAPI esta en `/docs`; sin esa variable, que es lo normal en el servidor, `/docs` y `/openapi.json` no existen.

## Calidad del codigo

| Comando | Descripcion |
|---------|-------------|
| `pytest` | Ejecuta las pruebas. Las que usan PostgreSQL se omiten si no se define `TEST_DATABASE_ADMIN_URL` |
| `ruff check .` | Revisa el codigo |
| `ruff format --check .` | Verifica el formato |
| `bash db/probar.sh` | Prueba el esquema y los permisos del rol de la API (requiere `psql` y un servidor PostgreSQL) |
| `bash ops/tests/probar_rol_app.sh` | Prueba `ops/crear_rol_app.sh` contra un contenedor PostgreSQL real (`DB_CONTENEDOR`) |
| `bash ops/tests/probar_respaldos.sh` | Prueba el respaldo y la restauracion con un `docker` simulado (requiere `psql`, `pg_dump` y `gzip`) |
| `PROBAR_DOCKER_REAL=1 bash ops/tests/probar_respaldos.sh` | La misma prueba contra un contenedor `slotspot-db` real |

El workflow `.github/workflows/ci.yml` ejecuta todos, ademas de revisar la sintaxis de los scripts y validar el compose de referencia, en cada pull request hacia `dev` o `main`, contra un PostgreSQL 16 real. Corre en los servidores de GitHub, no en el servidor propio.

En el CI la prueba de respaldos usa un contenedor real `postgres:16-alpine` y `docker exec`, igual que en produccion. Asi `pg_dump` y `psql` son de la misma version que el servidor. Usar los clientes del runner no sirve: un `pg_dump` 17 o 18 escribe `SET transaction_timeout`, un parametro que PostgreSQL 16 no conoce, y la restauracion falla.

### Pruebas con PostgreSQL

Las pruebas de la API crean una base nueva por cada prueba a partir de una plantilla con el esquema, de modo que ninguna depende de otra. Necesitan un usuario que pueda crear bases de datos:

```bash
export TEST_DATABASE_ADMIN_URL=postgresql://postgres:contrasena@localhost:5432/postgres
pytest
```

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

### Mostrar la demo en otro sitio (portafolio)

Por defecto un navegador no deja que una pagina se muestre dentro de otra (`iframe`). `ops/Caddyfile` lo permite **solo para el portafolio**, con la directiva de la politica de seguridad:

```
frame-ancestors 'self' https://portafoliomariajosemontepequezet.pamcing.me
```

- Cualquier otro sitio que intente incrustar la aplicacion queda bloqueado; el navegador lo registra como `violates the following Content Security Policy directive: "frame-ancestors ..."`.
- No se envia `X-Frame-Options`: esa cabecera no admite una lista de origenes y contradiria a `frame-ancestors`.
- El resto de la politica no cambia: los scripts solo pueden venir del propio sitio.

Para aplicarlo en el servidor, primero comparar con el Caddyfile actual y luego recargar `web`:

```bash
cd ~/slotspot
cp Caddyfile Caddyfile.bak
diff Caddyfile slotspot-mj/ops/Caddyfile
cp slotspot-mj/ops/Caddyfile Caddyfile
docker compose restart web
```

Reiniciar `web` es necesario porque el Caddyfile se monta como archivo unico. Para comprobarlo:

```bash
curl -sI https://slotspotmj.pamcing.me/ | grep -i content-security-policy
```

La salida debe contener `frame-ancestors 'self' https://portafoliomariajosemontepequezet.pamcing.me` y no debe aparecer `X-Frame-Options`.

El portafolio, a su vez, debe permitir cargar la direccion en su propia politica (`frame-src https://slotspotmj.pamcing.me`), y el `iframe` debe apuntar a `https://slotspotmj.pamcing.me/?demo=1`, que entra solo a la demo (ver el repositorio del frontend).

### Puerto del servicio web y tunel propio

`web` publica el puerto solo en `127.0.0.1:8439`, asi que no es alcanzable desde la red. El trafico de internet entra por el servicio `tunel` de este compose (`cloudflared` con la version fijada), que llega a `web` por la red interna de Docker. SlotSpot no depende del conector de ningun otro proyecto.

Para activarlo hay que crear un tunel propio en Cloudflare Zero Trust (Networks > Tunnels > Create a tunnel > Cloudflared > Docker), copiar su token a `TUNEL_TOKEN` en el `.env` del servidor y apuntar el hostname `slotspotmj.pamcing.me` a `http://web:80`. El token nunca se sube al repositorio.

### Rol de base de datos de la API

La API ya no entra a PostgreSQL como superusuario sino con el rol `slotspot_app`, definido en `db/roles.sql`: puede leer y escribir las tablas del negocio, solo insertar y leer en `auditoria`, y no puede borrar ni modificar pagos, borrar nada, alterar el esquema, crear objetos ni leer archivos del servidor. Asi, aunque alguien lograra inyectar SQL, no podria vaciar tablas ni reescribir la bitacora. `db/tests/permisos.sql` lo comprueba (corre dentro de `bash db/probar.sh`) y toda la suite de la API se ejecuta con ese rol.

Para crearlo o cambiar su contrasena en el servidor (se puede repetir sin riesgo):

```bash
export APP_DB_PASSWORD="$(openssl rand -hex 24)"
bash ops/crear_rol_app.sh
echo "APP_DB_PASSWORD=$APP_DB_PASSWORD" >> ~/slotspot/.env
```

La contrasena viaja por el entorno del contenedor y no por la linea de comandos. Despues hay que copiar el compose nuevo y ejecutar `docker compose up -d api`. Cuando el cambio de esquema necesite permisos de dueno (migraciones), se ejecutan con el usuario `POSTGRES_USER`, nunca con la API.

### Inicios de sesion limitados

`POST /auth/login` esta protegido contra fuerza bruta y contra saturacion:

- Maximo 20 intentos por direccion IP cada 5 minutos y 8 fallos por correo cada 15 minutos (un inicio correcto reinicia la cuenta del correo). Al excederlos responde `429` con `Retry-After`.
- Maximo 8 inicios de sesion calculando el hash a la vez; el resto recibe `503` al instante. Sin este tope, una rafaga agotaba el pool de 5 conexiones y toda la API dejaba de responder.
- La conexion a la base se suelta antes de calcular Argon2id, asi que un login lento ya no bloquea al resto de la API.

Los contadores viven en memoria de un solo proceso (la API corre con un worker). Para que la IP sea la del visitante y no la del proxy, define `IP_CLIENTE_CABECERA` (por ejemplo `CF-Connecting-IP` detras de Cloudflare); sin ella se usa la direccion del socket y las cabeceras no se toman en cuenta.

### Endurecimiento de los contenedores

En el compose, `api` y `web` corren con sistema de archivos de solo lectura (con `tmpfs` donde hace falta), sin capacidades de Linux (`web` conserva solo `NET_BIND_SERVICE`) y con `no-new-privileges`; `db` lleva `no-new-privileges`. El CI levanta la imagen de la API con esas mismas restricciones y consulta `/salud/bd`. Caddy envia `Strict-Transport-Security` por un ano (sin `includeSubDomains`, para no afectar otros subdominios).

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
| `TUNEL_TOKEN` | Token del tunel de Cloudflare propio de SlotSpot |
| `APP_DB_PASSWORD` | Contrasena del rol `slotspot_app` con el que se conecta la API |
| `IP_CLIENTE_CABECERA` | Opcional. Cabecera con la IP real del visitante (`CF-Connecting-IP`); vacia por defecto |
| `JWT_SECRET` | Firma de los tokens de sesion (minimo 32 caracteres) |
| `ALLOWED_ORIGINS` | Origenes permitidos por CORS, separados por comas |
| `JWT_EXPIRA_MINUTOS` | Opcional. Duracion de la sesion, de 1 a 1440 (por defecto 60) |
| `API_DOCS` | Opcional. Con valor `1` publica `/docs`; por defecto esta oculta |

## Despliegue

Cada push a `main` despliega la API en el servidor propio mediante un runner self-hosted de GitHub Actions (etiqueta `slotspot`).

1. El workflow copia el codigo a `~/slotspot/slotspot-mj` con `rsync`, excluyendo `.git`, `.env` y `.venv`.
2. Ejecuta `~/slotspot/desplegar.sh api`, que reconstruye el servicio con Docker Compose y espera a que el healthcheck de `/salud` quede sano.

El servidor ejecuta tres servicios: `db` (PostgreSQL con volumen), `api` (esta aplicacion) y `web` (Caddy, que sirve el frontend y envia `/api/*` a la API).

Flujo de ramas: una rama por tarea, pull request hacia `dev` y de `dev` a `main` al cerrar cada entrega. Solo el merge a `main` despliega.

## Licencia

Proyecto academico desarrollado por Maria Jose Montepeque Zet.
