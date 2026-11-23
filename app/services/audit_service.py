"""Lectura de la auditoría (A07a). Solo lectura; la salida se redacta SIEMPRE antes de enviarse.

Defensa en profundidad: `audit.record` ya descarta claves sospechosas al escribir, pero aquí se
vuelve a filtrar al leer (por si una fila vieja o un cambio futuro dejó un secreto) y además se
enmascaran valores con forma de clave/token.
"""

import json
import re
from datetime import datetime
from typing import Any

from app.db.database import Database
from app.domain.admin_schemas import AuditEntry
from app.errors import validation_error
from app.security.audit import FORBIDDEN_KEYS

REDACTED = "[redactado]"
_SECRET_VALUE = re.compile(
    r"(sk-[A-Za-z0-9_\-]{8,}"  # claves tipo OpenAI/Anthropic
    r"|AIza[0-9A-Za-z_\-]{20,}"  # Google
    r"|eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"  # JWT (también tokens de Turso)
    r"|(?:token|key|secret|password|authorization)\s*[=:]\s*\S+"
    r"|[?&](?:authToken|token|key)=[^&\s]+"
    r"|[A-Fa-f0-9]{40,}"  # hashes/tokens hexadecimales largos
    r"|[A-Za-z0-9+/_\-]{48,}={0,2})"  # cadenas largas en base64
)


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return _SECRET_VALUE.sub(REDACTED, value)
    if isinstance(value, dict):
        return redact_meta(value)
    if isinstance(value, list):
        return [_redact_value(v) for v in value]
    return value


def redact_meta(meta: dict[str, Any]) -> dict[str, Any]:
    return {
        k: _redact_value(v)
        for k, v in meta.items()
        if not any(f in k.lower() for f in FORBIDDEN_KEYS)
    }


def _iso(value: str | None, field: str) -> str | None:
    if value is None or value == "":
        return None
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise validation_error(f"{field}: fecha ISO-8601 no válida") from None
    return value


def list_entries(
    db: Database,
    *,
    limit: int = 200,
    action: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[AuditEntry]:
    where: list[str] = []
    params: list[Any] = []
    if action:
        where.append("action = ?")
        params.append(action)
    if (frm := _iso(date_from, "from")) is not None:
        where.append("created_at >= ?")
        params.append(frm)
    if (to := _iso(date_to, "to")) is not None:
        where.append("created_at <= ?")
        params.append(to)
    # Alias explícitos: en Turso la columna puede venir como "ACTION" con SELECT *.
    sql = (
        "SELECT id AS id, user_id AS user_id, action AS action, target_type AS target_type,"
        " target_id AS target_id, ip AS ip, meta AS meta, created_at AS created_at FROM audit_log"
    )
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
    params.append(limit)
    entries: list[AuditEntry] = []
    for r in db.fetch_all(sql, params):
        try:
            meta = json.loads(r["meta"])
        except (TypeError, ValueError):
            meta = {}
        entries.append(
            AuditEntry(
                id=r["id"],
                user_id=r["user_id"],
                action=r["action"],
                target_type=r["target_type"],
                target_id=r["target_id"],
                ip=r["ip"],
                meta=redact_meta(meta) if isinstance(meta, dict) else {},
                created_at=r["created_at"],
            )
        )
    return entries
