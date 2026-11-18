from typing import Annotated, Any

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from psycopg import Connection

from app.config import Settings, get_settings
from app.db import get_conexion
from app.errores import NoAutenticado, Prohibido, TokenInvalido
from app.repositorio import buscar_por_id
from app.seguridad import decodificar_token

_esquema_bearer = HTTPBearer(auto_error=False)

ConexionBD = Annotated[Connection, Depends(get_conexion)]
Ajustes = Annotated[Settings, Depends(get_settings)]


def get_usuario_actual(
    credenciales: Annotated[HTTPAuthorizationCredentials | None, Depends(_esquema_bearer)],
    conexion: ConexionBD,
    ajustes: Ajustes,
) -> dict[str, Any]:
    if credenciales is None:
        raise NoAutenticado("Falta el token de acceso.")
    contenido = decodificar_token(credenciales.credentials, ajustes)
    try:
        usuario_id = int(contenido["sub"])
    except ValueError as error:
        raise TokenInvalido() from error
    usuario = buscar_por_id(conexion, usuario_id)
    if usuario is None or not usuario["activo"]:
        raise TokenInvalido("La sesión ya no es válida.")
    return usuario


UsuarioActual = Annotated[dict[str, Any], Depends(get_usuario_actual)]


def requiere_admin(usuario: UsuarioActual) -> dict[str, Any]:
    if usuario["rol"] != "admin":
        raise Prohibido("Se necesita el rol de administrador.")
    return usuario
