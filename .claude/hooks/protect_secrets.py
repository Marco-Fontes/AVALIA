#!/usr/bin/env python
"""CC-H02 — protect_secrets: impede GRAVAR segredos no repositório.

PreToolUse (Edit|Write|MultiEdit). Bloqueia (deny) quando:
- o destino é arquivo de segredo (.env real, **/secrets/**, *.pem); ou
- o conteúdo proposto contém um segredo de fornecedor de ALTA confiança
  (chave Anthropic/OpenRouter/OpenAI/AWS/GitHub/Slack) como literal.

Complementa as permissions.deny de LEITURA do settings.json (este pega a ESCRITA).
Conservador por decisão: só padrões de altíssima confiança → não vira loop de falso
positivo (placeholders e leituras de env tipo os.environ[...] passam).

Falha interna do hook → exit 0 (allow): guard quebrado não pode travar o trabalho.
"""

from __future__ import annotations

import json
import re
import sys

SECRET_PATTERNS = [
    (re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"), "chave Anthropic (sk-ant-…)"),
    (re.compile(r"sk-or-v1-[A-Za-z0-9]{20,}"), "chave OpenRouter (sk-or-…)"),
    (re.compile(r"sk-[A-Za-z0-9]{32,}"), "chave OpenAI (sk-…)"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS Access Key ID"),
    (re.compile(r"ghp_[A-Za-z0-9]{36}"), "GitHub PAT"),
    (re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"), "token Slack"),
]


def is_secret_path(path: str) -> bool:
    p = path.replace("\\", "/").lower()
    name = p.rsplit("/", 1)[-1]
    if "/secrets/" in p or p.endswith(".pem"):
        return True
    return name == ".env" or (name.startswith(".env.") and name != ".env.example")


def extract_target(data: dict) -> tuple[str, str]:
    ti = data.get("tool_input", {}) or {}
    path = ti.get("file_path") or ti.get("path") or ""
    parts: list[str] = []
    for key in ("content", "new_string", "new_str"):
        if isinstance(ti.get(key), str):
            parts.append(ti[key])
    for edit in ti.get("edits", []) or []:
        if isinstance(edit, dict) and isinstance(edit.get("new_string"), str):
            parts.append(edit["new_string"])
    return path, "\n".join(parts)


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

    path, content = extract_target(data)
    if path and is_secret_path(path):
        deny(
            f"protect_secrets: gravar em arquivo de segredo ('{path}') é proibido. "
            "Use .env (não versionado) ou variável de ambiente; versione só .env.example."
        )
    for rx, label in SECRET_PATTERNS:
        if rx.search(content):
            deny(
                f"protect_secrets: segredo detectado no conteúdo ({label}). Não escreva "
                "segredos no repositório; leia de variável de ambiente / cofre."
            )
    sys.exit(0)


if __name__ == "__main__":
    main()
