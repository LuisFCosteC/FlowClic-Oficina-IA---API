"""Conexión de BD desde el panel (A05, PLAN §13.2 con la bóveda cifrada de §16).

Reglas de seguridad:
- El token NUNCA sale de aquí: ni en respuestas, ni en errores, ni en logs, ni en auditoría.
- Los mensajes de error no reflejan la URL ni el token (los fabrica `setup_service`).
- «Vacío = conservar el token actual» solo si la URL es idéntica (byte a byte): si no, el token de
  una BD se enviaría a otro servidor.
- `/test` no cambia nada: no migra y ni siquiera crea un archivo `file:` que no exista.
"""

import re
import threading
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from app.config import Settings
from app.db.database import (
    Database,
    DatabaseError,
    connect_database,
    swap_db,
    try_get_db,
)
from app.domain.admin_schemas import BackupResult, DbStatus, DbTestResult
from app.errors import AppError, unprocessable
from app.events.bus import EventBus
from app.security import audit
from app.security.setup_gate import SetupGate
from app.security.vault import Vault
from app.services import setup_service
from app.util import now_iso

_change_lock = threading.Lock()  # un solo cambio de BD a la vez
_BACKUP_DIR = re.compile(r"^(\d{8}T\d{6}Z)(-\d+)?$")
_SKIP_TABLES = ("sessions",)  # tokens de sesión vivos: no se guardan en backups


def describe(url: str) -> tuple[Literal["local", "remote"], str]:
    """(modo, host visible). Nunca devuelve usuario, contraseña, query ni ruta completa."""
    if url.startswith("file:"):
        name = Path(url[len("file:") :].split("?", 1)[0]).name
        return "local", name or "local"
    return "remote", urlsplit(url).hostname or ""


def _schema_version(db: Database) -> int | None:
    try:
        row = db.fetch_one("SELECT MAX(version) AS v FROM schema_migrations")
    except DatabaseError:
        return None
    return int(row["v"]) if row and row["v"] is not None else None


def last_backup_at(backup_dir: Path) -> str | None:
    if not backup_dir.is_dir():
        return None
    stamps = sorted(m.group(1) for p in backup_dir.iterdir() if (m := _BACKUP_DIR.match(p.name)))
    if not stamps:
        return None
    return (
        datetime.strptime(stamps[-1], "%Y%m%dT%H%M%SZ")
        .replace(tzinfo=UTC)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def status(vault: Vault, settings: Settings) -> DbStatus:
    url = vault.get_secret("db.url") or ""
    mode, host = describe(url) if url else ("local", "")
    db = try_get_db()
    connected = False
    version: int | None = None
    if db is not None:
        try:
            db.fetch_one("SELECT 1 AS ok")
            connected = True
            version = _schema_version(db)
        except DatabaseError:
            connected = False
    return DbStatus(
        mode=mode,
        host=host,
        connected=connected,
        schema_version=version,
        has_token=vault.has("db.auth_token"),
        last_backup_at=last_backup_at(Path(settings.backup_dir)),
    )


def probe_connection(url: str, token: str | None, settings: Settings) -> DbTestResult:
    """Prueba la conexión (máx. 5 s) SIN cambiar nada: no migra, no guarda, no crea archivos."""
    setup_service.validate_url(url)
    mode, host = describe(url)
    if url.startswith("file:") and not Path(url[len("file:") :].split("?", 1)[0]).exists():
        return DbTestResult(ok=True, mode=mode, host=host, schema_version=None, will_create=True)

    def _probe() -> int | None:
        db = connect_database(url, token or None, settings.db_driver)
        try:
            db.fetch_one("SELECT COUNT(*) AS n FROM sqlite_master")  # lee el archivo de verdad
            return _schema_version(db)
        finally:
            db.close()

    pool = ThreadPoolExecutor(max_workers=1)
    try:
        version = pool.submit(_probe).result(timeout=setup_service.CONNECT_TIMEOUT)
    except FutureTimeout:
        raise unprocessable("Tiempo de espera agotado al conectar con la base de datos") from None
    except (DatabaseError, ValueError, OSError):
        raise unprocessable(
            "No se pudo conectar con la base de datos (revisa la URL y el token)"
        ) from None
    finally:
        pool.shutdown(wait=False)
    return DbTestResult(ok=True, mode=mode, host=host, schema_version=version, will_create=False)


def change_database(
    url: str,
    token: str | None,
    *,
    vault: Vault,
    settings: Settings,
    bus: EventBus | None,
    gate: SetupGate | None,
    user_id: str | None = None,
) -> DbStatus:
    """Prueba, migra, guarda en la bóveda y cambia la BD en caliente. 403 si no está permitido."""
    if not settings.admin_allow_db_change:
        raise AppError(
            "FORBIDDEN", "El cambio de base de datos está desactivado (ADMIN_ALLOW_DB_CHANGE)"
        )
    setup_service.validate_url(url)
    with _change_lock:
        old_url = vault.get_secret("db.url")
        old_token = vault.get_secret("db.auth_token")
        new_token = token or None
        if new_token is None and old_url is not None and old_url == url:
            new_token = old_token  # misma URL exacta: se conserva el token guardado
        new_db = setup_service.connect_and_migrate(url, new_token, settings.db_driver)
        try:
            vault.set_secret("db.url", url, updated_by="admin")
            if new_token:
                vault.set_secret("db.auth_token", new_token, updated_by="admin")
            else:
                vault.delete_secret("db.auth_token")
        except Exception:
            new_db.close()
            _restore_vault(vault, old_url, old_token)
            raise
        mode, host = describe(url)
        try:
            audit.record(
                new_db,
                "admin.db_changed",
                target_type="database",
                user_id=user_id,
                meta={"mode": mode, "host": host},
            )
        except DatabaseError:
            pass  # la auditoría no debe impedir un cambio ya validado
        swap_db(new_db)  # el cliente anterior se cierra a los 5 s
        if gate is not None and not setup_service.has_admin(new_db):
            gate.issue()  # BD nueva sin ADMIN: el asistente de setup vuelve a abrirse
        if bus is not None:
            bus.emit("system.db_changed", {"mode": mode, "host": host, "at": now_iso()})
    return status(vault, settings)


def _restore_vault(vault: Vault, url: str | None, token: str | None) -> None:
    try:
        if url is not None:
            vault.set_secret("db.url", url, updated_by="admin")
        if token is not None:
            vault.set_secret("db.auth_token", token, updated_by="admin")
    except Exception:  # noqa: S110 - mejor esfuerzo: el error original es el que se propaga
        pass


def manual_backup(db: Database, settings: Settings, user_id: str | None = None) -> BackupResult:
    """Backup JSON por tabla en `backups/<ts>/` con permisos restringidos al propietario."""
    from app.db.wipe import backup_tables

    rows = db.fetch_all("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")
    tables = tuple(
        str(r["name"])
        for r in rows
        if not str(r["name"]).startswith(("sqlite_", "_", "libsql_"))
        and r["name"] not in _SKIP_TABLES
    )
    root = Path(settings.backup_dir)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = root / stamp
    n = 1
    while target.exists():
        target = root / f"{stamp}-{n}"
        n += 1
    try:
        counts = backup_tables(db, tables, target)
    except OSError:
        raise AppError("INTERNAL", "No se pudo crear el backup con permisos restringidos") from None
    audit.record(
        db,
        "admin.backup_created",
        target_type="database",
        user_id=user_id,
        meta={"folder": target.name, "tables": len(counts), "rows": sum(counts.values())},
    )
    return BackupResult(
        folder=f"{root.name}/{target.name}",
        tables=counts,
        created_at=now_iso(),
    )
