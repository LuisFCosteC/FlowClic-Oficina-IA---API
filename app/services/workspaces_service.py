"""Espacios de trabajo: id lógico → carpeta local (J03).

La ruta NUNCA va al system_prompt ni se expone a los agentes: solo la usará el orquestador en
la Fase 2. Pendiente de S09: estas rutas exigirán ADMIN.
"""

import os

from app.db.database import Database
from app.domain.agent_policy import effective_access
from app.domain.schemas import (
    Agent,
    AgentWorkspaceView,
    Workspace,
    WorkspaceBody,
    WorkspaceCheck,
)
from app.domain.workspace_paths import WORKSPACE_ID, validate_workspace_path
from app.errors import not_found, validation_error
from app.repositories import workspaces_repo as repo
from app.security import audit
from app.services import projects_service
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
    sent = body.model_fields_set
    project_id = (
        body.project_id if "project_id" in sent else (existing.project_id if existing else None)
    )
    kind = body.kind or (existing.kind if existing else "other")
    if project_id is not None and not (existing and existing.project_id == project_id):
        projects_service.require_active(db, project_id)
    now = now_iso()
    with db.transaction() as tx:
        if existing is None:
            repo.insert(tx, ws_id, name, path, project_id, kind, now)
        else:
            repo.update(tx, ws_id, name, path, project_id, kind, now)
        audit.record(
            tx,
            "workspace.created" if existing is None else "workspace.updated",
            target_type="workspace",
            target_id=ws_id,
            meta={"name": name, "path": path, "projectId": project_id, "kind": kind},
        )
    return get_or_404(db, ws_id), existing is None


def delete(db: Database, ws_id: str) -> None:
    ws = get_or_404(db, ws_id)
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


def workspaces_for_agent(db: Database, agent: Agent) -> list[AgentWorkspaceView]:
    """Lo que un agente puede saber de sus espacios (PERM01): id, nombre, tipo, proyecto y nivel.

    NUNCA incluye la ruta local: esa solo la usa el servidor/orquestador.
    """
    views: list[AgentWorkspaceView] = []
    for ws in repo.list_all(db):
        level = effective_access(agent.permissions, kind=ws.kind, project_id=ws.project_id)
        if level != "none":
            views.append(
                AgentWorkspaceView(
                    id=ws.id, name=ws.name, kind=ws.kind, project_id=ws.project_id, access=level
                )
            )
    return views
