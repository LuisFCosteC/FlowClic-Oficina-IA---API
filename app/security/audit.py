"""Registro de auditoría (tabla `audit_log`). S10 añadirá el helper basado en la petición.

`meta` NUNCA debe llevar contraseñas, tokens, claves ni URLs con credenciales.
"""

import json
from typing import Any

from app.db.database import Database
from app.util import new_id, now_iso

_FORBIDDEN_KEYS = ("password", "token", "secret", "key", "authorization", "cookie", "ciphertext")


def _clean(meta: dict[str, Any]) -> dict[str, Any]:
    """Defensa en profundidad: descarta cualquier clave que parezca un secreto."""
    return {k: v for k, v in meta.items() if not any(f in k.lower() for f in _FORBIDDEN_KEYS)}


def record(
    db: Database,
    action: str,
    *,
    target_type: str | None = None,
    target_id: str | None = None,
    user_id: str | None = None,
    ip: str | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    db.execute(
        "INSERT INTO audit_log (id, user_id, action, target_type, target_id, ip, meta, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            new_id(),
            user_id,
            action,
            target_type,
            target_id,
            ip,
            json.dumps(_clean(meta or {}), ensure_ascii=False),
            now_iso(),
        ),
    )
