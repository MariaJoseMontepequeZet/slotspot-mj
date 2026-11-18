import threading
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.config import Settings
from app.errores import TokenExpirado, TokenInvalido

ALGORITMO_JWT = "HS256"

_hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)
_cupo_de_hash = threading.BoundedSemaphore(4)
_HASH_FALSO = _hasher.hash("contraseña-que-no-pertenece-a-nadie")


def hashear_password(password: str) -> str:
    with _cupo_de_hash:
        return _hasher.hash(password)


def verificar_password(password: str, hash_guardado: str | None) -> bool:
    objetivo = hash_guardado or _HASH_FALSO
    try:
        with _cupo_de_hash:
            _hasher.verify(objetivo, password)
    except (VerificationError, InvalidHashError):
        return False
    return hash_guardado is not None


def necesita_rehash(hash_guardado: str) -> bool:
    return _hasher.check_needs_rehash(hash_guardado)


def crear_token(
    usuario_id: int, rol: str, settings: Settings, ahora: datetime | None = None
) -> str:
    emitido = ahora or datetime.now(UTC)
    contenido = {
        "sub": str(usuario_id),
        "rol": rol,
        "iss": settings.jwt_emisor,
        "iat": emitido,
        "exp": emitido + timedelta(minutes=settings.jwt_expira_minutos),
    }
    return jwt.encode(contenido, settings.jwt_secret, algorithm=ALGORITMO_JWT)


def decodificar_token(token: str, settings: Settings) -> dict:
    try:
        return jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[ALGORITMO_JWT],
            issuer=settings.jwt_emisor,
            options={"require": ["exp", "iat", "sub", "iss"]},
        )
    except jwt.ExpiredSignatureError as error:
        raise TokenExpirado() from error
    except jwt.InvalidTokenError as error:
        raise TokenInvalido() from error
