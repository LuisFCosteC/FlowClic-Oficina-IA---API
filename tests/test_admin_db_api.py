"""A05: conexión de BD desde el panel (bóveda cifrada, cambio en caliente) y backup manual."""

import logging
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db.database import connect_database, try_get_db
from app.db.migrate import migrate
from app.events.bus import DomainEvent, get_bus
from app.main import create_app
from app.security.crypto import SecretBox, generate_master_key
from app.security.vault import Vault

TOKEN = "token-secreto-que-no-debe-filtrarse-xyz"


@dataclass
class Env:
    client: TestClient
    vault: Vault
    url1: str
    url2: str
    tmp: Path


def _url(path: Path) -> str:
    return "file:" + path.as_posix()


def _make(tmp_path: Path, allow: bool) -> Iterator[Env]:
    key = generate_master_key()
    url1, url2 = _url(tmp_path / "uno.db"), _url(tmp_path / "dos.db")
    db = connect_database(url1)
    migrate(db)
    db.close()
    vault = Vault(tmp_path / "data" / "vault.db", SecretBox.from_base64(key))
    vault.set_secret("db.url", url1)
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        node_env="test",
        app_master_key=key,
        admin_allow_db_change=allow,
        backup_dir=str(tmp_path / "backups"),
    )
    app = create_app(settings, None, vault)
    with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 1)) as c:
        yield Env(c, vault, url1, url2, tmp_path)
    vault.close()


@pytest.fixture
def env(tmp_path: Path) -> Iterator[Env]:
    yield from _make(tmp_path, allow=True)


@pytest.fixture
def env_locked(tmp_path: Path) -> Iterator[Env]:
    yield from _make(tmp_path, allow=False)


@pytest.fixture
def events() -> Iterator[list[DomainEvent]]:
    seen: list[DomainEvent] = []
    off = get_bus().subscribe(seen.append)
    yield seen
    off()


def _put(e: Env, url: str, token: str | None = None):
    body: dict[str, str] = {"url": url}
    if token is not None:
        body["authToken"] = token
    return e.client.put("/api/admin/db", json=body)


# ── GET ──────────────────────────────────────────────────────────────────────────────────────
def test_get_db_estado_sin_token_ni_ruta_completa(env: Env) -> None:
    r = env.client.get("/api/admin/db")
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "local" and body["host"] == "uno.db"
    assert body["connected"] is True and body["hasToken"] is False
    assert isinstance(body["schemaVersion"], int) and body["lastBackupAt"] is None
    assert set(body) == {"mode", "host", "connected", "schemaVersion", "hasToken", "lastBackupAt"}
    assert str(env.tmp.as_posix()) not in r.text  # ni la ruta completa


def test_get_db_hastoken_true_pero_nunca_el_token(env: Env) -> None:
    env.vault.set_secret("db.auth_token", TOKEN)
    r = env.client.get("/api/admin/db")
    assert r.json()["hasToken"] is True and TOKEN not in r.text


# ── POST /test ───────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "url",
    ["http://x.test/db", "postgres://u:p@h/db", "ftp://h", "ws://h", "/ruta/suelta", "FILE:x"],
)
def test_test_solo_acepta_file_libsql_https(env: Env, url: str) -> None:
    r = env.client.post("/api/admin/db/test", json={"url": url})
    assert r.status_code == 400 and r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_test_no_cambia_nada(env: Env) -> None:
    before = env.vault.get_secret("db.url")
    r = env.client.post("/api/admin/db/test", json={"url": env.url1})
    assert r.status_code == 200
    assert r.json()["ok"] is True and r.json()["willCreate"] is False
    assert isinstance(r.json()["schemaVersion"], int)
    # un archivo que no existe NO se crea al probarlo
    r2 = env.client.post("/api/admin/db/test", json={"url": env.url2})
    assert r2.json()["willCreate"] is True and r2.json()["schemaVersion"] is None
    assert not (env.tmp / "dos.db").exists()
    assert env.vault.get_secret("db.url") == before


def test_test_con_archivo_que_no_es_bd_da_422_sin_reflejar_el_token(
    env: Env, caplog: pytest.LogCaptureFixture
) -> None:
    bad = env.tmp / "basura.db"
    bad.write_bytes(b"esto no es una base de datos " * 50)
    with caplog.at_level(logging.DEBUG):
        r = env.client.post("/api/admin/db/test", json={"url": _url(bad), "authToken": TOKEN})
    assert r.status_code == 422
    assert TOKEN not in r.text and TOKEN not in caplog.text


