from fastapi.testclient import TestClient

from app.main import create_app


def test_swagger_docs_disponibles() -> None:
    client = TestClient(create_app())
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").json()["info"]["title"].startswith("FlowClic")
