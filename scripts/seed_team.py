"""Siembra el equipo base (Sheldon, Leonard, Penny, Raj) en la BD configurada. Idempotente.

Uso: `python -m scripts.seed_team` (o `python scripts/seed_team.py` con PYTHONPATH=.).
Es una herramienta de operador, no un endpoint: el equipo real no se carga desde la API.
"""

import sys

from app.config import get_settings
from app.db.bootstrap import open_configured_database
from app.db.seed import seed_demo_agents
from app.security.vault import VaultError


def main() -> int:
    try:
        opened = open_configured_database(get_settings())
    except VaultError as exc:
        print(exc, file=sys.stderr)
        return 1
    if opened is None:
        print("No hay conexion de BD configurada (modo SETUP).", file=sys.stderr)
        return 1
    db, vault = opened
    try:
        created = seed_demo_agents(db)
        print(f"Equipo base: {created} creados, {4 - created} ya existian.")
    finally:
        db.close()
        vault.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
