import threading

import pytest
from starlette.requests import Request

from app.errores import LimiteExcedido, ServidorOcupado
from app.limitador import LimitadorLogin, ip_cliente


class Reloj:
    def __init__(self) -> None:
        self.ahora = 1000.0

    def __call__(self) -> float:
        return self.ahora

    def avanzar(self, segundos: float) -> None:
        self.ahora += segundos


@pytest.fixture
def reloj() -> Reloj:
    return Reloj()


def peticion(cabeceras: dict[str, str] | None = None, cliente=("10.0.0.5", 4000)) -> Request:
    alcance = {
        "type": "http",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (cabeceras or {}).items()],
        "client": cliente,
    }
    return Request(alcance)


class TestIntentosPorIp:
    def test_permite_hasta_el_maximo_y_luego_bloquea(self, reloj):
        limitador = LimitadorLogin(intentos_por_ip=3, ventana_ip=300, reloj=reloj)
        for _ in range(3):
            limitador.comprobar("1.1.1.1", "a@x.com")
        with pytest.raises(LimiteExcedido) as error:
            limitador.comprobar("1.1.1.1", "a@x.com")
        assert error.value.status_code == 429
        assert 1 <= error.value.reintentar_en <= 300

    def test_otra_ip_no_se_ve_afectada(self, reloj):
        limitador = LimitadorLogin(intentos_por_ip=1, reloj=reloj)
        limitador.comprobar("1.1.1.1", "a@x.com")
        limitador.comprobar("2.2.2.2", "a@x.com")

    def test_se_libera_al_pasar_la_ventana(self, reloj):
        limitador = LimitadorLogin(intentos_por_ip=2, ventana_ip=300, reloj=reloj)
        limitador.comprobar("1.1.1.1", "a@x.com")
        limitador.comprobar("1.1.1.1", "a@x.com")
        reloj.avanzar(299)
        with pytest.raises(LimiteExcedido):
            limitador.comprobar("1.1.1.1", "a@x.com")
        reloj.avanzar(2)
        limitador.comprobar("1.1.1.1", "a@x.com")

    def test_el_tiempo_de_espera_disminuye_con_el_reloj(self, reloj):
        limitador = LimitadorLogin(intentos_por_ip=1, ventana_ip=300, reloj=reloj)
        limitador.comprobar("1.1.1.1", "a@x.com")
        reloj.avanzar(100)
        with pytest.raises(LimiteExcedido) as error:
            limitador.comprobar("1.1.1.1", "a@x.com")
        assert error.value.reintentar_en == 200

    def test_es_seguro_con_hilos(self):
        limitador = LimitadorLogin(intentos_por_ip=50)
        aceptados = []
        rechazados = []

        def intentar():
            try:
                limitador.comprobar("9.9.9.9", "a@x.com")
                aceptados.append(1)
            except LimiteExcedido:
                rechazados.append(1)

        hilos = [threading.Thread(target=intentar) for _ in range(200)]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join()
        assert len(aceptados) == 50
        assert len(rechazados) == 150


class TestFallosPorCorreo:
    def fallar(self, limitador, correo, veces):
        for _ in range(veces):
            limitador.comprobar("1.1.1.1", correo)
            limitador.registrar_fallo(correo)

    def test_bloquea_el_correo_tras_el_maximo_de_fallos(self, reloj):
        limitador = LimitadorLogin(fallos_por_correo=3, ventana_correo=900, reloj=reloj)
        self.fallar(limitador, "a@x.com", 3)
        with pytest.raises(LimiteExcedido) as error:
            limitador.comprobar("1.1.1.1", "a@x.com")
        assert 1 <= error.value.reintentar_en <= 900

    def test_otro_correo_sigue_disponible(self, reloj):
        limitador = LimitadorLogin(fallos_por_correo=2, reloj=reloj)
        self.fallar(limitador, "a@x.com", 2)
        limitador.comprobar("1.1.1.1", "b@x.com")

    def test_no_distingue_mayusculas_ni_espacios(self, reloj):
        limitador = LimitadorLogin(fallos_por_correo=2, reloj=reloj)
        limitador.registrar_fallo("Ana@X.com")
        limitador.registrar_fallo("  ana@x.COM ")
        with pytest.raises(LimiteExcedido):
            limitador.comprobar("1.1.1.1", "ANA@x.com")

    def test_un_inicio_correcto_reinicia_la_cuenta(self, reloj):
        limitador = LimitadorLogin(fallos_por_correo=3, reloj=reloj)
        self.fallar(limitador, "a@x.com", 2)
        limitador.registrar_exito("a@x.com")
        self.fallar(limitador, "a@x.com", 2)
        limitador.comprobar("1.1.1.1", "a@x.com")

    def test_los_fallos_caducan(self, reloj):
        limitador = LimitadorLogin(fallos_por_correo=2, ventana_correo=900, reloj=reloj)
        self.fallar(limitador, "a@x.com", 2)
        reloj.avanzar(901)
        limitador.comprobar("1.1.1.1", "a@x.com")

    def test_un_correo_bloqueado_no_consume_el_cupo_de_la_ip(self, reloj):
        limitador = LimitadorLogin(intentos_por_ip=2, fallos_por_correo=1, reloj=reloj)
        limitador.registrar_fallo("a@x.com")
        for _ in range(10):
            with pytest.raises(LimiteExcedido):
                limitador.comprobar("1.1.1.1", "a@x.com")
        limitador.comprobar("1.1.1.1", "b@x.com")
        limitador.comprobar("1.1.1.1", "b@x.com")


