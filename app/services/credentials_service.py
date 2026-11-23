"""Conexiones API de los agentes (PLAN §16.5–16.6).

- La clave se cifra con AES-256-GCM (HKDF `agent-credentials`) y AAD `agent_id|provider|id`:
  un texto cifrado copiado a otra fila no se puede descifrar.
- La API NUNCA devuelve la clave, ni siquiera al ADMIN: solo `last4`.
- Cada operación queda en la auditoría SIN el valor.
- Un agente puede tener varias conexiones activas (CEO, 2026-11-23); la etiqueta no se repite
  entre las activas del mismo agente.
- Pendiente de S09: las rutas exigirán ADMIN + MFA reciente; `created_by` será el usuario.
"""

from app.db.database import Database, IntegrityError
from app.domain.schemas import AgentCredential, CredentialCreate, CredentialRotate
from app.errors import AppError, conflict, not_found, validation_error
from app.repositories import agents_repo
from app.repositories import credentials_repo as repo
from app.security import audit
from app.security.crypto import SecretBox
from app.util import new_id, now_iso

ACTOR = "human"  # hasta S09 (sesiones) no hay usuario identificado


def _aad(agent_id: str, provider: str, cred_id: str) -> str:
    return f"{agent_id}|{provider}|{cred_id}"


def _clean_secret(secret: str) -> str:
    value = secret.strip()
    if len(value) < 8:
        raise validation_error("La clave es demasiado corta")
    if any(c.isspace() or ord(c) < 32 for c in value):
        raise validation_error("La clave no puede contener espacios ni saltos de línea")
    return value


def box_from_key(master_key: str | None) -> SecretBox:
    if not master_key:
        raise AppError(
            "ENCRYPTION_UNAVAILABLE",
            "Falta APP_MASTER_KEY en el servidor: ejecuta python scripts/setup_env.py",
        )
    return SecretBox.from_base64(master_key)


def _active_agent_or_error(db: Database, agent_id: str) -> None:
    agent = agents_repo.get_agent(db, agent_id)
    if agent is None:
        raise not_found("Agente no encontrado")
    if agent.archived_at is not None:
        raise conflict("El agente está archivado")


def _credential_of_agent(db: Database, agent_id: str, cred_id: str) -> AgentCredential:
    cred = repo.get(db, cred_id)
    if cred is None or cred.agent_id != agent_id:
        raise not_found("Conexión no encontrada")
    return cred


def list_credentials(db: Database, agent_id: str) -> list[AgentCredential]:
    if agents_repo.get_agent(db, agent_id) is None:
        raise not_found("Agente no encontrado")
    return repo.list_for_agent(db, agent_id)


def list_all_active(db: Database) -> list[AgentCredential]:
    return repo.list_active(db)


def add_credential(
    db: Database, box: SecretBox, agent_id: str, body: CredentialCreate
) -> AgentCredential:
    _active_agent_or_error(db, agent_id)
    secret = _clean_secret(body.secret)
    label = body.label.strip()
    if not label:
        raise validation_error("La etiqueta no puede estar vacía")
    if repo.find_active_by_label(db, agent_id, label) is not None:
        raise conflict(f"Este agente ya tiene una conexión activa llamada «{label}»")
    cred_id = new_id()
    sealed = box.encrypt_text("agent-credentials", secret, _aad(agent_id, body.provider, cred_id))
    now = now_iso()
    try:
        with db.transaction() as tx:
            repo.insert(
                tx,
                cred_id=cred_id,
                agent_id=agent_id,
                provider=body.provider,
                label=label,
                sealed=sealed,
                last4=secret[-4:],
                created_by=ACTOR,
                now=now,
            )
            audit.record(
                tx,
                "agent_credential.created",
                target_type="agent_credential",
                target_id=cred_id,
                meta={"agentId": agent_id, "provider": body.provider, "label": label},
            )
    except IntegrityError:
        raise conflict(f"Este agente ya tiene una conexión activa llamada «{label}»") from None
    created = repo.get(db, cred_id)
    if created is None:  # pragma: no cover - recién insertada en la misma transacción
        raise not_found("Conexión no encontrada")
    return created


def rotate_credential(
    db: Database, box: SecretBox, agent_id: str, cred_id: str, body: CredentialRotate
) -> AgentCredential:
    _active_agent_or_error(db, agent_id)
    cred = _credential_of_agent(db, agent_id, cred_id)
    if cred.revoked_at is not None:
        raise conflict("La conexión está revocada: crea una nueva")
    secret = _clean_secret(body.secret)
    sealed = box.encrypt_text("agent-credentials", secret, _aad(agent_id, cred.provider, cred_id))
    now = now_iso()
    with db.transaction() as tx:
        repo.replace_secret(tx, cred_id, sealed, secret[-4:], now)
        audit.record(
            tx,
            "agent_credential.rotated",
            target_type="agent_credential",
            target_id=cred_id,
            meta={"agentId": agent_id, "provider": cred.provider, "label": cred.label},
        )
    rotated = repo.get(db, cred_id)
    if rotated is None:  # pragma: no cover
        raise not_found("Conexión no encontrada")
    return rotated


def revoke_credential(db: Database, agent_id: str, cred_id: str) -> None:
    """Revoca (borrado lógico, idempotente). El texto cifrado se conserva para auditoría."""
    cred = _credential_of_agent(db, agent_id, cred_id)
    if cred.revoked_at is not None:
        return
    with db.transaction() as tx:
        repo.revoke(tx, cred_id, now_iso())
        audit.record(
            tx,
            "agent_credential.revoked",
            target_type="agent_credential",
            target_id=cred_id,
            meta={"agentId": agent_id, "provider": cred.provider, "label": cred.label},
        )


def reveal_for_server(db: Database, box: SecretBox, cred_id: str) -> str:
    """Descifra EN MEMORIA para el orquestador (Fase 2). Nunca se expone por HTTP ni se registra."""
    cred = repo.get(db, cred_id)
    sealed = repo.get_sealed(db, cred_id)
    if cred is None or sealed is None or cred.revoked_at is not None:
        raise not_found("Conexión no encontrada")
    return box.decrypt_text(
        "agent-credentials", sealed, _aad(cred.agent_id, cred.provider, cred.id)
    )
