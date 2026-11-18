import argparse
import getpass
import sys

import psycopg
from psycopg.rows import dict_row
from pydantic import ValidationError

from app.config import get_settings
from app.errores import Conflicto
from app.esquemas import UsuarioNuevo
from app.repositorio import crear_usuario
from app.seguridad import hashear_password


def leer_password(desde_stdin: bool) -> str:
    if desde_stdin:
        return sys.stdin.readline().rstrip("\r\n")
    primera = getpass.getpass("Contraseña: ")
    segunda = getpass.getpass("Repite la contraseña: ")
    if primera != segunda:
        raise ValueError("Las contraseñas no coinciden.")
    return primera


def crear_admin(args: argparse.Namespace) -> int:
    try:
        password = leer_password(args.password_stdin)
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2

    try:
        datos = UsuarioNuevo(nombre=args.nombre, email=args.email, password=password, rol="admin")
    except ValidationError as error:
        for item in error.errors():
            campo = ".".join(str(parte) for parte in item["loc"])
            print(f"Error en {campo}: {item['msg']}", file=sys.stderr)
        return 2

    with psycopg.connect(get_settings().database_url, row_factory=dict_row) as conexion:
        try:
            crear_usuario(
                conexion, datos.nombre, datos.email, hashear_password(datos.password), "admin"
            )
        except Conflicto:
            print("Error: ya existe un usuario con ese correo.", file=sys.stderr)
            return 1

    print(f"Administrador creado: {datos.email.lower()}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    subcomandos = parser.add_subparsers(dest="comando", required=True)
    crear = subcomandos.add_parser("crear-admin", help="Crea un usuario administrador")
    crear.add_argument("--nombre", required=True)
    crear.add_argument("--email", required=True)
    crear.add_argument(
        "--password-stdin",
        action="store_true",
        help="Lee la contraseña de la entrada estándar en lugar de pedirla",
    )
    args = parser.parse_args(argv)
    return crear_admin(args)


if __name__ == "__main__":
    sys.exit(main())