class TestInicioDeSesionSimultaneos:
    def test_rechaza_cuando_no_quedan_puestos(self):
        limitador = LimitadorLogin(simultaneos=2)
        with (
            limitador.puesto(),
            limitador.puesto(),
            pytest.raises(ServidorOcupado) as error,
            limitador.puesto(),
        ):
            pass
        assert error.value.status_code == 503
        assert error.value.reintentar_en == 2

    def test_libera_el_puesto_al_salir(self):
        limitador = LimitadorLogin(simultaneos=1)
        with limitador.puesto():
            pass
        with limitador.puesto():
            pass

    def test_libera_el_puesto_aunque_haya_un_error(self):
        limitador = LimitadorLogin(simultaneos=1)
        with pytest.raises(RuntimeError), limitador.puesto():
            raise RuntimeError("fallo")
        with limitador.puesto():
            pass


class TestMemoria:
    def test_las_claves_caducadas_se_eliminan(self, reloj):
        limitador = LimitadorLogin(ventana_ip=300, ventana_correo=900, reloj=reloj)
        for i in range(400):
            limitador.comprobar(f"10.0.{i // 250}.{i % 250}", f"u{i}@x.com")
            limitador.registrar_fallo(f"u{i}@x.com")
        assert len(limitador._ip) == 400
        reloj.avanzar(1000)
        for i in range(120):
            limitador.comprobar(f"8.8.{i // 250}.{i % 250}", f"nuevo{i}@x.com")
        assert len(limitador._ip) == 120
        assert len(limitador._correo) == 0


class TestIpCliente:
    def test_sin_cabecera_configurada_usa_la_direccion_del_socket(self):
        assert ip_cliente(peticion()) == "10.0.0.5"

    def test_ignora_una_cabecera_que_no_se_configuro(self):
        solicitud = peticion({"CF-Connecting-IP": "203.0.113.9"})
        assert ip_cliente(solicitud) == "10.0.0.5"

    def test_usa_la_cabecera_configurada(self):
        solicitud = peticion({"CF-Connecting-IP": "203.0.113.9"})
        assert ip_cliente(solicitud, "CF-Connecting-IP") == "203.0.113.9"

    def test_toma_la_primera_direccion_de_una_lista(self):
        solicitud = peticion({"X-Forwarded-For": "203.0.113.9, 10.1.1.1"})
        assert ip_cliente(solicitud, "X-Forwarded-For") == "203.0.113.9"

    def test_acepta_ipv6(self):
        solicitud = peticion({"CF-Connecting-IP": "2001:db8::1"})
        assert ip_cliente(solicitud, "CF-Connecting-IP") == "2001:db8::1"

    @pytest.mark.parametrize("basura", ["no-es-una-ip", "", "999.1.1.1", "1.1.1.1; DROP"])
    def test_una_cabecera_invalida_cae_a_la_direccion_del_socket(self, basura):
        solicitud = peticion({"CF-Connecting-IP": basura})
        assert ip_cliente(solicitud, "CF-Connecting-IP") == "10.0.0.5"

    def test_cabecera_configurada_pero_ausente(self):
        assert ip_cliente(peticion(), "CF-Connecting-IP") == "10.0.0.5"

    def test_sin_cliente_devuelve_desconocida(self):
        assert ip_cliente(peticion(cliente=None)) == "desconocida"
