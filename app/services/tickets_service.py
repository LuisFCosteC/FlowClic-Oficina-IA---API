"""Tickets: alta y transiciones del flujo (PLAN §19.4). G05 parcial: actor humano.

Pendiente: `actingAgentId` y permisos por agente (S09), edición/reasignación/borrado (T42–T43).
"""

import json

from app.db.database import Database
from app.domain.agent_policy import GLOBAL_RESTRICTIONS, is_self_review, is_senior_reviewer
from app.domain.models_catalog import MODEL_IDS
from app.domain.schemas import (
    Agent,
    RequestCreate,
    TaskCreate,
    Ticket,
    TicketEdit,
    TicketTransitionBody,
)
from app.domain.ticket_flow import PROTECTED_AGENT_STATUSES, agent_status_for, can_transition
from app.errors import AppError, conflict, not_found, validation_error
from app.events.bus import EventBus
from app.repositories import agents_repo
from app.repositories import tickets_repo as repo
from app.services import projects_service, settings_service
from app.services.agents_service import agent_payload
from app.util import new_id, now_iso

STATUS_LABEL = {
    "PENDING": "PENDIENTE",
    "IN_PROGRESS": "EN CURSO",
    "IN_SENIOR_REVIEW": "REVISIÓN SENIOR",
    "IN_QA": "EN QA",
    "IN_REVIEW": "REVISIÓN CTO",
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


def new_ticket(
    db: Database,
    bus: EventBus | None,
    *,
    title: str,
    kind: str,
    priority: str | None,
    assigned_agent_id: str | None,
    project_id: str | None,
    model: str | None,
    description: str = "",
    objective: str = "",
    acceptance_criteria: list[str] | None = None,
    actions: list[str] | None = None,
    restrictions: list[str] | None = None,
    dependencies: list[str] | None = None,
    parent_ticket_id: str | None = None,
    requirement: str = "",
    model_tier: str = "sonnet_pro",
    estimated_cost_usd: float = 0,
) -> Ticket:
    """Alta común (siempre PENDIENTE). Valida agente, proyecto y modelo; emite `ticket.created`."""
    if assigned_agent_id is not None:
        agent = agents_repo.get_agent(db, assigned_agent_id)
        if agent is None or agent.archived_at is not None:
            raise validation_error("El agente asignado no existe o está archivado")
    clean_title = title.strip()
    if not clean_title:
        raise validation_error("El título no puede estar vacío")
    if project_id is not None:
        projects_service.require_active(db, project_id)
    if model is not None and model not in MODEL_IDS:
        raise validation_error(
            f"model: modelo desconocido: {model}",
            [{"path": "model", "message": f"modelo desconocido: {model}"}],
        )
    now = now_iso()
    row = db.fetch_one("SELECT COALESCE(MAX(position), -1) + 1 AS p FROM tickets")
    ticket = Ticket.model_validate(
        {
            "id": new_id(),
            "title": clean_title,
            "description": description.strip(),
            "status": "PENDING",
            "priority": priority,
            "assigned_agent_id": assigned_agent_id,
            "project_id": project_id,
            "model_tier": model_tier,
            "estimated_cost_usd": estimated_cost_usd,
            "position": int(row["p"]) if row else 0,
            "created_at": now,
            "updated_at": now,
            "objective": objective.strip(),
            "acceptance_criteria": _clean_list(acceptance_criteria or []),
            "actions": _clean_list(actions or []),
            "restrictions": _task_restrictions(restrictions or []),
            "dependencies": _clean_list(dependencies or []),
            "model": model,
            "kind": kind,
            "parent_ticket_id": parent_ticket_id,
            "requirement": requirement.strip(),
        }
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
            payload=json.dumps({"kind": kind}),
            now=now,
        )
    created = get_ticket_or_404(db, ticket.id)  # con el nombre del proyecto
    if bus is not None:
        bus.emit("ticket.created", ticket_payload(created))
    return created


def active_cto(db: Database) -> Agent:
    """El único CTO activo. 409 si no hay ninguno o hay más de uno."""
    ctos = [a for a in agents_repo.list_agents(db) if a.role_type == "CTO"]
    if not ctos:
        raise conflict("Crea primero un agente con rol CTO")
    if len(ctos) > 1:
        raise conflict("Hay más de un agente CTO activo: deja solo uno")
    return ctos[0]


def create_request(db: Database, bus: EventBus | None, body: RequestCreate) -> Ticket:
    """Pedido del CEO (REQ01): lo recibe el CTO; prioridad y modelo quedan "Por definir"."""
    projects_service.require_active(db, body.project_id)
    cto = active_cto(db)
    return new_ticket(
        db,
        bus,
        title=body.title,
        kind="REQUEST",
        priority=None,
        assigned_agent_id=cto.id,
        project_id=body.project_id,
        model=None,
        description=body.requirement,
        requirement=body.requirement,
    )


def _check_can_create_tasks(db: Database, acting_agent_id: str) -> None:
    """Subtareas: las crean el CTO o Leonard (DEV_BACKEND) o un agente con `tickets.create`."""
    agent = agents_repo.get_agent(db, acting_agent_id)
    if agent is None or agent.archived_at is not None:
        raise validation_error("actingAgentId: el agente no existe o está archivado")
    if agent.role_type not in ("CTO", "DEV_BACKEND") and "tickets.create" not in (
        agent.permissions.actions
    ):
        raise AppError("FORBIDDEN", "Solo el CTO o Leonard pueden crear subtareas de un pedido")


def create_task(db: Database, bus: EventBus | None, body: TaskCreate) -> Ticket:
    """Subtarea (kind TASK) de un pedido (REQ01). Hasta GM05 también se crea por API en pruebas."""
    if body.acting_agent_id is not None:
        _check_can_create_tasks(db, body.acting_agent_id)
    parent = get_ticket_or_404(db, body.parent_ticket_id)
    if parent.kind != "REQUEST":
        raise validation_error("parentTicketId: debe ser un pedido (kind REQUEST)")
    if parent.status == "DONE":
        raise conflict("El pedido ya está HECHO: no admite más subtareas")
    return new_ticket(
        db,
        bus,
        title=body.title,
        kind="TASK",
        priority=body.priority,
        assigned_agent_id=body.assigned_agent_id,
        project_id=parent.project_id,
        model=body.model,
        objective=body.objective,
        acceptance_criteria=body.acceptance_criteria,
        actions=body.actions,
        restrictions=body.restrictions,
        dependencies=body.dependencies,
        parent_ticket_id=parent.id,
    )


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


def authorize_agent_transition(db: Database, agent_id: str, ticket: Ticket, to: str) -> Agent:
    """403 `TRANSITION_FORBIDDEN` si el agente simulado no puede hacer esta transición (GM02).

    Reglas duras: la pareja (origen, destino) debe estar en sus `ticketTransitions`, y con
    `onlyAssignedTickets` el ticket debe estar asignado a él. Lo evalúa el servidor, nunca el
    modelo.
    """
    agent = agents_repo.get_agent(db, agent_id)
    if agent is None or agent.archived_at is not None:
        raise validation_error(
            "actingAgentId: el agente no existe o está archivado",
            [{"path": "actingAgentId", "message": "no existe o archivado"}],
        )
    pair = (ticket.status, to)
    if pair not in {(a, b) for a, b in agent.permissions.ticket_transitions}:
        raise AppError(
            "TRANSITION_FORBIDDEN",
            f"{agent.name} no puede pasar un ticket de {STATUS_LABEL[ticket.status]} "
            f"a {STATUS_LABEL[to]}",
        )
    if pair == ("IN_PROGRESS", "IN_QA") and agent.reports_to is not None:
        boss = agents_repo.get_agent(db, agent.reports_to)
        if boss is not None and boss.archived_at is None and is_senior_reviewer(boss.permissions):
            raise AppError(
                "TRANSITION_FORBIDDEN",
                f"{agent.name} reporta a {boss.name} (revisor senior): debe pasar por "
                "REVISIÓN SENIOR antes de EN QA",
            )
    if is_self_review(agent.id, ticket.assigned_agent_id, ticket.kind, pair):
        raise AppError(
            "TRANSITION_FORBIDDEN",
            f"{agent.name} no puede aprobar ni devolver su propio trabajo "
            "(restricción global 6: nadie autoaprueba)",
        )
    if agent.permissions.only_assigned_tickets and ticket.assigned_agent_id != agent.id:
        raise AppError(
            "TRANSITION_FORBIDDEN",
            f"{agent.name} solo puede mover tickets asignados a él",
        )
    return agent


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
    actor = "human"
    if body.acting_agent_id is not None:
        acting = authorize_agent_transition(db, body.acting_agent_id, ticket, body.to)
        actor = acting.id
    if body.to == "DONE" and repo.count_pending_gates(db, ticket_id) > 0:
        raise AppError("GATE_PENDING", "El ticket tiene compuertas de aprobación pendientes")
    if body.to == "DONE" and ticket.kind == "REQUEST":
        open_subtasks = repo.count_open_subtasks(db, ticket_id)
        if open_subtasks > 0:
            raise AppError(
                "SUBTASKS_PENDING",
                f"El pedido tiene {open_subtasks} subtareas sin terminar: ciérralas antes",
            )
    _check_limits(db, ticket, body.to)
    now = now_iso()
    extra: dict[str, str] = {}
    if body.note:
        extra["note"] = body.note
    if actor != "human":
        extra["actingAgentId"] = actor  # simulado por un agente
    payload = json.dumps(extra, ensure_ascii=False)
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
            actor=actor,
        )
        agent = _apply_agent_effect(tx, ticket, body.to, now)
    updated = get_ticket_or_404(db, ticket_id)
    if bus is not None:
        bus.emit("ticket.updated", ticket_payload(updated))
        if agent is not None:
            bus.emit("agent.updated", agent_payload(agent))
    return updated


