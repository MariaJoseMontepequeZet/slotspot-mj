from collections.abc import Iterator
from contextlib import contextmanager, suppress
from typing import Annotated

import psycopg
from fastapi import Depends, Request
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool, PoolTimeout

from app.errores import BaseDatosNoDisponible

ESPERA_CONEXION_SEGUNDOS = 5.0


def crear_pool(database_url: str) -> ConnectionPool:
    return ConnectionPool(
        database_url,
        min_size=1,
        max_size=5,
        kwargs={"row_factory": dict_row},
        open=False,
    )


@contextmanager
def tomar_conexion(pool: ConnectionPool) -> Iterator[Connection]:
    try:
        conexion = pool.getconn(timeout=ESPERA_CONEXION_SEGUNDOS)
    except PoolTimeout as error:
        raise BaseDatosNoDisponible() from error
    try:
        yield conexion
    finally:
        with suppress(psycopg.Error):
            conexion.rollback()
        pool.putconn(conexion)


def get_pool(request: Request) -> ConnectionPool:
    return request.app.state.pool


def get_conexion(pool: Annotated[ConnectionPool, Depends(get_pool)]) -> Iterator[Connection]:
    with tomar_conexion(pool) as conexion:
        yield conexion
