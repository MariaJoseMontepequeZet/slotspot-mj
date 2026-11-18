ADMIN = "admin@slotspotmj.com"
OPERADOR = "operador@slotspotmj.com"
CLAVE = "Contraseña-segura-1"


def nuevo(**cambios) -> dict:
    datos = {
        "nombre": "Ana Perez",
        "email": "ana@slotspotmj.com",
        "password": "Otra-clave-segura-2",
        "rol": "operador",
    }
    datos.update(cambios)
    return datos


def campos(respuesta) -> dict[str, str]:
    return {item["campo"]: item["mensaje"] for item in respuesta.json()["error"]["detalle"]}


class TestCrearUsuario:
    def test_un_admin_crea_un_operador(self, entorno):
        entorno.crear_usuario(ADMIN, rol="admin")
        respuesta = entorno.cliente.post(
            "/usuarios", json=nuevo(), headers=entorno.cabeceras(ADMIN)
        )
        assert respuesta.status_code == 201
        cuerpo = respuesta.json()
        assert cuerpo["email"] == "ana@slotspotmj.com"
        assert cuerpo["rol"] == "operador"
        assert cuerpo["activo"] is True
        assert "password" not in cuerpo
        assert "password_hash" not in cuerpo

    def test_guarda_la_contrasena_cifrada(self, entorno):
        entorno.crear_usuario(ADMIN, rol="admin")
        entorno.cliente.post("/usuarios", json=nuevo(), headers=entorno.cabeceras(ADMIN))
        fila = entorno.consultar(
            "SELECT password_hash FROM usuarios WHERE email = 'ana@slotspotmj.com'"
        )[0]
        assert fila["password_hash"].startswith("$argon2id$")
        assert "Otra-clave-segura-2" not in fila["password_hash"]

    def test_el_usuario_nuevo_puede_iniciar_sesion(self, entorno):
        entorno.crear_usuario(ADMIN, rol="admin")
        entorno.cliente.post("/usuarios", json=nuevo(), headers=entorno.cabeceras(ADMIN))
        respuesta = entorno.cliente.post(
            "/auth/login", json={"email": "ana@slotspotmj.com", "password": "Otra-clave-segura-2"}
        )
        assert respuesta.status_code == 200

    def test_normaliza_el_correo_y_recorta_el_nombre(self, entorno):
        entorno.crear_usuario(ADMIN, rol="admin")
        respuesta = entorno.cliente.post(
            "/usuarios",
            json=nuevo(nombre="  Ana Perez  ", email="ANA@SlotSpotMJ.com"),
            headers=entorno.cabeceras(ADMIN),
        )
        assert respuesta.status_code == 201
        assert respuesta.json()["nombre"] == "Ana Perez"
        assert respuesta.json()["email"] == "ana@slotspotmj.com"

    def test_el_rol_por_defecto_es_operador(self, entorno):
        entorno.crear_usuario(ADMIN, rol="admin")
        datos = nuevo()
        del datos["rol"]
        respuesta = entorno.cliente.post("/usuarios", json=datos, headers=entorno.cabeceras(ADMIN))
        assert respuesta.json()["rol"] == "operador"

    def test_un_admin_puede_crear_otro_admin(self, entorno):
        entorno.crear_usuario(ADMIN, rol="admin")
        respuesta = entorno.cliente.post(
            "/usuarios", json=nuevo(rol="admin"), headers=entorno.cabeceras(ADMIN)
        )
        assert respuesta.json()["rol"] == "admin"

    def test_un_operador_no_puede_crear_usuarios(self, entorno):
        entorno.crear_usuario(OPERADOR, rol="operador")
        respuesta = entorno.cliente.post(
            "/usuarios", json=nuevo(), headers=entorno.cabeceras(OPERADOR)
        )
        assert respuesta.status_code == 403
        assert respuesta.json()["error"]["codigo"] == "prohibido"
        assert entorno.consultar("SELECT count(*) AS n FROM usuarios")[0]["n"] == 1

    def test_sin_sesion_no_se_puede_crear(self, entorno):
        respuesta = entorno.cliente.post("/usuarios", json=nuevo())
        assert respuesta.status_code == 401
        assert entorno.consultar("SELECT count(*) AS n FROM usuarios")[0]["n"] == 0

    def test_un_correo_repetido_da_conflicto_sin_importar_mayusculas(self, entorno):
        entorno.crear_usuario(ADMIN, rol="admin")
        cabeceras = entorno.cabeceras(ADMIN)
        assert entorno.cliente.post("/usuarios", json=nuevo(), headers=cabeceras).status_code == 201
        repetido = entorno.cliente.post(
            "/usuarios", json=nuevo(email="ANA@slotspotmj.com"), headers=cabeceras
        )
        assert repetido.status_code == 409
        assert repetido.json()["error"]["codigo"] == "conflicto"

    def test_un_conflicto_no_deja_la_conexion_inservible(self, entorno):
        entorno.crear_usuario(ADMIN, rol="admin")
        cabeceras = entorno.cabeceras(ADMIN)
        entorno.cliente.post("/usuarios", json=nuevo(), headers=cabeceras)
        for _ in range(8):
            entorno.cliente.post("/usuarios", json=nuevo(), headers=cabeceras)
        assert entorno.cliente.get("/usuarios", headers=cabeceras).status_code == 200


