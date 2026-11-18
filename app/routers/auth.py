from fastapi import APIRouter

from app.dependencias import Ajustes, ConexionBD, UsuarioActual
from app.errores import CredencialesInvalidas
from app.esquemas import LoginEntrada, TokenSalida, UsuarioSalida
from app.repositorio import actualizar_hash, buscar_por_email
from app.seguridad import crear_token, hashear_password, necesita_rehash, verificar_password

router = APIRouter(prefix="/auth", tags=["autenticacion"])


@router.post("/login", response_model=TokenSalida)
def login(datos: LoginEntrada, conexion: ConexionBD, ajustes: Ajustes) -> TokenSalida:
    usuario = buscar_por_email(conexion, datos.email)
    hash_guardado = usuario["password_hash"] if usuario else None

    if not verificar_password(datos.password, hash_guardado) or not usuario["activo"]:
        raise CredencialesInvalidas()

    if necesita_rehash(hash_guardado):
        actualizar_hash(conexion, usuario["id"], hashear_password(datos.password))

    token = crear_token(usuario["id"], usuario["rol"], ajustes)
    return TokenSalida(access_token=token, expires_in=ajustes.jwt_expira_minutos * 60)


@router.get("/yo", response_model=UsuarioSalida)
def usuario_actual(usuario: UsuarioActual) -> dict:
    return usuario
