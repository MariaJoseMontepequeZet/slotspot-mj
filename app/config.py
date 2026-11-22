import os
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    database_url: str
    jwt_secret: str = Field(min_length=32)
    jwt_expira_minutos: int = Field(default=60, ge=1, le=1440)
    jwt_emisor: str = "slotspot-mj"
    ip_cliente_cabecera: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


def origenes_permitidos() -> list[str]:
    bruto = os.environ.get("ALLOWED_ORIGINS", "")
    return [origen.strip() for origen in bruto.split(",") if origen.strip()]


def docs_habilitadas() -> bool:
    return os.environ.get("API_DOCS") == "1"