def edit_ticket(db: Database, bus: EventBus | None, ticket_id: str, body: TicketEdit) -> Ticket:
    """El CEO edita título, requerimiento, prioridad, modelo o proyecto (no si está HECHO)."""
    ticket = get_ticket_or_404(db, ticket_id)
    if ticket.status == "DONE":
        raise conflict("El ticket ya está HECHO: no se puede editar")
    sent = body.model_fields_set
    title = ticket.title
    if "title" in sent and body.title is not None:
        title = body.title.strip()
        if not title:
            raise validation_error("El título no puede estar vacío")
    requirement = ticket.requirement
    description = ticket.description
    if "requirement" in sent and body.requirement is not None:
        requirement = body.requirement.strip()
        description = requirement
    priority = body.priority if "priority" in sent else ticket.priority
    model = body.model if "model" in sent else ticket.model
    if model is not None and model not in MODEL_IDS:
        raise validation_error(
            f"model: modelo desconocido: {model}",
            [{"path": "model", "message": f"modelo desconocido: {model}"}],
        )
    project_id = body.project_id if "project_id" in sent else ticket.project_id
    if project_id is not None and project_id != ticket.project_id:
        projects_service.require_active(db, project_id)
    changed = [
        name
        for name, old, new in (
            ("title", ticket.title, title),
            ("requirement", ticket.requirement, requirement),
            ("priority", ticket.priority, priority),
            ("model", ticket.model, model),
            ("projectId", ticket.project_id, project_id),
        )
        if old != new
    ]
    if not changed:
        return ticket
    now = now_iso()
    with db.transaction() as tx:
        tx.execute(
            "UPDATE tickets SET title = ?, description = ?, requirement = ?, priority = ?,"
            " model = ?, project_id = ?, updated_at = ? WHERE id = ?",
            (title, description, requirement, priority, model, project_id, now, ticket_id),
        )
        repo.insert_event(
            tx,
            event_id=new_id(),
            ticket_id=ticket_id,
            type_="UPDATED",
            from_value=None,
            to_value=None,
            payload=json.dumps({"fields": changed}),
            now=now,
        )
    updated = get_ticket_or_404(db, ticket_id)
    if bus is not None:
        bus.emit("ticket.updated", ticket_payload(updated))
    return updated
