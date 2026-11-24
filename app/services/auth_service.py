"""Login, sesiones y cambio de contraseña (S06).

- Contraseñas con scrypt (`app/security/password.py`); la sesión es un token aleatorio de 256 bits
  en una cookie HttpOnly. En la BD solo se guarda su SHA-256 (un volcado no permite entrar).
- Tras 5 fallos seguidos la cuenta se bloquea 15 minutos. Los mensajes de error son genéricos
  (no revelan si el correo existe) y nada de esto registra contraseñas ni tokens.
- Sesión: caduca por inactividad (`session_idle_minutes`) y por antigüedad (`session_max_hours`).
"""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache

from app.config import Settings
from app.db.database import Database, Row
from app.domain.schemas import CamelModel
from app.errors import AppError, validation_error
from app.security import audit
from app.security.password import PasswordPolicyError, hash_password, verify_password
from app.services import quota_time
from app.util import new_id

COOKIE_NAME = "flowclic_session"
MAX_FAILED_ATTEMPTS = 5
LOCK_MINUTES = 15
TOUCH_SECONDS = 60  # no se escribe `last_seen_at` en cada petición


class AuthUser(CamelModel):
    id: str
    email: str
    display_name: str
    role: str
    must_change_password: bool
    mfa_enabled: bool


@dataclass(frozen=True)
class Principal:
    session_id: str
    user: AuthUser


def _now() -> datetime:
    return datetime.now(UTC)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@lru_cache
def _dummy_hash() -> str:
    # Para gastar el mismo tiempo cuando el correo no existe (no revela qué correos hay).
    return hash_password("contraseña-ficticia-" + secrets.token_hex(4))


def _user_from_row(r: Row) -> AuthUser:
    return AuthUser(
        id=str(r["id"]),
        email=str(r["email"]),
        display_name=str(r["display_name"]),
        role=str(r["role"]),
        must_change_password=bool(r["must_change_password"]),
        mfa_enabled=bool(r["mfa_enabled"]),
    )


def _bad_credentials() -> AppError:
    return AppError("UNAUTHENTICATED", "Correo o contraseña incorrectos")


def login(
    db: Database,
    settings: Settings,
    email: str,
    password: str,
    *,
    ip: str | None,
    user_agent: str | None,
) -> tuple[AuthUser, str]:
    """Devuelve (usuario, token). El token solo sale aquí (cookie); nunca se guarda en claro."""
    clean = email.strip().lower()
    row = db.fetch_one("SELECT * FROM users WHERE email = ?", (clean,))
    now = _now()
    if row is None:
        verify_password(password, _dummy_hash())
        audit.record(db, "auth.login_failed", ip=ip, meta={"reason": "unknown_user"})
        raise _bad_credentials()

    locked_until = row["locked_until"]
    if locked_until and quota_time.parse_iso(str(locked_until)) > now:
        audit.record(db, "auth.login_blocked", target_type="user", target_id=str(row["id"]), ip=ip)
        raise AppError(
            "TOO_MANY_REQUESTS",
            "Cuenta bloqueada temporalmente por demasiados intentos: espera unos minutos",
        )
    ok = verify_password(password, str(row["password_hash"]))
    if not ok or row["disabled_at"]:
        attempts = int(row["failed_attempts"]) + 1
        lock = (
            quota_time.iso(now + timedelta(minutes=LOCK_MINUTES))
            if attempts >= MAX_FAILED_ATTEMPTS
            else None
        )
        with db.transaction() as tx:
            tx.execute(
                "UPDATE users SET failed_attempts = ?, locked_until = ? WHERE id = ?",
                (0 if lock else attempts, lock, str(row["id"])),
            )
            audit.record(
                tx,
                "auth.login_failed",
                target_type="user",
                target_id=str(row["id"]),
                ip=ip,
                meta={"attempts": attempts, "locked": lock is not None},
            )
        raise _bad_credentials()

    token = secrets.token_urlsafe(32)
    now_s = quota_time.iso(now)
    expires = quota_time.iso(now + timedelta(hours=settings.session_max_hours))
    with db.transaction() as tx:
        tx.execute(
            "UPDATE users SET failed_attempts = 0, locked_until = NULL, last_login_at = ?"
            " WHERE id = ?",
            (now_s, str(row["id"])),
        )
        tx.execute(
            "INSERT INTO sessions (id, user_id, token_hash, ip, user_agent, created_at,"
            " last_seen_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                new_id(),
                str(row["id"]),
                _token_hash(token),
                ip,
                (user_agent or "")[:200],
                now_s,
                now_s,
                expires,
            ),
        )
        audit.record(tx, "auth.login", target_type="user", target_id=str(row["id"]), ip=ip)
    return _user_from_row(row), token


