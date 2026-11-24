"""Tickets: alta y transiciones del flujo (PLAN §19.4). G05 parcial: actor humano.

Pendiente: `actingAgentId` y permisos por agente (S09), edición/reasignación/borrado (T42–T43).
"""

import json

from app.db.database import Database
from app.domain.agent_policy import GLOBAL_RESTRICTIONS
from app.domain.models_catalog import MODEL_IDS
from app.domain.schemas import Agent, Ticket, TicketCreate, TicketTransitionBody
from app.domain.ticket_flow import PROTECTED_AGENT_STATUSES, agent_status_for, can_transition
from app.errors import AppError, not_found, validation_error
from app.events.bus import EventBus
from app.repositories import agents_repo
from app.repositories import tickets_repo as repo
from app.services import projects_service, settings_service
from app.services.agents_service import agent_payload
from app.util import new_id, now_iso

STATUS_LABEL = {
    "PENDING": "PENDIENTE",
    "IN_PROGRESS": "EN CURSO",
    "IN_QA": "EN QA",
    "IN_REVIEW": "EN REVISIÓN",
    "DONE": "HECHO",
    "RETURNED": "DEVUELTA",
}


def _norm(text: str) -> str:
    return " ".join(text.split()).casefold()


def _clean_list(items: list[str]) -> list[str]:
    return [i.strip() for i in items if i.strip()]


def _task_restrictions(items: list[str]) -> list[str]:
    """Las restricciones de la tarea se suman a las 5 globales; una que coincida con una global
    se descarta (como en G02): las globales no se pueden quitar ni duplicar."""
    globals_ = {_norm(g) for g in GLOBAL_RESTRICTIONS}
    return [r for r in _clean_list(items) if _norm(r) not in globals_]


def ticket_payload(t: Ticket) -> dict[str, object]:
    return t.model_dump(by_alias=True, mode="json")


def get_ticket_or_404(db: Database, ticket_id: str) -> Ticket:
    ticket = repo.get_ticket(db, ticket_id)
    if ticket is None:
        raise not_found("Ticket no encontrado")
    return ticket


def create_ticket(db: Database, bus: EventBus | None, data: TicketCreate) -> Ticket:
    if data.status not in (None, "PENDING"):
        raise validation_error("Los tickets nuevos empiezan en PENDIENTE; muévelos después")
    if data.assigned_agent_id is not None:
        agent = agents_repo.get_agent(db, data.assigned_agent_id)
        if agent is None or agent.archived_at is not None:
            raise validation_error("El agente asignado no existe o está archivado")
    title = data.title.strip()
    if not title:
        raise validation_error("El título no puede estar vacío")
    if data.project_id is not None:
        projects_service.require_active(db, data.project_id)
    if data.model is not None and data.model not in MODEL_IDS:
        raise validation_error(
            f"model: modelo desconocido: {data.model}",
            [{"path": "model", "message": f"modelo desconocido: {data.model}"}],
        )
    now = now_iso()
    row = db.fetch_one("SELECT COALESCE(MAX(position), -1) + 1 AS p FROM tickets")
    ticket = Ticket(
        id=new_id(),
        title=title,
        description=(data.description or "").strip(),
        status="PENDING",
        priority=data.priority or "MEDIUM",
        assigned_agent_id=data.assigned_agent_id,
        project_id=data.project_id,
        model_tier=data.model_tier or "sonnet_pro",
        estimated_cost_usd=data.estimated_cost_usd or 0,
        position=int(row["p"]) if row else 0,
        created_at=now,
        updated_at=now,
        objective=(data.objective or "").strip(),
        acceptance_criteria=_clean_list(data.acceptance_criteria),
        actions=_clean_list(data.actions),
        restrictions=_task_restrictions(data.restrictions),
        dependencies=_clean_list(data.dependencies),
        model=data.model,
    )
    with db.transaction() as tx:
        repo.insert_ticket(tx, ticket)
        repo.insert_event(
            tx,
            event_id=new_id(),
            ticket_id=ticket.id,
            type_="CREATED",
            from_value=None,
            to_value="PENDING",
            payload="{}",
            now=now,
        )
    created = get_ticket_or_404(db, ticket.id)  # con el nombre del proyecto
    if bus is not None:
        bus.emit("ticket.created", ticket_payload(created))
    return created


def _apply_agent_effect(db: Database, ticket: Ticket, to: str, now: str) -> Agent | None:
    """Efecto en el agente asignado (R1: no toca BLOCKED ni SLEEP_QUOTA)."""
    if ticket.assigned_agent_id is None:
        return None
    agent = agents_repo.get_agent(db, ticket.assigned_agent_id)
    if agent is None or agent.archived_at is not None:
        return None
    if agent.status in PROTECTED_AGENT_STATUSES:
        return None
    target = agent_status_for(to)  # type: ignore[arg-type]
    if target is None:  # DONE o PENDING: IDLE solo si no le quedan tickets activos
        if repo.count_active_for_agent(db, agent.id, ticket.id) > 0:
            return None
        agents_repo.set_status(db, agent.id, "IDLE", None, now)
    else:
        agents_repo.set_status(db, agent.id, target, ticket.title, now)
    return agents_repo.get_agent(db, agent.id)


def _check_limits(db: Database, ticket: Ticket, to: str) -> None:
    """Límites de Administración (A04): 409 LIMIT_EXCEEDED."""
    limits = settings_service.get_limits(db)
    if to == "IN_PROGRESS" and ticket.assigned_agent_id is not None:
        active = repo.count_active_for_agent(db, ticket.assigned_agent_id, ticket.id)
        if active >= limits.max_active_tickets_per_agent:
            raise settings_service.limit_exceeded(
                f"El agente ya tiene {active} tickets activos (máximo "
                f"{limits.max_active_tickets_per_agent}). Termina o devuelve alguno antes"
            )
    if to == "DONE" and limits.require_approval_for_done and not repo.has_approved(db, ticket.id):
        raise settings_service.limit_exceeded(
            "Este proyecto exige una aprobación APPROVED para pasar a HECHO"
        )


def transition(
    db: Database, bus: EventBus | None, ticket_id: str, body: TicketTransitionBody
) -> Ticket:
    ticket = get_ticket_or_404(db, ticket_id)
    decision = can_transition(ticket.status, body.to)
    if decision == "NOOP":
        return ticket
    if decision == "INVALID":
        raise AppError(
            "INVALID_TRANSITION",
            f"No se puede pasar de {STATUS_LABEL[ticket.status]} a {STATUS_LABEL[body.to]}",
        )
    if body.to == "DONE" and repo.count_pending_gates(db, ticket_id) > 0:
        raise AppError("GATE_PENDING", "El ticket tiene compuertas de aprobación pendientes")
    _check_limits(db, ticket, body.to)
    now = now_iso()
    payload = json.dumps({"note": body.note} if body.note else {}, ensure_ascii=False)
    with db.transaction() as tx:
        repo.set_status(tx, ticket_id, body.to, now)
        repo.insert_event(
            tx,
            event_id=new_id(),
            ticket_id=ticket_id,
            type_="STATUS_CHANGED",
            from_value=ticket.status,
            to_value=body.to,
            payload=payload,
            now=now,
        )
        agent = _apply_agent_effect(tx, ticket, body.to, now)
    updated = get_ticket_or_404(db, ticket_id)
    if bus is not None:
        bus.emit("ticket.updated", ticket_payload(updated))
        if agent is not None:
            bus.emit("agent.updated", agent_payload(agent))
    return updated
