from typing import Annotated

from fastapi import APIRouter, Depends, Request
from psycopg_pool import ConnectionPool

from app.db import get_pool, tomar_conexion
from app.dependencias import Ajustes, UsuarioActual
from app.errores import CredencialesInvalidas
from app.esquemas import LoginEntrada, TokenSalida, UsuarioSalida
from app.limitador import Limitador, ip_cliente
from app.repositorio import actualizar_hash, buscar_por_email
from app.seguridad import crear_token, hashear_password, necesita_rehash, verificar_password

router = APIRouter(prefix="/auth", tags=["autenticacion"])

PoolBD = Annotated[ConnectionPool, Depends(get_pool)]


@router.post("/login", response_model=TokenSalida)
def login(
    datos: LoginEntrada,
    request: Request,
    pool: PoolBD,
    ajustes: Ajustes,
    limitador: Limitador,
) -> TokenSalida:
    limitador.comprobar(ip_cliente(request, ajustes.ip_cliente_cabecera), datos.email)

    with limitador.puesto():
        with tomar_conexion(pool) as conexion:
            usuario = buscar_por_email(conexion, datos.email)
        hash_guardado = usuario["password_hash"] if usuario else None

        if not verificar_password(datos.password, hash_guardado) or not usuario["activo"]:
            limitador.registrar_fallo(datos.email)
            raise CredencialesInvalidas()

        limitador.registrar_exito(datos.email)

        if necesita_rehash(hash_guardado):
            nuevo_hash = hashear_password(datos.password)
            with tomar_conexion(pool) as conexion:
                actualizar_hash(conexion, usuario["id"], nuevo_hash)

    token = crear_token(usuario["id"], usuario["rol"], ajustes)
    return TokenSalida(access_token=token, expires_in=ajustes.jwt_expira_minutos * 60)


@router.get("/yo", response_model=UsuarioSalida)
def usuario_actual(usuario: UsuarioActual) -> dict:
    return usuario
