"""Configuración de la API: lee y valida el entorno (`.env`) con pydantic-settings."""

import base64
import binascii
import sys
from functools import lru_cache
from typing import Literal, Self

from pydantic import ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # `env_ignore_empty`: una variable vacía (`CLAVE=`) equivale a no definida.
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        case_sensitive=False,
    )

    node_env: Literal["development", "test", "production"] = "development"
    host: str = "127.0.0.1"
    port: int = 4000

    # Legado: solo se lee para importarlos a la bóveda cifrada y borrarlos del .env (C03).
    turso_database_url: str | None = None
    turso_auth_token: str | None = None
    db_driver: Literal["libsql", "sqlite"] = "libsql"
    vault_path: str = "data/vault.db"

    cors_origin: str = "http://localhost:3000"
    api_public_origin: str = "http://localhost:4000"
    # Activo salvo que se ponga "off". "noop" (valor antiguo de .env.example) también lo activa.
    orchestrator: Literal["off", "noop", "llm"] = "llm"
    # None = según el entorno (activa en development/test, desactivada en production).
    docs_enabled: bool | None = None

    # Seguridad (PLAN §12.5). Las claves las genera `python scripts/setup_env.py`.
    app_master_key: str | None = None
    session_secret: str | None = None
    session_idle_minutes: int = 30
    session_max_hours: int = 8
    # None = exigir login salvo en NODE_ENV=test; AUTH_ENFORCED=false lo desactiva (solo dev).
    auth_enforced: bool | None = None

    backup_dir: str = "backups"
    backup_interval_hours: int = 24
    backup_keep: int = 14
    admin_allow_db_change: bool = False  # exige ADMIN_ALLOW_DB_CHANGE=true

    @field_validator("port")
    @classmethod
    def _port_range(cls, v: int) -> int:
        if not 1 <= v <= 65535:
            raise ValueError("debe estar entre 1 y 65535")
        return v

    @field_validator(
        "session_idle_minutes", "session_max_hours", "backup_interval_hours", "backup_keep"
    )
    @classmethod
    def _positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("debe ser un entero >= 1")
        return v

    @field_validator("app_master_key")
    @classmethod
    def _key_is_32_bytes(cls, v: str | None) -> str | None:
        if v is None:
            return v
        try:
            ok = len(base64.b64decode(v, validate=True)) == 32
        except (binascii.Error, ValueError):
            ok = False
        if not ok:
            raise ValueError("debe ser 32 bytes en base64 (ejecuta python scripts/setup_env.py)")
        return v

    @model_validator(mode="after")
    def _production_requires_secrets(self) -> Self:
        if self.node_env == "production":
            missing = [
                name.upper()
                for name in ("app_master_key", "session_secret")
                if not getattr(self, name)
            ]
            if missing:
                raise ValueError(f"obligatorias en producción: {', '.join(missing)}")
        return self

    @property
    def docs_active(self) -> bool:
        if self.docs_enabled is not None:
            return self.docs_enabled
        return self.node_env != "production"


def format_validation_error(err: ValidationError) -> str:
    lines = []
    for issue in err.errors():
        loc = ".".join(str(p) for p in issue["loc"]).upper() or "(entorno)"
        msg = "falta la variable" if issue["type"] == "missing" else issue["msg"]
        lines.append(f"  - {loc}: {msg}")
    return "Configuración de entorno inválida:\n" + "\n".join(lines)


@lru_cache
def get_settings() -> Settings:
    """Settings del proceso. Si el entorno es inválido, termina con un mensaje claro y código 1."""
    try:
        return Settings()
    except ValidationError as err:
        print(format_validation_error(err), file=sys.stderr)
        print("Revisa tu archivo .env (usa .env.example como base).", file=sys.stderr)
        raise SystemExit(1) from None
