"""Lectura de los espacios de trabajo para los agentes (solo lectura, con permisos duros).

Todo lo decide el código: acceso efectivo del agente (PERM01), restricción 2 (nada de `.env` ni
llaves), la ruta no puede salir de la carpeta del workspace y hay topes de tamaño.
"""

import os
from pathlib import Path

from app.db.database import Database
from app.domain.agent_policy import effective_access, enforce_path_allowed
from app.domain.schemas import Agent, Workspace
from app.errors import AppError
from app.repositories import workspaces_repo

MAX_FILE_BYTES = 60_000
MAX_ENTRIES = 200
_SKIP_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    "dist",
    "build",
    ".next",
    ".idea",
    ".vscode",
    "coverage",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
}


def visible_workspaces(db: Database, agent: Agent) -> list[Workspace]:
    """Workspaces a los que el agente tiene algún acceso (nunca expone la ruta local)."""
    out: list[Workspace] = []
    for ws in workspaces_repo.list_all(db):
        level = effective_access(agent.permissions, kind=ws.kind, project_id=ws.project_id)
        if level != "none":
            out.append(ws)
    return out


def _resolve(db: Database, agent: Agent, workspace_id: str, rel: str) -> tuple[Workspace, Path]:
    ws = next((w for w in visible_workspaces(db, agent) if w.id == workspace_id), None)
    if ws is None:
        raise AppError("FORBIDDEN", f"No tienes acceso al espacio de trabajo «{workspace_id}»")
    enforce_path_allowed(rel)
    root = Path(ws.path).resolve()
    target = (root / rel).resolve() if rel not in ("", ".") else root
    if root != target and root not in target.parents:
        raise AppError("FORBIDDEN", "La ruta sale del espacio de trabajo")
    if target != root:
        # Un enlace simbólico no puede esconder un archivo sensible tras un nombre inocente:
        # se revisa también la ruta REAL y no se admiten enlaces en ningún tramo.
        enforce_path_allowed(str(target.relative_to(root)))
        probe = root / rel
        between = []
        for parent in probe.parents:
            if parent == root:
                break
            between.append(parent)
        if probe.is_symlink() or any(p.is_symlink() for p in between):
            raise AppError("FORBIDDEN", "No se permiten enlaces simbólicos")
    return ws, target


def list_dir(db: Database, agent: Agent, workspace_id: str, rel: str = "") -> str:
    _, target = _resolve(db, agent, workspace_id, rel)
    if not target.is_dir():
        raise AppError("NOT_FOUND", "La carpeta no existe")
    names: list[str] = []
    for entry in sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
        if entry.is_symlink() or (entry.is_dir() and entry.name in _SKIP_DIRS):
            continue
        try:
            enforce_path_allowed(entry.name)
        except AppError:
            continue  # los archivos sensibles ni siquiera se listan
        names.append(entry.name + ("/" if entry.is_dir() else ""))
        if len(names) >= MAX_ENTRIES:
            names.append("… (más entradas omitidas)")
            break
    return "\n".join(names) if names else "(carpeta vacía)"


def read_file(db: Database, agent: Agent, workspace_id: str, rel: str) -> str:
    _, target = _resolve(db, agent, workspace_id, rel)
    if not target.is_file():
        raise AppError("NOT_FOUND", "El archivo no existe")
    size = target.stat().st_size
    with target.open("rb") as fh:
        raw = fh.read(MAX_FILE_BYTES)
    if b"\x00" in raw[:2048]:
        raise AppError("VALIDATION_ERROR", "Es un archivo binario: no se puede leer como texto")
    text = raw.decode("utf-8", errors="replace")
    if size > MAX_FILE_BYTES:
        text += f"\n… (recortado: el archivo pesa {size} bytes)"
    return text


def tree(db: Database, agent: Agent, workspace_id: str, rel: str = "", depth: int = 2) -> str:
    """Árbol corto (2 niveles) para orientarse sin pedir carpeta por carpeta."""
    _, target = _resolve(db, agent, workspace_id, rel)
    lines: list[str] = []

    def walk(path: Path, level: int, prefix: str) -> None:
        if len(lines) >= MAX_ENTRIES:
            return
        try:
            entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        except OSError:
            return
        for e in entries:
            if e.is_symlink() or (e.is_dir() and e.name in _SKIP_DIRS):
                continue
            try:
                enforce_path_allowed(e.name)
            except AppError:
                continue
            lines.append(f"{prefix}{e.name}{'/' if e.is_dir() else ''}")
            if e.is_dir() and level < depth:
                walk(e, level + 1, prefix + "  ")

    walk(target, 1, "")
    return "\n".join(lines) if lines else "(carpeta vacía)"


def exists(path: str) -> bool:
    return os.path.isdir(path)
