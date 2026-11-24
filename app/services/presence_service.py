"""Presencia de los agentes (laboratorio / oficina de Sheldon / descanso) y modo de la oficina.

Modo de la oficina (`app_settings.office_mode`): `work` (normal) o una pausa global —`breakfast`,
`lunch`, `sleep`— en la que NADIE trabaja: los agentes pasan a IDLE sin perder lo que tenían entre
manos (los tickets no se tocan) y el orquestador no avanza hasta volver a `work`.
"""

from app.db.database import Database
from app.domain.schemas import Agent
from app.errors import validation_error
from app.events.bus import EventBus
from app.repositories import agents_repo, settings_repo, tickets_repo
from app.services.agents_service import agent_payload
from app.util import now_iso

MODES = ("work", "breakfast", "lunch", "sleep")
_KEY = "office_mode"
_PROTECTED = ("BLOCKED", "SLEEP_QUOTA")


def get_mode(db: Database) -> str:
    value = settings_repo.get_value(db, _KEY)
    return value if value in MODES else "work"


def _emit(bus: EventBus | None, db: Database, agent_id: str) -> None:
    updated = agents_repo.get_agent(db, agent_id)
    if bus is not None and updated is not None:
        bus.emit("agent.updated", agent_payload(updated))


def set_agent(
    db: Database, bus: EventBus | None, agent: Agent, status: str, task: str | None
) -> None:
    """Cambia el estado visible (no toca BLOCKED ni SLEEP_QUOTA) y avisa por SSE."""
    if agent.archived_at is not None or agent.status in _PROTECTED:
        return
    if agent.status == status and agent.current_task == task:
        return
    agents_repo.set_status(db, agent.id, status, task, now_iso())  # type: ignore[arg-type]
    _emit(bus, db, agent.id)


def settle_agent(db: Database, bus: EventBus | None, agent_id: str) -> None:
    """Estado según sus tickets: trabajando → laboratorio; su trabajo en revisión → oficina de
    Sheldon; nada pendiente (o ya aprobado) → zona de descanso. En pausa global siempre IDLE."""
    agent = agents_repo.get_agent(db, agent_id)
    if agent is None:
        return
    if get_mode(db) != "work":
        set_agent(db, bus, agent, "IDLE", agent.current_task)
        return
    mine = [t for t in tickets_repo.list_tickets(db) if t.assigned_agent_id == agent_id]
    working = next((t for t in mine if t.status in ("IN_PROGRESS", "RETURNED")), None)
    review = next((t for t in mine if t.status in ("IN_SENIOR_REVIEW", "IN_QA")), None)
    if working is not None:
        set_agent(db, bus, agent, "WORKING", working.title)
    elif review is not None:
        set_agent(db, bus, agent, "REVIEW", review.title)
    else:
        set_agent(db, bus, agent, "IDLE", None)


def settle_all(db: Database, bus: EventBus | None) -> None:
    for agent in agents_repo.list_agents(db):
        settle_agent(db, bus, agent.id)


def set_mode(db: Database, bus: EventBus | None, mode: str) -> str:
    """`work` reanuda (cada agente según sus tickets); otro modo pausa a todos sin perder nada."""
    if mode not in MODES:
        raise validation_error("mode debe ser work, breakfast, lunch o sleep")
    settings_repo.put_value(db, _KEY, mode, None, now_iso())
    settle_all(db, bus)
    return mode
