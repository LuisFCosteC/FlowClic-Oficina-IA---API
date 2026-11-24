"""KEY01: bolsa global de claves API (rutas, cifrado, SSE, 410 de las rutas antiguas)."""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.db.database import Database
from app.domain.key_schemas import KeyTestResult
from app.events.bus import DomainEvent, get_bus
from app.repositories import keys_repo
from app.routers.admin_keys import get_key_tester
from app.security.crypto import SecretBox

SECRET = "AIzaSyD-SUPERSECRETO-abcd1234"
K = "/api/admin/keys"


@pytest.fixture
def events() -> Iterator[list[DomainEvent]]:
    seen: list[DomainEvent] = []
    off = get_bus().subscribe(seen.append)
    yield seen
    off()


def add(c: TestClient, label: str = "g1", provider: str = "google", secret: str = SECRET) -> Any:
    r = c.post(K, json={"provider": provider, "label": label, "secret": secret})
    assert r.status_code == 201, r.text
    return r.json()


def test_crear_nunca_devuelve_la_clave(kclient: TestClient, migrated_db: Database) -> None:
    body = add(kclient)
    assert body["last4"] == "1234" and body["status"] == "ACTIVE"
    assert body["computedStatus"] == "ACTIVE" and body["statusLabel"] == "Activa"
    assert body["position"] == 0 and body["usageToday"]["requests"] == 0
    everything = kclient.get(K).text + str(body)
    assert SECRET not in everything and "SUPERSECRETO" not in everything
    assert "ciphertext" not in everything and "nonce" not in everything
    row = migrated_db.fetch_one("SELECT ciphertext FROM provider_keys")
    assert row is not None and b"SUPERSECRETO" not in bytes(row["ciphertext"])


def test_cifrado_aad_provider_id(
    kclient: TestClient, migrated_db: Database, master_key: str
) -> None:
    key = add(kclient)
    box = SecretBox.from_base64(master_key)
    sealed = keys_repo.get_sealed(migrated_db, key["id"])
    assert sealed is not None
    assert box.decrypt_text("provider-keys", sealed, f"google|{key['id']}") == SECRET
    from app.security.crypto import CryptoError

    with pytest.raises(CryptoError):
        box.decrypt_text("provider-keys", sealed, f"anthropic|{key['id']}")
    with pytest.raises(CryptoError):
        box.decrypt_text("agent-credentials", sealed, f"google|{key['id']}")


def test_auditoria_y_eventos_sin_el_valor(
    kclient: TestClient, migrated_db: Database, events: list[DomainEvent]
) -> None:
    key = add(kclient)
    kclient.post(f"{K}/{key['id']}/rotate", json={"secret": SECRET + "-nueva-9876"})
    kclient.patch(f"{K}/{key['id']}", json={"dailyRequestLimit": 10})
    kclient.delete(f"{K}/{key['id']}")
    rows = migrated_db.fetch_all(
        "SELECT action, meta FROM audit_log WHERE target_id = ?", (key["id"],)
    )
    assert [r["action"] for r in rows] == [
        "key.created",
        "key.rotated",
        "key.updated",
        "key.revoked",
    ]
    assert all("SUPERSECRETO" not in r["meta"] for r in rows)
    assert "SUPERSECRETO" not in kclient.get("/api/admin/audit?limit=500").text
    key_events = [e for e in events if e.type == "key.updated"]
    assert len(key_events) == 4 and all("SUPERSECRETO" not in str(e.payload) for e in key_events)
    assert key_events[-1].payload["status"] == "REVOKED"


@pytest.mark.parametrize(
    "payload",
    [
        {"provider": "google", "label": "x", "secret": "corta"},
        {"provider": "azure", "label": "x", "secret": SECRET},
        {"provider": "google", "label": "", "secret": SECRET},
        {"provider": "google", "label": "x", "secret": "con espacio dentro"},
        {"provider": "google", "label": "x", "secret": SECRET, "extra": 1},
    ],
)
def test_entrada_invalida_400(kclient: TestClient, payload: dict[str, Any]) -> None:
    assert kclient.post(K, json=payload).status_code == 400


def test_etiqueta_unica_entre_activas_del_proveedor(kclient: TestClient) -> None:
    key = add(kclient, "g1")
    assert (
        kclient.post(K, json={"provider": "google", "label": "g1", "secret": SECRET}).status_code
        == 409
    )
    add(kclient, "g1", provider="anthropic")  # otro proveedor: permitido
    kclient.delete(f"{K}/{key['id']}")
    add(kclient, "g1")  # la revocada libera la etiqueta
    r = kclient.post(f"{K}/{key['id']}/reactivate")
    assert r.status_code == 409  # ahora chocaría con la nueva


