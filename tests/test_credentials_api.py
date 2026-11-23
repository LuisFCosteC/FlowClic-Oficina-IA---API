"""Conexiones API de agentes (PLAN §16): cifrado, nunca se devuelve la clave, varias por agente."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db.database import Database
from app.security.crypto import SecretBox, generate_master_key
from app.services import credentials_service

SECRET = "sk-ant-api03-SUPERSECRETO-abcd1234"


@pytest.fixture
def master_key() -> str:
    return generate_master_key()


@pytest.fixture
def cclient(migrated_db: Database, master_key: str) -> Iterator[TestClient]:
    from app.main import create_app

    settings = Settings(_env_file=None, node_env="test", app_master_key=master_key)  # type: ignore[call-arg]
    app = create_app(settings, migrated_db)
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as c:
        yield c


def _agent(c: TestClient, name: str = "Howard") -> str:
    r = c.post("/api/agents", json={"name": name, "role": "Hardware"})
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


def _add(c: TestClient, agent_id: str, label: str = "Principal", provider: str = "anthropic"):
    return c.post(
        f"/api/admin/agents/{agent_id}/credentials",
        json={"provider": provider, "label": label, "secret": SECRET},
    )


def test_add_never_returns_secret(cclient: TestClient) -> None:
    aid = _agent(cclient)
    r = _add(cclient, aid)
    assert r.status_code == 201
    body = r.json()
    assert body["last4"] == "1234"
    assert body["provider"] == "anthropic"
    assert SECRET not in r.text
    assert "ciphertext" not in r.text and "secret" not in body
    listed = cclient.get(f"/api/admin/agents/{aid}/credentials")
    assert listed.status_code == 200 and len(listed.json()) == 1
    assert SECRET not in listed.text
    assert SECRET not in cclient.get("/api/admin/credentials").text


def test_stored_encrypted_and_decryptable_on_server(
    cclient: TestClient, migrated_db: Database, master_key: str
) -> None:
    aid = _agent(cclient)
    cid = _add(cclient, aid).json()["id"]
    row = migrated_db.fetch_one("SELECT ciphertext FROM agent_credentials WHERE id = ?", (cid,))
    assert row is not None and SECRET.encode() not in bytes(row["ciphertext"])
    box = SecretBox.from_base64(master_key)
    assert credentials_service.reveal_for_server(migrated_db, box, cid) == SECRET


def test_ciphertext_bound_to_its_row(
    cclient: TestClient, migrated_db: Database, master_key: str
) -> None:
    aid = _agent(cclient)
    c1 = _add(cclient, aid, "Uno").json()["id"]
    c2 = _add(cclient, aid, "Dos").json()["id"]
    migrated_db.execute(
        "UPDATE agent_credentials SET ciphertext = (SELECT ciphertext FROM agent_credentials"
        " WHERE id = ?), nonce = (SELECT nonce FROM agent_credentials WHERE id = ?) WHERE id = ?",
        (c1, c1, c2),
    )
    from app.security.crypto import CryptoError

    with pytest.raises(CryptoError):
        credentials_service.reveal_for_server(migrated_db, SecretBox.from_base64(master_key), c2)


def test_multiple_connections_per_agent_even_same_provider(cclient: TestClient) -> None:
    aid = _agent(cclient)
    assert _add(cclient, aid, "Principal").status_code == 201
    assert _add(cclient, aid, "Respaldo").status_code == 201
    assert _add(cclient, aid, "Gemini", "google").status_code == 201
    assert len(cclient.get(f"/api/admin/agents/{aid}/credentials").json()) == 3


def test_duplicate_label_conflicts_until_revoked(cclient: TestClient) -> None:
    aid = _agent(cclient)
    cid = _add(cclient, aid).json()["id"]
    assert _add(cclient, aid).status_code == 409
    assert cclient.delete(f"/api/admin/agents/{aid}/credentials/{cid}").status_code == 204
    assert cclient.get(f"/api/admin/agents/{aid}/credentials").json() == []
    assert _add(cclient, aid).status_code == 201


def test_rotate_changes_last4_and_sets_rotated_at(
    cclient: TestClient, migrated_db: Database, master_key: str
) -> None:
    aid = _agent(cclient)
    cid = _add(cclient, aid).json()["id"]
    r = cclient.post(
        f"/api/admin/agents/{aid}/credentials/{cid}/rotate", json={"secret": "nueva-clave-9876"}
    )
    assert r.status_code == 200
    assert r.json()["last4"] == "9876" and r.json()["rotatedAt"]
    box = SecretBox.from_base64(master_key)
    assert credentials_service.reveal_for_server(migrated_db, box, cid) == "nueva-clave-9876"


def test_rotate_revoked_conflicts_and_revoke_idempotent(cclient: TestClient) -> None:
    aid = _agent(cclient)
    cid = _add(cclient, aid).json()["id"]
    assert cclient.delete(f"/api/admin/agents/{aid}/credentials/{cid}").status_code == 204
    assert cclient.delete(f"/api/admin/agents/{aid}/credentials/{cid}").status_code == 204
    r = cclient.post(
        f"/api/admin/agents/{aid}/credentials/{cid}/rotate", json={"secret": "nueva-clave-9876"}
    )
    assert r.status_code == 409


def test_audit_without_secret(cclient: TestClient, migrated_db: Database) -> None:
    aid = _agent(cclient)
    cid = _add(cclient, aid).json()["id"]
    cclient.post(f"/api/admin/agents/{aid}/credentials/{cid}/rotate", json={"secret": "x" * 12})
    cclient.delete(f"/api/admin/agents/{aid}/credentials/{cid}")
    rows = migrated_db.fetch_all(
        "SELECT action, meta FROM audit_log WHERE target_id = ? ORDER BY created_at", (cid,)
    )
    assert [r["action"] for r in rows] == [
        "agent_credential.created",
        "agent_credential.rotated",
        "agent_credential.revoked",
    ]
    assert all(SECRET not in r["meta"] and "xxxxxxxx" not in r["meta"] for r in rows)


@pytest.mark.parametrize(
    "payload",
    [
        {"provider": "anthropic", "label": "x", "secret": "corta"},
        {"provider": "azure", "label": "x", "secret": SECRET},
        {"provider": "anthropic", "label": "", "secret": SECRET},
        {"provider": "anthropic", "label": "x", "secret": "con espacio dentro"},
        {"provider": "anthropic", "label": "x", "secret": SECRET, "extra": 1},
    ],
)
def test_invalid_input_400(cclient: TestClient, payload: dict[str, object]) -> None:
    aid = _agent(cclient)
    r = cclient.post(f"/api/admin/agents/{aid}/credentials", json=payload)
    assert r.status_code == 400, r.text


def test_unknown_agent_and_wrong_agent_404(cclient: TestClient) -> None:
    assert _add(cclient, "no-existe").status_code == 404
    a1, a2 = _agent(cclient, "Uno"), _agent(cclient, "Dos")
    cid = _add(cclient, a1).json()["id"]
    assert cclient.delete(f"/api/admin/agents/{a2}/credentials/{cid}").status_code == 404


def test_archived_agent_conflicts(cclient: TestClient) -> None:
    aid = _agent(cclient)
    assert cclient.delete(f"/api/agents/{aid}").status_code == 204
    assert _add(cclient, aid).status_code == 409


def test_without_master_key_503(client: TestClient) -> None:
    aid = _agent(client)
    r = _add(client, aid)
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "ENCRYPTION_UNAVAILABLE"
