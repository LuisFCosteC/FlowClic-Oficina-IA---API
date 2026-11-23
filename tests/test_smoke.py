from fastapi.testclient import TestClient


def test_swagger_disponible_en_api_docs(client: TestClient) -> None:
    assert client.get("/api/docs").status_code == 200
    assert client.get("/api/openapi.json").json()["info"]["title"].startswith("FlowClic")
    assert client.get("/docs").status_code == 404  # la raíz ya no sirve la documentación
