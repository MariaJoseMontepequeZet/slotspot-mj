from typing import Annotated, Literal

from pydantic import BaseModel, EmailStr, Field, StringConstraints

Nombre = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class LoginEntrada(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenSalida(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class UsuarioNuevo(BaseModel):
    nombre: Nombre
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    rol: Literal["admin", "operador"] = "operador"


class UsuarioSalida(BaseModel):
    id: int
    nombre: str
    email: str
    rol: str
    activo: bool
