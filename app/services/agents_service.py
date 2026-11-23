"""Reglas de negocio de agentes (PLAN §19). Las rutas solo llaman a estas funciones."""

from app.db.database import Database, IntegrityError
from app.domain.agent_policy import check_profile, generate_system_prompt
from app.domain.agent_templates import BASE_TEAM, AgentTemplate
from app.domain.schemas import Agent, AgentAvatar, AgentCreate
from app.errors import conflict
from app.events.bus import EventBus
from app.repositories import agents_repo as repo
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
        consecutive_failures=0,
        created_at=now,
        updated_at=now,
        archived_at=None,
    )


def create_agent(
    db: Database, bus: EventBus | None, data: AgentCreate, *, agent_id: str | None = None
) -> Agent:
    """Crea un agente (409 si el nombre ya lo usa uno activo) y emite `agent.created`."""
    agent = build_agent(data, agent_id=agent_id)
    if repo.find_active_by_name(db, agent.name) is not None:
        raise conflict(f"Ya existe un agente activo llamado «{agent.name}»")
    try:
        repo.insert_agent(db, agent)
    except IntegrityError:
        raise conflict(f"Ya existe un agente activo llamado «{agent.name}»") from None
    if bus is not None:
        bus.emit("agent.created", agent_payload(agent))
    return agent


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


def load_base_team(db: Database, bus: EventBus | None = None) -> tuple[list[Agent], list[str]]:
    """Crea los 4 agentes del equipo base desde las plantillas. Idempotente.

    Devuelve (creados, nombres_omitidos). Se omite una plantilla si ya hay un agente (activo)
    con ese id o con ese nombre; nunca se modifica un agente existente.
    """
    created: list[Agent] = []
    skipped: list[str] = []
    for template in BASE_TEAM:
        existing_by_id = repo.get_agent(db, template.id)
        if (existing_by_id is not None and existing_by_id.archived_at is None) or (
            repo.find_active_by_name(db, template.name) is not None
        ):
            skipped.append(template.name)
            continue
        agent_id = template.id if existing_by_id is None else None  # id libre → slug estable
        created.append(create_agent(db, bus, template_to_create(template), agent_id=agent_id))
    return created, skipped
