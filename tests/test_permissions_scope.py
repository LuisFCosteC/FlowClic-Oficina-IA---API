import json
import shutil
from itertools import product
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db.database import Database
from app.db.migrate import MIGRATIONS_DIR, migrate
from app.domain.agent_policy import effective_access
from app.domain.schemas import Permissions
from app.repositories import agents_repo
from app.services import workspaces_service


def perms(**kw: object) -> Permissions:
    return Permissions.model_validate(kw)


LEVELS = ["none", "read", "tests", "qa_report", "write"]
KINDS = ["api", "front", "docs", "mobile", "other"]


@pytest.mark.parametrize(("kind", "level"), list(product(KINDS, LEVELS)))
def test_nivel_por_tipo_con_alcance_all(kind: str, level: str) -> None:
    p = perms(folderAccess={kind: level}, projectScope="ALL")
    assert effective_access(p, kind=kind, project_id="web") == level
    assert effective_access(p, kind=kind, project_id=None) == level  # sin proyecto: ALL lo ve
    for other in KINDS:
        if other != kind:
            assert effective_access(p, kind=other, project_id="web") == "none"


def test_alcance_por_lista_de_proyectos() -> None:
    p = perms(folderAccess={"api": "write"}, projectScope=["web"])
    assert effective_access(p, kind="api", project_id="web") == "write"
    assert effective_access(p, kind="api", project_id="crm") == "none"
    assert effective_access(p, kind="api", project_id=None) == "none"  # sin proyecto: solo ALL
    assert effective_access(p, kind="front", project_id="web") == "none"


def test_alcance_vacio_no_ve_nada_y_all_incluye_proyectos_futuros() -> None:
    assert effective_access(perms(folderAccess={"api": "read"}), kind="api", project_id="x") == (
        "none"
    )
    p = perms(folderAccess={"api": "read"}, projectScope="ALL")
    assert effective_access(p, kind="api", project_id="proyecto-futuro") == "read"


def test_workspaces_for_agent_sin_ruta(
    client: TestClient, migrated_db: Database, tmp_path: Path
) -> None:
    client.post("/api/admin/projects", json={"id": "web", "name": "Web"})
    client.post("/api/admin/projects", json={"id": "crm", "name": "CRM"})
    for ws_id, kind, project in [
        ("w-api", "api", "web"),
        ("c-api", "api", "crm"),
        ("w-doc", "docs", "web"),
        ("huerfano", "api", None),
    ]:
        d = tmp_path / ws_id
        d.mkdir()
        body = {"name": ws_id, "path": str(d), "kind": kind, "projectId": project}
        assert client.put(f"/api/admin/workspaces/{ws_id}", json=body).status_code == 201
    r = client.post(
        "/api/agents",
        json={
            "name": "Zed",
            "role": "Dev",
            "permissions": {
                "folderAccess": {"api": "write", "docs": "read"},
                "projectScope": ["web"],
            },
        },
    )
    assert r.status_code == 201
    agent = agents_repo.get_agent(migrated_db, r.json()["id"])
    assert agent is not None
    views = workspaces_service.workspaces_for_agent(migrated_db, agent)
    assert {(v.id, v.access) for v in views} == {("w-api", "write"), ("w-doc", "read")}
    dumped = json.dumps([v.model_dump(by_alias=True) for v in views])
    assert str(tmp_path) not in dumped and "path" not in dumped.lower()
    assert str(tmp_path) not in r.text and str(tmp_path) not in agent.system_prompt


@pytest.mark.parametrize(
    "permissions",
    [
        {"projectScope": ["no-existe"]},
        {"projectScope": "ALGUNOS"},
        {"folderAccess": {"api": "root"}},
        {"folderAccess": {"nube": "read"}},
        {"workspaces": {"api": "read"}},
    ],
)
def test_validacion_400(client: TestClient, permissions: dict[str, object]) -> None:
    r = client.post("/api/agents", json={"name": "Zed", "role": "Dev", "permissions": permissions})
    assert r.status_code == 400


def test_migracion_010_toma_el_nivel_maximo_por_tipo(raw_db: Database, tmp_path: Path) -> None:
    old = tmp_path / "old"
    old.mkdir()
    for f in MIGRATIONS_DIR.glob("*.sql"):
        if int(f.name.split("_")[0]) <= 9:
            shutil.copy(f, old / f.name)
    migrate(raw_db, old)
    raw_db.execute(
        "INSERT INTO workspaces (id, name, path, kind, created_at, updated_at) VALUES"
        " ('api', 'A', 'x', 'api', 'n', 'n'), ('api2', 'A2', 'x', 'api', 'n', 'n'),"
        " ('docs', 'D', 'x', 'docs', 'n', 'n'), ('web', 'W', 'x', 'front', 'n', 'n')"
    )
    legacy = {
        "workspaces": {"api": "read", "api2": "tests", "docs": "qa_report", "web": "none"},
        "actions": ["repo.read"],
        "ticketTransitions": [["IN_QA", "RETURNED"]],
        "onlyAssignedTickets": False,
    }
    for aid in ("a1", "a2"):
        raw_db.execute(
            "INSERT INTO agents (id, name, character, role, created_at, updated_at, permissions)"
            " VALUES (?, ?, 'c', 'r', 'n', 'n', ?)",
            (aid, aid, json.dumps(legacy)),
        )
    migrate(raw_db)
    for row in raw_db.fetch_all("SELECT permissions FROM agents"):
        p = json.loads(row["permissions"])
        assert p == {
            "folderAccess": {
                "api": "tests",
                "front": "none",
                "docs": "qa_report",
                "mobile": "none",
                "other": "none",
            },
            "projectScope": "ALL",
            "actions": ["repo.read"],
            "ticketTransitions": [["IN_QA", "RETURNED"]],
            "onlyAssignedTickets": False,
        }
        Permissions.model_validate(p)  # el modelo nuevo lo acepta
    audits = raw_db.fetch_all(
        "SELECT target_id FROM audit_log WHERE action = ?", ("agent.permissions_migrated",)
    )
    assert {a["target_id"] for a in audits} == {"a1", "a2"}
