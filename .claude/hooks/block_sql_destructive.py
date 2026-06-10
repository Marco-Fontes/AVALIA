#!/usr/bin/env python
"""CC-H06 — block_sql_destructive: barra SQL destrutivo em comandos de shell.

PreToolUse (matcher Bash|PowerShell). Protege o Postgres de dev e o repositório de
laudos (T-601) contra operações destrutivas acidentais: DROP TABLE/DATABASE/SCHEMA/OWNED,
TRUNCATE, DELETE/UPDATE sem WHERE, ALTER … DROP, `alembic downgrade base`.

settings.json já faz `ask` para psql/alembic; este hook NEGA de forma dura o subconjunto
destrutivo. Migrações normais (alembic upgrade) passam.

Falha interna do hook → exit 0 (allow).
"""

from __future__ import annotations

import json
import re
import sys

DESTRUCTIVE = [
    (
        re.compile(r"\bDROP\s+(TABLE|DATABASE|SCHEMA|OWNED)\b", re.I),
        "DROP TABLE/DATABASE/SCHEMA/OWNED",
    ),
    (re.compile(r"\bTRUNCATE\b", re.I), "TRUNCATE"),
    (re.compile(r"\bALTER\s+TABLE\b.*\bDROP\b", re.I | re.S), "ALTER TABLE … DROP"),
    (re.compile(r"\balembic\b.*\bdowngrade\s+base\b", re.I), "alembic downgrade base"),
]
# DELETE/UPDATE sem cláusula WHERE → destrutivo em massa.
DELETE_NO_WHERE = re.compile(r"\bDELETE\s+FROM\s+\S+(?![^;]*\bWHERE\b)", re.I)
UPDATE_NO_WHERE = re.compile(r"\bUPDATE\s+\S+\s+SET\b(?![^;]*\bWHERE\b)", re.I)


def deny(reason: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )
    sys.exit(0)


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    cmd = (data.get("tool_input", {}) or {}).get("command", "")
    if not isinstance(cmd, str) or not cmd.strip():
        sys.exit(0)

    for rx, label in DESTRUCTIVE:
        if rx.search(cmd):
            deny(
                f"block_sql_destructive: comando SQL destrutivo bloqueado ({label}). "
                "Se for intencional, rode manualmente fora do agente."
            )
    if DELETE_NO_WHERE.search(cmd):
        deny("block_sql_destructive: DELETE sem WHERE bloqueado (apagaria a tabela inteira).")
    if UPDATE_NO_WHERE.search(cmd):
        deny("block_sql_destructive: UPDATE sem WHERE bloqueado (afetaria todas as linhas).")
    sys.exit(0)


if __name__ == "__main__":
    main()
