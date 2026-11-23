from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict, Field

from app.config import Settings
from app.db.database import Database
from app.errors import AppError, conflict, not_found, unprocessable
from app.main import create_app


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=20)
    count: int = 1


@pytest.fixture
def err_client(migrated_db: Database, test_settings: Settings) -> Iterator[TestClient]:
    app = create_app(test_settings, migrated_db)

    @app.post("/api/_test/body")
    def body(b: Body) -> dict[str, str]:
        return {"name": b.name}

    @app.get("/api/_test/conflict")
    def _conflict() -> None:
        raise conflict("ya existe")

    @app.get("/api/_test/missing")
    def _missing() -> None:
        raise not_found("no existe")

    @app.get("/api/_test/unprocessable")
    def _unprocessable() -> None:
        raise unprocessable("agente inexistente")

    @app.get("/api/_test/custom")
    def _custom() -> None:
        raise AppError("LIMIT_EXCEEDED", "límite superado", [{"limit": "maxAgents"}])

    @app.get("/api/_test/boom")
    def _boom() -> None:
        raise RuntimeError("secreto interno /ruta/privada token=abc123")

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def assert_shape(body: dict[str, object], code: str) -> dict[str, object]:
    assert set(body) == {"error"}
    err = body["error"]
    assert isinstance(err, dict)
    assert set(err) == {"code", "message", "details"}
    assert err["code"] == code
    assert isinstance(err["details"], list)
    return err


def test_body_invalido_devuelve_400_con_forma_y_details(err_client: TestClient) -> None:
    r = err_client.post("/api/_test/body", json={"name": "", "extra": 1})
    assert r.status_code == 400
    err = assert_shape(r.json(), "VALIDATION_ERROR")
    paths = {d["path"] for d in err["details"]}  # type: ignore[attr-defined]
    assert {"name", "extra"} <= paths


def test_json_mal_formado_devuelve_400(err_client: TestClient) -> None:
    r = err_client.post(
        "/api/_test/body", content="{bad", headers={"Content-Type": "application/json"}
    )
    assert r.status_code == 400
    assert_shape(r.json(), "VALIDATION_ERROR")


def test_ruta_inexistente_404_json(err_client: TestClient) -> None:
    r = err_client.get("/api/nada")
    assert r.status_code == 404
    err = assert_shape(r.json(), "NOT_FOUND")
    assert "GET /api/nada" in str(err["message"])


def test_metodo_no_permitido_405_json(err_client: TestClient) -> None:
    r = err_client.delete("/api/health")
    assert r.status_code == 405
    assert_shape(r.json(), "METHOD_NOT_ALLOWED")


@pytest.mark.parametrize(
    ("path", "status", "code"),
    [
        ("/api/_test/conflict", 409, "CONFLICT"),
        ("/api/_test/missing", 404, "NOT_FOUND"),
        ("/api/_test/unprocessable", 422, "UNPROCESSABLE"),
        ("/api/_test/custom", 409, "LIMIT_EXCEEDED"),
    ],
)
def test_errores_de_negocio(err_client: TestClient, path: str, status: int, code: str) -> None:
    r = err_client.get(path)
    assert r.status_code == status
    assert_shape(r.json(), code)


def test_500_sin_stack_ni_detalles_internos(err_client: TestClient) -> None:
    r = err_client.get("/api/_test/boom")
    assert r.status_code == 500
    err = assert_shape(r.json(), "INTERNAL")
    text = r.text
    assert "Traceback" not in text
    assert "secreto interno" not in text
    assert "token=abc123" not in text
    assert err["details"] == []
