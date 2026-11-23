"""Troceado de scripts SQL en sentencias (sustituye a `executescript`, que no es fiable)."""

import re
import sqlite3

_ONLY_COMMENTS = re.compile(r"^\s*(--[^\n]*\n?|/\*.*?\*/|\s)*$", re.DOTALL)


def split_statements(script: str) -> list[str]:
    """Divide un script en sentencias completas usando el propio analizador de SQLite.

    Respeta comentarios, cadenas y triggers (`BEGIN ... END;`) con `;` internos.
    """
    statements: list[str] = []
    buffer = ""
    for line in script.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            if not _ONLY_COMMENTS.match(buffer):
                statements.append(buffer.strip())
            buffer = ""
    if not _ONLY_COMMENTS.match(buffer):
        statements.append(buffer.strip())  # resto sin `;` final
    return statements
