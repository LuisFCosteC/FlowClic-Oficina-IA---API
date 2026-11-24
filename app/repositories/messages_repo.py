"""Mensajes del chat de mando y eventos de ticket para el hilo (SQL parametrizado)."""

from typing import Any

from app.db.database import Database, Row
from app.domain.schemas import Message, ThreadEntry


def row_to_message(r: Row) -> Message:
    return Message.model_validate(
        {
            "id": r["id"],
            "scope": r["scope"],
            "agent_id": r["agent_id"],
            "author_type": r["author_type"],
            "author_id": r["author_id"],
            "kind": r["kind"],
            "body": r["body"],
            "status": r["status"],
            "ticket_id": r["ticket_id"],
            "created_at": r["created_at"],
        }
    )


def insert_message(db: Database, m: Message) -> None:
    db.execute(
        "INSERT INTO agent_messages (id, scope, agent_id, author_type, author_id, kind, body,"
        " status, ticket_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            m.id,
            m.scope,
            m.agent_id,
            m.author_type,
            m.author_id,
            m.kind,
            m.body,
            m.status,
            m.ticket_id,
            m.created_at,
        ),
    )


def message_entry(m: Message) -> ThreadEntry:
    return ThreadEntry(
        id=m.id,
        entry_type="MESSAGE",
        kind=m.kind,
        scope=m.scope,
        agent_id=m.agent_id,
        author_type=m.author_type,
        author_id=m.author_id,
        body=m.body,
        status=m.status,
        ticket_id=m.ticket_id,
        created_at=m.created_at,
    )


def list_messages(
    db: Database, *, agent_id: str | None, everything: bool, limit: int
) -> list[Message]:
    """Mensajes más recientes primero (el servicio los ordena).

    - `everything`: todos (hilo de Sheldon: globales + copia de las individuales).
    - `agent_id`: solo los dirigidos a ese agente.
    - ninguno de los dos: solo los globales.
    """
    sql = "SELECT * FROM agent_messages"
    args: list[Any] = []
    if everything:
        pass
    elif agent_id is not None:
        sql += " WHERE agent_id = ?"
        args.append(agent_id)
    else:
        sql += " WHERE scope = 'GLOBAL'"
    sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
    args.append(limit)
    return [row_to_message(r) for r in db.fetch_all(sql, tuple(args))]


def list_ticket_event_entries(
    db: Database, *, agent_id: str | None, limit: int
) -> list[ThreadEntry]:
    """Eventos de ticket (del agente, o de todos si `agent_id` es None) como líneas del hilo."""
    sql = (
        "SELECT e.id, e.ticket_id, e.type, e.from_value, e.to_value, e.actor, e.created_at,"
        " t.title, t.assigned_agent_id FROM ticket_events e JOIN tickets t ON t.id = e.ticket_id"
    )
    args: list[Any] = []
    if agent_id is not None:
        sql += " WHERE t.assigned_agent_id = ?"
        args.append(agent_id)
    sql += " ORDER BY e.created_at DESC, e.id DESC LIMIT ?"
    args.append(limit)
    out: list[ThreadEntry] = []
    for r in db.fetch_all(sql, tuple(args)):
        change = (
            f"{r['from_value']} → {r['to_value']}" if r["from_value"] else str(r["to_value"] or "")
        )
        body = f"«{r['title']}»: {r['type']}" + (f" ({change})" if change else "")
        out.append(
            ThreadEntry(
                id=str(r["id"]),
                entry_type="TICKET_EVENT",
                kind=str(r["type"]),
                scope=None,
                agent_id=r["assigned_agent_id"],
                author_type=None,
                author_id=str(r["actor"]),
                body=body,
                status=None,
                ticket_id=str(r["ticket_id"]),
                created_at=str(r["created_at"]),
            )
        )
    return out


def list_for_ticket(db: Database, ticket_id: str, limit: int = 30) -> list[Message]:
    """Mensajes de un ticket (informes, revisiones, órdenes), del más viejo al más nuevo."""
    rows = db.fetch_all(
        "SELECT * FROM agent_messages WHERE ticket_id = ?"
        " ORDER BY created_at DESC, id DESC LIMIT ?",
        (ticket_id, limit),
    )
    return [row_to_message(r) for r in reversed(rows)]


def list_pending_human(db: Database, limit: int = 20) -> list[Message]:
    """Órdenes y preguntas del CEO que aún no se han atendido (las más viejas primero)."""
    rows = db.fetch_all(
        "SELECT * FROM agent_messages WHERE author_type = 'HUMAN' AND status = 'PENDING'"
        " ORDER BY created_at, id LIMIT ?",
        (limit,),
    )
    return [row_to_message(r) for r in rows]


def set_status(db: Database, message_id: str, status: str) -> None:
    db.execute("UPDATE agent_messages SET status = ? WHERE id = ?", (status, message_id))
