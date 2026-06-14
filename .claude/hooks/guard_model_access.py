#!/usr/bin/env python
"""CC-H07 — Guard RNF-06 + RNF-12: modelo é config, e todo acesso a LLM passa
pelo `ModelGateway`.

Cobre dois invariantes (decisão desta sessão de fechar o órfão RNF-12):
- RNF-06: nenhum slug de modelo hardcoded em literal de string no código.
- RNF-12: nenhuma instanciação direta de cliente LLM (Anthropic/OpenAI/ChatAnthropic/
  ChatOpenAI) fora do módulo do gateway — o acesso a modelo é centralizado.

PreToolUse + permissionDecision=deny (prevenção). Usa `ast` para ignorar
docstrings e comentários (evita falso positivo no texto que descreve "Opus→Sonnet").

Isenções: arquivos do próprio gateway/config/settings/conftest, onde a config de
modelo legitimamente vive.

Falha interna do hook → exit 0 (allow): um guard quebrado não pode travar o trabalho.
"""

from __future__ import annotations

import ast
import json
import re
import sys

# Slugs concretos de modelo (RNF-06). NÃO casa a palavra solta "opus"/"sonnet"
# (apareceria no texto que descreve o default) — exige o formato de slug versionado.
MODEL_SLUG = re.compile(r"^(claude-|gpt-|gemini-|o[134]-|moonshot|kimi-)", re.IGNORECASE)

# Construtores de cliente LLM proibidos fora do gateway (RNF-12).
CLIENT_NAMES = {
    "Anthropic",
    "AsyncAnthropic",
    "ChatAnthropic",
    "OpenAI",
    "AsyncOpenAI",
    "ChatOpenAI",
}

# Substrings de caminho isentas (config de modelo vive aqui legitimamente).
EXEMPT = ("model_gateway", "/config", "/settings", "conftest", "/gateway")


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


def in_scope(path: str) -> bool:
    p = path.replace("\\", "/")
    if not p.endswith(".py"):
        return False
    if "/src/" not in p and not p.startswith("src/"):
        return False
    if "/tests/fixtures/" in p or "/fixtures/" in p:
        return False
    return not any(e in p for e in EXEMPT)


def violations(content: str) -> list[str]:
    """Analisa via AST; só reporta o que está em código real (não docstring/comentário)."""
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return []  # edição parcial/incompleta — deixa passar; ast pega no estado final
    found: list[str] = []
    for node in ast.walk(tree):
        # RNF-06: slug de modelo em literal de string de código
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if MODEL_SLUG.match(node.value.strip()):
                found.append(f'slug de modelo hardcoded: "{node.value}" (RNF-06)')
        # RNF-12: instanciação direta de cliente LLM
        if isinstance(node, ast.Call):
            fn = node.func
            name = getattr(fn, "id", None) or getattr(fn, "attr", None)
            if name in CLIENT_NAMES:
                found.append(f"cliente LLM instanciado direto: {name}() (RNF-12)")
    return found


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    path, content = extract_target(data)
    if not path or not in_scope(path) or not content.strip():
        sys.exit(0)

    issues = violations(content)
    if issues:
        reason = (
            "RNF-06/RNF-12: modelo é configuração e todo acesso a LLM passa pelo "
            "ModelGateway. Problemas: " + "; ".join(dict.fromkeys(issues)) + ". "
            "Mova slugs para config e use o ModelGateway (default Opus→Sonnet, "
            "back-ends Anthropic/OpenRouter)."
        )
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
    sys.exit(0)


if __name__ == "__main__":
    main()
