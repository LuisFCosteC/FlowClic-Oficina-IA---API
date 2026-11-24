"""A07a (auditoría de solo lectura, sin secretos) y A07b (usuarios)."""

import json

from fastapi.testclient import TestClient

from app.db.database import Database

SECRET = "sk-ant-api03-SUPERSECRETO-abcd1234"
PASSWORD = "contraseña-muy-larga-1"
USERS = "/api/admin/users"


def _insert_audit(db: Database, id_: str, action: str, created: str, meta: object) -> None:
    db.execute(
        "INSERT INTO audit_log (id, action, meta, created_at) VALUES (?, ?, ?, ?)",
        (id_, action, json.dumps(meta), created),
    )


# ── A07a ─────────────────────────────────────────────────────────────────────────────────────
def test_audit_filtros_limite_y_orden(client: TestClient, migrated_db: Database) -> None:
    for i in range(5):
        _insert_audit(
            migrated_db, f"a{i}", "x.a" if i % 2 else "x.b", f"2026-11-2{i}T10:00:00.000Z", {}
        )
    body = client.get("/api/admin/audit").json()
    assert [e["id"] for e in body] == ["a4", "a3", "a2", "a1", "a0"]
    assert [e["id"] for e in client.get("/api/admin/audit?limit=2").json()] == ["a4", "a3"]
    assert {e["action"] for e in client.get("/api/admin/audit?action=x.a").json()} == {"x.a"}
    r = client.get("/api/admin/audit?from=2026-11-21T00:00:00Z&to=2026-11-23T00:00:00Z").json()
    assert [e["id"] for e in r] == ["a2", "a1"]
    assert client.get("/api/admin/audit?limit=0").status_code == 400
    assert client.get("/api/admin/audit?limit=501").status_code == 400
    assert client.get("/api/admin/audit?from=ayer").status_code == 400


def test_audit_es_de_solo_lectura(client: TestClient) -> None:
    for method in ("post", "put", "patch", "delete"):
        assert getattr(client, method)("/api/admin/audit").status_code == 405


def test_audit_redacta_secretos_aunque_esten_en_la_bd(
    client: TestClient, migrated_db: Database
) -> None:
    _insert_audit(
        migrated_db,
        "leak",
        "x.leak",
        "2026-11-23T10:00:00.000Z",
        {
            "apiKey": SECRET,  # clave sospechosa: se descarta
            "note": f"usé {SECRET} y token=abc123 y libsql://db?authToken=eyJhbGciOi.abcdefghijk",
            "nested": {"password": "hunter2", "ok": "bien", "list": [f"x {SECRET}"]},
        },
    )
    text = client.get("/api/admin/audit").text
    assert SECRET not in text and "SUPERSECRETO" not in text
    assert "hunter2" not in text and "abc123" not in text and "authToken=eyJ" not in text
    assert "apiKey" not in text and "bien" in text


def test_audit_de_claves_no_filtra_la_clave(kclient: TestClient) -> None:
    r = kclient.post(
        "/api/admin/keys", json={"provider": "anthropic", "label": "Principal", "secret": SECRET}
    )
    assert r.status_code == 201
    key_id = r.json()["id"]
    kclient.post(f"/api/admin/keys/{key_id}/rotate", json={"secret": SECRET + "-nueva"})
    text = kclient.get("/api/admin/audit?limit=500").text
    assert "SUPERSECRETO" not in text and SECRET not in text
    assert "key.created" in text and "key.rotated" in text


# ── A07b ─────────────────────────────────────────────────────────────────────────────────────
def _create(c: TestClient, email: str = "ana@example.com", role: str = "OPERATOR", **kw: object):
    body = {"email": email, "displayName": "Ana", "role": role, "password": PASSWORD}
    body.update(kw)
    return c.post(USERS, json=body)


def test_crear_y_listar_nunca_devuelve_secretos(client: TestClient, migrated_db: Database) -> None:
    r = _create(client)
    assert r.status_code == 201
    u = r.json()
    assert u["email"] == "ana@example.com" and u["role"] == "OPERATOR" and u["mfaEnabled"] is False
    assert u["disabledAt"] is None
    text = r.text + client.get(USERS).text
    for banned in (PASSWORD, "password", "passwordHash", "mfaSecret", "scrypt$"):
        assert banned not in text
    row = migrated_db.fetch_one("SELECT password_hash FROM users")
    assert row is not None and row["password_hash"].startswith("scrypt$")
    audit = client.get("/api/admin/audit?action=user.created").text
    assert PASSWORD not in audit and "ana@example.com" in audit


