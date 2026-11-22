import threading
import time

from fastapi.testclient import TestClient

from app import db, seguridad
from app.config import Settings, get_settings
from app.limitador import LimitadorLogin
from tests.conftest import SECRETO

CORREO = "operador@slotspotmj.com"
CLAVE = "Contraseña-segura-1"


class HasherEspia:
    def __init__(self, real, al_verificar=None, bloqueo=None):
        self.real = real
        self.al_verificar = al_verificar
        self.bloqueo = bloqueo
        self.verificaciones = 0

    def verify(self, hash_guardado, password):
        self.verificaciones += 1
        if self.al_verificar:
            self.al_verificar()
        if self.bloqueo:
            self.bloqueo.wait(timeout=15)
        return self.real.verify(hash_guardado, password)

    def __getattr__(self, nombre):
        return getattr(self.real, nombre)


def intentar(entorno, correo=CORREO, clave="mala-contraseña", cabeceras=None):
    return entorno.cliente.post(
        "/auth/login", json={"email": correo, "password": clave}, headers=cabeceras
    )


class TestLimitePorCorreo:
    def test_tras_8_fallos_ni_la_clave_correcta_entra(self, entorno):
        entorno.crear_usuario(CORREO)
        for _ in range(8):
            assert intentar(entorno).status_code == 401
        respuesta = intentar(entorno, clave=CLAVE)
        assert respuesta.status_code == 429
        assert respuesta.json()["error"]["codigo"] == "demasiados_intentos"
        assert int(respuesta.headers["retry-after"]) > 0

    def test_un_correo_inexistente_se_limita_igual_y_no_se_distingue(self, entorno):
        entorno.crear_usuario(CORREO)
        for _ in range(8):
            assert intentar(entorno, correo="nadie@slotspotmj.com").status_code == 401
        inexistente = intentar(entorno, correo="nadie@slotspotmj.com")
        existente = intentar(entorno, correo=CORREO)
        assert inexistente.status_code == 429
        assert existente.status_code == 401
        assert inexistente.json()["error"]["codigo"] == "demasiados_intentos"

    def test_un_inicio_correcto_reinicia_los_fallos(self, entorno):
        entorno.crear_usuario(CORREO)
        for _ in range(5):
            assert intentar(entorno).status_code == 401
        assert intentar(entorno, clave=CLAVE).status_code == 200
        for _ in range(5):
            assert intentar(entorno).status_code == 401

    def test_el_bloqueo_no_afecta_a_otro_usuario(self, entorno):
        entorno.crear_usuario(CORREO)
        entorno.crear_usuario("otra@slotspotmj.com")
        for _ in range(8):
            intentar(entorno)
        assert intentar(entorno, correo="otra@slotspotmj.com", clave=CLAVE).status_code == 200

    def test_el_limite_se_aplica_antes_de_calcular_el_hash(self, entorno, monkeypatch):
        entorno.crear_usuario(CORREO)
        for _ in range(8):
            intentar(entorno)
        espia = HasherEspia(seguridad._hasher)
        monkeypatch.setattr(seguridad, "_hasher", espia)
        assert intentar(entorno, clave=CLAVE).status_code == 429
        assert espia.verificaciones == 0


class TestLimitePorIp:
    def test_corta_antes_de_verificar(self, entorno, monkeypatch):
        entorno.crear_usuario(CORREO)
        entorno.app.state.limitador = LimitadorLogin(intentos_por_ip=3)
        espia = HasherEspia(seguridad._hasher)
        monkeypatch.setattr(seguridad, "_hasher", espia)
        for i in range(3):
            assert intentar(entorno, correo=f"u{i}@slotspotmj.com").status_code == 401
        assert intentar(entorno, correo="u9@slotspotmj.com").status_code == 429
        assert espia.verificaciones == 3

    def test_con_la_cabecera_configurada_cada_visitante_tiene_su_cupo(self, entorno):
        entorno.crear_usuario(CORREO)
        entorno.app.state.limitador = LimitadorLogin(intentos_por_ip=2)
        entorno.app.dependency_overrides[get_settings] = lambda: Settings(
            database_url=entorno.url_app,
            jwt_secret=SECRETO,
            ip_cliente_cabecera="CF-Connecting-IP",
        )
        a = {"CF-Connecting-IP": "203.0.113.1"}
        b = {"CF-Connecting-IP": "203.0.113.2"}
        assert intentar(entorno, cabeceras=a).status_code == 401
        assert intentar(entorno, cabeceras=a).status_code == 401
        assert intentar(entorno, cabeceras=a).status_code == 429
        assert intentar(entorno, cabeceras=b).status_code == 401

    def test_sin_configurar_la_cabecera_no_se_puede_falsificar_la_ip(self, entorno):
        entorno.crear_usuario(CORREO)
        entorno.app.state.limitador = LimitadorLogin(intentos_por_ip=2)
        for i in range(2):
            intentar(entorno, cabeceras={"CF-Connecting-IP": f"203.0.113.{i}"})
        respuesta = intentar(entorno, cabeceras={"CF-Connecting-IP": "203.0.113.99"})
        assert respuesta.status_code == 429


