"""Reinicia la BD local: borra el archivo y ejecuta migrate + seed.

Uso: `python -m app.db.reset`. Se niega si la URL guardada en la bóveda no empieza por `file:`
(nunca toca una base remota como Turso).
"""

import sys
from pathlib import Path
from typing import Literal

from app.db.database import connect_database
from app.db.migrate import migrate
from app.db.seed import seed


class ResetRefused(Exception):
    """La URL no es de una base local: no se borra nada."""


def local_path(url: str) -> Path | None:
    """Ruta del archivo de una URL `file:`; None para `:memory:`. ResetRefused si no es `file:`."""
    if not url.startswith("file:"):
        raise ResetRefused("db:reset solo funciona con bases locales (file:...). No se borró nada.")
    target = url[len("file:") :]
    if target == "" or target.startswith(":memory:"):
        return None
    return Path(target)


def reset_database(url: str, driver: Literal["libsql", "sqlite"] = "libsql") -> None:
    path = local_path(url)  # valida ANTES de borrar nada
    if path is not None:
        base = path if path.is_absolute() else Path.cwd() / path
        for suffix in ("", "-wal", "-shm", "-journal"):
            Path(str(base) + suffix).unlink(missing_ok=True)
    db = connect_database(url, driver=driver)
    try:
        migrate(db)
        seed(db)
    finally:
        db.close()


def main() -> int:
    from app.config import get_settings
    from app.db.bootstrap import build_vault
    from app.security.vault import VaultError

    settings = get_settings()
    try:
        vault = build_vault(settings)
    except VaultError as exc:
        print(exc, file=sys.stderr)
        return 1
    try:
        url = vault.get_secret("db.url")
    except VaultError as exc:
        print(exc, file=sys.stderr)
        return 1
    finally:
        vault.close()
    if url is None:
        print("No hay conexión de BD configurada (modo SETUP). No se hizo nada.", file=sys.stderr)
        return 1
    try:
        reset_database(url, settings.db_driver)
    except ResetRefused as exc:
        print(exc, file=sys.stderr)  # no se imprime la URL: puede llevar datos sensibles
        return 1
    print("Base local reiniciada: migraciones y semilla aplicadas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
