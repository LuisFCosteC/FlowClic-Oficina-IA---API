import logging
import subprocess
import sys
from pathlib import Path

import pytest

from app.config import Settings
from app.db.bootstrap import open_configured_database
from app.security.crypto import SecretBox, generate_master_key
from app.security.envfile import import_env_secrets
from app.security.vault import Vault

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

URL = "libsql://mi-bd-secreta-org.turso.io"
TOKEN = "eyJhbGciOiJFZERTQSJ9.token-super-secreto"
ENV = (
    "# comentario\r\n"
    "PORT=4000\r\n"
    f"TURSO_DATABASE_URL={URL}\r\n"
    "HOST=127.0.0.1\r\n"
    f'TURSO_AUTH_TOKEN="{TOKEN}"\r\n'
    "CORS_ORIGIN=http://localhost:3000\r\n"
)
REST = "# comentario\r\nPORT=4000\r\nHOST=127.0.0.1\r\nCORS_ORIGIN=http://localhost:3000\r\n"


@pytest.fixture
def vault(tmp_path: Path) -> Vault:
    return Vault(tmp_path / "data" / "vault.db", SecretBox.from_base64(generate_master_key()))


def test_importa_a_la_boveda_y_limpia_el_env(
    tmp_path: Path, vault: Vault, caplog: pytest.LogCaptureFixture
) -> None:
    env = tmp_path / ".env"
    env.write_bytes(ENV.encode())
    with caplog.at_level(logging.DEBUG):
        assert import_env_secrets(env, vault) is True
    assert vault.get_secret("db.url") == URL
    assert vault.get_secret("db.auth_token") == TOKEN
    assert env.read_bytes().decode() == REST  # el resto queda exactamente igual
    assert not (tmp_path / ".env.bak").exists()
    assert list(tmp_path.glob(".env*")) == [env]  # sin temporales ni copias
    assert "conexión importada a la bóveda" in caplog.text
    assert URL not in caplog.text
    assert TOKEN not in caplog.text


def test_si_la_boveda_ya_tiene_conexion_no_toca_el_env(tmp_path: Path, vault: Vault) -> None:
    vault.set_secret("db.url", "file:otra.db")
    env = tmp_path / ".env"
    env.write_bytes(ENV.encode())
    assert import_env_secrets(env, vault) is False
    assert env.read_bytes().decode() == ENV
    assert vault.get_secret("db.url") == "file:otra.db"


def test_sin_env_o_sin_turso_no_hace_nada(tmp_path: Path, vault: Vault) -> None:
    assert import_env_secrets(tmp_path / ".env", vault) is False
    env = tmp_path / ".env"
    env.write_text("PORT=4000\n", encoding="utf-8")
    assert import_env_secrets(env, vault) is False
    assert env.read_text(encoding="utf-8") == "PORT=4000\n"
    assert not vault.has("db.url")


def test_respaldo_desde_variables_de_entorno_reales(tmp_path: Path, vault: Vault) -> None:
    env = tmp_path / ".env"
    env.write_text("PORT=4000\n", encoding="utf-8")
    assert import_env_secrets(env, vault, URL, TOKEN) is True
    assert vault.get_secret("db.url") == URL
    assert env.read_text(encoding="utf-8") == "PORT=4000\n"


def test_arranque_con_turso_en_el_env_deja_todo_en_la_boveda(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    db_url = "file:" + (tmp_path / "main.db").as_posix()
    key = generate_master_key()
    (tmp_path / ".env").write_text(
        f"APP_MASTER_KEY={key}\nTURSO_DATABASE_URL={db_url}\nTURSO_AUTH_TOKEN=\nPORT=4000\n",
        encoding="utf-8",
    )
    with caplog.at_level(logging.DEBUG):
        opened = open_configured_database(Settings(_env_file=".env"))  # type: ignore[call-arg]
    assert opened is not None
    db, v = opened
    assert db.fetch_one("SELECT 1 AS x") == {"x": 1}
    assert v.get_secret("db.url") == db_url
    text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "TURSO" not in text
    assert f"APP_MASTER_KEY={key}" in text
    assert "PORT=4000" in text
    assert db_url not in caplog.text
    db.close()
    v.close()


def test_setup_env_crea_sin_turso_con_claves_y_no_sobrescribe(tmp_path: Path) -> None:
    import setup_env

    (tmp_path / ".env.example").write_text(
        (ROOT / ".env.example").read_text(encoding="utf-8"), encoding="utf-8"
    )
    result, added = setup_env.setup(tmp_path)
    assert result == "created"
    assert set(added) == {"APP_MASTER_KEY", "SESSION_SECRET"}
    first = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "TURSO" not in first
    assert setup_env.setup(tmp_path) == ("unchanged", [])
    assert (tmp_path / ".env").read_text(encoding="utf-8") == first


def test_setup_env_en_un_env_existente_solo_anade_lo_que_falta(tmp_path: Path) -> None:
    import setup_env

    (tmp_path / ".env.example").write_text("X=1\n", encoding="utf-8")
    env = tmp_path / ".env"
    env.write_text("PORT=4000\nSESSION_SECRET=ya-existe", encoding="utf-8")
    result, added = setup_env.setup(tmp_path)
    assert result == "updated"
    assert added == ["APP_MASTER_KEY"]
    assert env.read_text(encoding="utf-8").startswith("PORT=4000\nSESSION_SECRET=ya-existe\n")


@pytest.mark.skipif(sys.platform != "win32", reason="icacls solo en Windows")
def test_en_windows_el_env_queda_con_un_unico_permiso_del_usuario(tmp_path: Path) -> None:
    import setup_env

    (tmp_path / ".env.example").write_text("APP_MASTER_KEY=\nSESSION_SECRET=\n", encoding="utf-8")
    setup_env.setup(tmp_path)
    out = subprocess.run(  # noqa: S603
        ["icacls", str(tmp_path / ".env")],  # noqa: S607
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    entries = [ln for ln in out.splitlines() if ":(" in ln]
    assert len(entries) == 1, out
