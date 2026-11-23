"""Lógica del asistente de primer arranque (PLAN §16.3)."""

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from typing import Literal

from app.db.database import Database, DatabaseError, IntegrityError, connect_database
from app.db.migrate import MigrationError, migrate
from app.errors import AppError, conflict, unprocessable, validation_error
from app.security.password import PasswordPolicyError, hash_password
from app.util import new_id, now_iso

log = logging.getLogger("flowclic")

ALLOWED_SCHEMES = ("file:", "libsql://", "https://")
CONNECT_TIMEOUT = 5.0
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,189}\.[^@\s.]{2,}$")


def validate_url(url: str) -> None:
    if not url.startswith(ALLOWED_SCHEMES):
        raise validation_error("La URL debe empezar por file:, libsql:// o https://")


def connect_and_migrate(
    url: str,
    token: str | None,
    driver: Literal["libsql", "sqlite"] = "libsql",
    timeout: float = CONNECT_TIMEOUT,
) -> Database:
    """Prueba la conexión (máx. `timeout` s), migra el esquema y devuelve la conexión abierta.

    Si algo falla no queda nada abierto ni guardado. Los mensajes no incluyen la URL ni el token.
    """
    validate_url(url)
    generic = unprocessable("No se pudo conectar con la base de datos (revisa la URL y el token)")

    def _open() -> Database:
        db = connect_database(url, token, driver)
        try:
            db.fetch_one("SELECT 1 AS ok")
        except BaseException:
            db.close()
            raise
        return db

    pool = ThreadPoolExecutor(max_workers=1)
    try:
        db = pool.submit(_open).result(timeout=timeout)
    except FutureTimeout:
        raise unprocessable("Tiempo de espera agotado al conectar con la base de datos") from None
    except (DatabaseError, ValueError, OSError) as exc:
        log.warning("setup: fallo de conexión (%s)", type(exc).__name__)
        raise generic from None
    finally:
        pool.shutdown(wait=False)

    try:
        migrate(db)
    except (MigrationError, DatabaseError) as exc:
        db.close()
        log.warning("setup: fallo al migrar (%s)", type(exc).__name__)
        raise unprocessable("La conexión funciona, pero no se pudo preparar el esquema") from None
    return db


def has_admin(db: Database | None) -> bool:
    if db is None:
        return False
    try:
        row = db.fetch_one(
            "SELECT COUNT(*) AS n FROM users WHERE role = 'ADMIN' AND disabled_at IS NULL"
        )
    except DatabaseError:  # esquema aún sin migrar
        return False
    return bool(row and int(row["n"]) > 0)


def create_first_admin(db: Database, email: str, display_name: str, password: str) -> str:
    """Crea el primer ADMIN (debe activar MFA en su primer login). Devuelve su id."""
    email = email.strip().lower()
    if len(email) > 254 or not EMAIL_RE.match(email):
        raise validation_error("Email inválido", [{"path": "email", "message": "formato inválido"}])
    try:
        password_hash = hash_password(password)
    except PasswordPolicyError as exc:
        raise validation_error(str(exc), [{"path": "password", "message": str(exc)}]) from None
    user_id = new_id()
    now = now_iso()
    try:
        with db.transaction() as tx:
            # Inserción atómica: solo si todavía no existe ningún ADMIN (no hay carrera posible).
            tx.execute(
                "INSERT INTO users (id, email, display_name, password_hash, role, mfa_enabled,"
                " password_changed_at, created_at, updated_at)"
                " SELECT ?, ?, ?, ?, 'ADMIN', 0, ?, ?, ?"
                " WHERE NOT EXISTS (SELECT 1 FROM users WHERE role = 'ADMIN')",
                (user_id, email, display_name.strip(), password_hash, now, now, now),
            )
            changed = tx.fetch_one("SELECT changes() AS n")
            if not changed or int(changed["n"]) == 0:
                raise AppError("NOT_FOUND", "Ruta no encontrada")
    except IntegrityError:
        raise conflict("Ya existe un usuario con ese email") from None
    return user_id
