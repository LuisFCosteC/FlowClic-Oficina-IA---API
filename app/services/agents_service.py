"""Reglas de negocio de agentes (PLAN §19). Las rutas solo llaman a estas funciones."""

from typing import Any

from app.db.database import Database, IntegrityError
from app.domain.agent_policy import check_profile, generate_system_prompt
from app.domain.agent_templates import AgentTemplate
from app.domain.schemas import Agent, AgentAvatar, AgentCreate, AgentStatusBody, AgentUpdate
from app.errors import conflict, not_found, validation_error
from app.events.bus import EventBus
from app.repositories import agents_repo as repo
from app.services import settings_service
from app.services.projects_service import ensure_projects_exist
from app.util import new_id, now_iso

DEFAULT_AVATAR = AgentAvatar(color="#06B6D4")


def agent_payload(agent: Agent) -> dict[str, object]:
    """JSON (camelCase) listo para respuestas y eventos SSE."""
    return agent.model_dump(by_alias=True, mode="json")


def build_agent(data: AgentCreate, *, agent_id: str | None = None) -> Agent:
    """Construye un agente nuevo aplicando la política. NO escribe en la BD.

    El prompt y `is_cto` los fija siempre el servidor; el cliente no puede enviarlos.
    """
    check_profile(data.role_type, data.permissions, data.model, data.limits)
    now = now_iso()
    return Agent(
        id=agent_id or new_id(),
        name=data.name.strip(),
        character=(data.character or data.name).strip(),
        role=data.role.strip(),
        role_type=data.role_type,
        status="IDLE",
        avatar=data.avatar or DEFAULT_AVATAR,
        functions=data.functions,
        rules=data.rules,
        restrictions=data.restrictions,
        permissions=data.permissions,
        model=data.model,
        limits=data.limits,
        system_prompt=generate_system_prompt(
            name=data.name.strip(),
            role=data.role.strip(),
            role_type=data.role_type,
            functions=data.functions,
            rules=data.rules,
            restrictions=data.restrictions,
        ),
        is_cto=data.role_type == "CTO",
        current_task=None,
        project=data.project,
        reports_to=data.reports_to,
        consecutive_failures=0,
        created_at=now,
        updated_at=now,
        archived_at=None,
    )


def create_agent(
    db: Database,
    bus: EventBus | None,
    data: AgentCreate,
    *,
    agent_id: str | None = None,
) -> Agent:
    """Crea un agente (409 si el nombre ya lo usa uno activo) y emite `agent.created`."""
    agent = build_agent(data, agent_id=agent_id)
    ensure_projects_exist(db, agent.permissions)
    _check_single_cto(db, agent.role_type, None)
    _check_reports_to(db, agent.id, agent.reports_to)
    _check_max_agents(db)
    if repo.find_active_by_name(db, agent.name) is not None:
        raise conflict(f"Ya existe un agente activo llamado «{agent.name}»")
    try:
        repo.insert_agent(db, agent)
    except IntegrityError:
        raise conflict(f"Ya existe un agente activo llamado «{agent.name}»") from None
    if bus is not None:
        bus.emit("agent.created", agent_payload(agent))
    return agent


def _check_single_cto(db: Database, role_type: str, exclude_id: str | None) -> None:
    """409 si ya hay otro CTO activo (REQ01: solo puede haber 1)."""
    if role_type == "CTO" and repo.count_active_with_role(db, "CTO", exclude_id) > 0:
        raise conflict("Ya existe un agente activo con rol CTO: solo puede haber uno")


def _check_reports_to(db: Database, agent_id: str, reports_to: str | None) -> None:
    """RPT01: `reports_to` apunta a un agente activo y no forma ciclos (null = el CEO)."""
    if reports_to is None:
        return
    seen = {agent_id}
    current: str | None = reports_to
    first = True
    while current is not None:
        if current in seen:
            raise validation_error(
                "reportsTo: no puede formar un ciclo de mando",
                [{"path": "reportsTo", "message": "ciclo"}],
            )
        seen.add(current)
        boss = repo.get_agent(db, current)
        if boss is None or (first and boss.archived_at is not None):
            raise validation_error(
                f"reportsTo: el agente «{current}» no existe o está archivado",
                [{"path": "reportsTo", "message": f"no existe o archivado: {current}"}],
            )
        first = False
        current = boss.reports_to


def _check_max_agents(db: Database) -> None:
    """409 LIMIT_EXCEEDED si ya se alcanzó `limits.maxAgents` de agentes activos."""
    max_agents = settings_service.get_limits(db).max_agents
    if repo.count_active(db) >= max_agents:
        raise settings_service.limit_exceeded(
            f"Se alcanzó el máximo de agentes activos ({max_agents}). "
            "Archiva alguno o sube el límite en Administración → Límites"
        )


def restore_agent(db: Database, bus: EventBus | None, agent_id: str) -> Agent:
    """Restaura un agente archivado. Respeta `maxAgents` y la unicidad del nombre (409)."""
    agent = get_agent_or_404(db, agent_id)
    if agent.archived_at is None:
        return agent
    if repo.find_active_by_name(db, agent.name) is not None:
        raise conflict(f"Ya existe un agente activo llamado «{agent.name}»: renómbralo antes")
    _check_single_cto(db, agent.role_type, agent_id)
    _check_max_agents(db)
    try:
        repo.restore_agent(db, agent_id, now_iso())
    except IntegrityError:
        raise conflict(f"Ya existe un agente activo llamado «{agent.name}»") from None
    restored = get_agent_or_404(db, agent_id)
    if bus is not None:
        bus.emit("agent.created", agent_payload(restored))  # reaparece en las vistas
    return restored


