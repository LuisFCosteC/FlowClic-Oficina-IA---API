"""Espacios de trabajo: id lógico → carpeta local (J03).

La ruta NUNCA va al system_prompt ni se expone a los agentes: solo la usará el orquestador en
la Fase 2. Pendiente de S09: estas rutas exigirán ADMIN.
"""

import os

from app.db.database import Database
from app.domain.schemas import Permissions, Workspace, WorkspaceBody, WorkspaceCheck
from app.domain.workspace_paths import WORKSPACE_ID, validate_workspace_path
from app.errors import conflict, not_found, validation_error
from app.repositories import agents_repo
from app.repositories import workspaces_repo as repo
from app.security import audit
from app.util import now_iso


def _valid_id(ws_id: str) -> str:
    if not WORKSPACE_ID.match(ws_id):
        raise validation_error(
            "id: usa un identificador lógico (minúsculas, números, - y _; hasta 32 caracteres)"
        )
    return ws_id


def list_workspaces(db: Database) -> list[Workspace]:
    return repo.list_all(db)


def get_or_404(db: Database, ws_id: str) -> Workspace:
    ws = repo.get(db, ws_id)
    if ws is None:
        raise not_found("Espacio de trabajo no encontrado")
    return ws


def upsert(db: Database, ws_id: str, body: WorkspaceBody) -> tuple[Workspace, bool]:
    """Crea o actualiza. Devuelve (espacio, creado)."""
    _valid_id(ws_id)
    name = body.name.strip()
    if not name:
        raise validation_error("name: no puede estar vacío")
    path = validate_workspace_path(body.path)
    existing = repo.get(db, ws_id)
    now = now_iso()
    with db.transaction() as tx:
        if existing is None:
            repo.insert(tx, ws_id, name, path, now)
        else:
            repo.update(tx, ws_id, name, path, now)
        audit.record(
            tx,
            "workspace.created" if existing is None else "workspace.updated",
            target_type="workspace",
            target_id=ws_id,
            meta={"name": name, "path": path},
        )
    return get_or_404(db, ws_id), existing is None


def delete(db: Database, ws_id: str) -> None:
    ws = get_or_404(db, ws_id)
    users = [a.name for a in agents_repo.list_agents(db) if ws_id in a.permissions.workspaces]
    if users:
        raise conflict(
            f"El espacio «{ws_id}» lo usan estos agentes: {', '.join(sorted(users))}. "
            "Quítalo de sus permisos antes de borrarlo"
        )
    with db.transaction() as tx:
        repo.delete(tx, ws_id)
        audit.record(
            tx,
            "workspace.deleted",
            target_type="workspace",
            target_id=ws_id,
            meta={"name": ws.name, "path": ws.path},
        )


def check(db: Database, ws_id: str) -> WorkspaceCheck:
    """Comprueba la carpeta SIN listar su contenido. Ruta no permitida → 400."""
    ws = get_or_404(db, ws_id)
    path = validate_workspace_path(ws.path, must_exist=False)
    exists = os.path.exists(path)
    is_dir = exists and os.path.isdir(path)
    return WorkspaceCheck(
        exists=exists,
        is_dir=is_dir,
        writable=is_dir and os.access(path, os.W_OK),
    )


def ensure_workspaces_exist(db: Database, permissions: Permissions) -> None:
    """400 si un agente referencia un espacio de trabajo que no existe en la tabla."""
    ids = list(permissions.workspaces)
    missing = sorted(set(ids) - repo.existing_ids(db, ids))
    if missing:
        raise validation_error(
            f"permissions.workspaces: el espacio «{missing[0]}» no existe; créalo antes",
            [{"path": "permissions.workspaces", "message": f"no existe: {w}"} for w in missing],
        )
