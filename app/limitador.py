import ipaddress
import math
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Annotated

from fastapi import Depends, Request

from app.errores import LimiteExcedido, ServidorOcupado


class _Ventana:
    def __init__(self, maximo: int, segundos: float) -> None:
        self.maximo = maximo
        self.segundos = segundos
        self._eventos: dict[str, deque[float]] = defaultdict(deque)

    def _vigentes(self, clave: str, ahora: float) -> deque[float] | None:
        eventos = self._eventos.get(clave)
        if eventos is None:
            return None
        while eventos and ahora - eventos[0] >= self.segundos:
            eventos.popleft()
        if not eventos:
            del self._eventos[clave]
            return None
        return eventos

    def cuenta(self, clave: str, ahora: float) -> int:
        eventos = self._vigentes(clave, ahora)
        return len(eventos) if eventos else 0

    def registrar(self, clave: str, ahora: float) -> None:
        self._eventos[clave].append(ahora)

    def espera(self, clave: str, ahora: float) -> int:
        eventos = self._vigentes(clave, ahora)
        if not eventos:
            return 0
        return max(1, math.ceil(self.segundos - (ahora - eventos[0])))

    def olvidar(self, clave: str) -> None:
        self._eventos.pop(clave, None)

    def purgar(self, ahora: float) -> None:
        for clave in list(self._eventos):
            self._vigentes(clave, ahora)

    def __len__(self) -> int:
        return len(self._eventos)


def _normalizar(correo: str) -> str:
    return correo.strip().lower()


class LimitadorLogin:
    def __init__(
        self,
        intentos_por_ip: int = 20,
        ventana_ip: float = 300,
        fallos_por_correo: int = 8,
        ventana_correo: float = 900,
        simultaneos: int = 8,
        reloj: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ip = _Ventana(intentos_por_ip, ventana_ip)
        self._correo = _Ventana(fallos_por_correo, ventana_correo)
        self._cupo = threading.BoundedSemaphore(simultaneos)
        self._reloj = reloj
        self._candado = threading.Lock()
        self._operaciones = 0

    def comprobar(self, ip: str, correo: str) -> None:
        ahora = self._reloj()
        clave = _normalizar(correo)
        with self._candado:
            self._mantener(ahora)
            if self._correo.cuenta(clave, ahora) >= self._correo.maximo:
                raise LimiteExcedido(reintentar_en=self._correo.espera(clave, ahora))
            if self._ip.cuenta(ip, ahora) >= self._ip.maximo:
                raise LimiteExcedido(reintentar_en=self._ip.espera(ip, ahora))
            self._ip.registrar(ip, ahora)

    def registrar_fallo(self, correo: str) -> None:
        with self._candado:
            self._correo.registrar(_normalizar(correo), self._reloj())

    def registrar_exito(self, correo: str) -> None:
        with self._candado:
            self._correo.olvidar(_normalizar(correo))

    @contextmanager
    def puesto(self) -> Iterator[None]:
        if not self._cupo.acquire(blocking=False):
            raise ServidorOcupado(reintentar_en=2)
        try:
            yield
        finally:
            self._cupo.release()

    def _mantener(self, ahora: float) -> None:
        self._operaciones += 1
        if self._operaciones % 500 == 0:
            self._ip.purgar(ahora)
            self._correo.purgar(ahora)


def ip_cliente(request: Request, cabecera: str = "") -> str:
    if cabecera:
        candidata = request.headers.get(cabecera, "").split(",")[0].strip()
        try:
            return str(ipaddress.ip_address(candidata))
        except ValueError:
            pass
    return request.client.host if request.client else "desconocida"


def get_limitador(request: Request) -> LimitadorLogin:
    return request.app.state.limitador


Limitador = Annotated[LimitadorLogin, Depends(get_limitador)]
