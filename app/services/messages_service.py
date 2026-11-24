"""Chat de mando: hilo de mensajes y eventos, y resumen de estado de un agente (H01).

Reglas (coherentes con las restricciones globales):
- Las órdenes GLOBALES van a Sheldon (CTO), que las reparte: aparecen en su hilo.
- Las individuales van al agente, con copia visible para Sheldon.
- En la Fase 1 no hay IA: la orden se guarda como PENDING hasta que exista el orquestador.
- El texto se guarda tal cual (nunca se interpreta como HTML).
"""

import json
from datetime import datetime

from app.db.database import Database
from app.domain.schemas import (
    Message,
    MessageCreate,
    PendingApprovalBrief,
    StatusSummary,
    ThreadEntry,
    TicketBrief,
)
from app.errors import conflict, validation_error
from app.events.bus import EventBus
from app.repositories import messages_repo
from app.services.agents_service import get_agent_or_404
from app.util import new_id, now_iso

DEFAULT_LIMIT = 100
MAX_LIMIT = 500
HUMAN_ID = "human"  # S06 lo sustituirá por el id del usuario de la sesión


def create_message(
    db: Database, bus: EventBus | None, data: MessageCreate, author_id: str = HUMAN_ID
) -> Message:
    body = data.body.strip()
    if not body:
        raise validation_error("body: no puede estar vacío", [{"path": "body", "message": "vacío"}])
    if data.scope == "AGENT":
        if data.agent_id is None:
            raise validation_error(
                "agentId es obligatorio con scope=AGENT", [{"path": "agentId", "message": "falta"}]
            )
        agent = get_agent_or_404(db, data.agent_id)
        if agent.archived_at is not None:
            raise conflict("El agente está archivado")
    elif data.agent_id is not None:
        raise validation_error(
            "Una orden GLOBAL no lleva agentId (se dirige a Sheldon)",
            [{"path": "agentId", "message": "no admitido con scope=GLOBAL"}],
        )
    message = Message(
        id=new_id(),
        scope=data.scope,
        agent_id=data.agent_id,
        author_type="HUMAN",
        author_id=author_id,
        kind=data.kind,
        body=body,
        status="PENDING",
        ticket_id=data.ticket_id,
        created_at=now_iso(),
    )
    messages_repo.insert_message(db, message)
    if bus is not None:
        bus.emit("message.created", message.model_dump(by_alias=True, mode="json"))
    return message


def get_thread(
    db: Database, *, agent_id: str | None, scope: str | None, limit: int = DEFAULT_LIMIT
) -> list[ThreadEntry]:
    """Hilo en orden cronológico (los `limit` más recientes). Exige agentId o scope=GLOBAL."""
    if not 1 <= limit <= MAX_LIMIT:
        raise validation_error(
            f"limit debe estar entre 1 y {MAX_LIMIT}",
            [{"path": "limit", "message": "fuera de rango"}],
        )
    if agent_id is None:
        if scope != "GLOBAL":
            raise validation_error(
                "Indica agentId o scope=GLOBAL", [{"path": "agentId", "message": "falta"}]
            )
        messages = messages_repo.list_messages(db, agent_id=None, everything=False, limit=limit)
        events = messages_repo.list_ticket_event_entries(db, agent_id=None, limit=limit)
    else:
        agent = get_agent_or_404(db, agent_id)
        messages = messages_repo.list_messages(
            db, agent_id=agent.id, everything=agent.is_cto, limit=limit
        )
        events = messages_repo.list_ticket_event_entries(db, agent_id=agent.id, limit=limit)
    entries = [messages_repo.message_entry(m) for m in messages] + events
    entries.sort(key=lambda e: (e.created_at, e.id))
    return entries[-limit:]