def principal_for_token(db: Database, settings: Settings, token: str | None) -> Principal | None:
    """Sesión válida (no revocada, no caducada ni inactiva) y usuario activo; si no, None."""
    if not token:
        return None
    row = db.fetch_one(
        "SELECT s.id AS sid, s.last_seen_at, s.expires_at, s.revoked_at, u.* FROM sessions s"
        " JOIN users u ON u.id = s.user_id WHERE s.token_hash = ?",
        (_token_hash(token),),
    )
    if row is None or row["revoked_at"] or row["disabled_at"]:
        return None
    now = _now()
    if quota_time.parse_iso(str(row["expires_at"])) <= now:
        return None
    idle = timedelta(minutes=settings.session_idle_minutes)
    last_seen = quota_time.parse_iso(str(row["last_seen_at"]))
    if now - last_seen > idle:
        return None
    if (now - last_seen).total_seconds() > TOUCH_SECONDS:
        db.execute(
            "UPDATE sessions SET last_seen_at = ? WHERE id = ?",
            (quota_time.iso(now), str(row["sid"])),
        )
    return Principal(session_id=str(row["sid"]), user=_user_from_row(row))


def logout(db: Database, session_id: str) -> None:
    db.execute(
        "UPDATE sessions SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
        (quota_time.iso(_now()), session_id),
    )


def change_password(
    db: Database, principal: Principal, current_password: str, new_password: str
) -> AuthUser:
    row = db.fetch_one("SELECT * FROM users WHERE id = ?", (principal.user.id,))
    if row is None or not verify_password(current_password, str(row["password_hash"])):
        audit.record(
            db, "auth.password_change_failed", target_type="user", target_id=principal.user.id
        )
        raise validation_error(
            "currentPassword: la contraseña actual no es correcta",
            [{"path": "currentPassword", "message": "incorrecta"}],
        )
    if current_password == new_password:
        raise validation_error(
            "newPassword: debe ser distinta de la actual",
            [{"path": "newPassword", "message": "igual a la actual"}],
        )
    try:
        new_hash = hash_password(new_password)
    except PasswordPolicyError as exc:
        raise validation_error(
            f"newPassword: {exc}", [{"path": "newPassword", "message": str(exc)}]
        ) from None
    now_s = quota_time.iso(_now())
    with db.transaction() as tx:
        tx.execute(
            "UPDATE users SET password_hash = ?, password_changed_at = ?, must_change_password = 0,"
            " failed_attempts = 0, locked_until = NULL, updated_at = ? WHERE id = ?",
            (new_hash, now_s, now_s, principal.user.id),
        )
        tx.execute(  # el resto de sesiones del usuario deja de valer
            "UPDATE sessions SET revoked_at = ? WHERE user_id = ? AND id <> ?"
            " AND revoked_at IS NULL",
            (now_s, principal.user.id, principal.session_id),
        )
        audit.record(tx, "auth.password_changed", target_type="user", target_id=principal.user.id)
    refreshed = db.fetch_one("SELECT * FROM users WHERE id = ?", (principal.user.id,))
    assert refreshed is not None  # noqa: S101 - acaba de actualizarse
    return _user_from_row(refreshed)