def test_patch_etiqueta_y_limites(kclient: TestClient) -> None:
    a, b = add(kclient, "a"), add(kclient, "b")
    r = kclient.patch(
        f"{K}/{a['id']}", json={"label": "A2", "dailyRequestLimit": 5, "dailyTokenLimit": 1000}
    )
    assert r.json()["label"] == "A2" and r.json()["dailyRequestLimit"] == 5
    r = kclient.patch(f"{K}/{a['id']}", json={"dailyRequestLimit": None})
    assert r.json()["dailyRequestLimit"] is None and r.json()["dailyTokenLimit"] == 1000
    assert kclient.patch(f"{K}/{a['id']}", json={"label": "b"}).status_code == 409
    assert kclient.patch(f"{K}/{a['id']}", json={"dailyTokenLimit": 0}).status_code == 400
    assert kclient.patch(f"{K}/{a['id']}", json={"label": None}).status_code == 400
    assert kclient.patch(f"{K}/nope", json={"label": "x"}).status_code == 404
    assert b["id"]


def test_orden(kclient: TestClient) -> None:
    ids = [add(kclient, n)["id"] for n in ("a", "b", "c")]
    r = kclient.put(f"{K}/order", json={"ids": [ids[2], ids[0], ids[1]]})
    assert [k["id"] for k in r.json()] == [ids[2], ids[0], ids[1]]
    assert [k["position"] for k in r.json()] == [0, 1, 2]
    assert kclient.put(f"{K}/order", json={"ids": ids[:2]}).status_code == 400
    assert kclient.put(f"{K}/order", json={"ids": [ids[0], ids[0], ids[1]]}).status_code == 400


def test_rotar_revocar_y_reactivar(
    kclient: TestClient, migrated_db: Database, master_key: str
) -> None:
    key = add(kclient)
    r = kclient.post(f"{K}/{key['id']}/rotate", json={"secret": "nueva-clave-9876"})
    assert r.json()["last4"] == "9876" and r.json()["rotatedAt"]
    sealed = keys_repo.get_sealed(migrated_db, key["id"])
    assert sealed is not None
    box = SecretBox.from_base64(master_key)
    assert box.decrypt_text("provider-keys", sealed, f"google|{key['id']}") == "nueva-clave-9876"
    assert kclient.delete(f"{K}/{key['id']}").status_code == 204
    assert kclient.delete(f"{K}/{key['id']}").status_code == 204  # idempotente
    assert (
        kclient.post(f"{K}/{key['id']}/rotate", json={"secret": "otra-clave-0000"}).status_code
        == 409
    )
    r = kclient.post(f"{K}/{key['id']}/reactivate")
    assert r.status_code == 200 and r.json()["status"] == "ACTIVE" and r.json()["revokedAt"] is None
    assert kclient.delete(f"{K}/nope").status_code == 404


def test_probar_la_clave_no_la_devuelve(kclient: TestClient) -> None:
    key = add(kclient)
    seen: list[tuple[str, str]] = []

    def fake(provider: str, secret: str) -> KeyTestResult:
        seen.append((provider, secret))
        return KeyTestResult(ok=True, status="OK", message="La clave es válida")

    kclient.app.dependency_overrides[get_key_tester] = lambda: fake  # type: ignore[attr-defined]
    r = kclient.post(f"{K}/{key['id']}/test")
    assert r.status_code == 200 and r.json()["ok"] is True
    assert seen == [("google", SECRET)]  # el tester recibe la clave en memoria...
    assert SECRET not in r.text  # ...pero la respuesta no la devuelve
    assert kclient.post(f"{K}/nope/test").status_code == 404


def test_sin_master_key_503(client: TestClient) -> None:
    r = client.post(K, json={"provider": "google", "label": "g", "secret": SECRET})
    assert r.status_code == 503 and r.json()["error"]["code"] == "ENCRYPTION_UNAVAILABLE"
    assert client.get(K).status_code == 200  # listar no necesita la clave maestra


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/admin/credentials"),
        ("GET", "/api/admin/agents/x/credentials"),
        ("POST", "/api/admin/agents/x/credentials"),
        ("POST", "/api/admin/agents/x/credentials/y/rotate"),
        ("DELETE", "/api/admin/agents/x/credentials/y"),
    ],
)
def test_rutas_antiguas_410(client: TestClient, method: str, path: str) -> None:
    r = client.request(method, path, json={} if method == "POST" else None)
    assert r.status_code == 410
    assert r.json()["error"]["code"] == "GONE" and "/api/admin/keys" in r.json()["error"]["message"]


def test_estados_calculados_invalida_y_limite(kclient: TestClient, migrated_db: Database) -> None:
    key = add(kclient)
    migrated_db.execute("UPDATE provider_keys SET status = 'INVALID' WHERE id = ?", (key["id"],))
    got = kclient.get(K).json()[0]
    assert got["computedStatus"] == "INVALID" and got["statusLabel"] == "Inválida"
    kclient.post(f"{K}/{key['id']}/reactivate")
    assert kclient.get(K).json()[0]["statusLabel"] == "Activa"
