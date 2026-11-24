"""Crea (o restablece) un administrador con una contraseña TEMPORAL aleatoria.

Uso:  python -m app.db.create_admin [--email lcoste@flowclic.com] [--name "Luis Coste"] [--reset]

- La contraseña temporal se genera al azar, se muestra UNA vez en esta consola y no se guarda en
  ningún otro sitio; el usuario queda obligado a cambiarla en su primer acceso.
- Si el correo ya existe, no hace nada salvo que se pase `--reset` (nueva contraseña temporal,
  desbloqueo y cierre de todas sus sesiones).
"""

import argparse
import secrets
import sys

from app.config import get_settings
from app.db.bootstrap import open_configured_database
from app.db.database import Database
from app.domain.admin_schemas import UserCreate
from app.errors import AppError
from app.security import audit
from app.security.password import hash_password
from app.services import users_service
from app.util import now_iso

DEFAULT_EMAIL = "lcoste@flowclic.com"
DEFAULT_NAME = "Luis Coste"


def temporary_password() -> str:
    return secrets.token_urlsafe(12)  # 16 caracteres, cumple la política (≥ 12)


def create_or_reset_admin(db: Database, email: str, name: str, *, reset: bool) -> str | None:
    """Devuelve la contraseña temporal, o None si el usuario ya existe y no se pidió `--reset`."""
    clean = email.strip().lower()
    existing = db.fetch_one("SELECT id FROM users WHERE email = ?", (clean,))
    password = temporary_password()
    if existing is None:
        users_service.create_user(
            db,
            UserCreate(email=clean, display_name=name, role="ADMIN", password=password),
        )
        return password
    if not reset:
        return None
    now = now_iso()
    with db.transaction() as tx:
        tx.execute(
            "UPDATE users SET password_hash = ?, must_change_password = 1, failed_attempts = 0,"
            " locked_until = NULL, disabled_at = NULL, role = 'ADMIN', password_changed_at = ?,"
            " updated_at = ? WHERE id = ?",
            (hash_password(password), now, now, str(existing["id"])),
        )
        tx.execute(
            "UPDATE sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
            (now, str(existing["id"])),
        )
        audit.record(tx, "user.admin_reset", target_type="user", target_id=str(existing["id"]))
    return password


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Crea o restablece un administrador.")
    parser.add_argument("--email", default=DEFAULT_EMAIL)
    parser.add_argument("--name", default=DEFAULT_NAME)
    parser.add_argument("--reset", action="store_true", help="restablece si ya existe")
    args = parser.parse_args(argv)

    opened = open_configured_database(get_settings())
    if opened is None:
        print("No hay conexión de BD configurada (modo SETUP).", file=sys.stderr)
        return 1
    db, vault = opened
    try:
        try:
            password = create_or_reset_admin(db, args.email, args.name, reset=args.reset)
        except AppError as exc:
            print(exc.message, file=sys.stderr)
            return 1
    finally:
        db.close()
        vault.close()
    if password is None:
        print(f"{args.email} ya existe. Usa --reset para darle una contraseña temporal nueva.")
        return 1
    print(f"Administrador: {args.name} <{args.email}>")
    print(f"Contraseña temporal (se pedirá cambiarla al entrar): {password}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
