"""Flujo de tickets (PLAN §19.4): funciones puras, sin BD.

Fase 1 (sin S09): el único actor es el humano (CEO), que puede hacer cualquier transición VÁLIDA
del grafo. Los permisos por agente (`actingAgentId`) se añaden con S09.
"""

from typing import Literal

from app.domain.agent_policy import VALID_TRANSITIONS
from app.domain.schemas import AgentStatus, TicketStatus

Decision = Literal["ALLOWED", "INVALID", "NOOP"]

# Estados en los que el ticket "ocupa" a su agente (para decidir si vuelve a IDLE).
ACTIVE_STATUSES: tuple[TicketStatus, ...] = (
    "IN_PROGRESS",
    "IN_SENIOR_REVIEW",
    "IN_QA",
    "IN_REVIEW",
    "RETURNED",
)

# R1: las reglas automáticas no tocan estos estados (solo cambian a mano).
PROTECTED_AGENT_STATUSES: tuple[AgentStatus, ...] = ("BLOCKED", "SLEEP_QUOTA")


def can_transition(current: TicketStatus, to: TicketStatus) -> Decision:
    if current == to:
        return "NOOP"
    return "ALLOWED" if (current, to) in VALID_TRANSITIONS else "INVALID"


def agent_status_for(to: TicketStatus) -> AgentStatus | None:
    """Efecto en el agente asignado. `None` = IDLE solo si no le quedan tickets activos."""
    if to in ("IN_PROGRESS", "RETURNED"):
        return "WORKING"
    if to in ("IN_SENIOR_REVIEW", "IN_QA"):
        return "REVIEW"  # su trabajo está en revisión: espera en la oficina de Sheldon
    return (
        None  # IN_REVIEW (ya aprobado, en manos del CEO), DONE, PENDING: descansa si no tiene más
    )
