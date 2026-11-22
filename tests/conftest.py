import os
import shutil
import subprocess
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row

from app.config import get_settings
from app.main import create_app
from app.repositorio import crear_usuario
from app.seguridad import hashear_password

ADMIN_URL = os.environ.get("TEST_DATABASE_ADMIN_URL")
RAIZ = Path(__file__).resolve().parent.parent
SECRETO = "secreto-de-pruebas-" + "a" * 48
ROL_APP = "slotspot_app_pruebas"
CLAVE_APP = "clave-del-rol-de-pruebas"


@dataclass
class Entorno:
    app: FastAPI
    cliente: TestClient
    url: str
    url_app: str

    def crear_usuario(
        self,
        email: str,
        password: str = "Contraseña-segura-1",
        rol: str = "operador",
        nombre: str = "Persona de prueba",
        activo: bool = True,
    ) -> dict:
        with psycopg.connect(self.url, row_factory=dict_row) as conexion:
            usuario = crear_usuario(conexion, nombre, email, hashear_password(password), rol)
            if not activo:
                conexion.execute(
                    "UPDATE usuarios SET activo = false WHERE id = %s", (usuario["id"],)
                )
                conexion.commit()
        return usuario

    def ejecutar(self, sql: str, parametros: tuple = ()) -> None:
        with psycopg.connect(self.url) as conexion:
            conexion.execute(sql, parametros)

    def consultar(self, sql: str, parametros: tuple = ()) -> list[dict]:
        with psycopg.connect(self.url, row_factory=dict_row) as conexion:
            return conexion.execute(sql, parametros).fetchall()

    def token(self, email: str, password: str = "Contraseña-segura-1") -> str:
        respuesta = self.cliente.post("/auth/login", json={"email": email, "password": password})
        assert respuesta.status_code == 200, respuesta.text
        return respuesta.json()["access_token"]

    def cabeceras(self, email: str, password: str = "Contraseña-segura-1") -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token(email, password)}"}


def _crear_base(nombre: str, plantilla: str | None = None) -> str:
    with psycopg.connect(ADMIN_URL, autocommit=True) as conexion:
        if plantilla:
            conexion.execute(f'CREATE DATABASE "{nombre}" TEMPLATE "{plantilla}"')
        else:
            conexion.execute(f'CREATE DATABASE "{nombre}"')
    return make_conninfo(ADMIN_URL, dbname=nombre)


def _borrar_base(nombre: str) -> None:
    with psycopg.connect(ADMIN_URL, autocommit=True) as conexion:
        conexion.execute(f'DROP DATABASE IF EXISTS "{nombre}" WITH (FORCE)')


def _aplicar_rol_de_la_app(url: str) -> None:
    psql = shutil.which("psql")
    if not psql:
        pytest.fail("Las pruebas con PostgreSQL necesitan psql para crear el rol de la aplicacion")
    subprocess.run(
        [
            psql,
            "-v",
            "ON_ERROR_STOP=1",
            "-q",
            "-d",
            url,
            "-v",
            f"rol={ROL_APP}",
            "-v",
            f"clave={CLAVE_APP}",
            "-f",
            str(RAIZ / "db" / "roles.sql"),
        ],
        check=True,
        capture_output=True,
    )


@pytest.fixture(scope="session")
def plantilla_bd() -> Iterator[str]:
    if not ADMIN_URL:
        pytest.skip("Define TEST_DATABASE_ADMIN_URL para las pruebas con PostgreSQL")
    nombre = f"slotspot_plantilla_{uuid.uuid4().hex[:8]}"
    url = _crear_base(nombre)
    with psycopg.connect(url, autocommit=True) as conexion:
        conexion.execute((RAIZ / "db" / "schema.sql").read_text(encoding="utf-8"))
        conexion.execute((RAIZ / "db" / "seed.sql").read_text(encoding="utf-8"))
    _aplicar_rol_de_la_app(url)
    yield nombre
    _borrar_base(nombre)


@pytest.fixture
def entorno(plantilla_bd: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[Entorno]:
    nombre = f"slotspot_prueba_{uuid.uuid4().hex[:10]}"
    url = _crear_base(nombre, plantilla_bd)
    url_app = make_conninfo(url, user=ROL_APP, password=CLAVE_APP)
    monkeypatch.setenv("DATABASE_URL", url_app)
    monkeypatch.setenv("JWT_SECRET", SECRETO)
    monkeypatch.delenv("JWT_EXPIRA_MINUTOS", raising=False)
    monkeypatch.delenv("API_DOCS", raising=False)
    get_settings.cache_clear()
    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as cliente:
        yield Entorno(app=app, cliente=cliente, url=url, url_app=url_app)
    get_settings.cache_clear()
    _borrar_base(nombre)
