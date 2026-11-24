"""Orquestador (Fase 2): Sheldon (CTO) recibe los pedidos del CEO, los reparte entre los agentes,
cada agente trabaja y entrega por el orden del flujo, y Sheldon avisa al CEO en REVISIÓN CTO.

Reglas que el CÓDIGO impone (no el modelo):
- Solo el CEO (humano) pasa un ticket a HECHO: el orquestador nunca lo hace.
- Solo el CTO habla con el CEO y crea pedidos.
- Nadie revisa su propio trabajo; los archivos sensibles (.env, llaves) no se leen.
- Cada agente solo ve los espacios de trabajo que sus permisos le dan.
- El CEO solo recibe un mensaje cuando hay una entrega o un fallo que no se resuelve solo.

El orquestador conduce las transiciones mecánicas del flujo (tomar, entregar, enrutar a revisión) en
nombre del agente (`as_agent`); las revisiones las hace un agente distinto del autor.
"""

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.db.database import Database
from app.domain.agent_policy import is_senior_reviewer
from app.domain.schemas import (
    Agent,
    Message,
    TaskCreate,
    Ticket,
    TicketTransitionBody,
)
from app.errors import AppError
from app.events.bus import EventBus
from app.orchestrator import fs_tools
from app.orchestrator.llm import (
    LlmClient,
    LlmError,
    ToolCall,
    ToolDef,
    Turn,
    complete_with_pool,
)
from app.repositories import agents_repo, messages_repo, projects_repo, tickets_repo
from app.services import tickets_service
from app.services.key_pool import KeyPool
from app.util import new_id, now_iso

log = logging.getLogger("flowclic.orchestrator")

MAX_STEPS = 10
RETRY_SECONDS = 60.0
MAX_FAILS = 3
_RESULT_CAP = 12_000
_BLOCKED = ("BLOCKED",)

Handler = Callable[[dict[str, Any]], str]


@dataclass
class Tool:
    spec: ToolDef
    run: Handler
    terminal: bool = False


