"""Administración: proyecto, límites y reglas (PLAN §13). Pendiente de S09: solo ADMIN."""

import json

from app.db.database import Database
from app.domain.admin_schemas import (
    LimitsSettings,
    ProjectSettings,
    Rule,
    RuleCreate,
    RuleOrder,
    RuleUpdate,
)
from app.errors import AppError, not_found, validation_error
from app.events.bus import EventBus
from app.repositories import settings_repo as repo
from app.security import audit
from app.util import new_id, now_iso

DEFAULT_LIMITS = LimitsSettings(
    max_agents=20, max_active_tickets_per_agent=3, require_approval_for_done=False
)


def _dump(model: ProjectSettings | LimitsSettings) -> dict[str, object]:
    return model.model_dump(by_alias=True, mode="json")


# ── Proyecto y límites ───────────────────────────────────────────────────────────────────────
def get_project(db: Database) -> ProjectSettings:
    raw = repo.get_value(db, "project")
    return ProjectSettings.model_validate(json.loads(raw)) if raw else ProjectSettings()


def get_limits(db: Database) -> LimitsSettings:
    raw = repo.get_value(db, "limits")
    return LimitsSettings.model_validate(json.loads(raw)) if raw else DEFAULT_LIMITS


def put_project(
    db: Database, bus: EventBus | None, body: ProjectSettings, user_id: str | None = None
) -> ProjectSettings:
    before = _dump(get_project(db))
    stored = ProjectSettings(company_name=body.company_name.strip())  # solo la empresa
    after = _dump(stored)
    changed = sorted(k for k, v in after.items() if before.get(k) != v)
    with db.transaction() as tx:
        repo.put_value(
            tx,
            "project",
            json.dumps({"companyName": stored.company_name}, ensure_ascii=False),
            user_id,
            now_iso(),
        )
        audit.record(
            tx,
            "settings.project_updated",
            target_type="settings",
            target_id="project",
            user_id=user_id,
            meta={"changedFields": changed},
        )
    if bus is not None:
        bus.emit("settings.updated", {"key": "project", "value": after})
    return stored


def put_limits(
    db: Database, bus: EventBus | None, body: LimitsSettings, user_id: str | None = None
) -> LimitsSettings:
    after = _dump(body)
    with db.transaction() as tx:
        repo.put_value(tx, "limits", json.dumps(after), user_id, now_iso())
        audit.record(
            tx,
            "settings.limits_updated",
            target_type="settings",
            target_id="limits",
            user_id=user_id,
            meta=after,
        )
    if bus is not None:
        bus.emit("settings.updated", {"key": "limits", "value": after})
    return body


# ── Reglas ───────────────────────────────────────────────────────────────────────────────────
def _rule_payload(rule: Rule) -> dict[str, object]:
    return rule.model_dump(by_alias=True, mode="json")


def list_rules(db: Database) -> list[Rule]:
    return repo.list_rules(db)


def _rule_or_404(db: Database, rule_id: str) -> Rule:
    rule = repo.get_rule(db, rule_id)
    if rule is None:
        raise not_found("Regla no encontrada")
    return rule


def create_rule(
    db: Database, bus: EventBus | None, body: RuleCreate, user_id: str | None = None
) -> Rule:
    title = body.title.strip()
    if not title:
        raise validation_error("title: no puede estar vacío")
    now = now_iso()
    rule = Rule(
        id=new_id(),
        title=title,
        description=body.description.strip(),
        severity=body.severity,
        enabled=body.enabled,
        position=0,
        created_at=now,
        updated_at=now,
    )
    with db.transaction() as tx:
        rule.position = repo.next_position(tx)
        repo.insert_rule(tx, rule)
        audit.record(
            tx,
            "rule.created",
            target_type="rule",
            target_id=rule.id,
            user_id=user_id,
            meta={"title": rule.title, "severity": rule.severity},
        )
    if bus is not None:
        bus.emit("rule.created", _rule_payload(rule))
    return rule


def update_rule(
    db: Database, bus: EventBus | None, rule_id: str, patch: RuleUpdate, user_id: str | None = None
) -> Rule:
    current = _rule_or_404(db, rule_id)
    changes = patch.model_dump(exclude_unset=True)
    if not changes:
        return current
    for field, value in changes.items():
        if value is None:
            raise validation_error(f"{field} no puede ser null")
    if "title" in changes:
        changes["title"] = changes["title"].strip()
        if not changes["title"]:
            raise validation_error("title: no puede estar vacío")
    if "description" in changes:
        changes["description"] = changes["description"].strip()
    updated = current.model_copy(update={**changes, "updated_at": now_iso()})
    with db.transaction() as tx:
        repo.update_rule(tx, updated)
        audit.record(
            tx,
            "rule.updated",
            target_type="rule",
            target_id=rule_id,
            user_id=user_id,
            meta={"changedFields": sorted(changes)},
        )
    if bus is not None:
        bus.emit("rule.updated", _rule_payload(updated))
    return updated


def delete_rule(
    db: Database, bus: EventBus | None, rule_id: str, user_id: str | None = None
) -> None:
    rule = _rule_or_404(db, rule_id)
    with db.transaction() as tx:
        repo.delete_rule(tx, rule_id)
        audit.record(
            tx,
            "rule.deleted",
            target_type="rule",
            target_id=rule_id,
            user_id=user_id,
            meta={"title": rule.title},
        )
    if bus is not None:
        bus.emit("rule.deleted", {"id": rule_id})


def reorder_rules(
    db: Database, bus: EventBus | None, body: RuleOrder, user_id: str | None = None
) -> list[Rule]:
    existing = [r.id for r in repo.list_rules(db)]
    if len(set(body.ids)) != len(body.ids) or sorted(body.ids) != sorted(existing):
        raise validation_error(
            "ids: debe contener todas las reglas existentes, sin repetir ni añadir otras"
        )
    now = now_iso()
    with db.transaction() as tx:
        for position, rule_id in enumerate(body.ids):
            repo.set_position(tx, rule_id, position, now)
        audit.record(
            tx, "rule.reordered", target_type="rule", user_id=user_id, meta={"count": len(body.ids)}
        )
    rules = repo.list_rules(db)
    if bus is not None:
        for rule in rules:
            bus.emit("rule.updated", _rule_payload(rule))
    return rules


# ── Aplicación de límites (A04) ──────────────────────────────────────────────────────────────
def limit_exceeded(message: str) -> AppError:
    return AppError("LIMIT_EXCEEDED", message)