# ── PUT ──────────────────────────────────────────────────────────────────────────────────────
def test_put_sin_permiso_da_403_y_no_cambia_nada(env_locked: Env) -> None:
    r = _put(env_locked, env_locked.url2)
    assert r.status_code == 403 and r.json()["error"]["code"] == "FORBIDDEN"
    assert env_locked.vault.get_secret("db.url") == env_locked.url1
    assert not (env_locked.tmp / "dos.db").exists()


def test_put_cambia_en_caliente_y_lee_de_la_nueva(env: Env, events: list[DomainEvent]) -> None:
    c = env.client
    assert c.post("/api/agents", json={"name": "Howard", "role": "HW"}).status_code == 201
    assert len(c.get("/api/agents").json()) == 1
    r = _put(env, env.url2)
    assert r.status_code == 200
    assert r.json()["host"] == "dos.db" and r.json()["connected"] is True
    # sin reiniciar: la lectura ya viene de la BD nueva (vacía)
    assert c.get("/api/agents").json() == []
    assert env.vault.get_secret("db.url") == env.url2
    assert [e.payload["host"] for e in events if e.type == "system.db_changed"] == ["dos.db"]
    # y la BD anterior conserva sus datos intactos
    old = connect_database(env.url1)
    n = old.fetch_one("SELECT COUNT(*) AS n FROM agents")
    old.close()
    assert n == {"n": 1}
    new = try_get_db()
    assert new is not None
    row = new.fetch_one("SELECT meta FROM audit_log WHERE action = 'admin.db_changed'")
    assert row is not None and "dos.db" in row["meta"]


def test_put_guarda_el_token_en_la_boveda_y_nunca_lo_expone(
    env: Env, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        r = _put(env, env.url2, TOKEN)
        env.client.get("/api/admin/audit?limit=500")
    assert r.status_code == 200 and r.json()["hasToken"] is True
    assert env.vault.get_secret("db.auth_token") == TOKEN
    everything = r.text + env.client.get("/api/admin/audit?limit=500").text + caplog.text
    everything += env.client.get("/api/admin/db").text
    assert TOKEN not in everything


def test_put_que_falla_no_toca_nada(env: Env) -> None:
    bad = env.tmp / "basura.db"
    bad.write_bytes(b"esto no es una base de datos " * 50)
    env.vault.set_secret("db.auth_token", "tok-previo")
    r = _put(env, _url(bad), TOKEN)
    assert r.status_code == 422 and TOKEN not in r.text
    assert env.vault.get_secret("db.url") == env.url1
    assert env.vault.get_secret("db.auth_token") == "tok-previo"
    assert env.client.get("/api/agents").status_code == 200  # la BD actual sigue operativa
    assert env.client.put("/api/admin/db", json={"url": "http://x"}).status_code == 400


def test_token_vacio_se_conserva_solo_si_el_host_no_cambia(env: Env) -> None:
    env.vault.set_secret("db.auth_token", "tok-previo")
    assert _put(env, env.url1).json()["hasToken"] is True  # mismo host: se conserva
    assert env.vault.get_secret("db.auth_token") == "tok-previo"
    assert _put(env, env.url2).json()["hasToken"] is False  # otro host: no se reutiliza
    assert env.vault.get_secret("db.auth_token") is None


def test_put_a_una_bd_sin_admin_reabre_el_asistente(env: Env) -> None:
    gate = env.client.app.state.setup_gate  # type: ignore[attr-defined]
    gate.close()
    assert gate.code is None
    _put(env, env.url2)
    assert gate.code is not None


# ── Backup ───────────────────────────────────────────────────────────────────────────────────
def test_backup_manual(env: Env) -> None:
    env.client.post("/api/agents", json={"name": "Howard", "role": "HW"})
    r = env.client.post("/api/admin/backup")
    assert r.status_code == 200
    body = r.json()
    assert body["tables"]["agents"] == 1 and "sessions" not in body["tables"]
    folder = env.tmp / body["folder"]
    assert (folder / "agents.json").is_file()
    assert env.client.get("/api/admin/db").json()["lastBackupAt"] is not None
    audit = env.client.get("/api/admin/audit?action=admin.backup_created").json()
    assert len(audit) == 1
    # dos backups seguidos no se pisan
    r2 = env.client.post("/api/admin/backup")
    assert r2.json()["folder"] != body["folder"]


@pytest.mark.skipif(not hasattr(__import__("os"), "getuid"), reason="permisos POSIX")
def test_backup_con_permisos_restringidos(env: Env) -> None:
    import stat

    body = env.client.post("/api/admin/backup").json()
    mode = stat.S_IMODE((env.tmp / body["folder"] / "agents.json").stat().st_mode)
    assert mode == 0o600
