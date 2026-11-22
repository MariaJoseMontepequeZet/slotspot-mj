import re
from pathlib import Path

import pytest

OPS = Path(__file__).resolve().parent.parent / "ops"
PORTAFOLIO = "https://portafoliomariajosemontepequezet.pamcing.me"


@pytest.fixture(scope="module")
def caddyfile() -> str:
    return (OPS / "Caddyfile").read_text(encoding="utf-8")


def directivas_csp(caddyfile: str) -> dict[str, list[str]]:
    linea = next(
        fila
        for fila in caddyfile.splitlines()
        if fila.strip().startswith("Content-Security-Policy")
    )
    politica = re.search(r'"(.*)"', linea).group(1)
    resultado = {}
    for parte in politica.split(";"):
        palabras = parte.split()
        if palabras:
            resultado[palabras[0]] = palabras[1:]
    return resultado


class TestIncrustacion:
    def test_solo_el_propio_sitio_y_el_portafolio_pueden_incrustarlo(self, caddyfile):
        assert directivas_csp(caddyfile)["frame-ancestors"] == ["'self'", PORTAFOLIO]

    def test_no_permite_incrustar_desde_cualquier_sitio(self, caddyfile):
        permitidos = directivas_csp(caddyfile)["frame-ancestors"]
        assert "*" not in permitidos
        assert "https:" not in permitidos
        assert all(valor == "'self'" or valor.startswith("https://") for valor in permitidos)

    def test_no_queda_x_frame_options_que_lo_contradiga(self, caddyfile):
        assert "x-frame-options" not in caddyfile.lower()


class TestPoliticaDeSeguridad:
    def test_los_scripts_solo_vienen_del_propio_sitio(self, caddyfile):
        assert directivas_csp(caddyfile)["script-src"] == ["'self'"]

    def test_no_permite_eval_ni_scripts_en_linea(self, caddyfile):
        for valor in directivas_csp(caddyfile).get("script-src", []):
            assert "unsafe" not in valor

    def test_el_origen_por_defecto_es_el_propio_sitio(self, caddyfile):
        assert directivas_csp(caddyfile)["default-src"] == ["'self'"]

    def test_los_formularios_y_la_base_solo_apuntan_al_propio_sitio(self, caddyfile):
        directivas = directivas_csp(caddyfile)
        assert directivas["form-action"] == ["'self'"]
        assert directivas["base-uri"] == ["'self'"]

    def test_mantiene_las_cabeceras_de_endurecimiento(self, caddyfile):
        assert "X-Content-Type-Options nosniff" in caddyfile
        assert "Referrer-Policy" in caddyfile
        assert "Permissions-Policy" in caddyfile
        assert "-Server" in caddyfile

    def test_pide_https_por_un_ano_sin_alcanzar_otros_subdominios(self, caddyfile):
        linea = next(f for f in caddyfile.splitlines() if "Strict-Transport-Security" in f)
        assert "max-age=31536000" in linea
        assert "includeSubDomains" not in linea
        assert "preload" not in linea


class TestRutas:
    def test_la_api_se_publica_sin_el_prefijo_api(self, caddyfile):
        assert "handle_path /api/* {" in caddyfile
        assert "reverse_proxy api:8000" in caddyfile

    def test_tiene_la_ruta_de_salud(self, caddyfile):
        assert "handle /healthz" in caddyfile

    def test_las_llaves_estan_balanceadas(self, caddyfile):
        assert caddyfile.count("{") == caddyfile.count("}")


class TestCompose:
    def test_el_puerto_web_solo_escucha_en_el_propio_servidor(self):
        compose = (OPS / "docker-compose.yml").read_text(encoding="utf-8")
        assert '- "127.0.0.1:8439:80"' in compose
        assert '- "8439:80"' not in compose

    def test_el_tunel_propio_llega_a_web_por_la_red_de_docker(self):
        compose = (OPS / "docker-compose.yml").read_text(encoding="utf-8")
        bloque = servicio(compose, "tunel")
        assert "TUNNEL_TOKEN: ${TUNEL_TOKEN}" in bloque
        assert "ports:" not in bloque

    def test_el_caddyfile_se_monta_desde_la_carpeta_del_proyecto(self):
        compose = (OPS / "docker-compose.yml").read_text(encoding="utf-8")
        assert "./Caddyfile:/etc/caddy/Caddyfile:ro" in compose


def servicio(compose: str, nombre: str) -> str:
    inicio = re.search(rf"^  {nombre}:$", compose, re.MULTILINE).end()
    resto = compose[inicio:]
    fin = re.search(r"^  \S|^\S", resto, re.MULTILINE)
    return resto[: fin.start()] if fin else resto


class TestEndurecimientoDelCompose:
    @pytest.fixture(scope="module")
    def compose(self) -> str:
        return (OPS / "docker-compose.yml").read_text(encoding="utf-8")

    @pytest.mark.parametrize("nombre", ["db", "api", "web"])
    def test_ningun_contenedor_gana_privilegios(self, compose, nombre):
        assert "no-new-privileges:true" in servicio(compose, nombre)

    @pytest.mark.parametrize("nombre", ["api", "web"])
    def test_api_y_web_no_conservan_capacidades_ni_escriben_en_disco(self, compose, nombre):
        bloque = servicio(compose, nombre)
        assert "cap_drop:\n      - ALL" in bloque
        assert "read_only: true" in bloque

    def test_la_api_no_se_conecta_como_superusuario(self, compose):
        bloque = servicio(compose, "api")
        assert "postgresql://slotspot_app:${APP_DB_PASSWORD}@db" in bloque
        assert "POSTGRES_USER" not in bloque
        assert "POSTGRES_PASSWORD" not in bloque
