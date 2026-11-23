"""Repositorio de credenciales API de agentes (tabla `agent_credentials`, PLAN §16.2).

Las funciones de lectura devuelven metadatos (`AgentCredential`): nunca el texto cifrado.
Solo `get_sealed` lo devuelve, para uso interno del servidor (Fase 2: `SecretsProvider`).
"""

from app.db.database import Database, Row
from app.domain.schemas import AgentCredential
from app.security.crypto import Sealed

_COLUMNS = (
    "id, agent_id, provider, label, last4, key_version, created_by, created_at, rotated_at,"
    " revoked_at"
)


def _to_model(r: Row) -> AgentCredential:
    return AgentCredential.model_validate(
        {
            "id": r["id"],
            "agent_id": r["agent_id"],
            "provider": r["provider"],
            "label": r["label"],
            "last4": r["last4"],
            "key_version": r["key_version"],
            "created_by": r["created_by"],
            "created_at": r["created_at"],
            "rotated_at": r["rotated_at"],
            "revoked_at": r["revoked_at"],
        }
    )


def list_for_agent(
    db: Database, agent_id: str, include_revoked: bool = False
) -> list[AgentCredential]:
    where = "agent_id = ?" + ("" if include_revoked else " AND revoked_at IS NULL")
    rows = db.fetch_all(
        f"SELECT {_COLUMNS} FROM agent_credentials WHERE {where} ORDER BY created_at",  # noqa: S608
        (agent_id,),
    )
    return [_to_model(r) for r in rows]


def list_active(db: Database) -> list[AgentCredential]:
    rows = db.fetch_all(
        f"SELECT {_COLUMNS} FROM agent_credentials WHERE revoked_at IS NULL"  # noqa: S608
        " ORDER BY agent_id, created_at"
    )
    return [_to_model(r) for r in rows]


def get(db: Database, cred_id: str) -> AgentCredential | None:
    row = db.fetch_one(
        f"SELECT {_COLUMNS} FROM agent_credentials WHERE id = ?",  # noqa: S608
        (cred_id,),
    )
    return _to_model(row) if row else None


def find_active_by_label(db: Database, agent_id: str, label: str) -> AgentCredential | None:
    row = db.fetch_one(
        f"SELECT {_COLUMNS} FROM agent_credentials"  # noqa: S608
        " WHERE agent_id = ? AND label = ? AND revoked_at IS NULL",
        (agent_id, label),
    )
    return _to_model(row) if row else None


def insert(
    db: Database,
    *,
    cred_id: str,
    agent_id: str,
    provider: str,
    label: str,
    sealed: Sealed,
    last4: str,
    created_by: str,
    now: str,
) -> None:
    db.execute(
        "INSERT INTO agent_credentials (id, agent_id, provider, label, ciphertext, nonce,"
        " key_version, last4, created_by, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            cred_id,
            agent_id,
            provider,
            label,
            sealed.ciphertext,
            sealed.nonce,
            sealed.key_version,
            last4,
            created_by,
            now,
        ),
    )


def replace_secret(db: Database, cred_id: str, sealed: Sealed, last4: str, now: str) -> None:
    db.execute(
        "UPDATE agent_credentials SET ciphertext = ?, nonce = ?, key_version = ?, last4 = ?,"
        " rotated_at = ? WHERE id = ?",
        (sealed.ciphertext, sealed.nonce, sealed.key_version, last4, now, cred_id),
    )


def revoke(db: Database, cred_id: str, now: str) -> None:
    db.execute(
        "UPDATE agent_credentials SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
        (now, cred_id),
    )


def get_sealed(db: Database, cred_id: str) -> Sealed | None:
    """Solo para el servidor (descifrado en memoria en la Fase 2). Nunca se expone por HTTP."""
    row = db.fetch_one(
        "SELECT ciphertext, nonce, key_version FROM agent_credentials WHERE id = ?", (cred_id,)
    )
    if row is None:
        return None
    return Sealed(bytes(row["ciphertext"]), bytes(row["nonce"]), int(row["key_version"]))


def active_providers(db: Database) -> set[str]:
    """Proveedores con al menos una conexión activa en cualquier agente."""
    rows = db.fetch_all("SELECT DISTINCT provider FROM agent_credentials WHERE revoked_at IS NULL")
    return {str(r["provider"]) for r in rows}
