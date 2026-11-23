"""Utilidades pequeñas compartidas (fechas ISO y ids)."""

import uuid
from datetime import UTC, datetime


def now_iso() -> str:
    """Fecha/hora UTC en ISO-8601 con milisegundos y sufijo Z (formato uniforme, PLAN §3)."""
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def new_id() -> str:
    return str(uuid.uuid4())
