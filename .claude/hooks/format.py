#!/usr/bin/env python
"""CC-H03 — Formatação automática (PostToolUse).

Roda `ruff format` + `ruff check --fix` apenas no arquivo .py editado, eliminando
fadiga de aprovação de formatação. Defensivo: se ruff ainda não estiver instalado
(M0 sem venv), é no-op silencioso. NUNCA bloqueia (sempre exit 0).

Não executa o código do alvo — só formata o fonte do próprio AVALIA.
"""

from __future__ import annotations

import json
import subprocess
import sys


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    ti = data.get("tool_input", {}) or {}
    path = ti.get("file_path") or ti.get("path") or ""
    if not path.endswith(".py"):
        sys.exit(0)

    for args in (["format", path], ["check", "--fix", path]):
        try:
            subprocess.run(
                [sys.executable, "-m", "ruff", *args],
                capture_output=True,
                timeout=30,
                check=False,
            )
        except Exception:
            # ruff ausente ou erro de ambiente → não atrapalha o fluxo.
            break
    sys.exit(0)


if __name__ == "__main__":
    main()
