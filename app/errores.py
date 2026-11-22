import logging
from typing import Any

import psycopg
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

registro = logging.getLogger("slotspot")


class ErrorApp(Exception):
    status_code = 500
    codigo = "error_interno"
    mensaje = "Ocurrió un error inesperado."

    def __init__(
        self,
        mensaje: str | None = None,
        detalle: Any = None,
        reintentar_en: int | None = None,
    ) -> None:
        super().__init__(mensaje or self.mensaje)
        self.mensaje = mensaje or self.mensaje
        self.detalle = detalle
        self.reintentar_en = reintentar_en


class NoAutenticado(ErrorApp):
    status_code = 401
    codigo = "no_autenticado"
    mensaje = "Debes iniciar sesión."


class CredencialesInvalidas(NoAutenticado):
    codigo = "credenciales_invalidas"
    mensaje = "Correo o contraseña incorrectos."


class TokenInvalido(NoAutenticado):
    codigo = "token_invalido"
    mensaje = "El token de acceso no es válido."


class TokenExpirado(TokenInvalido):
    codigo = "token_expirado"
    mensaje = "El token de acceso expiró. Inicia sesión de nuevo."


class Prohibido(ErrorApp):
    status_code = 403
    codigo = "prohibido"
    mensaje = "No tienes permiso para hacer esto."


class NoEncontrado(ErrorApp):
    status_code = 404
    codigo = "no_encontrado"
    mensaje = "No se encontró el recurso."


class Conflicto(ErrorApp):
    status_code = 409
    codigo = "conflicto"
    mensaje = "La operación entra en conflicto con datos existentes."


class LimiteExcedido(ErrorApp):
    status_code = 429
    codigo = "demasiados_intentos"
    mensaje = "Demasiados intentos. Espera unos minutos antes de volver a intentarlo."


class ServidorOcupado(ErrorApp):
    status_code = 503
    codigo = "servidor_ocupado"
    mensaje = "Hay muchos inicios de sesión en curso. Intenta de nuevo en unos segundos."


class BaseDatosNoDisponible(ErrorApp):
    status_code = 503
    codigo = "bd_no_disponible"
    mensaje = "La base de datos no está disponible. Intenta de nuevo en un momento."


def respuesta_error(
    status: int,
    codigo: str,
    mensaje: str,
    detalle: Any = None,
    cabeceras: dict[str, str] | None = None,
) -> JSONResponse:
    cuerpo = {"error": {"codigo": codigo, "mensaje": mensaje, "detalle": detalle}}
    return JSONResponse(status_code=status, content=cuerpo, headers=cabeceras)


def traducir_validacion(error: dict[str, Any]) -> str:
    tipo = error.get("type", "")
    contexto = error.get("ctx") or {}
    if tipo == "missing":
        return "Este campo es obligatorio."
    if tipo == "string_too_short":
        return f"Debe tener al menos {contexto.get('min_length')} caracteres."
    if tipo == "string_too_long":
        return f"Debe tener como máximo {contexto.get('max_length')} caracteres."
    if tipo in ("string_type", "int_type", "bool_type"):
        return "El tipo de dato no es válido."
    if tipo == "literal_error":
        return "El valor no está permitido."
    if tipo == "json_invalid":
        return "El cuerpo de la petición no es un JSON válido."
    if "value_error" in tipo and error.get("loc", ("",))[-1] == "email":
        return "El correo electrónico no es válido."
    if "value_error" in tipo:
        return "El valor no es válido."
    return str(error.get("msg", "El valor no es válido."))


async def manejar_error_app(request: Request, error: ErrorApp) -> JSONResponse:
    cabeceras: dict[str, str] = {}
    if error.status_code == 401:
        cabeceras["WWW-Authenticate"] = "Bearer"
    if error.reintentar_en:
        cabeceras["Retry-After"] = str(error.reintentar_en)
    return respuesta_error(
        error.status_code, error.codigo, error.mensaje, error.detalle, cabeceras or None
    )


async def manejar_validacion(request: Request, error: RequestValidationError) -> JSONResponse:
    detalle = [
        {
            "campo": ".".join(str(parte) for parte in item["loc"][1:]) or str(item["loc"][0]),
            "mensaje": traducir_validacion(item),
        }
        for item in error.errors()
    ]
    return respuesta_error(422, "validacion", "Los datos enviados no son válidos.", detalle)


async def manejar_http(request: Request, error: StarletteHTTPException) -> JSONResponse:
    codigos = {
        404: ("no_encontrado", "No se encontró el recurso."),
        405: ("metodo_no_permitido", "El método no está permitido en esta ruta."),
    }
    codigo, mensaje = codigos.get(
        error.status_code, ("error_http", "No se pudo procesar la petición.")
    )
    return respuesta_error(
        error.status_code, codigo, mensaje, None, getattr(error, "headers", None)
    )


async def manejar_bd(request: Request, error: psycopg.OperationalError) -> JSONResponse:
    registro.error("Fallo de base de datos: %s", error)
    esperado = BaseDatosNoDisponible()
    return respuesta_error(esperado.status_code, esperado.codigo, esperado.mensaje)


async def manejar_inesperado(request: Request, error: Exception) -> JSONResponse:
    registro.exception(
        "Error no controlado en %s %s", request.method, request.url.path, exc_info=error
    )
    return respuesta_error(500, "error_interno", "Ocurrió un error inesperado.")


def registrar_manejadores(app: FastAPI) -> None:
    app.add_exception_handler(ErrorApp, manejar_error_app)
    app.add_exception_handler(RequestValidationError, manejar_validacion)
    app.add_exception_handler(StarletteHTTPException, manejar_http)
    app.add_exception_handler(psycopg.OperationalError, manejar_bd)
    app.add_exception_handler(Exception, manejar_inesperado)
