import logging
import re
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db.database import Database, connect_database, try_get_db
from app.main import create_app
from app.security.crypto import SecretBox, generate_master_key
from app.security.setup_gate import SetupGate
from app.security.vault import Vault

PASSWORD = "una-clave-larga-y-segura-1"
TOKEN = "token-secreto-que-no-debe-filtrarse-xyz"


class Env:
    def __init__(self, tmp_path: Path) -> None:
        key = generate_master_key()
        self.settings = Settings(_env_file=None, app_master_key=key, node_env="test")  # type: ignore[call-arg]
        self.vault = Vault(tmp_path / "data" / "vault.db", SecretBox.from_base64(key))
        self.app = create_app(self.settings, None, self.vault)
        self.db_url = "file:" + (tmp_path / "main.db").as_posix()
        self.local = TestClient(self.app, base_url="http://localhost", client=("127.0.0.1", 50000))
        self.remote = TestClient(self.app, base_url="http://localhost", client=("10.0.0.5", 50000))

    @property
    def code(self) -> str:
        code = self.app.state.setup_gate.code
        assert code is not None
        return str(code)

    def database(self, **over: object) -> dict[str, object]:
        body: dict[str, object] = {
            "setupCode": self.app.state.setup_gate.code or "",
            "url": self.db_url,
        }
        body.update(over)
        return body

    def admin(self, **over: object) -> dict[str, object]:
        body: dict[str, object] = {
            "setupCode": self.app.state.setup_gate.code or "",
            "email": "Luis@Example.com",
            "displayName": "Luis",
            "password": PASSWORD,
        }
        body.update(over)
        return body


@pytest.fixture
def env(tmp_path: Path) -> Iterator[Env]:
    e = Env(tmp_path)
    with e.local, e.remote:
        yield e
    e.vault.close()


