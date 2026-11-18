from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher

from app import seguridad
from app.config import Settings
from app.seguridad import crear_token
from tests.conftest import SECRETO

CORREO = "operador@slotspotmj.com"
CLAVE = "Contraseña-segura-1"


def error_de(respuesta) -> dict:
    return respuesta.json()["error"]


class TestLogin:
    def test_con_credenciales_correctas_devuelve_un_token(self, entorno):
        entorno.crear_usuario(CORREO)
        respuesta = entorno.cliente.post("/auth/login", json={"email": CORREO, "password": CLAVE})
        assert respuesta.status_code == 200
        cuerpo = respuesta.json()
        assert cuerpo["token_type"] == "bearer"
        assert cuerpo["expires_in"] == 3600
        assert cuerpo["access_token"].count(".") == 2

    def test_el_correo_no_distingue_mayusculas(self, entorno):
        entorno.crear_usuario(CORREO)
        respuesta = entorno.cliente.post(
            "/auth/login", json={"email": CORREO.upper(), "password": CLAVE}
        )
        assert respuesta.status_code == 200

    def test_el_token_trae_el_usuario_y_el_rol(self, entorno):
        usuario = entorno.crear_usuario(CORREO, rol="admin")
        token = entorno.token(CORREO)
        contenido = jwt.decode(token, options={"verify_signature": False})
        assert contenido["sub"] == str(usuario["id"])
        assert contenido["rol"] == "admin"

    def test_contrasena_incorrecta(self, entorno):
        entorno.crear_usuario(CORREO)
        respuesta = entorno.cliente.post(
            "/auth/login", json={"email": CORREO, "password": "otra-contraseña"}
        )
        assert respuesta.status_code == 401
        assert error_de(respuesta)["codigo"] == "credenciales_invalidas"
        assert respuesta.headers["www-authenticate"] == "Bearer"

    def test_correo_inexistente_responde_igual_que_contrasena_incorrecta(self, entorno):
        entorno.crear_usuario(CORREO)
        mala = entorno.cliente.post("/auth/login", json={"email": CORREO, "password": "x" * 9})
        inexistente = entorno.cliente.post(
            "/auth/login", json={"email": "nadie@slotspotmj.com", "password": "x" * 9}
        )
        assert inexistente.status_code == mala.status_code == 401
        assert inexistente.json() == mala.json()

    def test_un_correo_inexistente_tambien_gasta_el_trabajo_de_verificar(
        self, entorno, monkeypatch
    ):
        llamadas = []

        class Espia:
            def __init__(self, real):
                self.real = real

            def verify(self, hash_guardado, password):
                llamadas.append(hash_guardado)
                return self.real.verify(hash_guardado, password)

        monkeypatch.setattr(seguridad, "_hasher", Espia(seguridad._hasher))
        entorno.cliente.post(
            "/auth/login", json={"email": "nadie@slotspotmj.com", "password": "x" * 9}
        )
        assert len(llamadas) == 1

    def test_un_usuario_inactivo_no_entra_y_no_se_revela(self, entorno):
        entorno.crear_usuario(CORREO, activo=False)
        respuesta = entorno.cliente.post("/auth/login", json={"email": CORREO, "password": CLAVE})
        assert respuesta.status_code == 401
        assert error_de(respuesta)["codigo"] == "credenciales_invalidas"

    def test_actualiza_un_hash_con_parametros_debiles(self, entorno):
        usuario = entorno.crear_usuario(CORREO)
        debil = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash(CLAVE)
        entorno.ejecutar(
            "UPDATE usuarios SET password_hash = %s WHERE id = %s", (debil, usuario["id"])
        )
        primera = entorno.cliente.post("/auth/login", json={"email": CORREO, "password": CLAVE})
        assert primera.status_code == 200
        nuevo = entorno.consultar(
            "SELECT password_hash FROM usuarios WHERE id = %s", (usuario["id"],)
        )[0]["password_hash"]
        assert nuevo != debil
        segunda = entorno.cliente.post("/auth/login", json={"email": CORREO, "password": CLAVE})
        assert segunda.status_code == 200

    def test_valida_el_cuerpo(self, entorno):
        respuesta = entorno.cliente.post("/auth/login", json={"email": "no-es-correo"})
        assert respuesta.status_code == 422
        campos = {item["campo"] for item in error_de(respuesta)["detalle"]}
        assert campos == {"email", "password"}

    def test_rechaza_un_cuerpo_que_no_es_json(self, entorno):
        respuesta = entorno.cliente.post(
            "/auth/login", content="no es json", headers={"Content-Type": "application/json"}
        )
        assert respuesta.status_code == 422
        assert error_de(respuesta)["codigo"] == "validacion"

    def test_rechaza_una_contrasena_demasiado_larga(self, entorno):
        respuesta = entorno.cliente.post(
            "/auth/login", json={"email": CORREO, "password": "x" * 129}
        )
        assert respuesta.status_code == 422

    def test_get_no_esta_permitido(self, entorno):
        respuesta = entorno.cliente.get("/auth/login")
        assert respuesta.status_code == 405
        assert error_de(respuesta)["codigo"] == "metodo_no_permitido"


