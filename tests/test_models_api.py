from fastapi.testclient import TestClient


def _by_id(client: TestClient) -> dict[str, dict[str, object]]:
    r = client.get("/api/models")
    assert r.status_code == 200
    return {m["id"]: m for m in r.json()}


def test_catalogo_completo_en_camel_case_sin_conexiones(client: TestClient) -> None:
    models = _by_id(client)
    assert list(models) == [
        "claude-opus-5-5",
        "claude-sonnet-5-5",
        "claude-haiku-5-5",
        "gemini-pro",
        "gemini-flash",
    ]
    assert models["claude-opus-5-5"] == {
        "id": "claude-opus-5-5",
        "label": "Claude Opus 5.5",
        "provider": "anthropic",
        "apiModel": "claude-opus-5-5",
        "hasConnection": False,
    }
    assert models["gemini-flash"]["provider"] == "google"
    assert models["gemini-pro"]["apiModel"] == "gemini-2.5-pro"
    assert models["gemini-flash"]["apiModel"] == "gemini-2.5-flash"
    assert all(m["hasConnection"] is False for m in models.values())


def test_has_connection_por_proveedor_modelo_y_revocada_no_cuenta(kclient: TestClient) -> None:
    r = kclient.post(
        "/api/admin/keys", json={"provider": "google", "label": "g1", "secret": "AIza-test-0001"}
    )
    assert r.status_code == 201
    models = _by_id(kclient)
    assert models["gemini-pro"]["hasConnection"] is True
    assert models["gemini-flash"]["hasConnection"] is True
    assert models["claude-sonnet-5-5"]["hasConnection"] is False
    kclient.delete(f"/api/admin/keys/{r.json()['id']}")
    assert _by_id(kclient)["gemini-pro"]["hasConnection"] is False
