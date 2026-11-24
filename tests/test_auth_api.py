"""S06: login, sesión por cookie, cambio obligatorio de contraseña, bloqueo y roles."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db.create_admin import create_or_reset_admin
from app.db.database import Database
from app.main import create_app
from app.services import quota_time

EMAIL = "lcoste@flowclic.com"
NEW = "una-clave-nueva-larga-1"


@pytest.fixture
def temp_password(migrated_db: Database) -> str:
    pw = create_or_reset_admin(migrated_db, EMAIL, "Luis Coste", reset=False)
    assert pw is not None
    return pw


@pytest.fixture
def auth_client(migrated_db: Database, temp_password: str) -> Iterator[TestClient]:
    settings = Settings(_env_file=None, node_env="test", auth_enforced=True)  # type: ignore[call-arg]
    with TestClient(
        create_app(settings, migrated_db), base_url="http://localhost", client=("127.0.0.1", 50000)
    ) as c:
        yield c


def login(c: TestClient, password: str, email: str = EMAIL):  # type: ignore[no-untyped-def]
    return c.post("/api/auth/login", json={"email": email, "password": password})


def test_sin_sesion_todo_da_401_salvo_lo_publico(auth_client: TestClient) -> None:
    for path in ("/api/snapshot", "/api/agents", "/api/admin/keys", "/api/events", "/api/auth/me"):
        r = auth_client.get(path)
        assert r.status_code == 401, path
        assert r.json()["error"]["code"] == "UNAUTHENTICATED"
    assert auth_client.get("/api/health").status_code == 200


def test_el_admin_se_crea_con_clave_temporal_que_obliga_a_cambiarla(
    auth_client: TestClient, migrated_db: Database, temp_password: str
) -> None:
    row = migrated_db.fetch_one("SELECT * FROM users WHERE email = ?", (EMAIL,))
    assert row is not None
    assert row["role"] == "ADMIN" and row["must_change_password"] == 1
    assert row["password_hash"].startswith("scrypt$") and temp_password not in row["password_hash"]
    assert len(temp_password) >= 12
    # no se puede crear dos veces; con --reset da otra clave y la anterior deja de valer
    assert create_or_reset_admin(migrated_db, EMAIL, "Luis Coste", reset=False) is None
    again = create_or_reset_admin(migrated_db, EMAIL, "Luis Coste", reset=True)
    assert again and again != temp_password
    assert login(auth_client, temp_password).status_code == 401
    assert login(auth_client, again).status_code == 200


def test_login_ok_cookie_httponly_y_me(auth_client: TestClient, temp_password: str) -> None:
    r = login(auth_client, temp_password)
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == EMAIL and body["role"] == "ADMIN" and body["mustChangePassword"] is True
    assert "passwordHash" not in r.text and temp_password not in r.text
    cookie = r.headers["set-cookie"].lower()
    assert "flowclic_session=" in cookie and "httponly" in cookie and "samesite=lax" in cookie
    assert "path=/api" in cookie
    assert auth_client.get("/api/auth/me").json()["displayName"] == "Luis Coste"


def test_con_clave_temporal_solo_se_puede_cambiar_la_clave(
    auth_client: TestClient, temp_password: str
) -> None:
    login(auth_client, temp_password)
    blocked = auth_client.get("/api/snapshot")
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "PASSWORD_CHANGE_REQUIRED"
    assert auth_client.get("/api/auth/me").status_code == 200  # permitido
    bad = auth_client.post(
        "/api/auth/change-password", json={"currentPassword": "no-es-esta", "newPassword": NEW}
    )
    assert bad.status_code == 400
    short = auth_client.post(
        "/api/auth/change-password", json={"currentPassword": temp_password, "newPassword": "corta"}
    )
    assert short.status_code == 400
    same = auth_client.post(
        "/api/auth/change-password",
        json={"currentPassword": temp_password, "newPassword": temp_password},
    )
    assert same.status_code == 400
    ok = auth_client.post(
        "/api/auth/change-password", json={"currentPassword": temp_password, "newPassword": NEW}
    )
    assert ok.status_code == 200 and ok.json()["mustChangePassword"] is False
    assert auth_client.get("/api/snapshot").status_code == 200  # ya entra a todo
    # la clave temporal ya no vale; la nueva sí
    other = TestClient(auth_client.app, base_url="http://localhost", client=("127.0.0.1", 1))
    assert login(other, temp_password).status_code == 401
    assert login(other, NEW).status_code == 200


def test_credenciales_incorrectas_son_genericas(
    auth_client: TestClient, temp_password: str
) -> None:
    a = login(auth_client, "mala-clave-larga-xx")
    b = login(auth_client, "mala-clave-larga-xx", email="nadie@flowclic.com")
    assert a.status_code == b.status_code == 401
    assert a.json()["error"]["message"] == b.json()["error"]["message"]
    assert "set-cookie" not in a.headers


def test_cinco_fallos_bloquean_la_cuenta(
    auth_client: TestClient, temp_password: str, migrated_db: Database
) -> None:
    for _ in range(5):
        assert login(auth_client, "mala-clave-larga-xx").status_code == 401
    r = login(auth_client, temp_password)  # ni la correcta entra mientras está bloqueada
    assert r.status_code == 429
    migrated_db.execute(
        "UPDATE users SET locked_until = ? WHERE email = ?",
        (quota_time.iso(datetime.now(UTC) - timedelta(seconds=1)), EMAIL),
    )
    assert login(auth_client, temp_password).status_code == 200


def test_logout_revoca_la_sesion(auth_client: TestClient, temp_password: str) -> None:
    login(auth_client, temp_password)
    assert auth_client.post("/api/auth/logout").status_code == 204
    assert auth_client.get("/api/auth/me").status_code == 401


def test_sesion_caduca_por_inactividad(
    auth_client: TestClient, temp_password: str, migrated_db: Database
) -> None:
    login(auth_client, temp_password)
    old = quota_time.iso(datetime.now(UTC) - timedelta(minutes=31))
    migrated_db.execute("UPDATE sessions SET last_seen_at = ?", (old,))
    assert auth_client.get("/api/auth/me").status_code == 401


def test_el_token_no_se_guarda_en_claro(
    auth_client: TestClient, temp_password: str, migrated_db: Database
) -> None:
    r = login(auth_client, temp_password)
    token = r.cookies.get("flowclic_session")
    assert token
    rows = migrated_db.fetch_all("SELECT token_hash FROM sessions")
    assert rows and all(token not in row["token_hash"] for row in rows)
    logs = " ".join(row["meta"] for row in migrated_db.fetch_all("SELECT meta FROM audit_log"))
    assert temp_password not in logs and token not in logs


def _login_as(c: TestClient, db: Database, role: str) -> None:
    from app.security.password import hash_password

    db.execute(
        "INSERT INTO users (id, email, display_name, password_hash, role, password_changed_at,"
        " created_at, updated_at) VALUES (?, ?, 'U', ?, ?, 'n', 'n', 'n')",
        (f"u-{role}", f"{role.lower()}@x.com", hash_password("clave-de-prueba-123"), role),
    )
    assert login(c, "clave-de-prueba-123", f"{role.lower()}@x.com").status_code == 200


def test_roles_operator_y_viewer(auth_client: TestClient, migrated_db: Database) -> None:
    _login_as(auth_client, migrated_db, "VIEWER")
    assert auth_client.get("/api/snapshot").status_code == 200
    assert auth_client.post("/api/agents", json={"name": "A", "role": "r"}).status_code == 403
    assert auth_client.get("/api/admin/keys").status_code == 403
    auth_client.post("/api/auth/logout")
    _login_as(auth_client, migrated_db, "OPERATOR")
    assert auth_client.post("/api/agents", json={"name": "A", "role": "r"}).status_code == 201
    assert auth_client.get("/api/admin/keys").status_code == 403  # /api/admin solo ADMIN


def test_admin_puede_revocar_sesiones_de_otro_usuario(
    auth_client: TestClient, temp_password: str, migrated_db: Database
) -> None:
    other = TestClient(auth_client.app, base_url="http://localhost", client=("127.0.0.1", 2))
    _login_as(other, migrated_db, "OPERATOR")
    login(auth_client, temp_password)
    auth_client.post(
        "/api/auth/change-password", json={"currentPassword": temp_password, "newPassword": NEW}
    )
    assert other.get("/api/snapshot").status_code == 200
    assert auth_client.post("/api/admin/users/u-OPERATOR/revoke-sessions").status_code == 204
    assert other.get("/api/snapshot").status_code == 401


def test_usuarios_creados_por_el_panel_empiezan_con_clave_temporal(
    auth_client: TestClient, temp_password: str
) -> None:
    login(auth_client, temp_password)
    auth_client.post(
        "/api/auth/change-password", json={"currentPassword": temp_password, "newPassword": NEW}
    )
    r = auth_client.post(
        "/api/admin/users",
        json={
            "email": "ana@flowclic.com",
            "displayName": "Ana",
            "role": "OPERATOR",
            "password": "clave-inicial-larga-1",
        },
    )
    assert r.status_code == 201 and r.json()["mustChangePassword"] is True
