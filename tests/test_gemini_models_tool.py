"""GM01: catálogo con apiModel y herramienta gemini_models (usa KeyPool)."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.db.database import Database
from app.domain.models_catalog import MODELS_CATALOG
from app.errors import AppError
from app.events.bus import get_bus
from app.orchestrator import tools
from app.routers.admin_tools import get_http_get
from app.security.crypto import SecretBox
from app.services.key_pool import KeyPool

SECRETS = {"a": "AIza-AAAA-0001-secret", "b": "AIza-BBBB-0002-secret"}
MODELS = {
    "models": [
        {
            "name": "models/gemini-2.5-pro",
            "displayName": "Gemini 2.5 Pro",
            "inputTokenLimit": 1048576,
            "outputTokenLimit": 65536,
            "supportedGenerationMethods": ["generateContent", "countTokens"],
        },
        {
            "name": "models/gemini-embedding-001",
            "supportedGenerationMethods": ["embedContent"],
        },
        {"name": "models/text-bison", "supportedGenerationMethods": ["generateText"]},
    ]
}


def test_el_catalogo_tiene_api_model() -> None:
    by_id = {m.id: m for m in MODELS_CATALOG}
    assert all(m.api_model for m in MODELS_CATALOG)
    assert by_id["claude-opus-5-5"].api_model == "claude-opus-5-5"
    assert by_id["gemini-pro"].api_model == "gemini-2.5-pro"
    assert by_id["gemini-flash"].api_model == "gemini-2.5-flash"


def test_la_herramienta_esta_registrada() -> None:
    assert tools.TOOLS["gemini_models"].name == "gemini_models"
    assert tools.TOOLS["gemini_models"].input_schema["additionalProperties"] is False


@pytest.fixture
def pool(migrated_db: Database, master_key: str) -> tuple[KeyPool, dict[str, str]]:
    from app.domain.key_schemas import KeyCreate
    from app.services import key_service

    box = SecretBox.from_base64(master_key)
    ids = {}
    for label, secret in SECRETS.items():
        k = key_service.create_key(
            migrated_db, box, None, KeyCreate(provider="google", label=label, secret=secret)
        )
        ids[label] = k.id
    return KeyPool(migrated_db, box, get_bus()), ids


def fake(responses: dict[str, tools.HttpResult], calls: list[str]) -> tools.HttpGet:
    def http_get(url: str, key: str) -> tools.HttpResult:
        calls.append(key)
        return responses[key]

    return http_get


def test_lista_solo_gemini_y_marca_el_catalogo(pool: tuple[KeyPool, dict[str, str]]) -> None:
    calls: list[str] = []
    ok = tools.HttpResult(200, MODELS)
    got = tools.gemini_models(pool[0], fake({SECRETS["a"]: ok}, calls))
    assert [m.api_model for m in got] == ["gemini-2.5-pro", "gemini-embedding-001"]
    pro = got[0]
    assert pro.supports_generate_content is True and pro.catalog_id == "gemini-pro"
    assert got[1].supports_generate_content is False and got[1].catalog_id is None
    assert calls == [SECRETS["a"]]  # la primera clave por posición


def test_rota_ante_429_y_marca_invalida_la_rechazada(
    pool: tuple[KeyPool, dict[str, str]], migrated_db: Database
) -> None:
    kp, ids = pool
    calls: list[str] = []
    responses = {
        SECRETS["a"]: tools.HttpResult(429, {}, 30.0),
        SECRETS["b"]: tools.HttpResult(200, MODELS),
    }
    got = tools.gemini_models(kp, fake(responses, calls))
    assert got and calls == [SECRETS["a"], SECRETS["b"]]
    # la 429 solo agota "models.list": la clave sigue sirviendo a los modelos reales
    assert kp.acquire("google", "gemini-pro").key_id == ids["a"]
    # la clave rechazada pasa a INVALID y no se vuelve a usar
    calls.clear()
    responses = {
        SECRETS["a"]: tools.HttpResult(400, {}),
        SECRETS["b"]: tools.HttpResult(200, MODELS),
    }
    migrated_db.execute("UPDATE key_usage SET exhausted_until = NULL")
    tools.gemini_models(kp, fake(responses, calls))
    assert calls == [SECRETS["a"], SECRETS["b"]]
    row = migrated_db.fetch_one("SELECT status FROM provider_keys WHERE id = ?", (ids["a"],))
    assert row is not None and row["status"] == "INVALID"


def test_sin_clave_usable_no_key_available(pool: tuple[KeyPool, dict[str, str]]) -> None:
    calls: list[str] = []
    bad = tools.HttpResult(401, {})
    with pytest.raises(AppError) as exc:
        tools.gemini_models(pool[0], fake({SECRETS["a"]: bad, SECRETS["b"]: bad}, calls))
    assert exc.value.code == "NO_KEY_AVAILABLE"
    assert len(calls) == 2


def test_error_del_proveedor_no_filtra_la_clave(pool: tuple[KeyPool, dict[str, str]]) -> None:
    with pytest.raises(AppError) as exc:
        tools.gemini_models(pool[0], fake({SECRETS["a"]: tools.HttpResult(500, {})}, []))
    assert exc.value.code == "UPSTREAM_ERROR" and SECRETS["a"] not in exc.value.message


def test_ruta_http_de_prueba(kclient: TestClient) -> None:
    for label, secret in SECRETS.items():
        r = kclient.post(
            "/api/admin/keys", json={"provider": "google", "label": label, "secret": secret}
        )
        assert r.status_code == 201
    app: Any = kclient.app
    app.dependency_overrides[get_http_get] = lambda: (
        lambda _url, _key: tools.HttpResult(200, MODELS)
    )
    r = kclient.get("/api/admin/tools/gemini-models")
    assert r.status_code == 200
    body = r.json()
    assert body[0]["apiModel"] == "gemini-2.5-pro" and body[0]["catalogId"] == "gemini-pro"
    assert body[0]["supportsGenerateContent"] is True
    assert SECRETS["a"] not in r.text


def test_ruta_http_sin_claves_503(kclient: TestClient) -> None:
    r = kclient.get("/api/admin/tools/gemini-models")
    assert r.status_code == 503 and r.json()["error"]["code"] == "NO_KEY_AVAILABLE"