def _obj(props: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": props, "required": required or []}


_S = {"type": "string"}
_RULES = (
    "Hablas SIEMPRE en español. Trabajas dentro de una oficina de agentes de IA: usa las "
    "herramientas, no inventes archivos ni resultados. NO pidas ayuda al CEO: decide con criterio "
    "y documenta tus supuestos. Solo se le consulta cuando hace falta un comentario o una "
    "aprobación suya. Nunca leas ni pidas archivos .env, llaves ni secretos."
)


class Orchestrator:
    def __init__(
        self,
        db: Database,
        bus: EventBus | None,
        pool: KeyPool,
        llm: LlmClient,
        *,
        max_steps: int = MAX_STEPS,
        retry_seconds: float = RETRY_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._db = db
        self._bus = bus
        self._pool = pool
        self._llm = llm
        self._max_steps = max_steps
        self._retry = retry_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._next_try: dict[str, float] = {}
        self._fails: dict[str, int] = {}
        self._notified: set[str] = set()

    # ── bucle ────────────────────────────────────────────────────────────────────────────────
    def tick(self) -> int:
        """Una pasada: responde mensajes del CEO y hace avanzar cada ticket. Devuelve acciones."""
        if not self._lock.acquire(blocking=False):
            return 0
        try:
            done = self._answer_messages()
            for ticket in tickets_repo.list_tickets(self._db):
                if ticket.status in ("DONE", "IN_REVIEW"):
                    continue
                key = f"t:{ticket.id}:{ticket.status}"
                if self._clock() < self._next_try.get(key, 0):
                    continue
                try:
                    if self._advance(ticket):
                        done += 1
                        self._fails.pop(key, None)
                except Exception as exc:  # noqa: BLE001 - un ticket roto no frena a los demás
                    self._on_failure(key, ticket, exc)
            return done
        finally:
            self._lock.release()

    def _on_failure(self, key: str, ticket: Ticket | None, exc: Exception) -> None:
        n = self._fails.get(key, 0) + 1
        self._fails[key] = n
        wait = (
            self._retry
            * min(n, 5)
            * (4 if isinstance(exc, AppError) and exc.code == "NO_KEY_AVAILABLE" else 1)
        )
        self._next_try[key] = self._clock() + wait
        what = exc.message if isinstance(exc, AppError) else str(exc) or exc.__class__.__name__
        log.warning("Orquestador: %s falló (%s/%s): %s", key, n, MAX_FAILS, what)
        if n >= MAX_FAILS and key not in self._notified and ticket is not None:
            self._notified.add(key)
            self._say_system(
                f"El orquestador no pudo avanzar «{ticket.title}» ({ticket.status}): {what}. "
                "Reintenta solo; si es por claves o permisos, corrígelo en Administración.",
                ticket.id,
            )

    # ── máquina de estados ───────────────────────────────────────────────────────────────────
    def _advance(self, t: Ticket) -> bool:
        if t.kind == "REQUEST":
            return self._advance_request(t)
        return self._advance_task(t)

    def _cto(self) -> Agent | None:
        ctos = [
            a
            for a in agents_repo.list_agents(self._db)
            if a.role_type == "CTO" and a.archived_at is None and a.status not in _BLOCKED
        ]
        return ctos[0] if len(ctos) == 1 else None

    def _move(self, t: Ticket, to: str, agent: Agent, note: str | None = None) -> Ticket:
        return tickets_service.transition(
            self._db,
            self._bus,
            t.id,
            TicketTransitionBody(to=to, note=note),
            as_agent=agent.id,
        )

    def _children(self, request_id: str) -> list[Ticket]:
        return [t for t in tickets_repo.list_tickets(self._db) if t.parent_ticket_id == request_id]

    def _advance_request(self, t: Ticket) -> bool:
        cto = self._cto()
        if cto is None:
            return False
        if t.status in ("PENDING", "RETURNED"):
            t = self._move(t, "IN_PROGRESS", cto, "Sheldon toma el pedido")
            self._plan(t, cto)
            return True
        if t.status == "IN_PROGRESS":
            kids = self._children(t.id)
            if not kids:
                self._plan(t, cto)
                return True
            if all(k.status in ("IN_REVIEW", "DONE") for k in kids):
                self._deliver(t, cto, kids)
                return True
        return False

    def _advance_task(self, t: Ticket) -> bool:
        if t.assigned_agent_id is None:
            return False
        worker = agents_repo.get_agent(self._db, t.assigned_agent_id)
        if worker is None or worker.archived_at is not None or worker.status in _BLOCKED:
            return False
        if t.status in ("PENDING", "RETURNED"):
            parent = (
                tickets_repo.get_ticket(self._db, t.parent_ticket_id)
                if t.parent_ticket_id
                else None
            )
            if parent is not None and parent.status != "IN_PROGRESS":
                return False
            t = self._move(t, "IN_PROGRESS", worker, "Empieza a trabajar")
            self._work(t, worker)
            return True
        if t.status == "IN_PROGRESS":
            self._work(t, worker)
            return True
        if t.status in ("IN_SENIOR_REVIEW", "IN_QA"):
            pair = (t.status, "IN_QA" if t.status == "IN_SENIOR_REVIEW" else "IN_REVIEW")
            reviewer = self._pick_reviewer(t, worker, pair)
            if reviewer is None:
                self._notify_once(
                    f"norev:{t.id}:{t.status}",
                    f"No hay quien revise «{t.title}» ({t.status}): hace falta un agente distinto "
                    f"del autor con permiso {pair[0]} → {pair[1]} (o el CTO activo).",
                    t.id,
                )
                return False
            self._review(t, reviewer, pair[1])
            return True
        return False

    def _pick_reviewer(self, t: Ticket, worker: Agent, pair: tuple[str, str]) -> Agent | None:
        agents = [
            a
            for a in agents_repo.list_agents(self._db)
            if a.archived_at is None and a.id != worker.id and a.status not in _BLOCKED
        ]
        ok = [
            a
            for a in agents
            if a.role_type == "CTO" or pair in {(x, y) for x, y in a.permissions.ticket_transitions}
        ]
        boss = next((a for a in ok if a.id == worker.reports_to), None)
        cto = next((a for a in ok if a.role_type == "CTO"), None)
        if pair[0] == "IN_SENIOR_REVIEW":
            return boss or next((a for a in ok if is_senior_reviewer(a.permissions)), None) or cto
        return cto or boss or (ok[0] if ok else None)

    # ── mensajes ─────────────────────────────────────────────────────────────────────────────
    def _post(
        self,
        *,
        agent: Agent | None,
        body: str,
        ticket_id: str | None,
        scope: str,
        kind: str = "REPLY",
        author_type: str = "AGENT",
    ) -> None:
        message = Message.model_validate(
            {
                "id": new_id(),
                "scope": scope,
                "agent_id": None if scope == "GLOBAL" else (agent.id if agent else None),
                "author_type": author_type,
                "author_id": agent.id if agent else "orchestrator",
                "kind": kind,
                "body": body.strip()[:8000] or "(sin texto)",
                "status": "DONE",
                "ticket_id": ticket_id,
                "created_at": now_iso(),
            }
        )
        messages_repo.insert_message(self._db, message)
        if self._bus is not None:
            self._bus.emit("message.created", message.model_dump(by_alias=True, mode="json"))

    def _say_system(self, body: str, ticket_id: str | None) -> None:
        self._post(
            agent=None,
            body=body,
            ticket_id=ticket_id,
            scope="GLOBAL",
            kind="STATUS",
            author_type="SYSTEM",
        )

    def _notify_once(self, key: str, body: str, ticket_id: str | None) -> None:
        if key in self._notified:
            return
        self._notified.add(key)
        self._say_system(body, ticket_id)

    def _answer_messages(self) -> int:
        done = 0
        for m in messages_repo.list_pending_human(self._db):
            key = f"m:{m.id}"
            if self._clock() < self._next_try.get(key, 0):
                continue
            target = agents_repo.get_agent(self._db, m.agent_id) if m.agent_id else self._cto()
            if target is None or target.archived_at is not None:
                messages_repo.set_status(self._db, m.id, "REJECTED")
                continue
            if m.kind == "NOTE":
                messages_repo.set_status(self._db, m.id, "ACK")
                continue
            try:
                self._reply_to(m, target)
                messages_repo.set_status(self._db, m.id, "DONE")
                done += 1
            except Exception as exc:  # noqa: BLE001
                n = self._fails.get(key, 0) + 1
                self._fails[key] = n
                self._next_try[key] = self._clock() + self._retry * n
                if n >= MAX_FAILS:
                    what = exc.message if isinstance(exc, AppError) else "error del proveedor"
                    messages_repo.set_status(self._db, m.id, "REJECTED")
                    self._say_system(f"No pude responder a «{m.body[:80]}»: {what}.", m.ticket_id)
        return done

    def _reply_to(self, m: Message, agent: Agent) -> None:
        is_cto = agent.role_type == "CTO"
        context = self._agent_context(agent)
        said: list[str] = []
        tools = self._read_tools(agent)

        def reply(a: dict[str, Any]) -> str:
            said.append(str(a.get("text", "")))
            return "enviado"

        tools["reply"] = Tool(
            ToolDef(
                "reply", "Responde al CEO con tu respuesta final.", _obj({"text": _S}, ["text"])
            ),
            reply,
            terminal=True,
        )
        if is_cto:
            tools["list_projects"] = self._list_projects_tool()
            tools["create_request"] = self._create_request_tool(agent, said)
        kind = "orden" if m.kind == "ORDER" else "pregunta"
        out = self._loop(
            agent,
            f"{context}\n\nEl CEO te envía una {kind}: «{m.body}».\n"
            + (
                "Si pide trabajo nuevo, créalo con create_request (elige el proyecto con "
                "list_projects) y luego responde con reply explicando qué harás. "
                if is_cto
                else ""
            )
            + "Si es una pregunta, responde con reply (consulta los archivos si hace falta).",
            tools,
        )
        text = " ".join(s for s in said if s).strip() or out
        self._post(agent=agent, body=text, ticket_id=m.ticket_id, scope=m.scope)

    # ── herramientas ─────────────────────────────────────────────────────────────────────────
    def _read_tools(self, agent: Agent) -> dict[str, Tool]:
        db = self._db

        def spaces(_: dict[str, Any]) -> str:
            ws = fs_tools.visible_workspaces(db, agent)
            if not ws:
                return "No tienes acceso a ningún espacio de trabajo."
            return "\n".join(
                f"- {w.id}: {w.name} (tipo {w.kind}, proyecto {w.project_id})" for w in ws
            )

        def tree(a: dict[str, Any]) -> str:
            return fs_tools.tree(db, agent, str(a.get("workspace_id", "")), str(a.get("path", "")))

        def ls(a: dict[str, Any]) -> str:
            return fs_tools.list_dir(
                db, agent, str(a.get("workspace_id", "")), str(a.get("path", ""))
            )

        def read(a: dict[str, Any]) -> str:
            return fs_tools.read_file(
                db, agent, str(a.get("workspace_id", "")), str(a.get("path", ""))
            )

        ws_id = {"workspace_id": _S, "path": _S}
        return {
            "list_workspaces": Tool(
                ToolDef(
                    "list_workspaces", "Lista tus espacios de trabajo (solo lectura).", _obj({})
                ),
                spaces,
            ),
            "tree": Tool(
                ToolDef(
                    "tree",
                    "Árbol de carpetas (2 niveles) de un espacio de trabajo o subcarpeta.",
                    _obj(ws_id, ["workspace_id"]),
                ),
                tree,
            ),
            "list_dir": Tool(
                ToolDef(
                    "list_dir",
                    "Lista una carpeta del espacio de trabajo.",
                    _obj(ws_id, ["workspace_id"]),
                ),
                ls,
            ),
            "read_file": Tool(
                ToolDef(
                    "read_file",
                    "Lee un archivo de texto del espacio de trabajo (recortado si es grande).",
                    _obj(ws_id, ["workspace_id", "path"]),
                ),
                read,
            ),
        }

    def _list_projects_tool(self) -> Tool:
        def run(_: dict[str, Any]) -> str:
            ps = projects_repo.list_projects(self._db)
            return "\n".join(f"- {p.id}: {p.name}" for p in ps) or "No hay proyectos activos."

        return Tool(ToolDef("list_projects", "Lista los proyectos activos.", _obj({})), run)

    def _create_request_tool(self, cto: Agent, said: list[str]) -> Tool:
        def run(a: dict[str, Any]) -> str:
            from app.domain.schemas import RequestCreate

            body = RequestCreate(
                title=str(a.get("title", "")),
                requirement=str(a.get("requirement", "")),
                project_id=str(a.get("project_id", "")),
            )
            t = tickets_service.create_request(self._db, self._bus, body)
            return f"Pedido creado: «{t.title}» ({t.id}). Lo tomarás en breve."

        return Tool(
            ToolDef(
                "create_request",
                "Crea un pedido nuevo (ticket) a partir de lo que pide el CEO.",
                _obj(
                    {"title": _S, "requirement": _S, "project_id": _S},
                    ["title", "requirement", "project_id"],
                ),
            ),
            run,
        )

    # ── contexto y bucle LLM ─────────────────────────────────────────────────────────────────
    def _agent_context(self, agent: Agent) -> str:
        mine = [
            t
            for t in tickets_repo.list_tickets(self._db)
            if t.assigned_agent_id == agent.id and t.status != "DONE"
        ]
        team = [
            f"- {a.name} ({a.role}, {a.role_type})"
            for a in agents_repo.list_agents(self._db)
            if a.archived_at is None
        ]
        tk = "\n".join(f"- «{t.title}» [{t.status}]" for t in mine) or "(ninguno)"
        return "Equipo:\n" + "\n".join(team) + f"\n\nTus tickets activos:\n{tk}"

    def _system(self, agent: Agent) -> str:
        return f"{agent.system_prompt}\n\n{_RULES}"

    def _loop(self, agent: Agent, user: str, tools: dict[str, Tool]) -> str:
        """Conversación con herramientas hasta una herramienta terminal o texto final."""
        models = [agent.model.primary] + ([agent.model.fallback] if agent.model.fallback else [])
        specs = [t.spec for t in tools.values()]
        turns: list[Turn] = [Turn("user", user)]
        last_text = ""
        for _ in range(self._max_steps):
            reply = complete_with_pool(
                self._pool,
                self._llm,
                model_ids=models,
                system=self._system(agent),
                turns=turns,
                tools=specs,
                agent_id=agent.id,
            )
            last_text = reply.text or last_text
            if not reply.calls:
                return last_text
            turns.append(Turn("assistant", reply.text, list(reply.calls)))
            results: list[tuple[ToolCall, str]] = []
            finished = False
            for call in reply.calls:
                tool = tools.get(call.name)
                if tool is None:
                    results.append((call, f"ERROR: la herramienta «{call.name}» no existe"))
                    continue
                try:
                    out = tool.run(call.args)
                    if tool.terminal:
                        finished = True
                except AppError as exc:
                    out = f"ERROR: {exc.message}"
                except Exception as exc:  # noqa: BLE001 - lo que falle vuelve al modelo como texto
                    out = f"ERROR: {str(exc)[:300] or exc.__class__.__name__}"
                results.append((call, out[:_RESULT_CAP]))
            turns.append(Turn("user", "", results=results))
            if finished:
                return last_text
        raise LlmError("El agente no terminó en el número máximo de pasos")

    def _ticket_context(self, t: Ticket) -> str:
        parts = [f"Ticket: «{t.title}» (estado {t.status})"]
        if t.kind == "TASK":
            parts.append(f"Objetivo: {t.objective}")
            if t.acceptance_criteria:
                parts.append(
                    "Criterios de aceptación:\n"
                    + "\n".join(f"- {c}" for c in t.acceptance_criteria)
                )
            if t.parent_ticket_id:
                parent = tickets_repo.get_ticket(self._db, t.parent_ticket_id)
                if parent is not None:
                    parts.append(f"Pedido del CEO: {parent.requirement or parent.description}")
        else:
            parts.append(f"Pedido del CEO: {t.requirement or t.description}")
        history = messages_repo.list_for_ticket(self._db, t.id, 12)
        if history:
            names = {a.id: a.name for a in agents_repo.list_agents(self._db)}
            parts.append(
                "Historial del ticket:\n"
                + "\n".join(
                    f"[{names.get(m.author_id, m.author_type)}] {m.body[:1500]}" for m in history
                )
            )
        return "\n".join(parts)

    # ── pasos con IA ─────────────────────────────────────────────────────────────────────────
    def _plan(self, t: Ticket, cto: Agent) -> None:
        """Sheldon lee el pedido y lo reparte en subtareas entre los agentes del equipo."""
        team = [
            a for a in agents_repo.list_agents(self._db) if a.archived_at is None and a.id != cto.id
        ]
        created: list[str] = []
        direct: list[str] = []
        tools = self._read_tools(cto)

        def create(a: dict[str, Any]) -> str:
            assignee = next((x for x in team if x.id == str(a.get("assigned_agent_id"))), None)
            if assignee is None:
                names = ", ".join(f"{x.name} ({x.id})" for x in team)
                raise AppError("VALIDATION_ERROR", f"assigned_agent_id inválido. Equipo: {names}")
            prio = str(a.get("priority", "MEDIUM")).upper()
            body = TaskCreate(
                parent_ticket_id=t.id,
                title=str(a.get("title", ""))[:200],
                objective=str(a.get("objective", "")),
                acceptance_criteria=[str(x) for x in (a.get("acceptance_criteria") or [])]
                or ["Entregado y revisado"],
                assigned_agent_id=assignee.id,
                model=assignee.model.primary,
                priority=prio if prio in ("HIGH", "MEDIUM", "LOW") else "MEDIUM",
                acting_agent_id=cto.id,
            )
            sub = tickets_service.create_task(self._db, self._bus, body)
            created.append(sub.id)
            return f"Subtarea creada para {assignee.name}: «{sub.title}»"

        def answer(a: dict[str, Any]) -> str:
            direct.append(str(a.get("summary", "")))
            return "entregado"

        tools["create_subtask"] = Tool(
            ToolDef(
                "create_subtask",
                "Crea una subtarea y la asigna a un agente del equipo.",
                _obj(
                    {
                        "title": _S,
                        "objective": _S,
                        "acceptance_criteria": {"type": "array", "items": _S},
                        "assigned_agent_id": _S,
                        "priority": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
                    },
                    ["title", "objective", "acceptance_criteria", "assigned_agent_id"],
                ),
            ),
            create,
        )
        tools["finish_planning"] = Tool(
            ToolDef(
                "finish_planning",
                "Termina el reparto cuando ya creaste todas las subtareas.",
                _obj({}),
            ),
            lambda _: "ok",
            terminal=True,
        )
        tools["answer_directly"] = Tool(
            ToolDef(
                "answer_directly",
                "Solo si NO hace falta repartir (nadie más puede, o es trivial): entrega tú el "
                "resultado.",
                _obj({"summary": _S}, ["summary"]),
            ),
            answer,
            terminal=True,
        )
        roster = (
            "\n".join(
                f"- {a.name} (id {a.id}): {a.role}. Funciones: {'; '.join(a.functions[:4])}"
                for a in team
            )
            or "(no hay más agentes)"
        )
        self._loop(
            cto,
            f"{self._ticket_context(t)}\n\nEquipo disponible:\n{roster}\n\n"
            "Eres el CTO. Lee el pedido (explora los archivos si lo necesitas) y repártelo: crea "
            "con create_subtask UNA subtarea por cada pieza de trabajo, asignada al agente más "
            "adecuado, con objetivo claro y criterios de aceptación medibles. Al terminar llama "
            "finish_planning. Si el equipo no tiene a nadie adecuado o es trivial, usa "
            "answer_directly con el resultado.",
            tools,
        )
        if direct and not created:
            self._deliver_text(t, cto, direct[0])
        elif not created and not self._children(t.id):
            raise LlmError("Sheldon no creó ninguna subtarea")

    def _work(self, t: Ticket, agent: Agent) -> None:
        reports: list[str] = []
        tools = self._read_tools(agent)

        def submit(a: dict[str, Any]) -> str:
            reports.append(str(a.get("report", "")))
            return "entregado"

        tools["submit_report"] = Tool(
            ToolDef(
                "submit_report",
                "Entrega tu trabajo terminado con un informe completo (qué hiciste, hallazgos, "
                "resultado).",
                _obj({"report": _S}, ["report"]),
            ),
            submit,
            terminal=True,
        )
        out = self._loop(
            agent,
            f"{self._ticket_context(t)}\n\nTe toca ejecutar este ticket. Explora lo necesario con "
            "las herramientas de lectura y entrega con submit_report un informe completo. Si es "
            "una devolución, atiende lo que pidió el revisor.",
            tools,
        )
        report = (reports[0] if reports else out).strip()
        if not report:
            raise LlmError("El agente no entregó ningún informe")
        self._post(agent=agent, body=report, ticket_id=t.id, scope="AGENT")
        boss = agents_repo.get_agent(self._db, agent.reports_to) if agent.reports_to else None
        senior = (
            boss is not None and boss.archived_at is None and is_senior_reviewer(boss.permissions)
        )
        self._move(t, "IN_SENIOR_REVIEW" if senior else "IN_QA", agent, "Trabajo entregado")

    def _review(self, t: Ticket, reviewer: Agent, approve_to: str) -> None:
        verdict: list[tuple[bool, str]] = []
        tools = self._read_tools(reviewer)

        def approve(a: dict[str, Any]) -> str:
            verdict.append((True, str(a.get("comment", ""))))
            return "aprobado"

        def reject(a: dict[str, Any]) -> str:
            verdict.append((False, str(a.get("reason", ""))))
            return "devuelto"

        tools["approve"] = Tool(
            ToolDef("approve", "Aprueba el trabajo.", _obj({"comment": _S}, ["comment"])),
            approve,
            True,
        )
        tools["reject"] = Tool(
            ToolDef(
                "reject",
                "Devuelve el trabajo con el motivo concreto (qué falta o está mal).",
                _obj({"reason": _S}, ["reason"]),
            ),
            reject,
            True,
        )
        self._loop(
            reviewer,
            f"{self._ticket_context(t)}\n\nRevisa el trabajo entregado contra los criterios de "
            "aceptación. Aprueba con approve si cumple; si no, reject con el motivo concreto. "
            "Sé exigente pero justo: no devuelvas por detalles menores.",
            tools,
        )
        if not verdict:
            raise LlmError("El revisor no decidió")
        ok, text = verdict[0]
        label = "Aprobado" if ok else "Devuelto"
        self._post(agent=reviewer, body=f"{label}. {text}".strip(), ticket_id=t.id, scope="AGENT")
        self._move(t, approve_to if ok else "RETURNED", reviewer, text[:900] or label)

    def _deliver(self, t: Ticket, cto: Agent, kids: list[Ticket]) -> None:
        """Subtareas listas: Sheldon resume, avisa al CEO y el pedido pasa a REVISIÓN CTO."""
        names = {a.id: a.name for a in agents_repo.list_agents(self._db)}
        sections = []
        for k in kids:
            msgs = [
                m
                for m in messages_repo.list_for_ticket(self._db, k.id, 12)
                if m.author_id == k.assigned_agent_id
            ]
            last = msgs[-1].body[:3000] if msgs else "(sin informe)"
            sections.append(f"### {k.title} — {names.get(k.assigned_agent_id or '', '?')}\n{last}")
        out: list[str] = []

        def deliver(a: dict[str, Any]) -> str:
            out.append(str(a.get("summary", "")))
            return "entregado"

        tools = {
            "deliver": Tool(
                ToolDef(
                    "deliver",
                    "Entrega el resumen final al CEO.",
                    _obj({"summary": _S}, ["summary"]),
                ),
                deliver,
                True,
            )
        }
        text = self._loop(
            cto,
            f"{self._ticket_context(t)}\n\nEl equipo terminó todo. Resultados:\n\n"
            + "\n\n".join(sections)
            + "\n\nEscribe para el CEO un resumen ejecutivo claro (qué se hizo, hallazgos y "
            "recomendaciones) y entrégalo con deliver.",
            tools,
        )
        self._deliver_text(t, cto, (out[0] if out else text) or "Trabajo terminado: revísalo.")

    def _deliver_text(self, t: Ticket, cto: Agent, summary: str) -> None:
        self._post(
            agent=cto,
            body=f"Listo para tu revisión: «{t.title}».\n\n{summary}",
            ticket_id=t.id,
            scope="GLOBAL",
        )
        current = tickets_repo.get_ticket(self._db, t.id)
        if current is not None and current.status == "IN_PROGRESS":
            current = self._move(current, "IN_QA", cto, "Resumen de Sheldon")
        if current is not None and current.status == "IN_QA":
            self._move(current, "IN_REVIEW", cto, "En Revisión CTO: el CEO decide si es HECHO")
