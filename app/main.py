from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import docs_habilitadas, get_settings, origenes_permitidos
from app.db import crear_pool
from app.dependencias import ConexionBD
from app.errores import registrar_manejadores
from app.routers import auth, usuarios


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI) -> AsyncIterator[None]:
    pool = crear_pool(get_settings().database_url)
    pool.open(wait=False)
    app.state.pool = pool
    try:
        yield
    finally:
        pool.close()


def create_app() -> FastAPI:
    docs = "/docs" if docs_habilitadas() else None
    app = FastAPI(
        title="SlotSpot MJ API",
        lifespan=ciclo_de_vida,
        docs_url=docs,
        redoc_url=None,
        openapi_url="/openapi.json" if docs else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origenes_permitidos(),
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
    registrar_manejadores(app)

    @app.get("/salud")
    def salud() -> dict[str, str]:
        return {"estado": "ok"}

    @app.get("/salud/bd")
    def salud_bd(conexion: ConexionBD) -> dict[str, str]:
        conexion.execute("SELECT 1")
        return {"estado": "ok", "base_de_datos": "ok"}

    app.include_router(auth.router)
    app.include_router(usuarios.router)
    return app


app = create_app()
