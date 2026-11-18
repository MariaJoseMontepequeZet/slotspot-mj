from typing import Any

from psycopg import Connection
from psycopg.errors import UniqueViolation

from app.errores import Conflicto

_COLUMNAS = """
    u.id, u.nombre, u.email, u.password_hash, u.activo, r.nombre AS rol
    FROM usuarios u JOIN roles r ON r.id = u.rol_id
"""


def buscar_por_email(conexion: Connection, email: str) -> dict[str, Any] | None:
    consulta = f"SELECT {_COLUMNAS} WHERE lower(u.email) = lower(%s)"
    return conexion.execute(consulta, (email,)).fetchone()


def buscar_por_id(conexion: Connection, usuario_id: int) -> dict[str, Any] | None:
    consulta = f"SELECT {_COLUMNAS} WHERE u.id = %s"
    return conexion.execute(consulta, (usuario_id,)).fetchone()


def listar_usuarios(conexion: Connection) -> list[dict[str, Any]]:
    consulta = f"SELECT {_COLUMNAS} ORDER BY u.id"
    return conexion.execute(consulta).fetchall()


def crear_usuario(
    conexion: Connection, nombre: str, email: str, password_hash: str, rol: str
) -> dict[str, Any]:
    try:
        fila = conexion.execute(
            """
            INSERT INTO usuarios (nombre, email, password_hash, rol_id)
            VALUES (%s, %s, %s, (SELECT id FROM roles WHERE nombre = %s))
            RETURNING id
            """,
            (nombre, email.lower(), password_hash, rol),
        ).fetchone()
    except UniqueViolation as error:
        conexion.rollback()
        raise Conflicto("Ya existe un usuario con ese correo.") from error
    conexion.commit()
    usuario = buscar_por_id(conexion, fila["id"])
    conexion.rollback()
    return usuario


def actualizar_hash(conexion: Connection, usuario_id: int, password_hash: str) -> None:
    conexion.execute(
        "UPDATE usuarios SET password_hash = %s WHERE id = %s", (password_hash, usuario_id)
    )
    conexion.commit()
