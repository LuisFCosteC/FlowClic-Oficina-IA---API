from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db.database import Database, clear_db
from app.main import create_app
from app.security.crypto import SecretBox, generate_master_key
from app.security.vault import Vault

LOCAL = {"base_url": "http://localhost", "client": ("127.0.0.1", 50000)}
DOC_PATHS = ("/api/docs", "/api/redoc", "/api/openapi.json")
ROOT_PATHS = ("/docs", "/redoc", "/openapi.json")


def make_client(db: Database, settings: Settings, **kw: object) -> TestClient:
    app = create_app(settings, db)
    return TestClient(app, **{**LOCAL, **kw})  # type: ignore[arg-type]


def test_local_con_docs_activados_sirve_swagger_redoc_y_el_esquema(client: TestClient) -> None:
    docs = client.get("/api/docs")
    assert docs.status_code == 200 and "text/html" in docs.headers["content-type"]
    assert "/api/openapi.json" in docs.text  # Swagger apunta al esquema bajo /api
    assert client.get("/api/redoc").status_code == 200
    spec = client.get("/api/openapi.json")
    assert spec.status_code == 200
    assert spec.json()["info"]["title"].startswith("FlowClic")


@pytest.mark.parametrize("path", ROOT_PATHS)
def test_las_rutas_antiguas_de_la_raiz_dan_404(client: TestClient, path: str) -> None:
    r = client.get(path)
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.parametrize("path", DOC_PATHS)
def test_docs_enabled_false_da_404_tambien_en_api_docs(migrated_db: Database, path: str) -> None:
    settings = Settings(_env_file=None, node_env="test", docs_enabled=False)  # type: ignore[call-arg]
    with make_client(migrated_db, settings) as c:
        assert c.get(path).status_code == 404


def test_en_produccion_la_documentacion_esta_apagada_por_defecto(migrated_db: Database) -> None:
    key = generate_master_key()
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None, node_env="production", app_master_key=key, session_secret=key
    )
    with make_client(migrated_db, settings) as c:
        for path in DOC_PATHS:
            assert c.get(path).status_code == 404
    on = Settings(  # type: ignore[call-arg]
        _env_file=None,
        node_env="production",
        app_master_key=key,
        session_secret=key,
        docs_enabled=True,
    )
    with make_client(migrated_db, on) as c:
        assert c.get("/api/docs").status_code == 200


@pytest.mark.parametrize("path", DOC_PATHS)
def test_desde_otra_ip_no_se_sirve_y_no_revela_que_existe(
    migrated_db: Database, test_settings: Settings, path: str
) -> None:
    with make_client(migrated_db, test_settings, client=("10.0.0.5", 50000)) as c:
        r = c.get(path)
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.parametrize(
    "headers",
    [
        {"X-Forwarded-For": "203.0.113.9"},
        {"Forwarded": "for=203.0.113.9"},
        {"X-Real-IP": "203.0.113.9"},
        {"Host": "api.ejemplo.com"},
    ],
)
def test_tras_un_proxy_o_con_host_ajeno_no_se_sirve(
    client: TestClient, headers: dict[str, str]
) -> None:
    for path in DOC_PATHS:
        assert client.get(path, headers=headers).status_code == 404


def test_la_documentacion_no_aparece_en_el_propio_esquema(client: TestClient) -> None:
    paths = client.get("/api/openapi.json").json()["paths"]
    for hidden in DOC_PATHS:
        assert hidden not in paths
    assert "/api/health" in paths


def test_csp_de_swagger_permitida_solo_en_la_documentacion(client: TestClient) -> None:
    assert "cdn.jsdelivr.net" in client.get("/api/docs").headers["content-security-policy"]
    assert "cdn.jsdelivr.net" in client.get("/api/redoc").headers["content-security-policy"]
    assert (
        "cdn.jsdelivr.net" not in client.get("/api/openapi.json").headers["content-security-policy"]
    )


def test_en_modo_setup_la_documentacion_sigue_disponible_en_local(
    test_settings: Settings, tmp_path: Path
) -> None:
    clear_db()
    key = generate_master_key()
    vault = Vault(tmp_path / "v.db", SecretBox.from_base64(key))
    app = create_app(test_settings, None, vault)
    with TestClient(app, **LOCAL) as c:  # type: ignore[arg-type]
        assert c.get("/api/docs").status_code == 200
        assert c.get("/api/openapi.json").status_code == 200
        assert c.get("/api/agents").status_code == 503  # el resto sigue en modo SETUP
    vault.close()
