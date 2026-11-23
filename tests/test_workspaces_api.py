import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db.database import Database

win_only = pytest.mark.skipif(sys.platform != "win32", reason="rutas de Windows")


def put(client: TestClient, ws_id: str, path: object, name: str = "API") -> object:
    return client.put(f"/api/admin/workspaces/{ws_id}", json={"name": name, "path": str(path)})


def agent_with_ws(client: TestClient, ws: dict[str, str], name: str = "Zed") -> object:
    return client.post(
        "/api/agents",
        json={"name": name, "role": "Dev", "permissions": {"workspaces": ws}},
    )


def test_crear_actualizar_listar_y_auditar(
    client: TestClient, tmp_path: Path, migrated_db: Database
) -> None:
    folder = tmp_path / "api"
    folder.mkdir()
    r = put(client, "api", folder)
    assert r.status_code == 201  # type: ignore[attr-defined]
    body = r.json()  # type: ignore[attr-defined]
    assert body["id"] == "api" and body["name"] == "API"
    assert Path(body["path"]) == folder
    r2 = put(client, "api", folder, name="API v2")
    assert r2.status_code == 200  # type: ignore[attr-defined]
    listed = client.get("/api/admin/workspaces").json()
    assert [w["name"] for w in listed] == ["API v2"]
    actions = [r["action"] for r in migrated_db.fetch_all("SELECT action FROM audit_log")]
    assert actions == ["workspace.created", "workspace.updated"]


@pytest.mark.parametrize("ws_id", ["Api", "1api", "a b", "x" * 33, "a.b"])
def test_id_logico_invalido_400(client: TestClient, tmp_path: Path, ws_id: str) -> None:
    r = put(client, ws_id, tmp_path)
    assert r.status_code in (400, 404)  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("path", "fragment"),
    [
        ("relativa/carpeta", "absoluta"),
        ("", "at least 1 character"),
        ("\\\\servidor\\compartida", "UNC"),
        ("//servidor/compartida", "UNC"),
    ],
)
def test_rutas_no_permitidas_400(client: TestClient, path: str, fragment: str) -> None:
    r = put(client, "api", path)
    assert r.status_code == 400  # type: ignore[attr-defined]
    assert fragment in r.json()["error"]["message"]  # type: ignore[attr-defined]


def test_no_existe_o_no_es_carpeta_y_punto_punto(client: TestClient, tmp_path: Path) -> None:
    r = put(client, "api", tmp_path / "no-existe")
    assert r.status_code == 400 and "no existe" in r.json()["error"]["message"]  # type: ignore[attr-defined]
    f = tmp_path / "archivo.txt"
    f.write_text("x")
    r = put(client, "api", f)
    assert r.status_code == 400 and "no es una carpeta" in r.json()["error"]["message"]  # type: ignore[attr-defined]
    r = put(client, "api", str(tmp_path) + "/sub/../..")
    assert r.status_code == 400 and ".." in r.json()["error"]["message"]  # type: ignore[attr-defined]


def test_raiz_de_unidad_y_carpeta_de_perfil(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    r = put(client, "api", tmp_path.anchor)
    assert r.status_code == 400 and "raíz" in r.json()["error"]["message"]  # type: ignore[attr-defined]
    profile = tmp_path / "perfil"
    profile.mkdir()
    (profile / "proyecto").mkdir()
    monkeypatch.setenv("USERPROFILE", str(profile))
    monkeypatch.setenv("HOME", str(profile))
    assert put(client, "api", profile).status_code == 400  # type: ignore[attr-defined]
    assert put(client, "api", profile / "proyecto").status_code == 201  # type: ignore[attr-defined]


@win_only
@pytest.mark.parametrize(
    "path", [r"C:\Windows", r"C:\Windows\System32", r"C:\Program Files", r"c:\program files (x86)"]
)
def test_carpetas_del_sistema_400(client: TestClient, path: str) -> None:
    r = put(client, "api", path)
    assert r.status_code == 400  # type: ignore[attr-defined]
    assert "sistema" in r.json()["error"]["message"]  # type: ignore[attr-defined]


def test_borrar_404_409_y_204(client: TestClient, tmp_path: Path) -> None:
    assert client.delete("/api/admin/workspaces/api").status_code == 404
    put(client, "api", tmp_path)
    assert agent_with_ws(client, {"api": "read"}).status_code == 201  # type: ignore[attr-defined]
    r = client.delete("/api/admin/workspaces/api")
    assert r.status_code == 409 and "Zed" in r.json()["error"]["message"]
    agent_id = client.get("/api/agents").json()[0]["id"]
    client.patch(f"/api/agents/{agent_id}", json={"permissions": {"workspaces": {}}})
    assert client.delete("/api/admin/workspaces/api").status_code == 204
    assert client.get("/api/admin/workspaces").json() == []


def test_check_no_lista_contenido(client: TestClient, tmp_path: Path) -> None:
    folder = tmp_path / "w"
    folder.mkdir()
    (folder / "secreto.txt").write_text("x")
    put(client, "docs", folder)
    r = client.post("/api/admin/workspaces/docs/check")
    assert r.status_code == 200
    assert r.json() == {"exists": True, "isDir": True, "writable": True}
    assert "secreto" not in r.text
    (folder / "secreto.txt").unlink()
    folder.rmdir()
    assert client.post("/api/admin/workspaces/docs/check").json() == {
        "exists": False,
        "isDir": False,
        "writable": False,
    }
    assert client.post("/api/admin/workspaces/nada/check").status_code == 404


def test_agente_con_espacio_inexistente_da_400_y_con_existente_201(
    client: TestClient, tmp_path: Path
) -> None:
    r = agent_with_ws(client, {"api": "read"})
    assert r.status_code == 400 and "api" in r.json()["error"]["message"]  # type: ignore[attr-defined]
    put(client, "api", tmp_path)
    r = agent_with_ws(client, {"api": "read"})
    assert r.status_code == 201  # type: ignore[attr-defined]
    agent = r.json()  # type: ignore[attr-defined]
    # la ruta nunca llega al agente ni a su prompt
    assert str(tmp_path) not in r.text  # type: ignore[attr-defined]
    assert str(tmp_path) not in agent["systemPrompt"]
    bad = client.patch(
        f"/api/agents/{agent['id']}", json={"permissions": {"workspaces": {"x": "read"}}}
    )
    assert bad.status_code == 400
