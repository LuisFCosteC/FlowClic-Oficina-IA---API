import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.db.database import Database
from app.db.migrate import MIGRATIONS_DIR, migrate
from app.events.bus import DomainEvent, get_bus

P = "/api/admin/projects"


@pytest.fixture
def events() -> Iterator[list[DomainEvent]]:
    seen: list[DomainEvent] = []
    off = get_bus().subscribe(seen.append)
    yield seen
    off()


def mk(client: TestClient, pid: str = "web", **kw: Any) -> dict[str, Any]:
    r = client.post(P, json={"id": pid, "name": "Web", **kw})
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


def test_crud_eventos_y_snapshot(client: TestClient, events: list[DomainEvent]) -> None:
    p = mk(client, goals=["g"], stack=["py"])
    assert p["status"] == "ACTIVE" and p["goals"] == ["g"]
    r = client.patch(f"{P}/web", json={"name": "Web 2", "description": "d"})
    assert r.json()["name"] == "Web 2"
    assert client.get("/api/snapshot").json()["projects"][0]["id"] == "web"
    types = [e.type for e in events]
    assert types == ["project.created", "project.updated"]


@pytest.mark.parametrize("pid", ["Web", "1web", "a b", "x" * 33, "-a", ""])
def test_id_invalido_400(client: TestClient, pid: str) -> None:
    assert client.post(P, json={"id": pid, "name": "X"}).status_code == 400


def test_id_repetido_409_y_patch_invalido(client: TestClient) -> None:
    mk(client)
    assert client.post(P, json={"id": "web", "name": "otro"}).status_code == 409
    assert client.patch(f"{P}/web", json={"name": None}).status_code == 400
    assert client.patch(f"{P}/web", json={"id": "z"}).status_code == 400
    assert client.patch(f"{P}/nope", json={"name": "x"}).status_code == 404


def test_archivar_restaurar_y_listado(client: TestClient, events: list[DomainEvent]) -> None:
    mk(client)
    assert client.post(f"{P}/web/archive").json()["status"] == "ARCHIVED"
    assert client.get(P).json() == []
    assert len(client.get(P, params={"includeArchived": "true"}).json()) == 1
    assert client.post(f"{P}/web/restore").json()["status"] == "ACTIVE"
    assert [e.type for e in events] == ["project.created", "project.archived", "project.updated"]
    assert client.post(f"{P}/nope/archive").status_code == 404


def test_no_se_archiva_con_tickets_activos(client: TestClient) -> None:
    mk(client)
    client.post("/api/agents", json={"name": "Sheldon", "role": "CTO", "roleType": "CTO"})
    t = client.post("/api/tickets", json={"title": "T", "requirement": "R", "projectId": "web"})
    assert t.status_code == 201
    assert t.json()["projectId"] == "web" and t.json()["project"] == "Web"
    r = client.post(f"{P}/web/archive")
    assert r.status_code == 409
    assert client.get(P).json()[0]["status"] == "ACTIVE"


def test_ticket_con_proyecto_inexistente_o_archivado_400(client: TestClient) -> None:
    client.post("/api/agents", json={"name": "Sheldon", "role": "CTO", "roleType": "CTO"})

    def post(**kw: str) -> int:
        body = {"title": "T", "requirement": "R", **kw}
        return client.post("/api/tickets", json=body).status_code

    assert post(projectId="no") == 400
    mk(client)
    client.post(f"{P}/web/archive")
    assert post(projectId="web") == 400
    assert post(project="web") == 400  # el texto libre ya no existe


def test_workspace_con_proyecto_y_kind(client: TestClient, tmp_path: Path) -> None:
    mk(client)
    folder = tmp_path / "w"
    folder.mkdir()
    url = "/api/admin/workspaces/api"
    r = client.put(
        url, json={"name": "API", "path": str(folder), "projectId": "web", "kind": "api"}
    )
    assert r.status_code == 201
    assert r.json()["projectId"] == "web" and r.json()["kind"] == "api"
    # al editar sin projectId/kind se conservan
    r2 = client.put(url, json={"name": "API 2", "path": str(folder)})
    assert r2.json()["projectId"] == "web" and r2.json()["kind"] == "api"
    # projectId: null lo deja vacío
    r3 = client.put(url, json={"name": "API 2", "path": str(folder), "projectId": None})
    assert r3.json()["projectId"] is None
    bad = client.put(url, json={"name": "A", "path": str(folder), "projectId": "no"})
    assert bad.status_code == 400
    assert client.put(url, json={"name": "A", "path": str(folder), "kind": "x"}).status_code == 400


def test_migracion_009_convierte_datos_existentes(raw_db: Database, tmp_path: Path) -> None:
    old = tmp_path / "old"
    old.mkdir()
    for f in MIGRATIONS_DIR.glob("*.sql"):
        if int(f.name.split("_")[0]) <= 8:
            shutil.copy(f, old / f.name)
    migrate(raw_db, old)
    raw_db.execute(
        "UPDATE app_settings SET value = ? WHERE key = 'project'",
        (
            '{"companyName":"Acme","projectName":"Página Web","description":"d",'
            '"goals":["g1"],"stack":["py"]}',
        ),
    )
    for i, project in enumerate(["FlowClic CRM", "flowclic crm", "Año Nuevo", None, ""]):
        raw_db.execute(
            "INSERT INTO tickets (id, title, project, created_at, updated_at)"
            " VALUES (?, 't', ?, 'n', 'n')",
            (f"t{i}", project),
        )
    raw_db.execute(
        "INSERT INTO workspaces (id, name, path, created_at, updated_at)"
        " VALUES ('front', 'F', 'x', 'n', 'n'), ('misc', 'M', 'x', 'n', 'n')"
    )
    migrate(raw_db)
    projects = {r["id"]: r for r in raw_db.fetch_all("SELECT * FROM projects")}
    assert set(projects) == {"pagina-web", "flowclic-crm", "ano-nuevo"}
    assert projects["pagina-web"]["goals"] == '["g1"]'
    assert projects["pagina-web"]["description"] == "d"
    tickets = {r["id"]: r["project_id"] for r in raw_db.fetch_all("SELECT * FROM tickets")}
    assert tickets == {
        "t0": "flowclic-crm",
        "t1": "flowclic-crm",
        "t2": "ano-nuevo",
        "t3": None,
        "t4": None,
    }
    setting = raw_db.fetch_one("SELECT value FROM app_settings WHERE key = 'project'")
    assert setting is not None and setting["value"] == '{"companyName":"Acme"}'
    kinds = {r["id"]: r["kind"] for r in raw_db.fetch_all("SELECT id, kind FROM workspaces")}
    assert kinds == {"front": "front", "misc": "other"}


def test_seed_demo_crea_proyectos(seeded_client: TestClient) -> None:
    ids = {p["id"] for p in seeded_client.get(P).json()}
    assert ids == {"flowclic-web", "flowclic-crm"}
