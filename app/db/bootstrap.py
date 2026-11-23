"""Construye la conexión a la BD a partir de la bóveda cifrada (PLAN §16)."""

from pathlib import Path

from app.config import Settings
from app.db.database import Database, connect_database
from app.security.crypto import SecretBox
from app.security.vault import Vault, VaultError


def build_vault(settings: Settings) -> Vault:
    """Abre (o crea) la bóveda. Requiere `APP_MASTER_KEY`."""
    if not settings.app_master_key:
        raise VaultError("Falta APP_MASTER_KEY en el .env (ejecuta python scripts/setup_env.py)")
    box = SecretBox.from_base64(settings.app_master_key)
    return Vault(Path(settings.vault_path), box)


def open_database_from_vault(vault: Vault, driver: str = "libsql") -> Database | None:
    """Conecta con la URL y el token de la bóveda. Devuelve None si aún no hay URL (modo SETUP)."""
    url = vault.get_secret("db.url")
    if url is None:
        return None
    token = vault.get_secret("db.auth_token")
    return connect_database(url, token, "sqlite" if driver == "sqlite" else "libsql")


def open_configured_database(settings: Settings) -> tuple[Database, Vault] | None:
    """Abre la BD configurada en la bóveda. None si no hay conexión guardada (modo SETUP)."""
    vault = build_vault(settings)
    db = open_database_from_vault(vault, settings.db_driver)
    if db is None:
        vault.close()
        return None
    return db, vault
