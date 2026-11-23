"""Runner de migraciones: aplica `migrations/NNN_nombre.sql` pendientes (una transacción c/u).

Uso: `python -m app.db.migrate`. Una migración aplicada nunca se edita; se añade otra nueva.
"""

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from app.db.database import Database, DatabaseError
from app.db.sqlsplit import split_statements
from app.util import now_iso

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent.parent / "migrations"
_FILE_RE = re.compile(r"^(\d+)_.+\.sql$")


class MigrationError(Exception):
    pass


@dataclass
class MigrationResult:
    applied: list[str] = field(default_factory=list)
    skipped: int = 0


def migrate(db: Database, directory: Path = MIGRATIONS_DIR) -> MigrationResult:
    """Aplica las migraciones pendientes en orden; si una falla, rollback y aborta."""
    db.execute(
        """CREATE TABLE IF NOT EXISTS schema_migrations (
             version    INTEGER PRIMARY KEY,
             name       TEXT NOT NULL,
             applied_at TEXT NOT NULL
           )"""
    )
    done = {int(r["version"]) for r in db.fetch_all("SELECT version FROM schema_migrations")}
    files = sorted(
        (int(m.group(1)), p) for p in directory.iterdir() if (m := _FILE_RE.match(p.name))
    )

    result = MigrationResult()
    for version, path in files:
        if version in done:
            result.skipped += 1
            continue
        statements = split_statements(path.read_text(encoding="utf-8"))
        try:
            with db.transaction() as tx:
                for stmt in statements:
                    tx.execute(stmt)
                tx.execute(
                    "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                    (version, path.name, now_iso()),
                )
        except DatabaseError as exc:
            raise MigrationError(f"Migración {path.name} falló: {exc}") from exc
        result.applied.append(path.name)
    return result


def schema_version(db: Database) -> int:
    """Última versión aplicada (0 si no hay ninguna)."""
    try:
        row = db.fetch_one("SELECT MAX(version) AS v FROM schema_migrations")
    except DatabaseError:
        return 0
    return int(row["v"]) if row and row["v"] is not None else 0


def main() -> int:
    from app.config import get_settings
    from app.db.bootstrap import open_configured_database
    from app.security.vault import VaultError

    try:
        opened = open_configured_database(get_settings())
    except VaultError as exc:
        print(exc, file=sys.stderr)
        return 1
    if opened is None:
        print(
            "No hay conexión de BD configurada. Arranca la API (modo SETUP) para configurarla.",
            file=sys.stderr,
        )
        return 1
    db, vault = opened
    try:
        result = migrate(db)
    except MigrationError as exc:
        print(exc, file=sys.stderr)
        return 1
    finally:
        db.close()
        vault.close()
    if result.applied:
        for name in result.applied:
            print(f"Aplicada: {name}")
    else:
        print(f"Sin migraciones pendientes ({result.skipped} ya aplicadas).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