class TestValidacion:
    def entrar(self, entorno) -> dict[str, str]:
        entorno.crear_usuario(ADMIN, rol="admin")
        return entorno.cabeceras(ADMIN)

    def test_contrasena_corta(self, entorno):
        respuesta = entorno.cliente.post(
            "/usuarios", json=nuevo(password="corta"), headers=self.entrar(entorno)
        )
        assert respuesta.status_code == 422
        assert campos(respuesta)["password"] == "Debe tener al menos 8 caracteres."

    def test_contrasena_demasiado_larga(self, entorno):
        respuesta = entorno.cliente.post(
            "/usuarios", json=nuevo(password="x" * 129), headers=self.entrar(entorno)
        )
        assert respuesta.status_code == 422
        assert "password" in campos(respuesta)

    def test_nombre_vacio_o_solo_espacios(self, entorno):
        cabeceras = self.entrar(entorno)
        for nombre in ["", "   "]:
            respuesta = entorno.cliente.post(
                "/usuarios", json=nuevo(nombre=nombre), headers=cabeceras
            )
            assert respuesta.status_code == 422
            assert "nombre" in campos(respuesta)

    def test_correo_invalido(self, entorno):
        respuesta = entorno.cliente.post(
            "/usuarios", json=nuevo(email="esto-no-es-un-correo"), headers=self.entrar(entorno)
        )
        assert respuesta.status_code == 422
        assert campos(respuesta)["email"] == "El correo electrónico no es válido."

    def test_rol_inexistente(self, entorno):
        respuesta = entorno.cliente.post(
            "/usuarios", json=nuevo(rol="superadmin"), headers=self.entrar(entorno)
        )
        assert respuesta.status_code == 422
        assert campos(respuesta)["rol"] == "El valor no está permitido."

    def test_faltan_campos(self, entorno):
        respuesta = entorno.cliente.post("/usuarios", json={}, headers=self.entrar(entorno))
        assert respuesta.status_code == 422
        assert set(campos(respuesta)) == {"nombre", "email", "password"}

    def test_no_devuelve_el_valor_enviado_en_el_error(self, entorno):
        respuesta = entorno.cliente.post(
            "/usuarios", json=nuevo(password="corta"), headers=self.entrar(entorno)
        )
        assert "corta" not in respuesta.text


class TestListarUsuarios:
    def test_un_admin_ve_la_lista_sin_secretos(self, entorno):
        entorno.crear_usuario(ADMIN, rol="admin", nombre="Admin")
        entorno.crear_usuario(OPERADOR, rol="operador", nombre="Operador")
        respuesta = entorno.cliente.get("/usuarios", headers=entorno.cabeceras(ADMIN))
        assert respuesta.status_code == 200
        lista = respuesta.json()
        assert [u["email"] for u in lista] == [ADMIN, OPERADOR]
        assert all("password_hash" not in u and "password" not in u for u in lista)

    def test_un_operador_no_puede_ver_la_lista(self, entorno):
        entorno.crear_usuario(OPERADOR, rol="operador")
        respuesta = entorno.cliente.get("/usuarios", headers=entorno.cabeceras(OPERADOR))
        assert respuesta.status_code == 403

    def test_sin_sesion(self, entorno):
        assert entorno.cliente.get("/usuarios").status_code == 401
