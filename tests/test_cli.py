import io

from app import cli

CORREO = "Admin@SlotSpotMJ.com"
CLAVE = "Clave-muy-segura-9"


def ejecutar(monkeypatch, argumentos: list[str], entrada: str = CLAVE + "\n") -> int:
    monkeypatch.setattr("sys.stdin", io.StringIO(entrada))
    return cli.main(["crear-admin", "--nombre", "Maria Jose", "--email", CORREO, *argumentos])


class TestCrearAdmin:
    def test_crea_un_administrador_que_puede_entrar(self, entorno, monkeypatch, capsys):
        codigo = ejecutar(monkeypatch, ["--password-stdin"])
        salida = capsys.readouterr()
        assert codigo == 0
        assert "admin@slotspotmj.com" in salida.out
        usuario = entorno.consultar(
            "SELECT u.email, r.nombre AS rol, u.password_hash FROM usuarios u "
            "JOIN roles r ON r.id = u.rol_id"
        )[0]
        assert usuario["email"] == "admin@slotspotmj.com"
        assert usuario["rol"] == "admin"
        assert usuario["password_hash"].startswith("$argon2id$")
        respuesta = entorno.cliente.post(
            "/auth/login", json={"email": "admin@slotspotmj.com", "password": CLAVE}
        )
        assert respuesta.status_code == 200

    def test_nunca_imprime_la_contrasena(self, entorno, monkeypatch, capsys):
        ejecutar(monkeypatch, ["--password-stdin"])
        salida = capsys.readouterr()
        assert CLAVE not in salida.out
        assert CLAVE not in salida.err

    def test_un_correo_repetido_falla_con_un_mensaje(self, entorno, monkeypatch, capsys):
        assert ejecutar(monkeypatch, ["--password-stdin"]) == 0
        capsys.readouterr()
        assert ejecutar(monkeypatch, ["--password-stdin"]) == 1
        assert "ya existe" in capsys.readouterr().err
        assert entorno.consultar("SELECT count(*) AS n FROM usuarios")[0]["n"] == 1

    def test_rechaza_una_contrasena_corta(self, entorno, monkeypatch, capsys):
        assert ejecutar(monkeypatch, ["--password-stdin"], entrada="corta\n") == 2
        assert "password" in capsys.readouterr().err
        assert entorno.consultar("SELECT count(*) AS n FROM usuarios")[0]["n"] == 0

    def test_rechaza_un_correo_invalido(self, entorno, monkeypatch, capsys):
        monkeypatch.setattr("sys.stdin", io.StringIO(CLAVE + "\n"))
        codigo = cli.main(
            ["crear-admin", "--nombre", "X", "--email", "no-es-correo", "--password-stdin"]
        )
        assert codigo == 2
        assert "email" in capsys.readouterr().err

    def test_pide_la_contrasena_dos_veces_cuando_es_interactivo(self, entorno, monkeypatch):
        respuestas = iter([CLAVE, CLAVE])
        monkeypatch.setattr(cli.getpass, "getpass", lambda _mensaje: next(respuestas))
        assert cli.main(["crear-admin", "--nombre", "Maria", "--email", CORREO]) == 0

    def test_falla_si_las_dos_contrasenas_no_coinciden(self, entorno, monkeypatch, capsys):
        respuestas = iter([CLAVE, CLAVE + "x"])
        monkeypatch.setattr(cli.getpass, "getpass", lambda _mensaje: next(respuestas))
        assert cli.main(["crear-admin", "--nombre", "Maria", "--email", CORREO]) == 2
        assert "no coinciden" in capsys.readouterr().err
        assert entorno.consultar("SELECT count(*) AS n FROM usuarios")[0]["n"] == 0
