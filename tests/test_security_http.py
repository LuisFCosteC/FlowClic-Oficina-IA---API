import logging
import threading
import time
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient

from app.config import Settings
from app.db.database import Database, DatabaseError
from app.main import create_app

SECURITY_HEADERS = {
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
    "x-frame-options": "DENY",
}


def test_cabeceras_de_seguridad_en_la_api(client: TestClient) -> None:
    r = client.get("/api/health")
    for name, value in SECURITY_HEADERS.items():
        assert r.headers[name] == value
    assert r.headers["content-security-policy"] == "default-src 'none'; frame-ancestors 'none'"
    assert r.headers["x-request-id"]


def test_las_cabeceras_salen_tambien_en_errores_y_preflight_cors(client: TestClient) -> None:
    for r in (
        client.get("/api/nada"),  # 404
        client.post("/api/agents", json={}),  # 400
        client.options(
            "/api/agents",
            headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"},
        ),
    ):
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["x-frame-options"] == "DENY"
        assert r.headers["x-request-id"]


def test_el_request_id_es_distinto_en_cada_peticion(client: TestClient) -> None:
    ids = {client.get("/api/health").headers["x-request-id"] for _ in range(5)}
    assert len(ids) == 5


def test_no_se_revela_el_software_ni_su_version(client: TestClient) -> None:
    r = client.get("/api/health")
    assert "x-powered-by" not in r.headers
    assert "server" not in r.headers
    blob = " ".join(f"{k}: {v}" for k, v in r.headers.items()).lower()
    for word in ("uvicorn", "starlette", "fastapi", "python", "0.1.0"):
        assert word not in blob
    assert r.json() == {"ok": True}  # sin version ni estado de la BD


def test_la_documentacion_tiene_una_csp_que_permite_swagger_pero_la_api_no(
    client: TestClient,
) -> None:
    docs = client.get("/docs").headers["content-security-policy"]
    assert "cdn.jsdelivr.net" in docs and "frame-ancestors 'none'" in docs
    assert "cdn.jsdelivr.net" not in client.get("/openapi.json").headers["content-security-policy"]
    assert "cdn.jsdelivr.net" not in client.get("/api/health").headers["content-security-policy"]


def test_body_de_200_kb_devuelve_413_json(client: TestClient) -> None:
    r = client.post("/api/agents", json={"name": "x" * 200_000, "role": "r"})
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"
    assert r.headers["x-content-type-options"] == "nosniff"


def test_body_justo_bajo_el_limite_no_da_413(client: TestClient) -> None:
    r = client.post("/api/agents", json={"name": "x" * 90_000, "role": "r"})
    assert r.status_code == 400  # nombre demasiado largo, pero NO 413
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_body_enviado_por_trozos_sin_content_length_tambien_da_413(client: TestClient) -> None:
    def chunks() -> Iterator[bytes]:
        for _ in range(30):
            yield b"x" * 8_192

    r = client.post("/api/agents", content=chunks(), headers={"Content-Type": "application/json"})
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


def test_el_host_por_defecto_es_solo_local() -> None:
    assert Settings(_env_file=None).host == "127.0.0.1"  # type: ignore[call-arg]


def test_python_m_app_arranca_con_host_local_sin_proxy_headers_ni_server_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.__main__ as entry

    captured: dict[str, Any] = {}
    monkeypatch.setattr(uvicorn, "run", lambda *a, **kw: captured.update(args=a, **kw))
    monkeypatch.setattr(
        entry,
        "get_settings",
        lambda: Settings(_env_file=None, port=4321),  # type: ignore[call-arg]
    )
    entry.main()
    assert captured["host"] == "127.0.0.1" and captured["port"] == 4321
    assert captured["proxy_headers"] is False
    assert captured["server_header"] is False


def test_health_devuelve_503_ok_false_si_la_bd_falla(
    migrated_db: Database, test_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = create_app(test_settings, migrated_db)

    def boom(*_a: object, **_k: object) -> None:
        raise DatabaseError("caída")

    monkeypatch.setattr(migrated_db, "fetch_one", boom)
    with TestClient(app) as c:
        r = c.get("/api/health")
    assert r.status_code == 503
    assert r.json() == {"ok": False}


def test_un_error_500_se_registra_con_el_request_id(
    migrated_db: Database, test_settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    app = create_app(test_settings, migrated_db)

    @app.get("/api/_boom")
    def boom() -> None:
        raise RuntimeError("secreto /ruta/interna")

    caplog.set_level(logging.ERROR, logger="flowclic")
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/api/_boom")
    rid = r.headers["x-request-id"]
    assert r.status_code == 500
    assert any(rid in rec.getMessage() for rec in caplog.records)
    assert "secreto" not in caplog.text and "secreto" not in r.text


# ── Servidor REAL: sin cabecera `server:` (uvicorn con server_header=False) ──────────────────
def test_servidor_real_sin_cabecera_server(migrated_db: Database, test_settings: Settings) -> None:
    app = create_app(test_settings, migrated_db)
    config = uvicorn.Config(
        app, host="127.0.0.1", port=0, log_level="warning", server_header=False, proxy_headers=False
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    end = time.monotonic() + 5
    while not (server.started and server.servers) and time.monotonic() < end:
        time.sleep(0.02)
    port = server.servers[0].sockets[0].getsockname()[1]
    try:
        r = httpx.get(f"http://127.0.0.1:{port}/api/health", timeout=5)
        assert r.json() == {"ok": True}
        assert "server" not in r.headers
        assert "x-powered-by" not in r.headers
        blob = " ".join(f"{k}: {v}" for k, v in r.headers.items()).lower()
        assert "uvicorn" not in blob and "starlette" not in blob
    finally:
        server.should_exit = True
        thread.join(10)


def test_un_json_valido_seguido_de_relleno_enorme_no_ejecuta_la_ruta(client: TestClient) -> None:
    """Fail-closed: pasado el límite el cuerpo se corta y la ruta NO se ejecuta."""

    def chunks() -> Iterator[bytes]:
        yield b'{"name": "Intruso", "role": "r"}'  # JSON completo y válido...
        for _ in range(40):
            yield b" " * 8_192  # ...seguido de 320 kB de espacios

    r = client.post("/api/agents", content=chunks(), headers={"Content-Type": "application/json"})
    assert r.status_code == 413
    assert client.get("/api/agents").json() == []  # no se creó nada