def test_el_codigo_tiene_formato_y_se_imprime_en_consola(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    e = Env(tmp_path)
    with e.local:
        out = capsys.readouterr().out
    assert re.search(r"\[SETUP\] Código de configuración: [A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}", out)
    assert e.code in out
    e.vault.close()


def test_status_en_modo_setup(env: Env) -> None:
    r = env.local.get("/api/setup/status")
    assert r.status_code == 200
    assert r.json() == {"setupRequired": True, "hasDatabase": False, "hasAdmin": False}


def test_las_demas_rutas_devuelven_503_setup_required_pero_health_y_docs_viven(env: Env) -> None:
    r = env.local.get("/api/agents")
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "SETUP_REQUIRED"
    assert env.local.get("/api/tickets").status_code == 503
    health = env.local.get("/api/health")
    assert health.status_code == 200
    assert health.json() == {"ok": True}
    assert env.local.get("/api/docs").status_code == 200


def test_sin_codigo_o_con_codigo_malo_403(env: Env) -> None:
    assert env.local.post("/api/setup/database", json={"url": env.db_url}).status_code == 400
    bad = env.local.post("/api/setup/database", json=env.database(setupCode="AAAA-AAAA-AAAA"))
    assert bad.status_code == 403
    assert bad.json()["error"]["code"] == "FORBIDDEN"
    assert try_get_db() is None
    assert not env.vault.has("db.url")


def test_desde_una_ip_no_local_403(env: Env) -> None:
    assert env.remote.get("/api/setup/status").status_code == 403
    assert env.remote.post("/api/setup/database", json=env.database()).status_code == 403
    assert env.remote.post("/api/setup/admin", json=env.admin()).status_code == 403
    assert not env.vault.has("db.url")


def test_flujo_completo_bd_admin_y_cierre(env: Env) -> None:
    code = env.code  # tras cerrar, el guardián ya no tiene código
    r = env.local.post("/api/setup/database", json=env.database(authToken=TOKEN))
    assert r.status_code == 200
    assert r.json() == {"setupRequired": True, "hasDatabase": True, "hasAdmin": False}
    assert env.vault.get_secret("db.url") == env.db_url
    assert env.vault.get_secret("db.auth_token") == TOKEN
    db = try_get_db()
    assert db is not None
    assert env.local.get("/api/health").json() == {"ok": True}
    # ya con BD, las demás rutas dejan de dar 503 (aquí 404: aún no existen)
    assert env.local.get("/api/agents").status_code != 503
    # la BD empieza vacía
    assert db.fetch_one("SELECT COUNT(*) AS n FROM agents") == {"n": 0}

    r = env.local.post("/api/setup/admin", json=env.admin())
    assert r.status_code == 201
    assert r.json() == {"setupRequired": False, "hasDatabase": True, "hasAdmin": True}
    user = db.fetch_one("SELECT * FROM users")
    assert user is not None
    assert user["role"] == "ADMIN"
    assert user["email"] == "luis@example.com"
    assert user["mfa_enabled"] == 0
    assert str(user["password_hash"]).startswith("scrypt$")
    assert PASSWORD not in str(user)

    # cerrado: 404 en los POST, incluso con el código anterior y desde localhost
    bodies = (
        ("/api/setup/database", env.database(setupCode=code)),
        ("/api/setup/admin", env.admin(setupCode=code)),
    )
    for path, body in bodies:
        closed = env.local.post(path, json=body)
        assert closed.status_code == 404
    status = env.remote.get("/api/setup/status")  # cerrado: sin exigir localhost
    assert status.status_code == 200
    assert status.json() == {"setupRequired": False}  # y sin hasDatabase/hasAdmin


def test_admin_antes_de_la_bd_409(env: Env) -> None:
    r = env.local.post("/api/setup/admin", json=env.admin())
    assert r.status_code == 409


def test_segunda_conexion_409_y_no_cambia_la_boveda(env: Env) -> None:
    assert env.local.post("/api/setup/database", json=env.database()).status_code == 200
    again = env.local.post("/api/setup/database", json=env.database(url="file:otra.db"))
    assert again.status_code == 409
    assert env.vault.get_secret("db.url") == env.db_url


@pytest.mark.parametrize(
    ("over", "status"),
    [
        ({"password": "corta"}, 400),
        ({"email": "no-es-email"}, 400),
        ({"displayName": ""}, 400),
        ({"role": "ADMIN"}, 400),  # campo desconocido
    ],
)
def test_validacion_del_admin(env: Env, over: dict[str, object], status: int) -> None:
    env.local.post("/api/setup/database", json=env.database())
    r = env.local.post("/api/setup/admin", json=env.admin(**over))
    assert r.status_code == status
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"
    db = try_get_db()
    assert db is not None
    assert db.fetch_one("SELECT COUNT(*) AS n FROM users") == {"n": 0}


def test_url_invalida_o_inalcanzable_no_guarda_nada_ni_filtra_secretos(
    env: Env, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    bad_scheme = env.local.post("/api/setup/database", json=env.database(url="ftp://x"))
    assert bad_scheme.status_code == 400
    secret_url = "file:/carpeta-que-no-existe-xyz/privado-123.db"
    r = env.local.post("/api/setup/database", json=env.database(url=secret_url, authToken=TOKEN))
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "UNPROCESSABLE"
    assert "privado-123" not in r.text
    assert TOKEN not in r.text
    assert "privado-123" not in caplog.text
    assert TOKEN not in caplog.text
    assert not env.vault.has("db.url")
    assert try_get_db() is None


def test_el_token_no_aparece_en_claro_en_la_boveda(env: Env) -> None:
    env.local.post("/api/setup/database", json=env.database(authToken=TOKEN))
    env.vault.close()
    assert TOKEN.encode() not in env.vault.path.read_bytes()


def test_cinco_intentos_malos_queman_el_codigo(env: Env) -> None:
    old = env.code
    for _ in range(5):
        r = env.local.post("/api/setup/database", json=env.database(setupCode="AAAA-AAAA-AAAA"))
        assert r.status_code == 403
    assert env.code != old
    r = env.local.post("/api/setup/database", json=env.database(setupCode=old))
    assert r.status_code == 403
    assert env.local.post("/api/setup/database", json=env.database()).status_code == 200


def test_el_codigo_caduca_a_los_30_minutos_y_se_emite_otro() -> None:
    now = [0.0]
    shown: list[str] = []
    gate = SetupGate(clock=lambda: now[0], announce=shown.append)
    first = gate.issue()
    now[0] = 29 * 60
    gate.verify(first)  # aún vale
    now[0] = 31 * 60
    with pytest.raises(Exception, match="inválido o caducado"):
        gate.verify(first)
    assert len(shown) == 2 and shown[1] != first
    gate.verify(shown[1])


def test_el_codigo_normaliza_mayusculas_y_espacios() -> None:
    gate = SetupGate(announce=lambda _c: None)
    code = gate.issue()
    gate.verify(f"  {code.lower()}  ")


def test_arrancar_con_bd_en_la_boveda_no_entra_en_modo_setup(tmp_path: Path) -> None:
    key = generate_master_key()
    settings = Settings(_env_file=None, app_master_key=key, node_env="test")  # type: ignore[call-arg]
    vault = Vault(tmp_path / "v.db", SecretBox.from_base64(key))
    url = "file:" + (tmp_path / "main.db").as_posix()
    vault.set_secret("db.url", url)
    from app.db.migrate import migrate

    db = connect_database(url)
    migrate(db)
    db.close()
    app = create_app(settings, None, vault)
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 1)) as c:
        assert c.get("/api/health").json() == {"ok": True}
        assert c.get("/api/setup/status").json() == {
            "setupRequired": True,
            "hasDatabase": True,
            "hasAdmin": False,
        }
    vault.close()