def template_to_create(t: AgentTemplate) -> AgentCreate:
    return AgentCreate(
        name=t.name,
        role=t.role,
        role_type=t.role_type,
        character=t.character,
        avatar=t.avatar,
        functions=t.functions,
        rules=t.rules,
        restrictions=t.restrictions,
        permissions=t.permissions,
        model=t.model,
        limits=t.limits,
    )


def get_agent_or_404(db: Database, agent_id: str) -> Agent:
    agent = repo.get_agent(db, agent_id)
    if agent is None:
        raise not_found("Agente no encontrado")
    return agent


def list_agents(db: Database, include_archived: bool = False) -> list[Agent]:
    return repo.list_agents(db, include_archived)


_NOT_NULL = (
    "role_type",
    "name",
    "role",
    "character",
    "permissions",
    "model",
    "limits",
    "functions",
    "rules",
    "restrictions",
)


def update_agent(db: Database, bus: EventBus | None, agent_id: str, patch: AgentUpdate) -> Agent:
    """Edición parcial. Reaplica la política sobre el perfil resultante y regenera el prompt."""
    current = get_agent_or_404(db, agent_id)
    changes = patch.model_dump(exclude_unset=True)
    if not changes:
        return current
    for field in _NOT_NULL:
        if field in changes and changes[field] is None:
            raise validation_error(
                f"{field} no puede ser null", [{"path": field, "message": "no puede ser null"}]
            )

    merged = current.model_copy(update={k: getattr(patch, k) for k in changes})
    check_profile(merged.role_type, merged.permissions, merged.model, merged.limits)
    if "permissions" in changes:
        ensure_projects_exist(db, merged.permissions)
    if "role_type" in changes:
        _check_single_cto(db, merged.role_type, agent_id)
    if "reports_to" in changes:
        _check_reports_to(db, agent_id, merged.reports_to)
    if "name" in changes:
        other = repo.find_active_by_name(db, merged.name.strip())
        if other is not None and other.id != agent_id:
            raise conflict(f"Ya existe un agente activo llamado «{merged.name}»")

    fields: dict[str, Any] = {}
    for key in changes:
        value = getattr(merged, key)
        if key in ("permissions", "model", "limits", "avatar"):
            fields[key] = value.model_dump(by_alias=True, mode="json")
        elif key in ("name", "role", "character"):
            fields[key] = value.strip()
        else:
            fields[key] = value
    fields["is_cto"] = merged.role_type == "CTO"
    fields["system_prompt"] = generate_system_prompt(
        name=merged.name.strip(),
        role=merged.role.strip(),
        role_type=merged.role_type,
        functions=merged.functions,
        rules=merged.rules,
        restrictions=merged.restrictions,
    )
    try:
        repo.update_agent(db, agent_id, fields, now_iso())
    except IntegrityError:
        raise conflict(f"Ya existe un agente activo llamado «{merged.name}»") from None
    updated = get_agent_or_404(db, agent_id)
    if bus is not None:
        bus.emit("agent.updated", agent_payload(updated))
    return updated


def archive_agent(db: Database, bus: EventBus | None, agent_id: str) -> None:
    """Borrado lógico. 409 si tiene tickets sin terminar o aprobaciones PENDING."""
    agent = get_agent_or_404(db, agent_id)
    if agent.archived_at is not None:
        return
    if repo.count_open_tickets(db, agent_id) > 0:
        raise conflict("El agente tiene tickets sin terminar: reasígnalos o ciérralos antes")
    if repo.count_pending_approvals(db, agent_id) > 0:
        raise conflict("El agente tiene aprobaciones pendientes: resuélvelas antes")
    reports = repo.list_active_subordinates(db, agent_id)
    if reports:
        names = ", ".join(a.name for a in reports)
        raise conflict(f"Otros agentes reportan a este agente ({names}): reasígnalos antes")
    repo.archive_agent(db, agent_id, now_iso())
    if bus is not None:
        bus.emit("agent.archived", {"id": agent_id})


def set_agent_status(
    db: Database, bus: EventBus | None, agent_id: str, body: AgentStatusBody
) -> Agent:
    """Cambio MANUAL de estado: cualquiera de los 5 estados.

    - IDLE limpia `current_task`; otro estado conserva la tarea salvo que se envíe una nueva.
    - Salir de BLOCKED a mano (decisión humana explícita) reinicia el contador de fallos.
    """
    agent = get_agent_or_404(db, agent_id)
    if agent.archived_at is not None:
        raise conflict("El agente está archivado: restáuralo antes de cambiar su estado")
    if body.status == "IDLE":
        task = None
    elif body.current_task is not None:
        task = body.current_task
    else:
        task = agent.current_task
    now = now_iso()
    with db.transaction() as tx:
        repo.set_status(tx, agent_id, body.status, task, now)
        if agent.status == "BLOCKED" and body.status != "BLOCKED":
            repo.set_failures(tx, agent_id, 0, now)
    updated = get_agent_or_404(db, agent_id)
    if bus is not None:
        bus.emit("agent.updated", agent_payload(updated))
    return updated
