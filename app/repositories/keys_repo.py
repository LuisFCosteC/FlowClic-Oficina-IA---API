"""Repositorio de `provider_keys` y `key_usage` (KEY01).

Solo `get_sealed` devuelve el texto cifrado, para uso interno del KeyPool.
"""

from dataclasses import dataclass

from app.db.database import Database, Row
from app.security.crypto import Sealed

_META = (
    "id, provider, label, last4, position, status, daily_request_limit, daily_token_limit,"
    " created_at, rotated_at, revoked_at"
)


@dataclass(frozen=True)
class KeyRow:
    id: str
    provider: str
    label: str
    last4: str
    position: int
    status: str
    daily_request_limit: int | None
    daily_token_limit: int | None
    created_at: str
    rotated_at: str | None
    revoked_at: str | None


def _row(r: Row) -> KeyRow:
    return KeyRow(
        id=str(r["id"]),
        provider=str(r["provider"]),
        label=str(r["label"]),
        last4=str(r["last4"]),
        position=int(r["position"]),
        status=str(r["status"]),
        daily_request_limit=None
        if r["daily_request_limit"] is None
        else int(r["daily_request_limit"]),
        daily_token_limit=None if r["daily_token_limit"] is None else int(r["daily_token_limit"]),
        created_at=str(r["created_at"]),
        rotated_at=r["rotated_at"],
        revoked_at=r["revoked_at"],
    )


def list_all(db: Database) -> list[KeyRow]:
    rows = db.fetch_all(
        f"SELECT {_META} FROM provider_keys ORDER BY position, created_at, id"  # noqa: S608
    )
    return [_row(r) for r in rows]


def list_for_provider(db: Database, provider: str, status: str = "ACTIVE") -> list[KeyRow]:
    rows = db.fetch_all(
        f"SELECT {_META} FROM provider_keys WHERE provider = ? AND status = ?"  # noqa: S608
        " ORDER BY position, created_at, id",
        (provider, status),
    )
    return [_row(r) for r in rows]


def get(db: Database, key_id: str) -> KeyRow | None:
    row = db.fetch_one(f"SELECT {_META} FROM provider_keys WHERE id = ?", (key_id,))  # noqa: S608
    return _row(row) if row else None


def find_by_label(db: Database, provider: str, label: str) -> KeyRow | None:
    row = db.fetch_one(
        f"SELECT {_META} FROM provider_keys"  # noqa: S608
        " WHERE provider = ? AND label = ? AND status <> 'REVOKED'",
        (provider, label),
    )
    return _row(row) if row else None


def next_position(db: Database) -> int:
    row = db.fetch_one("SELECT COALESCE(MAX(position), -1) + 1 AS n FROM provider_keys")
    return int(row["n"]) if row else 0


def insert(
    db: Database,
    *,
    key_id: str,
    provider: str,
    label: str,
    sealed: Sealed,
    last4: str,
    position: int,
    now: str,
) -> None:
    db.execute(
        "INSERT INTO provider_keys (id, provider, label, ciphertext, nonce, key_version, last4,"
        " position, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            key_id,
            provider,
            label,
            sealed.ciphertext,
            sealed.nonce,
            sealed.key_version,
            last4,
            position,
            now,
        ),
    )


def replace_secret(db: Database, key_id: str, sealed: Sealed, last4: str, now: str) -> None:
    db.execute(
        "UPDATE provider_keys SET ciphertext = ?, nonce = ?, key_version = ?, last4 = ?,"
        " rotated_at = ? WHERE id = ?",
        (sealed.ciphertext, sealed.nonce, sealed.key_version, last4, now, key_id),
    )


def update_fields(
    db: Database,
    key_id: str,
    *,
    label: str,
    daily_request_limit: int | None,
    daily_token_limit: int | None,
) -> None:
    db.execute(
        "UPDATE provider_keys SET label = ?, daily_request_limit = ?, daily_token_limit = ?"
        " WHERE id = ?",
        (label, daily_request_limit, daily_token_limit, key_id),
    )


def set_status(db: Database, key_id: str, status: str, revoked_at: str | None) -> None:
    db.execute(
        "UPDATE provider_keys SET status = ?, revoked_at = ? WHERE id = ?",
        (status, revoked_at, key_id),
    )


def set_position(db: Database, key_id: str, position: int) -> None:
    db.execute("UPDATE provider_keys SET position = ? WHERE id = ?", (position, key_id))


def get_sealed(db: Database, key_id: str) -> Sealed | None:
    row = db.fetch_one(
        "SELECT ciphertext, nonce, key_version FROM provider_keys WHERE id = ?", (key_id,)
    )
    if row is None:
        return None
    return Sealed(bytes(row["ciphertext"]), bytes(row["nonce"]), int(row["key_version"]))


# ── Uso ──────────────────────────────────────────────────────────────────────────────────────
def usage_rows(db: Database, key_id: str) -> list[Row]:
    return db.fetch_all("SELECT * FROM key_usage WHERE key_id = ?", (key_id,))


def day_row(db: Database, key_id: str, model: str, day: str) -> Row | None:
    return db.fetch_one(
        "SELECT * FROM key_usage WHERE key_id = ? AND model = ? AND day = ?", (key_id, model, day)
    )


def ensure_day_row(db: Database, key_id: str, model: str, day: str) -> None:
    db.execute(
        "INSERT INTO key_usage (key_id, model, day) VALUES (?, ?, ?)"
        " ON CONFLICT(key_id, model, day) DO NOTHING",
        (key_id, model, day),
    )


def add_usage(
    db: Database,
    key_id: str,
    model: str,
    day: str,
    *,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    now: str,
) -> None:
    ensure_day_row(db, key_id, model, day)
    db.execute(
        "UPDATE key_usage SET requests = requests + 1, input_tokens = input_tokens + ?,"
        " output_tokens = output_tokens + ?, cost_usd = cost_usd + ?, last_used_at = ?"
        " WHERE key_id = ? AND model = ? AND day = ?",
        (input_tokens, output_tokens, cost_usd, now, key_id, model, day),
    )


def mark_exhausted(
    db: Database, key_id: str, model: str, day: str, until: str, error_code: str | None, now: str
) -> None:
    ensure_day_row(db, key_id, model, day)
    db.execute(
        "UPDATE key_usage SET exhausted_until = ?, last_error_code = ?, last_used_at = ?"
        " WHERE key_id = ? AND model = ? AND day = ?",
        (until, error_code, now, key_id, model, day),
    )


def set_error(db: Database, key_id: str, model: str, day: str, code: str, now: str) -> None:
    ensure_day_row(db, key_id, model, day)
    db.execute(
        "UPDATE key_usage SET last_error_code = ?, last_used_at = ?"
        " WHERE key_id = ? AND model = ? AND day = ?",
        (code, now, key_id, model, day),
    )


def clear_exhausted(db: Database, key_id: str) -> None:
    db.execute("UPDATE key_usage SET exhausted_until = NULL WHERE key_id = ?", (key_id,))


def is_model_exhausted(db: Database, key_id: str, model: str, now: str) -> bool:
    row = db.fetch_one(
        "SELECT COUNT(*) AS n FROM key_usage WHERE key_id = ? AND model = ?"
        " AND exhausted_until IS NOT NULL AND exhausted_until > ?",
        (key_id, model, now),
    )
    return bool(row and int(row["n"]) > 0)
