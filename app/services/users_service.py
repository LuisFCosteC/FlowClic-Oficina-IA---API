"""Usuarios (A07b). Pendiente de S09: solo ADMIN (+ MFA reciente para crear o cambiar rol).

Nunca se devuelve `password_hash` ni `mfa_secret_enc`; la contraseña inicial exige ≥12 caracteres.
"""

from typing import Any

from app.db.database import Database, IntegrityError, Row
from app.domain.admin_schemas import AdminUser, UserCreate, UserUpdate
from app.errors import AppError, conflict, not_found, validation_error
from app.security import audit
from app.security.password import PasswordPolicyError, hash_password
from app.services.setup_service import EMAIL_RE
from app.util import new_id, now_iso

_COLUMNS = (
    "id, email, display_name, role, mfa_enabled, must_change_password, last_login_at,"
    " disabled_at, created_at, updated_at"
)


def _user(r: Row) -> AdminUser:
    return AdminUser.model_validate(
        {
            "id": r["id"],
            "email": r["email"],
            "display_name": r["display_name"],
            "role": r["role"],
            "mfa_enabled": bool(r["mfa_enabled"]),
            "must_change_password": bool(r["must_change_password"]),
            "last_login_at": r["last_login_at"],
            "disabled_at": r["disabled_at"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }
    )


def list_users(db: Database) -> list[AdminUser]:
    rows = db.fetch_all(f"SELECT {_COLUMNS} FROM users ORDER BY created_at, id")  # noqa: S608
    return [_user(r) for r in rows]


def get_or_404(db: Database, user_id: str) -> AdminUser:
    row = db.fetch_one(f"SELECT {_COLUMNS} FROM users WHERE id = ?", (user_id,))  # noqa: S608
    if row is None:
        raise not_found("Usuario no encontrado")
    return _user(row)


def create_user(db: Database, body: UserCreate, actor_id: str | None = None) -> AdminUser:
    email = body.email.strip().lower()
    if len(email) > 254 or not EMAIL_RE.match(email):
        raise validation_error(
            "email: formato inválido", [{"path": "email", "message": "inválido"}]
        )
    name = body.display_name.strip()
    if not name:
        raise validation_error("displayName: no puede estar vacío")
    try:
        password_hash = hash_password(body.password)
    except PasswordPolicyError as exc:
        raise validation_error(
            f"password: {exc}", [{"path": "password", "message": str(exc)}]
        ) from None
    user_id = new_id()
    now = now_iso()
    try:
        with db.transaction() as tx:
            tx.execute(
                "INSERT INTO users (id, email, display_name, password_hash, role, mfa_enabled,"
                " must_change_password, password_changed_at, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, 0, 1, ?, ?, ?)",
                (user_id, email, name, password_hash, body.role, now, now, now),
            )
            audit.record(
                tx,
                "user.created",
                target_type="user",
                target_id=user_id,
                user_id=actor_id,
                meta={"email": email, "role": body.role},
            )
    except IntegrityError:
        raise conflict("Ya existe un usuario con ese email") from None
    return get_or_404(db, user_id)


def _active_admins(db: Database) -> int:
    row = db.fetch_one(
        "SELECT COUNT(*) AS n FROM users WHERE role = 'ADMIN' AND disabled_at IS NULL"
    )
    return int(row["n"]) if row else 0


def update_user(
    db: Database, user_id: str, patch: UserUpdate, actor_id: str | None = None
) -> AdminUser:
    current = get_or_404(db, user_id)
    changes = patch.model_dump(exclude_unset=True)
    if not changes:
        return current
    for field, value in changes.items():
        if value is None:
            raise validation_error(f"{field} no puede ser null")
    name = changes.get("display_name")
    if name is not None and not name.strip():
        raise validation_error("displayName: no puede estar vacío")

    new_role = changes.get("role", current.role)
    new_disabled = changes.get("disabled", current.disabled_at is not None)
    disabling = new_disabled and current.disabled_at is None
    was_active_admin = current.role == "ADMIN" and current.disabled_at is None
    still_active_admin = new_role == "ADMIN" and not new_disabled
    now = now_iso()
    sets: list[str] = ["updated_at = ?"]
    params: list[Any] = [now]
    if name is not None:
        sets.append("display_name = ?")
        params.append(name.strip())
    if "role" in changes:
        sets.append("role = ?")
        params.append(new_role)
    if "disabled" in changes:
        sets.append("disabled_at = ?")
        params.append(now if changes["disabled"] else None)

    with db.transaction() as tx:
        # La comprobación va dentro de la transacción: dos PATCH a la vez no pueden dejar el
        # sistema sin ADMIN activo.
        if was_active_admin and not still_active_admin and _active_admins(tx) <= 1:
            raise AppError(
                "CONFLICT",
                "No se puede desactivar ni degradar al último ADMIN activo: crea o promueve "
                "otro ADMIN antes",
            )
        tx.execute(f"UPDATE users SET {', '.join(sets)} WHERE id = ?", (*params, user_id))  # noqa: S608
        if disabling:  # un usuario desactivado no conserva sesiones abiertas
            tx.execute(
                "UPDATE sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
                (now, user_id),
            )
        audit.record(
            tx,
            "user.updated",
            target_type="user",
            target_id=user_id,
            user_id=actor_id,
            meta={"changedFields": sorted(changes)},
        )
    return get_or_404(db, user_id)


def revoke_sessions(db: Database, user_id: str, actor_id: str | None = None) -> None:
    get_or_404(db, user_id)
    with db.transaction() as tx:
        tx.execute(
            "UPDATE sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
            (now_iso(), user_id),
        )
        audit.record(
            tx, "user.sessions_revoked", target_type="user", target_id=user_id, user_id=actor_id
        )
