"""Acceso a datos: interfaz `Database` y sus implementaciones (PLAN §0.3).

Lecciones de la prueba P00 que condicionan este diseño:
- `executescript` no lanza error con SQL roto ni es atómico: **no se usa**.
- Sin `BEGIN` explícito el DDL se autocommitea; con `BEGIN` + `execute` por sentencia el rollback
  sí deshace DDL y DML. Por eso `transaction()` hace `BEGIN` explícito.
- Los errores SQL de `libsql` llegan como `ValueError`; aquí se traducen a `DatabaseError`.
"""

import sqlite3
import threading
from collections.abc import Iterator, Sequence
from contextlib import AbstractContextManager, contextmanager
from typing import Any, Literal, Protocol

import libsql

Params = Sequence[Any]
Row = dict[str, Any]


class DatabaseError(Exception):
    """Error de la base de datos (SQL inválido, conexión, etc.)."""


class IntegrityError(DatabaseError):
    """Violación de UNIQUE, CHECK, NOT NULL, etc."""


class Database(Protocol):
    """Interfaz que usan repositorios y servicios. Ninguno importa `libsql` directamente."""

    def execute(self, sql: str, params: Params = ()) -> None: ...

    def fetch_all(self, sql: str, params: Params = ()) -> list[Row]: ...

    def fetch_one(self, sql: str, params: Params = ()) -> Row | None: ...

    def transaction(self) -> AbstractContextManager["Database"]:
        """Context manager: `BEGIN` al entrar, `COMMIT` al salir, `ROLLBACK` si hay excepción."""
        ...

    def close(self) -> None: ...


def _translate(exc: Exception) -> DatabaseError:
    msg = str(exc)
    if isinstance(exc, sqlite3.IntegrityError) or "constraint failed" in msg:
        return IntegrityError(msg)
    return DatabaseError(msg)


class _ConnectionDatabase:
    """Implementación sobre una conexión DB-API (libsql o sqlite3), con acceso serializado."""

    def __init__(self, conn: Any) -> None:
        self._conn = conn
        self._lock = threading.RLock()
        self._in_tx = False

    # --- internos ---
    def _run(self, sql: str, params: Params) -> Any:
        try:
            return self._conn.execute(sql, tuple(params))
        except (ValueError, sqlite3.Error) as exc:
            if not self._in_tx:
                self._safe_rollback()  # no dejar una transacción implícita abierta tras un error
            raise _translate(exc) from exc

    def _safe_rollback(self) -> None:
        try:
            self._conn.rollback()
        except (ValueError, sqlite3.Error):
            pass

    @staticmethod
    def _to_rows(cursor: Any) -> list[Row]:
        names = [d[0] for d in cursor.description or ()]
        return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]

    # --- API pública ---
    def execute(self, sql: str, params: Params = ()) -> None:
        with self._lock:
            self._run(sql, params)
            if not self._in_tx:
                self._conn.commit()

    def fetch_all(self, sql: str, params: Params = ()) -> list[Row]:
        with self._lock:
            return self._to_rows(self._run(sql, params))

    def fetch_one(self, sql: str, params: Params = ()) -> Row | None:
        rows = self.fetch_all(sql, params)
        return rows[0] if rows else None

    @contextmanager
    def transaction(self) -> Iterator[Database]:
        with self._lock:
            if self._in_tx:
                raise RuntimeError("Transacciones anidadas no soportadas")
            self._safe_rollback()  # limpia cualquier transacción implícita colgada
            try:
                self._conn.execute("BEGIN")
            except (ValueError, sqlite3.Error) as exc:
                raise _translate(exc) from exc
            self._in_tx = True
            try:
                yield self
            except BaseException:
                self._safe_rollback()
                raise
            else:
                try:
                    self._conn.commit()
                except (ValueError, sqlite3.Error) as exc:
                    self._safe_rollback()
                    raise _translate(exc) from exc
            finally:
                self._in_tx = False

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except (ValueError, sqlite3.Error):
                pass


class LibsqlDatabase(_ConnectionDatabase):
    """Cliente oficial libSQL/Turso: sirve para `file:` y para `libsql://`."""

    def __init__(self, url: str, auth_token: str | None = None) -> None:
        if auth_token:
            conn = libsql.connect(url, auth_token=auth_token)
        else:
            conn = libsql.connect(url)
        super().__init__(conn)


class SqliteDatabase(_ConnectionDatabase):
    """Respaldo con la biblioteca estándar, solo para URLs `file:` (DB_DRIVER=sqlite)."""

    def __init__(self, url: str) -> None:
        if not url.startswith("file:"):
            raise ValueError("DB_DRIVER=sqlite solo admite URLs file:")
        path = url[len("file:") :]
        # isolation_level=None: autocommit; las transacciones las controlamos con BEGIN explícito.
        conn = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
        super().__init__(conn)


def connect_database(
    url: str,
    auth_token: str | None = None,
    driver: Literal["libsql", "sqlite"] = "libsql",
) -> Database:
    """Crea una conexión. Con token vacío no se envía token."""
    if driver == "sqlite":
        return SqliteDatabase(url)
    return LibsqlDatabase(url, auth_token or None)


# --- Conexión activa de la aplicación (permite el cambio en caliente de PLAN §13.2) ---
_holder_lock = threading.Lock()
_current: Database | None = None


def set_db(db: Database) -> None:
    global _current
    with _holder_lock:
        _current = db


def get_db() -> Database:
    """Dependencia de FastAPI: conexión activa (los repositorios la reciben por argumento)."""
    db = _current
    if db is None:
        raise RuntimeError("La base de datos no está inicializada")
    return db


def try_get_db() -> Database | None:
    """Conexión activa o None (modo SETUP: aún no hay BD configurada)."""
    return _current


def clear_db() -> None:
    global _current
    with _holder_lock:
        _current = None


def swap_db(new: Database, close_old_after: float = 5.0) -> None:
    """Cambia la conexión activa en caliente; la anterior se cierra tras unos segundos."""
    global _current
    with _holder_lock:
        old, _current = _current, new
    if old is not None:
        timer = threading.Timer(close_old_after, old.close)
        timer.daemon = True
        timer.start()