class TestUsuarioActual:
    def test_devuelve_el_usuario_sin_el_hash(self, entorno):
        entorno.crear_usuario(CORREO, nombre="Maria Jose", rol="operador")
        respuesta = entorno.cliente.get("/auth/yo", headers=entorno.cabeceras(CORREO))
        assert respuesta.status_code == 200
        cuerpo = respuesta.json()
        assert cuerpo["email"] == CORREO
        assert cuerpo["nombre"] == "Maria Jose"
        assert cuerpo["rol"] == "operador"
        assert cuerpo["activo"] is True
        assert "password_hash" not in cuerpo
        assert "password" not in cuerpo

    def test_sin_token(self, entorno):
        respuesta = entorno.cliente.get("/auth/yo")
        assert respuesta.status_code == 401
        assert error_de(respuesta)["codigo"] == "no_autenticado"
        assert respuesta.headers["www-authenticate"] == "Bearer"

    def test_con_un_esquema_que_no_es_bearer(self, entorno):
        respuesta = entorno.cliente.get("/auth/yo", headers={"Authorization": "Basic abc"})
        assert respuesta.status_code == 401

    def test_con_un_token_que_es_basura(self, entorno):
        respuesta = entorno.cliente.get("/auth/yo", headers={"Authorization": "Bearer basura"})
        assert respuesta.status_code == 401
        assert error_de(respuesta)["codigo"] == "token_invalido"

    def test_con_un_token_vencido(self, entorno):
        usuario = entorno.crear_usuario(CORREO)
        ajustes = Settings(database_url="postgresql://x@localhost/x", jwt_secret=SECRETO)
        antiguo = crear_token(
            usuario["id"], "operador", ajustes, ahora=datetime.now(UTC) - timedelta(hours=3)
        )
        respuesta = entorno.cliente.get("/auth/yo", headers={"Authorization": f"Bearer {antiguo}"})
        assert respuesta.status_code == 401
        assert error_de(respuesta)["codigo"] == "token_expirado"

    def test_con_la_firma_manipulada(self, entorno):
        entorno.crear_usuario(CORREO)
        cabecera, cuerpo, firma = entorno.token(CORREO).split(".")
        manipulado = f"{cabecera}.{cuerpo}.{firma[:-3]}abc"
        respuesta = entorno.cliente.get(
            "/auth/yo", headers={"Authorization": f"Bearer {manipulado}"}
        )
        assert respuesta.status_code == 401
        assert error_de(respuesta)["codigo"] == "token_invalido"

    def test_no_se_puede_subir_de_rol_editando_el_token(self, entorno):
        entorno.crear_usuario(CORREO, rol="operador")
        cabecera, _, firma = entorno.token(CORREO).split(".")
        otro = Settings(database_url="postgresql://x@localhost/x", jwt_secret=SECRETO)
        cuerpo_admin = crear_token(1, "admin", otro).split(".")[1]
        respuesta = entorno.cliente.get(
            "/auth/yo", headers={"Authorization": f"Bearer {cabecera}.{cuerpo_admin}.{firma}"}
        )
        assert respuesta.status_code == 401

    def test_un_token_de_un_usuario_desactivado_deja_de_servir(self, entorno):
        usuario = entorno.crear_usuario(CORREO)
        cabeceras = entorno.cabeceras(CORREO)
        assert entorno.cliente.get("/auth/yo", headers=cabeceras).status_code == 200
        entorno.ejecutar("UPDATE usuarios SET activo = false WHERE id = %s", (usuario["id"],))
        respuesta = entorno.cliente.get("/auth/yo", headers=cabeceras)
        assert respuesta.status_code == 401
        assert error_de(respuesta)["codigo"] == "token_invalido"

    def test_el_rol_sale_de_la_base_de_datos_no_del_token(self, entorno):
        usuario = entorno.crear_usuario(CORREO, rol="admin")
        cabeceras = entorno.cabeceras(CORREO)
        entorno.ejecutar(
            "UPDATE usuarios SET rol_id = (SELECT id FROM roles WHERE nombre = 'operador') "
            "WHERE id = %s",
            (usuario["id"],),
        )
        assert entorno.cliente.get("/usuarios", headers=cabeceras).status_code == 403
