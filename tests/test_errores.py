import pytest
from fastapi.testclient import TestClient

from app import db
from app.config import get_settings
from app.main import create_app
from tests.conftest import SECRETO


def forma_de_error(respuesta) -> dict:
    cuerpo = respuesta.json()
    assert set(cuerpo) == {"error"}
    assert set(cuerpo["error"]) == {"codigo", "mensaje", "detalle"}
    return cuerpo["error"]


class TestFormatoUniforme:
    def test_ruta_inexistente(self, entorno):
        respuesta = entorno.cliente.get("/no-existe")
        assert respuesta.status_code == 404
        assert forma_de_error(respuesta)["codigo"] == "no_encontrado"

    def test_metodo_no_permitido(self, entorno):
        respuesta = entorno.cliente.delete("/salud")
        assert respuesta.status_code == 405
        assert forma_de_error(respuesta)["codigo"] == "metodo_no_permitido"

    def test_validacion(self, entorno):
        respuesta = entorno.cliente.post("/auth/login", json={})
        assert respuesta.status_code == 422
        error = forma_de_error(respuesta)
        assert error["codigo"] == "validacion"
        assert isinstance(error["detalle"], list)

    def test_no_autenticado(self, entorno):
        assert forma_de_error(entorno.cliente.get("/auth/yo"))["codigo"] == "no_autenticado"

    def test_un_error_inesperado_no_filtra_detalles(self, entorno):
        def falla() -> None:
            raise RuntimeError("secreto interno: clave=abc123")

        entorno.app.add_api_route("/falla", falla)
        respuesta = entorno.cliente.get("/falla")
        assert respuesta.status_code == 500
        error = forma_de_error(respuesta)
        assert error["codigo"] == "error_interno"
        assert "secreto" not in respuesta.text
        assert "abc123" not in respuesta.text
        assert "Traceback" not in respuesta.text


class TestSalud:
    def test_salud(self, entorno):
        respuesta = entorno.cliente.get("/salud")
        assert respuesta.status_code == 200
        assert respuesta.json() == {"estado": "ok"}

    def test_salud_de_la_base_de_datos(self, entorno):
        respuesta = entorno.cliente.get("/salud/bd")
        assert respuesta.status_code == 200
        assert respuesta.json() == {"estado": "ok", "base_de_datos": "ok"}


class TestBaseDeDatosCaida:
    def test_responde_503_con_el_formato_uniforme(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://nadie@127.0.0.1:1/nada?connect_timeout=1")
        monkeypatch.setenv("JWT_SECRET", SECRETO)
        monkeypatch.setattr(db, "ESPERA_CONEXION_SEGUNDOS", 0.3)
        get_settings.cache_clear()
        with TestClient(create_app(), raise_server_exceptions=False) as cliente:
            assert cliente.get("/salud").status_code == 200
            respuesta = cliente.get("/salud/bd")
            login = cliente.post("/auth/login", json={"email": "a@b.com", "password": "contraseña"})
        get_settings.cache_clear()
        assert respuesta.status_code == 503
        assert forma_de_error(respuesta)["codigo"] == "bd_no_disponible"
        assert login.status_code == 503


class TestDocumentacion:
    def test_la_documentacion_esta_oculta_por_defecto(self, monkeypatch):
        monkeypatch.delenv("API_DOCS", raising=False)
        cliente = TestClient(create_app())
        for ruta in ["/docs", "/openapi.json", "/redoc"]:
            assert cliente.get(ruta).status_code == 404

    def test_se_puede_activar_con_api_docs(self, monkeypatch):
        monkeypatch.setenv("API_DOCS", "1")
        cliente = TestClient(create_app())
        assert cliente.get("/docs").status_code == 200
        assert cliente.get("/openapi.json").status_code == 200


class TestCors:
    def preflight(self, cliente, origen: str):
        return cliente.options(
            "/auth/login",
            headers={
                "Origin": origen,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

    def test_permite_el_origen_configurado(self, monkeypatch):
        monkeypatch.setenv("ALLOWED_ORIGINS", "https://uno.example, https://dos.example")
        cliente = TestClient(create_app())
        respuesta = self.preflight(cliente, "https://dos.example")
        assert respuesta.status_code == 200
        assert respuesta.headers["access-control-allow-origin"] == "https://dos.example"

    def test_no_permite_otros_origenes(self, monkeypatch):
        monkeypatch.setenv("ALLOWED_ORIGINS", "https://uno.example")
        cliente = TestClient(create_app())
        respuesta = self.preflight(cliente, "https://malo.example")
        assert "access-control-allow-origin" not in respuesta.headers

    def test_sin_configuracion_no_permite_ninguno(self, monkeypatch):
        monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
        cliente = TestClient(create_app())
        respuesta = self.preflight(cliente, "https://uno.example")
        assert "access-control-allow-origin" not in respuesta.headers


@pytest.mark.parametrize("ruta", ["/auth/yo", "/usuarios"])
def test_las_rutas_protegidas_exigen_sesion(entorno, ruta):
    assert entorno.cliente.get(ruta).status_code == 401
