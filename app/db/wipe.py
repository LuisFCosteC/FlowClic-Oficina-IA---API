"""Vacía los datos de la BD configurada (también remota), conservando el esquema (J01).

Uso: `python -m app.db.wipe` (pide escribir BORRAR) o `python -m app.db.wipe --yes` (sin pregunta).

1. Antes de borrar guarda un backup JSON por tabla en `backups/<ts>/` (carpeta fuera de git).
2. Borra, en orden de claves foráneas, las filas de las tablas de datos.
3. NO toca el esquema, `schema_migrations` ni `audit_log`; añade la entrada `db.wiped` con el
   número de filas borradas por tabla.
"""

import base64
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.db.database import Database
from app.security import audit

# Orden de borrado: primero las tablas que apuntan a otras (claves foráneas).
WIPE_ORDER: tuple[str, ...] = (
    "agent_credentials",
    "agent_messages",
    "ticket_events",
    "approvals",
    "tickets",
    "project_memory",
    "agents",
)

CONFIRM_WORD = "BORRAR"


def _jsonable(value: Any) -> Any:
    if isinstance(value, bytes | bytearray | memoryview):
        return {"$base64": base64.b64encode(bytes(value)).decode("ascii")}
    return value


def _existing_tables(db: Database) -> set[str]:
    rows = db.fetch_all("SELECT name FROM sqlite_master WHERE type = 'table'")
    return {str(r["name"]) for r in rows}


def backup_tables(db: Database, tables: tuple[str, ...], directory: Path) -> dict[str, int]:
    """Escribe `<tabla>.json` por tabla. Devuelve las filas respaldadas por tabla."""
    from app.security.fileperms import restrict_to_owner

    directory.mkdir(parents=True, exist_ok=True)
    if not restrict_to_owner(directory):  # fallar en cerrado: sin permisos no hay backup ni borrado
        raise OSError("No se pudieron restringir los permisos de la carpeta de backup")
    present = _existing_tables(db)
    counts: dict[str, int] = {}
    for table in tables:
        if table not in present:
            continue
        rows = db.fetch_all(f"SELECT * FROM {table}")  # noqa: S608 - nombre de la lista fija
        path = directory / f"{table}.json"
        path.touch()
        if not restrict_to_owner(path):  # ANTES de escribir: el backup lleva textos cifrados
            raise OSError(f"No se pudieron restringir los permisos de {path.name}")
        path.write_text(
            json.dumps(
                [{k: _jsonable(v) for k, v in r.items()} for r in rows],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        counts[table] = len(rows)
    return counts


def wipe_data(db: Database, backup_dir: Path) -> dict[str, int]:
    """Backup + borrado + auditoría. Devuelve las filas borradas por tabla."""
    counts = backup_tables(db, WIPE_ORDER, backup_dir)
    with db.transaction() as tx:
        for table in WIPE_ORDER:
            if table in counts:
                tx.execute(f"DELETE FROM {table}")  # noqa: S608 - nombre de la lista fija
        audit.record(
            tx,
            "db.wiped",
            target_type="database",
            meta={"rows": counts, "total": sum(counts.values())},
        )
    return counts


def main(argv: list[str] | None = None) -> int:
    import argparse

    from app.config import get_settings
    from app.db.bootstrap import open_configured_database
    from app.security.vault import VaultError

    parser = argparse.ArgumentParser(description="Vacía los datos de la BD (conserva el esquema).")
    parser.add_argument("--yes", action="store_true", help="no pide confirmación (solo pruebas)")
    parser.add_argument(
        "--backup-dir", default="backups", help="carpeta de backups (por defecto backups/)"
    )
    args = parser.parse_args(argv)

    try:
        opened = open_configured_database(get_settings())
    except VaultError as exc:
        print(exc, file=sys.stderr)
        return 1
    if opened is None:
        print("No hay conexión de BD configurada (modo SETUP). No se hizo nada.", file=sys.stderr)
        return 1
    db, vault = opened
    try:
        if not args.yes:
            print("Esto BORRA todos los agentes, tickets, aprobaciones, memoria y conexiones API.")
            if input(f"Escribe {CONFIRM_WORD} para confirmar: ").strip() != CONFIRM_WORD:
                print("Cancelado. No se borró nada.")
                return 1
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        backup_dir = Path(args.backup_dir) / stamp
        counts = wipe_data(db, backup_dir)
    finally:
        db.close()
        vault.close()
    print(f"Backup en {backup_dir}")
    for table, n in counts.items():
        print(f"  {table}: {n} filas borradas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
