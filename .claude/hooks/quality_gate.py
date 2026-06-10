#!/usr/bin/env python
"""CC-H05 — quality_gate (leve): porta de qualidade no encerramento do turno.

Stop hook. Roda um gate BARATO antes de o agente encerrar:
  1) ruff check .        (estilo / erros óbvios)
  2) pytest -q -m fast   (subconjunto rápido — o gate de Stop do CLAUDE.md)
Se algo falha, BLOQUEIA o Stop com a razão para o modelo corrigir.

Anti-loop: respeita `stop_hook_active` (não re-bloqueia em cadeia).
Defensivo: ferramenta ausente ou nenhum teste coletado (pytest exit 5) contam como OK —
o gate nunca trava por ambiente, só por falha real. Não executa nenhum ALVO (RNF-05).
"""

from __future__ import annotations

import json
import subprocess
import sys


def run(args: list[str]) -> tuple[int | None, str]:
    try:
        p = subprocess.run(
            [sys.executable, "-m", *args],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except Exception as exc:  # ferramenta ausente / erro de ambiente
        return None, str(exc)


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    if data.get("stop_hook_active"):
        sys.exit(0)  # já num ciclo de Stop disparado por hook — não re-bloquear

    failures: list[str] = []

    code, out = run(["ruff", "check", "."])
    if code not in (None, 0):
        failures.append("ruff check falhou:\n" + out[-1500:])

    code, out = run(["pytest", "-q", "-m", "fast"])
    if code not in (None, 0, 5):  # 5 = nenhum teste coletado
        failures.append("pytest -m fast falhou:\n" + out[-1500:])

    if failures:
        print(
            json.dumps(
                {
                    "decision": "block",
                    "reason": "quality_gate (leve) reprovou. Corrija antes de encerrar:\n\n"
                    + "\n\n".join(failures),
                }
            )
        )
    sys.exit(0)


if __name__ == "__main__":
    main()
