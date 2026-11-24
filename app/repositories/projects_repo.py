"""Repositorio de proyectos (tabla `projects`, PRJ01)."""

import json

from app.db.database import Database, Row
from app.domain.schemas import Project


def _to_model(r: Row) -> Project:
    return Project.model_validate(
        {
            "id": r["id"],
            "name": r["name"],
            "description": r["description"],
            "goals": json.loads(r["goals"]),
            "stack": json.loads(r["stack"]),
            "status": r["status"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }
    )


def list_projects(db: Database, include_archived: bool = False) -> list[Project]:
    where = "" if include_archived else "WHERE status = 'ACTIVE'"
    rows = db.fetch_all(f"SELECT * FROM projects {where} ORDER BY created_at, id")  # noqa: S608
    return [_to_model(r) for r in rows]


def get(db: Database, project_id: str) -> Project | None:
    row = db.fetch_one("SELECT * FROM projects WHERE id = ?", (project_id,))
    return _to_model(row) if row else None


def existing_ids(db: Database, ids: list[str]) -> set[str]:
    if not ids:
        return set()
    marks = ", ".join("?" for _ in ids)
    rows = db.fetch_all(
        f"SELECT id FROM projects WHERE id IN ({marks})",  # noqa: S608 - solo "?" generados
        tuple(ids),
    )
    return {str(r["id"]) for r in rows}


def insert(db: Database, p: Project) -> None:
    db.execute(
        "INSERT INTO projects (id, name, description, goals, stack, status, created_at,"
        " updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            p.id,
            p.name,
            p.description,
            json.dumps(p.goals, ensure_ascii=False),
            json.dumps(p.stack, ensure_ascii=False),
            p.status,
            p.created_at,
            p.updated_at,
        ),
    )


def update(db: Database, p: Project) -> None:
    db.execute(
        "UPDATE projects SET name = ?, description = ?, goals = ?, stack = ?, status = ?,"
        " updated_at = ? WHERE id = ?",
        (
            p.name,
            p.description,
            json.dumps(p.goals, ensure_ascii=False),
            json.dumps(p.stack, ensure_ascii=False),
            p.status,
            p.updated_at,
            p.id,
        ),
    )


def count_active_tickets(db: Database, project_id: str) -> int:
    row = db.fetch_one(
        "SELECT COUNT(*) AS n FROM tickets WHERE project_id = ? AND status <> 'DONE'",
        (project_id,),
    )
    return int(row["n"]) if row else 0