@pytest.mark.parametrize(
    "header",
    [
        {"X-Forwarded-For": "203.0.113.9"},
        {"Forwarded": "for=203.0.113.9"},
        {"X-Real-IP": "203.0.113.9"},
        {"X-Forwarded-Host": "api.ejemplo.com"},
        {"X-Forwarded-Proto": "https"},
    ],
)
def test_cabeceras_de_proxy_dan_403_aunque_el_cliente_parezca_local(
    env: Env, header: dict[str, str]
) -> None:
    assert env.local.get("/api/setup/status", headers=header).status_code == 403
    r = env.local.post("/api/setup/database", json=env.database(), headers=header)
    assert r.status_code == 403
    assert not env.vault.has("db.url")


@pytest.mark.parametrize("host", ["evil.example.com", "api.ejemplo.com:4000", "10.0.0.5"])
def test_host_distinto_de_localhost_da_403(env: Env, host: str) -> None:
    assert env.local.get("/api/setup/status", headers={"Host": host}).status_code == 403
    r = env.local.post("/api/setup/database", json=env.database(), headers={"Host": host})
    assert r.status_code == 403


@pytest.mark.parametrize("host", ["localhost", "localhost:4000", "127.0.0.1:4000", "[::1]:4000"])
def test_hosts_locales_validos(env: Env, host: str) -> None:
    assert env.local.get("/api/setup/status", headers={"Host": host}).status_code == 200


def test_el_codigo_se_consume_tras_cada_paso_correcto(env: Env) -> None:
    first = env.code
    assert env.local.post("/api/setup/database", json=env.database()).status_code == 200
    assert env.code != first  # se emitió un código nuevo (solo en la consola)
    reuse = env.local.post("/api/setup/admin", json=env.admin(setupCode=first))
    assert reuse.status_code == 403
    assert env.local.post("/api/setup/admin", json=env.admin()).status_code == 201
    assert env.app.state.setup_gate.code is None


def _two_clients(env: Env) -> tuple[TestClient, TestClient]:
    def make() -> TestClient:
        return TestClient(env.app, base_url="http://localhost", client=("127.0.0.1", 50000))

    return make(), make()


def test_dos_peticiones_simultaneas_de_database_solo_una_tiene_exito(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    from concurrent.futures import ThreadPoolExecutor

    from app.services import setup_service

    real = setup_service.connect_and_migrate

    def slow(*a: object, **k: object):  # type: ignore[no-untyped-def]
        time.sleep(0.4)  # fuerza el solape entre las dos peticiones
        return real(*a, **k)  # type: ignore[arg-type]

    monkeypatch.setattr(setup_service, "connect_and_migrate", slow)
    c1, c2 = _two_clients(env)
    body = env.database()
    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(c.post, "/api/setup/database", json=body) for c in (c1, c2)]
        codes = sorted(f.result().status_code for f in futures)
    assert codes[0] == 200
    assert codes[1] in (403, 409)
    assert env.vault.get_secret("db.url") == env.db_url


def test_dos_peticiones_simultaneas_de_admin_solo_una_crea_el_admin(env: Env) -> None:
    from concurrent.futures import ThreadPoolExecutor

    assert env.local.post("/api/setup/database", json=env.database()).status_code == 200
    c1, c2 = _two_clients(env)
    code = env.code
    with ThreadPoolExecutor(2) as pool:
        futures = [
            pool.submit(
                c.post,
                "/api/setup/admin",
                json=env.admin(setupCode=code, email=f"admin{i}@example.com"),
            )
            for i, c in enumerate((c1, c2))
        ]
        codes = sorted(f.result().status_code for f in futures)
    assert codes[0] == 201
    assert codes[1] in (403, 404, 409)
    db = try_get_db()
    assert db is not None
    assert db.fetch_one("SELECT COUNT(*) AS n FROM users WHERE role = 'ADMIN'") == {"n": 1}


def test_insercion_atomica_del_admin_sin_pasar_por_el_lock(migrated_db: Database) -> None:
    """Aunque dos llamadas lleguen a la vez al servicio, la inserción garantiza un solo ADMIN."""
    from concurrent.futures import ThreadPoolExecutor

    from app.errors import AppError
    from app.services.setup_service import create_first_admin

    def attempt(i: int) -> str:
        try:
            create_first_admin(migrated_db, f"a{i}@example.com", "A", PASSWORD)
            return "ok"
        except AppError as exc:
            return exc.code

    with ThreadPoolExecutor(2) as pool:
        results = sorted(pool.map(attempt, range(2)))
    assert results == ["NOT_FOUND", "ok"]
    assert migrated_db.fetch_one("SELECT COUNT(*) AS n FROM users") == {"n": 1}