def test_password_corta_email_invalido_y_duplicado(client: TestClient) -> None:
    assert _create(client, password="corta-11-ch").status_code == 400  # 11 caracteres
    assert _create(client, password="exactamente12").status_code == 201
    assert _create(client, email="sin-arroba").status_code == 400
    assert _create(client, role="ROOT", email="b@example.com").status_code == 400
    assert _create(client, email="ANA@example.com").status_code == 409  # mismo email
    assert _create(client, email="c@example.com", extra=1).status_code == 400


def test_patch_nombre_rol_y_desactivar(client: TestClient, migrated_db: Database) -> None:
    _create(client, "admin@example.com", "ADMIN")
    uid = _create(client).json()["id"]
    r = client.patch(f"{USERS}/{uid}", json={"displayName": "Ana B", "role": "VIEWER"})
    assert r.json()["displayName"] == "Ana B" and r.json()["role"] == "VIEWER"
    migrated_db.execute(
        "INSERT INTO sessions (id, user_id, token_hash, created_at, last_seen_at, expires_at)"
        " VALUES ('s1', ?, 'h', 'n', 'n', 'z')",
        (uid,),
    )
    off = client.patch(f"{USERS}/{uid}", json={"disabled": True}).json()
    assert off["disabledAt"] is not None
    row = migrated_db.fetch_one("SELECT revoked_at FROM sessions WHERE id = 's1'")
    assert row is not None and row["revoked_at"] is not None
    on = client.patch(f"{USERS}/{uid}", json={"disabled": False}).json()
    assert on["disabledAt"] is None
    assert client.patch(f"{USERS}/nada", json={"role": "ADMIN"}).status_code == 404
    assert client.patch(f"{USERS}/{uid}", json={"role": None}).status_code == 400
    assert client.patch(f"{USERS}/{uid}", json={"password": "x" * 12}).status_code == 400


def test_el_ultimo_admin_no_se_desactiva_ni_degrada(client: TestClient) -> None:
    only = _create(client, "root@example.com", "ADMIN").json()["id"]
    for body in ({"disabled": True}, {"role": "OPERATOR"}, {"role": "VIEWER", "disabled": True}):
        r = client.patch(f"{USERS}/{only}", json=body)
        assert r.status_code == 409 and r.json()["error"]["code"] == "CONFLICT"
    second = _create(client, "second@example.com", "ADMIN").json()["id"]
    assert client.patch(f"{USERS}/{only}", json={"role": "OPERATOR"}).status_code == 200
    assert client.patch(f"{USERS}/{second}", json={"disabled": True}).status_code == 409
    # un ADMIN ya desactivado no cuenta: reactivar al otro y degradarlo es posible
    assert client.patch(f"{USERS}/{only}", json={"role": "ADMIN"}).status_code == 200
    assert client.patch(f"{USERS}/{second}", json={"disabled": True}).status_code == 200
    assert client.patch(f"{USERS}/{only}", json={"disabled": True}).status_code == 409


def test_cambiar_nombre_del_ultimo_admin_si_se_puede(client: TestClient) -> None:
    only = _create(client, "root@example.com", "ADMIN").json()["id"]
    assert client.patch(f"{USERS}/{only}", json={"displayName": "Root"}).status_code == 200
    assert client.patch(f"{USERS}/{only}", json={"role": "ADMIN"}).status_code == 200


def test_revoke_sessions_cierra_las_sesiones(client: TestClient, migrated_db: Database) -> None:
    uid = _create(client).json()["id"]
    migrated_db.execute(
        "INSERT INTO sessions (id, user_id, token_hash, created_at, last_seen_at, expires_at)"
        " VALUES ('s9', ?, 'h9', 'n', 'n', 'n')",
        (uid,),
    )
    assert client.post(f"{USERS}/{uid}/revoke-sessions").status_code == 204
    row = migrated_db.fetch_one("SELECT revoked_at FROM sessions WHERE id = 's9'")
    assert row is not None and row["revoked_at"] is not None
    assert client.post(f"{USERS}/nada/revoke-sessions").status_code == 404
