"""Repositorio de agentes: SQL parametrizado, sin lógica de negocio ni eventos."""

import json
from typing import Any

from app.db.database import Database, Row
from app.domain.schemas import Agent, AgentStatus

# Columnas que se guardan como JSON en `TEXT`.
JSON_FIELDS = {
    "avatar",
    "functions",
    "rules",
    "restrictions",
    "permissions",
    "model",
    "limits",
}
# Campos que `update_agent` acepta (nombres del dominio → columna).
UPDATABLE = {
    "name",
    "character",
    "role",
    "role_type",
    "avatar",
    "functions",
    "rules",
    "restrictions",
    "permissions",
    "model",
    "limits",
    "system_prompt",
    "is_cto",
    "current_task",
    "project",
}


def row_to_agent(r: Row) -> Agent:
    return Agent.model_validate(
        {
            "id": r["id"],
            "name": r["name"],
            "character": r["character"],
            "role": r["role"],
            "role_type": r["role_type"],
            "status": r["status"],
            "avatar": json.loads(r["avatar"]),
            "functions": json.loads(r["functions"]),
            "rules": json.loads(r["rules"]),
            "restrictions": json.loads(r["restrictions"]),
            "permissions": json.loads(r["permissions"]),
            "model": json.loads(r["model"]),
            "limits": json.loads(r["limits"]),
            "system_prompt": r["system_prompt"],
            "is_cto": bool(r["is_cto"]),
            "current_task": r["current_task"],
            "project": r["project"],
            "consecutive_failures": r["consecutive_failures"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
            "archived_at": r["archived_at"],
        }
    )


def list_agents(db: Database, include_archived: bool = False) -> list[Agent]:
    where = "" if include_archived else "WHERE archived_at IS NULL"
    rows = db.fetch_all(f"SELECT * FROM agents {where} ORDER BY created_at, name")  # noqa: S608
    return [row_to_agent(r) for r in rows]


def get_agent(db: Database, agent_id: str) -> Agent | None:
    row = db.fetch_one("SELECT * FROM agents WHERE id = ?", (agent_id,))
    return row_to_agent(row) if row else None


def find_active_by_name(db: Database, name: str) -> Agent | None:
    row = db.fetch_one("SELECT * FROM agents WHERE name = ? AND archived_at IS NULL", (name,))
    return row_to_agent(row) if row else None


def count_active(db: Database) -> int:
    row = db.fetch_one("SELECT COUNT(*) AS n FROM agents WHERE archived_at IS NULL")
    return int(row["n"]) if row else 0


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def insert_agent(db: Database, a: Agent) -> None:
    data = a.model_dump(by_alias=True, mode="json")
    db.execute(
        "INSERT INTO agents (id, name, character, role, role_type, status, avatar, functions,"
        " rules, restrictions, permissions, model, limits, system_prompt, is_cto, current_task,"
        " project, consecutive_failures, created_at, updated_at, archived_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            a.id,
            a.name,
            a.character,
            a.role,
            a.role_type,
            a.status,
            _dump(data["avatar"]),
            _dump(data["functions"]),
            _dump(data["rules"]),
            _dump(data["restrictions"]),
            _dump(data["permissions"]),
            _dump(data["model"]),
            _dump(data["limits"]),
            a.system_prompt,
            1 if a.is_cto else 0,
            a.current_task,
            a.project,
            a.consecutive_failures,
            a.created_at,
            a.updated_at,
            a.archived_at,
        ),
    )


def update_agent(db: Database, agent_id: str, fields: dict[str, Any], now: str) -> None:
    """Actualización parcial. `fields` usa nombres del dominio (snake_case) y valores ya
    serializables a JSON (dict/list) en los campos JSON. Campos desconocidos → ValueError."""
    unknown = set(fields) - UPDATABLE
    if unknown:
        raise ValueError(f"Campos no actualizables: {sorted(unknown)}")
    if not fields:
        return
    sets: list[str] = []
    args: list[Any] = []
    for name, value in fields.items():
        sets.append(f"{name} = ?")
        if name in JSON_FIELDS:
            args.append(_dump(value))
        elif name == "is_cto":
            args.append(1 if value else 0)
        else:
            args.append(value)
    sets.append("updated_at = ?")
    args.extend([now, agent_id])
    db.execute(f"UPDATE agents SET {', '.join(sets)} WHERE id = ?", tuple(args))  # noqa: S608


def set_status(
    db: Database, agent_id: str, status: AgentStatus, current_task: str | None, now: str
) -> None:
    db.execute(
        "UPDATE agents SET status = ?, current_task = ?, updated_at = ? WHERE id = ?",
        (status, current_task, now, agent_id),
    )


def set_failures(db: Database, agent_id: str, count: int, now: str) -> None:
    db.execute(
        "UPDATE agents SET consecutive_failures = ?, updated_at = ? WHERE id = ?",
        (count, now, agent_id),
    )


def archive_agent(db: Database, agent_id: str, now: str) -> None:
    db.execute(
        "UPDATE agents SET archived_at = ?, updated_at = ? WHERE id = ?", (now, now, agent_id)
    )


def restore_agent(db: Database, agent_id: str, now: str) -> None:
    db.execute("UPDATE agents SET archived_at = NULL, updated_at = ? WHERE id = ?", (now, agent_id))
