import threading
import time
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from argon2 import PasswordHasher

from app import seguridad
from app.config import Settings
from app.errores import TokenExpirado, TokenInvalido
from app.seguridad import (
    crear_token,
    decodificar_token,
    hashear_password,
    necesita_rehash,
    verificar_password,
)

SECRETO = "secreto-de-pruebas-" + "a" * 48


@pytest.fixture
def ajustes() -> Settings:
    return Settings(database_url="postgresql://x@localhost/x", jwt_secret=SECRETO)


class TestHash:
    def test_usa_argon2id(self):
        assert hashear_password("Contraseña-123").startswith("$argon2id$")

    def test_no_guarda_la_contrasena_en_claro(self):
        assert "Contraseña-123" not in hashear_password("Contraseña-123")

    def test_cada_hash_lleva_una_sal_distinta(self):
        assert hashear_password("igual-igual") != hashear_password("igual-igual")

    def test_verifica_la_contrasena_correcta(self):
        assert verificar_password("Contraseña-123", hashear_password("Contraseña-123"))

    def test_rechaza_una_contrasena_incorrecta(self):
        assert not verificar_password("otra", hashear_password("Contraseña-123"))

    def test_distingue_mayusculas(self):
        assert not verificar_password("contraseña-123", hashear_password("Contraseña-123"))

    def test_sin_hash_guardado_devuelve_falso(self):
        assert verificar_password("lo-que-sea", None) is False

    def test_un_hash_corrupto_devuelve_falso(self):
        assert verificar_password("lo-que-sea", "esto-no-es-un-hash") is False

    def test_sin_hash_guardado_hace_el_mismo_trabajo_que_con_hash(self, monkeypatch):
        llamadas = []

        class Espia:
            def __init__(self, real):
                self.real = real

            def verify(self, hash_guardado, password):
                llamadas.append(hash_guardado)
                return self.real.verify(hash_guardado, password)

        monkeypatch.setattr(seguridad, "_hasher", Espia(seguridad._hasher))
        verificar_password("x", None)
        assert len(llamadas) == 1
        assert llamadas[0].startswith("$argon2id$")

    def test_la_contrasena_del_hash_falso_tampoco_autentica(self):
        assert verificar_password("contraseña-que-no-pertenece-a-nadie", None) is False

    def test_limita_los_calculos_de_hash_simultaneos(self, monkeypatch):
        activos = 0
        maximo = 0
        candado = threading.Lock()

        class Lento:
            def __init__(self, real):
                self.real = real

            def verify(self, hash_guardado, password):
                nonlocal activos, maximo
                with candado:
                    activos += 1
                    maximo = max(maximo, activos)
                time.sleep(0.05)
                with candado:
                    activos -= 1
                return self.real.verify(hash_guardado, password)

        monkeypatch.setattr(seguridad, "_hasher", Lento(seguridad._hasher))
        hilos = [threading.Thread(target=verificar_password, args=("x", None)) for _ in range(16)]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join()
        assert 1 <= maximo <= 4

    def test_un_hash_reciente_no_necesita_rehash(self):
        assert not necesita_rehash(hashear_password("x" * 10))

    def test_un_hash_con_parametros_debiles_necesita_rehash(self):
        debil = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash("x" * 10)
        assert necesita_rehash(debil)


class TestToken:
    def test_ida_y_vuelta(self, ajustes):
        token = crear_token(7, "admin", ajustes)
        contenido = decodificar_token(token, ajustes)
        assert contenido["sub"] == "7"
        assert contenido["rol"] == "admin"
        assert contenido["iss"] == "slotspot-mj"

    def test_expira_en_los_minutos_configurados(self, ajustes):
        contenido = decodificar_token(crear_token(1, "admin", ajustes), ajustes)
        assert contenido["exp"] - contenido["iat"] == ajustes.jwt_expira_minutos * 60

    def test_un_token_vencido_se_rechaza_como_expirado(self, ajustes):
        hace_dos_horas = datetime.now(UTC) - timedelta(hours=2)
        token = crear_token(1, "admin", ajustes, ahora=hace_dos_horas)
        with pytest.raises(TokenExpirado):
            decodificar_token(token, ajustes)

    def test_una_firma_alterada_se_rechaza(self, ajustes):
        token = crear_token(1, "admin", ajustes)
        cabecera, cuerpo, firma = token.split(".")
        alterada = ".".join([cabecera, cuerpo, firma[:-2] + ("AA" if firma[-2:] != "AA" else "BB")])
        with pytest.raises(TokenInvalido):
            decodificar_token(alterada, ajustes)

    def test_un_cuerpo_alterado_se_rechaza(self, ajustes):
        token = crear_token(1, "operador", ajustes)
        falso = crear_token(1, "admin", ajustes).split(".")[1]
        cabecera, _, firma = token.split(".")
        with pytest.raises(TokenInvalido):
            decodificar_token(f"{cabecera}.{falso}.{firma}", ajustes)

    def test_otro_secreto_se_rechaza(self, ajustes):
        otro = Settings(database_url="postgresql://x@localhost/x", jwt_secret="o" * 40)
        with pytest.raises(TokenInvalido):
            decodificar_token(crear_token(1, "admin", otro), ajustes)

    def test_el_algoritmo_none_se_rechaza(self, ajustes):
        ahora = datetime.now(UTC)
        sin_firma = jwt.encode(
            {"sub": "1", "iss": "slotspot-mj", "iat": ahora, "exp": ahora + timedelta(hours=1)},
            key=None,
            algorithm="none",
        )
        with pytest.raises(TokenInvalido):
            decodificar_token(sin_firma, ajustes)

    def test_otro_algoritmo_hmac_se_rechaza(self, ajustes):
        ahora = datetime.now(UTC)
        token = jwt.encode(
            {"sub": "1", "iss": "slotspot-mj", "iat": ahora, "exp": ahora + timedelta(hours=1)},
            SECRETO,
            algorithm="HS512",
        )
        with pytest.raises(TokenInvalido):
            decodificar_token(token, ajustes)

    def test_otro_emisor_se_rechaza(self, ajustes):
        otro = Settings(
            database_url="postgresql://x@localhost/x", jwt_secret=SECRETO, jwt_emisor="otra-app"
        )
        with pytest.raises(TokenInvalido):
            decodificar_token(crear_token(1, "admin", otro), ajustes)

    @pytest.mark.parametrize("faltante", ["exp", "iat", "sub", "iss"])
    def test_exige_las_reclamaciones_obligatorias(self, ajustes, faltante):
        ahora = datetime.now(UTC)
        contenido = {
            "sub": "1",
            "iss": "slotspot-mj",
            "iat": ahora,
            "exp": ahora + timedelta(hours=1),
        }
        del contenido[faltante]
        token = jwt.encode(contenido, SECRETO, algorithm="HS256")
        with pytest.raises(TokenInvalido):
            decodificar_token(token, ajustes)

    @pytest.mark.parametrize("basura", ["", "abc", "a.b.c", "....", "Bearer x"])
    def test_texto_que_no_es_un_token_se_rechaza(self, ajustes, basura):
        with pytest.raises(TokenInvalido):
            decodificar_token(basura, ajustes)


class TestAjustes:
    def test_exige_un_secreto_largo(self):
        with pytest.raises(ValueError):
            Settings(database_url="postgresql://x@localhost/x", jwt_secret="corto")

    def test_la_expiracion_tiene_limites(self):
        with pytest.raises(ValueError):
            Settings(
                database_url="postgresql://x@localhost/x", jwt_secret=SECRETO, jwt_expira_minutos=0
            )