# ── Resumen de estado ("qué hace / qué le falta") ────────────────────────────────────────────
_TICKET_PRIORITY = (
    "IN_PROGRESS",
    "RETURNED",
    "IN_QA",
    "IN_SENIOR_REVIEW",
    "IN_REVIEW",
    "PENDING",
)
_NEXT_STEP = {
    "PENDING": "Iniciar el ticket (PENDING → IN_PROGRESS).",
    "IN_PROGRESS": "Terminar y pasar a QA (IN_PROGRESS → IN_QA).",
    "IN_QA": "Esperar la revisión de QA: pasa a IN_SENIOR_REVIEW o vuelve como RETURNED.",
    "IN_SENIOR_REVIEW": "Esperar la revisión senior: pasa a IN_REVIEW o vuelve como RETURNED.",
    "IN_REVIEW": "Esperar la revisión del CTO: DONE o RETURNED.",
    "RETURNED": "Corregir lo devuelto y retomar el ticket (RETURNED → IN_PROGRESS).",
}


def _seconds_since(iso: str) -> int:
    try:
        then = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return 0
    return max(
        0, int((datetime.fromisoformat(now_iso().replace("Z", "+00:00")) - then).total_seconds())
    )


def status_summary(db: Database, agent_id: str) -> StatusSummary:
    agent = get_agent_or_404(db, agent_id)
    rows = db.fetch_all(
        "SELECT id, title, status, priority, description, updated_at FROM tickets"
        " WHERE assigned_agent_id = ? AND status != 'DONE' ORDER BY updated_at DESC",
        (agent_id,),
    )
    open_tickets: dict[str, int] = {}
    for r in rows:
        open_tickets[str(r["status"])] = open_tickets.get(str(r["status"]), 0) + 1
    current = next((r for status in _TICKET_PRIORITY for r in rows if r["status"] == status), None)
    ticket = (
        TicketBrief(
            id=str(current["id"]),
            title=str(current["title"]),
            status=current["status"],
            priority=current["priority"],
            description=str(current["description"]),
            since_seconds=_seconds_since(str(current["updated_at"])),
        )
        if current
        else None
    )

    blocked_reason: str | None = None
    if agent.status == "BLOCKED":
        row = db.fetch_one(
            "SELECT meta FROM audit_log WHERE action = 'agent.auto_blocked' AND target_id = ?"
            " ORDER BY created_at DESC LIMIT 1",
            (agent_id,),
        )
        blocked_reason = "bloqueado manualmente"
        if row:
            reason = json.loads(str(row["meta"])).get("reason")
            blocked_reason = {
                "consecutive_failures": "3 fallos seguidos",
                "budget": "alcanzó su tope de coste diario",
            }.get(str(reason), "bloqueado automáticamente")

    approvals = db.fetch_all(
        "SELECT a.id, a.title, a.gate FROM approvals a LEFT JOIN tickets t ON t.id = a.ticket_id"
        " WHERE a.status = 'PENDING' AND (a.agent_id = ? OR t.assigned_agent_id = ?)"
        " ORDER BY a.requested_at",
        (agent_id, agent_id),
    )
    pending = [
        PendingApprovalBrief(id=str(r["id"]), title=str(r["title"]), gate=r["gate"])
        for r in approvals
    ]

    if agent.status == "BLOCKED":
        next_step = f"Desbloquear al agente ({blocked_reason}); requiere decisión humana."
    elif agent.status == "SLEEP_QUOTA":
        next_step = "Reanudar al agente (sin cuota) para que continúe."
    elif ticket is None:
        next_step = "Sin ticket asignado: esperando asignación."
    else:
        next_step = _NEXT_STEP[ticket.status]
    doing = f"Trabaja en «{ticket.title}» ({ticket.status})" if ticket else "Sin ticket asignado"
    summary = f"{agent.name}: {doing}. Siguiente paso: {next_step}"
    if pending:
        summary += f" Aprobaciones pendientes: {len(pending)}."
    return StatusSummary(
        agent_id=agent.id,
        name=agent.name,
        status=agent.status,
        current_task=agent.current_task,
        ticket=ticket,
        open_tickets=open_tickets,
        blocked_reason=blocked_reason,
        pending_approvals=pending,
        next_step=next_step,
        summary=summary,
    )
