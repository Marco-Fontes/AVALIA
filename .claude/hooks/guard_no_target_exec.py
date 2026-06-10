#!/usr/bin/env python
"""CC-H01 — Guard RNF-05: o AVALIA nunca executa/importa o código do alvo.

Enforça RNF-05 / S-04 / T-1006 na ESCRITA (PreToolUse), antes de o conteúdo
tocar o disco. Decisão desta sessão: PreToolUse + permissionDecision=deny
(prevenção, não correção).

Protocolo de hook do Claude Code:
- stdin: JSON com tool_name e tool_input (conteúdo proposto).
- PreToolUse: para BLOQUEAR, imprime JSON com
  hookSpecificOutput.permissionDecision="deny" e sai com código 0.
  Para permitir, sai 0 sem decisão (ou "allow").
Falha do próprio hook nunca deve travar o trabalho → erros internos = exit 0 (allow).

Escopo: só arquivos sob src/ do AVALIA. tests/fixtures/ são DADO ESTÁTICO do
alvo (não código do AVALIA) e são ignorados de propósito.
"""

from __future__ import annotations

import json
import re
import sys

# Padrões que significam "executar/importar código" — proibidos em src/ do AVALIA.
BLOCK_PATTERNS = [
    (re.compile(r"\bexec\s*\("), "exec()"),
    (re.compile(r"\beval\s*\("), "eval()"),
    (re.compile(r"\bos\.system\s*\("), "os.system()"),
    (re.compile(r"\b__import__\s*\("), "__import__()"),
    (re.compile(r"\bimportlib\b"), "importlib"),
    (re.compile(r"\brunpy\b"), "runpy"),
    (re.compile(r"\bcompile\s*\([^)]*['\"]exec['\"]"), "compile(..., 'exec')"),
    # importar fixtures de alvo como se fossem módulos do AVALIA
    (re.compile(r"\b(import|from)\s+tests\.fixtures"), "import de tests.fixtures"),
]
# Apenas AVISO (não bloqueia): subprocess é legítimo p/ ler metadados git do alvo
# (RF-28); executar o alvo via subprocess não é. O humano/juiz decide o caso.
WARN_PATTERNS = [(re.compile(r"\bsubprocess\b"), "subprocess")]


def extract_target(data: dict) -> tuple[str, str]:
    """Retorna (path, conteúdo_proposto) do tool_input, agnóstico a Edit/Write/MultiEdit."""
    ti = data.get("tool_input", {}) or {}
    path = ti.get("file_path") or ti.get("path") or ""
    parts: list[str] = []
    for key in ("content", "new_string", "new_str"):
        if isinstance(ti.get(key), str):
            parts.append(ti[key])
    for edit in ti.get("edits", []) or []:  # MultiEdit
        if isinstance(edit, dict) and isinstance(edit.get("new_string"), str):
            parts.append(edit["new_string"])
    return path, "\n".join(parts)


def in_scope(path: str) -> bool:
    p = path.replace("\\", "/")
    if "/src/" not in p and not p.startswith("src/"):
        return False
    if "/tests/fixtures/" in p or "/fixtures/" in p:  # dado estático do alvo
        return False
    return p.endswith(".py")


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
        sys.exit(0)  # sem input válido → não atrapalha

    path, content = extract_target(data)
    if not path or not in_scope(path):
        sys.exit(0)

    for rx, label in BLOCK_PATTERNS:
        if rx.search(content):
            deny(
                f"RNF-05/S-04: o AVALIA NUNCA executa nem importa o código do alvo. "
                f"Padrão proibido em src/: {label}. "
                f"A análise é estática (ast/tree-sitter). Ver T-1006 / tests/guards/."
            )

    warns = [label for rx, label in WARN_PATTERNS if rx.search(content)]
    if warns:
        # Aviso não bloqueia: emitir no stderr e permitir.
        sys.stderr.write(
            "AVISO RNF-05: uso de "
            + ", ".join(warns)
            + " — ler metadados git do alvo (RF-28) é OK; executar o alvo não é.\n"
        )
    sys.exit(0)


if __name__ == "__main__":
    main()
