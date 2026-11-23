"""Repositorio de `app_settings` y `project_rules` (SQL parametrizado, sin lógica de negocio)."""

from app.db.database import Database, Row
from app.domain.admin_schemas import Rule


def get_value(db: Database, key: str) -> str | None:
    row = db.fetch_one("SELECT value FROM app_settings WHERE key = ?", (key,))
    return str(row["value"]) if row else None


def put_value(db: Database, key: str, value: str, user_id: str | None, now: str) -> None:
    db.execute(
        "INSERT INTO app_settings (key, value, updated_by, updated_at) VALUES (?, ?, ?, ?)"
        " ON CONFLICT(key) DO UPDATE SET value = excluded.value,"
        " updated_by = excluded.updated_by, updated_at = excluded.updated_at",
        (key, value, user_id, now),
    )


def _rule(r: Row) -> Rule:
    return Rule.model_validate(
        {
            "id": r["id"],
            "title": r["title"],
            "description": r["description"],
            "severity": r["severity"],
            "enabled": bool(r["enabled"]),
            "position": r["position"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }
    )


def list_rules(db: Database) -> list[Rule]:
    rows = db.fetch_all("SELECT * FROM project_rules ORDER BY position, created_at, id")
    return [_rule(r) for r in rows]


def get_rule(db: Database, rule_id: str) -> Rule | None:
    row = db.fetch_one("SELECT * FROM project_rules WHERE id = ?", (rule_id,))
    return _rule(row) if row else None


def next_position(db: Database) -> int:
    row = db.fetch_one("SELECT COALESCE(MAX(position), -1) + 1 AS n FROM project_rules")
    return int(row["n"]) if row else 0


def insert_rule(db: Database, rule: Rule) -> None:
    db.execute(
        "INSERT INTO project_rules (id, title, description, severity, enabled, position,"
        " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            rule.id,
            rule.title,
            rule.description,
            rule.severity,
            int(rule.enabled),
            rule.position,
            rule.created_at,
            rule.updated_at,
        ),
    )


def update_rule(db: Database, rule: Rule) -> None:
    db.execute(
        "UPDATE project_rules SET title = ?, description = ?, severity = ?, enabled = ?,"
        " updated_at = ? WHERE id = ?",
        (rule.title, rule.description, rule.severity, int(rule.enabled), rule.updated_at, rule.id),
    )


def delete_rule(db: Database, rule_id: str) -> None:
    db.execute("DELETE FROM project_rules WHERE id = ?", (rule_id,))


def set_position(db: Database, rule_id: str, position: int, now: str) -> None:
    db.execute(
        "UPDATE project_rules SET position = ?, updated_at = ? WHERE id = ?",
        (position, now, rule_id),
    )
