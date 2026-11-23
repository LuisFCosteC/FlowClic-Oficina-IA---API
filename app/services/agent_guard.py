"""AgentGuard: bloqueo automático de agentes (restricción global 5, PLAN §19.2).

En la Fase 1 se ejerce con `POST /api/agents/{id}/failures` (solo ADMIN, para pruebas); en la
Fase 2 lo llamará el orquestador.
"""

from app.db.database import Database
from app.domain.schemas import Agent
from app.errors import conflict
from app.events.bus import EventBus
from app.repositories import agents_repo as repo
from app.security import audit
from app.services.agents_service import agent_payload, get_agent_or_404
from app.util import now_iso

MAX_CONSECUTIVE_FAILURES = 3


class AgentGuard:
    def __init__(self, db: Database, bus: EventBus | None = None) -> None:
        self._db = db
        self._bus = bus

    def _active(self, agent_id: str) -> Agent:
        agent = get_agent_or_404(self._db, agent_id)
        if agent.archived_at is not None:
            raise conflict("El agente está archivado")
        return agent

    def _block(self, agent: Agent, reason: str, meta: dict[str, object]) -> None:
        """Pasa a BLOCKED (si no lo estaba ya) y deja auditoría. No emite: lo hace el llamador."""
        repo.set_status(self._db, agent.id, "BLOCKED", agent.current_task, now_iso())
        audit.record(
            self._db,
            "agent.auto_blocked",
            target_type="agent",
            target_id=agent.id,
            meta={"reason": reason, **meta},
        )

    def _emit(self, agent_id: str) -> Agent:
        updated = get_agent_or_404(self._db, agent_id)
        if self._bus is not None:
            self._bus.emit("agent.updated", agent_payload(updated))
        return updated

    def record_failure(self, agent_id: str) -> Agent:
        """+1 fallo seguido; al 3.º el agente pasa a BLOCKED (evento + auditoría)."""
        agent = self._active(agent_id)
        count = agent.consecutive_failures + 1
        repo.set_failures(self._db, agent_id, count, now_iso())
        if count >= MAX_CONSECUTIVE_FAILURES and agent.status != "BLOCKED":
            self._block(agent, "consecutive_failures", {"failures": count})
        return self._emit(agent_id)

    def record_success(self, agent_id: str) -> Agent:
        """Un éxito reinicia el contador de fallos seguidos."""
        agent = self._active(agent_id)
        if agent.consecutive_failures != 0:
            repo.set_failures(self._db, agent_id, 0, now_iso())
            return self._emit(agent_id)
        return agent

    def check_budget(self, agent_id: str, usd_today: float) -> Agent:
        """Bloquea al agente si el gasto del día alcanza su tope `limits.maxUsdPerDay`."""
        agent = self._active(agent_id)
        if usd_today >= agent.limits.max_usd_per_day and agent.status != "BLOCKED":
            self._block(
                agent,
                "budget",
                {"usdToday": usd_today, "maxUsdPerDay": agent.limits.max_usd_per_day},
            )
            return self._emit(agent_id)
        return agent