class TestConexionesDelPool:
    def test_la_conexion_se_suelta_antes_de_calcular_el_hash(self, entorno, monkeypatch):
        entorno.crear_usuario(CORREO)
        en_uso = []

        def medir():
            estadisticas = entorno.app.state.pool.get_stats()
            en_uso.append(estadisticas["pool_size"] - estadisticas["pool_available"])

        monkeypatch.setattr(
            seguridad, "_hasher", HasherEspia(seguridad._hasher, al_verificar=medir)
        )
        assert intentar(entorno, clave=CLAVE).status_code == 200
        assert en_uso == [0]

    def test_logins_lentos_no_dejan_sin_conexiones_al_resto_de_la_api(self, entorno, monkeypatch):
        entorno.crear_usuario(CORREO)
        monkeypatch.setattr(db, "ESPERA_CONEXION_SEGUNDOS", 0.5)
        liberar = threading.Event()
        espia = HasherEspia(seguridad._hasher, bloqueo=liberar)
        monkeypatch.setattr(seguridad, "_hasher", espia)
        entorno.app.state.limitador = LimitadorLogin(simultaneos=8)
        respuestas = []

        def entrar():
            cliente = TestClient(entorno.app, raise_server_exceptions=False)
            respuestas.append(
                cliente.post("/auth/login", json={"email": CORREO, "password": CLAVE})
            )

        hilos = [threading.Thread(target=entrar) for _ in range(8)]
        for hilo in hilos:
            hilo.start()
        limite = time.monotonic() + 10
        while espia.verificaciones < 4 and time.monotonic() < limite:
            time.sleep(0.02)

        salud = entorno.cliente.get("/salud/bd")
        liberar.set()
        for hilo in hilos:
            hilo.join(timeout=30)

        assert salud.status_code == 200
        assert len(respuestas) == 8
        assert all(r.status_code == 200 for r in respuestas)


class TestSaturacion:
    def test_con_demasiados_logins_en_curso_responde_503_enseguida(self, entorno, monkeypatch):
        entorno.crear_usuario(CORREO)
        liberar = threading.Event()
        espia = HasherEspia(seguridad._hasher, bloqueo=liberar)
        monkeypatch.setattr(seguridad, "_hasher", espia)
        entorno.app.state.limitador = LimitadorLogin(simultaneos=2)
        respuestas = []

        def entrar():
            cliente = TestClient(entorno.app, raise_server_exceptions=False)
            respuestas.append(
                cliente.post("/auth/login", json={"email": CORREO, "password": CLAVE})
            )

        ocupados = [threading.Thread(target=entrar) for _ in range(2)]
        for hilo in ocupados:
            hilo.start()
        limite = time.monotonic() + 10
        while espia.verificaciones < 2 and time.monotonic() < limite:
            time.sleep(0.02)

        inicio = time.monotonic()
        rechazada = intentar(entorno, clave=CLAVE)
        duracion = time.monotonic() - inicio

        liberar.set()
        for hilo in ocupados:
            hilo.join(timeout=30)

        assert rechazada.status_code == 503
        assert rechazada.json()["error"]["codigo"] == "servidor_ocupado"
        assert rechazada.headers["retry-after"] == "2"
        assert duracion < 1
        assert [r.status_code for r in respuestas] == [200, 200]

    def test_despues_de_la_saturacion_vuelve_a_atender(self, entorno):
        entorno.crear_usuario(CORREO)
        entorno.app.state.limitador = LimitadorLogin(simultaneos=1)
        assert intentar(entorno, clave=CLAVE).status_code == 200
        assert intentar(entorno, clave=CLAVE).status_code == 200
