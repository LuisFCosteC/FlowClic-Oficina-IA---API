"""Proyectos (PRJ01). Pendiente de S09: las rutas exigirán ADMIN."""

from app.db.database import Database, IntegrityError
from app.domain.schemas import Permissions, Project, ProjectCreate, ProjectUpdate
from app.errors import conflict, not_found, validation_error
from app.events.bus import EventBus
from app.repositories import projects_repo as repo
from app.security import audit
from app.util import now_iso


def payload(p: Project) -> dict[str, object]:
    return p.model_dump(by_alias=True, mode="json")


def list_projects(db: Database, include_archived: bool = False) -> list[Project]:
    return repo.list_projects(db, include_archived)


def get_or_404(db: Database, project_id: str) -> Project:
    project = repo.get(db, project_id)
    if project is None:
        raise not_found("Proyecto no encontrado")
    return project


def require_active(db: Database, project_id: str, field: str = "projectId") -> Project:
    """400 si el proyecto no existe o está archivado (para asignarlo a tickets/espacios)."""
    project = repo.get(db, project_id)
    if project is None:
        raise validation_error(
            f"{field}: el proyecto «{project_id}» no existe",
            [{"path": field, "message": f"no existe: {project_id}"}],
        )
    if project.status != "ACTIVE":
        raise validation_error(
            f"{field}: el proyecto «{project_id}» está archivado",
            [{"path": field, "message": f"archivado: {project_id}"}],
        )
    return project


def ensure_projects_exist(db: Database, permissions: Permissions) -> None:
    """400 si `projectScope` nombra proyectos que no existen (PERM01)."""
    scope = permissions.project_scope
    if scope == "ALL":
        return
    missing = sorted(set(scope) - repo.existing_ids(db, list(scope)))
    if missing:
        raise validation_error(
            f"permissions.projectScope: el proyecto «{missing[0]}» no existe",
            [{"path": "permissions.projectScope", "message": f"no existe: {m}"} for m in missing],
        )


def create(db: Database, bus: EventBus | None, body: ProjectCreate) -> Project:
    name = body.name.strip()
    if not name:
        raise validation_error("name: no puede estar vacío")
    if repo.get(db, body.id) is not None:
        raise conflict(f"Ya existe un proyecto con id «{body.id}»")
    now = now_iso()
    project = Project(
        id=body.id,
        name=name,
        description=body.description.strip(),
        goals=[g.strip() for g in body.goals if g.strip()],
        stack=[s.strip() for s in body.stack if s.strip()],
        status="ACTIVE",
        created_at=now,
        updated_at=now,
    )
    try:
        with db.transaction() as tx:
            repo.insert(tx, project)
            audit.record(
                tx,
                "project.created",
                target_type="project",
                target_id=project.id,
                meta={"name": name},
            )
    except IntegrityError:
        raise conflict(f"Ya existe un proyecto con id «{body.id}»") from None
    if bus is not None:
        bus.emit("project.created", payload(project))
    return project


def update(db: Database, bus: EventBus | None, project_id: str, patch: ProjectUpdate) -> Project:
    current = get_or_404(db, project_id)
    changes = patch.model_dump(exclude_unset=True)
    if not changes:
        return current
    for field, value in changes.items():
        if value is None:
            raise validation_error(f"{field} no puede ser null")
    if "name" in changes:
        changes["name"] = changes["name"].strip()
        if not changes["name"]:
            raise validation_error("name: no puede estar vacío")
    if "description" in changes:
        changes["description"] = changes["description"].strip()
    for key in ("goals", "stack"):
        if key in changes:
            changes[key] = [i.strip() for i in changes[key] if i.strip()]
    updated = current.model_copy(update={**changes, "updated_at": now_iso()})
    with db.transaction() as tx:
        repo.update(tx, updated)
        audit.record(
            tx,
            "project.updated",
            target_type="project",
            target_id=project_id,
            meta={"changedFields": sorted(changes)},
        )
    if bus is not None:
        bus.emit("project.updated", payload(updated))
    return updated


def archive(db: Database, bus: EventBus | None, project_id: str) -> Project:
    current = get_or_404(db, project_id)
    if current.status == "ARCHIVED":
        return current
    active = repo.count_active_tickets(db, project_id)
    if active > 0:
        raise conflict(f"El proyecto tiene {active} tickets activos: termínalos antes de archivar")
    archived = current.model_copy(update={"status": "ARCHIVED", "updated_at": now_iso()})
    with db.transaction() as tx:
        repo.update(tx, archived)
        audit.record(tx, "project.archived", target_type="project", target_id=project_id)
    if bus is not None:
        bus.emit("project.archived", payload(archived))
    return archived


def restore(db: Database, bus: EventBus | None, project_id: str) -> Project:
    current = get_or_404(db, project_id)
    if current.status == "ACTIVE":
        return current
    restored = current.model_copy(update={"status": "ACTIVE", "updated_at": now_iso()})
    with db.transaction() as tx:
        repo.update(tx, restored)
        audit.record(tx, "project.restored", target_type="project", target_id=project_id)
    if bus is not None:
        bus.emit("project.updated", payload(restored))
    return restored
