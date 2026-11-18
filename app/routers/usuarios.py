from fastapi import APIRouter, Depends

from app.dependencias import ConexionBD, requiere_admin
from app.esquemas import UsuarioNuevo, UsuarioSalida
from app.repositorio import crear_usuario, listar_usuarios
from app.seguridad import hashear_password

router = APIRouter(prefix="/usuarios", tags=["usuarios"], dependencies=[Depends(requiere_admin)])


@router.post("", response_model=UsuarioSalida, status_code=201)
def crear(datos: UsuarioNuevo, conexion: ConexionBD) -> dict:
    return crear_usuario(
        conexion, datos.nombre, datos.email, hashear_password(datos.password), datos.rol
    )


@router.get("", response_model=list[UsuarioSalida])
def listar(conexion: ConexionBD) -> list[dict]:
    return listar_usuarios(conexion)
