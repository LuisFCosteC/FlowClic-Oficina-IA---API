"""Repositorio de espacios de trabajo (tabla `workspaces`, J03)."""

from app.db.database import Database, Row
from app.domain.schemas import Workspace


def _to_model(r: Row) -> Workspace:
    return Workspace.model_validate(
        {
            "id": r["id"],
            "name": r["name"],
            "path": r["path"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }
    )


def list_all(db: Database) -> list[Workspace]:
    rows = db.fetch_all("SELECT * FROM workspaces ORDER BY id")
    return [_to_model(r) for r in rows]


def get(db: Database, ws_id: str) -> Workspace | None:
    row = db.fetch_one("SELECT * FROM workspaces WHERE id = ?", (ws_id,))
    return _to_model(row) if row else None


def existing_ids(db: Database, ids: list[str]) -> set[str]:
    if not ids:
        return set()
    marks = ", ".join("?" for _ in ids)
    rows = db.fetch_all(
        f"SELECT id FROM workspaces WHERE id IN ({marks})",  # noqa: S608 - solo "?" generados
        tuple(ids),
    )
    return {str(r["id"]) for r in rows}


def insert(db: Database, ws_id: str, name: str, path: str, now: str) -> None:
    db.execute(
        "INSERT INTO workspaces (id, name, path, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (ws_id, name, path, now, now),
    )


def update(db: Database, ws_id: str, name: str, path: str, now: str) -> None:
    db.execute(
        "UPDATE workspaces SET name = ?, path = ?, updated_at = ? WHERE id = ?",
        (name, path, now, ws_id),
    )


def delete(db: Database, ws_id: str) -> None:
    db.execute("DELETE FROM workspaces WHERE id = ?", (ws_id,))
