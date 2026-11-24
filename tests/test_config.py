import base64
import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Settings

ROOT = Path(__file__).resolve().parent.parent
KEY = base64.b64encode(b"\x01" * 32).decode()


def make(**kw: object) -> Settings:
    return Settings(_env_file=None, **kw)  # type: ignore[arg-type]


def test_valores_validos_exportan_objeto_tipado() -> None:
    s = make(port="4010")
    assert s.port == 4010
    assert s.host == "127.0.0.1"
    assert s.turso_auth_token is None
    assert s.orchestrator == "llm"
    assert s.docs_active is True


def test_el_entorno_ya_no_exige_url_de_bd() -> None:
    # La URL y el token viven en la bóveda cifrada (PLAN §16), no en el .env.
    assert Settings(_env_file=None).turso_database_url is None  # type: ignore[call-arg]


def test_entorno_invalido_termina_con_mensaje_claro_y_codigo_distinto_de_cero(
    tmp_path: Path,
) -> None:
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("TURSO_", "APP_"))}
    env["PYTHONPATH"] = str(ROOT)
    env["PORT"] = "70000"
    res = subprocess.run(  # noqa: S603
        [sys.executable, "-c", "from app.config import get_settings; get_settings()"],
        cwd=tmp_path,  # carpeta sin .env
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode != 0
    assert "PORT" in res.stderr
    assert "Traceback" not in res.stderr


def test_produccion_exige_claves_y_apaga_docs_por_defecto() -> None:
    with pytest.raises(ValidationError, match="obligatorias en producción"):
        make(node_env="production")
    s = make(node_env="production", app_master_key=KEY, session_secret=KEY)
    assert s.docs_active is False
    prod = {"node_env": "production", "app_master_key": KEY, "session_secret": KEY}
    assert make(**prod, docs_enabled="true").docs_active


def test_clave_de_cifrado_debe_ser_32_bytes() -> None:
    with pytest.raises(ValidationError, match="32 bytes"):
        make(app_master_key="corta")


def test_variable_vacia_equivale_a_no_definida(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TURSO_AUTH_TOKEN", "")
    monkeypatch.setenv("SESSION_IDLE_MINUTES", "")
    s = make()
    assert s.turso_auth_token is None
    assert s.session_idle_minutes == 30


def test_enteros_invalidos() -> None:
    with pytest.raises(ValidationError):
        make(session_max_hours="0")
    with pytest.raises(ValidationError):
        make(port="70000")
