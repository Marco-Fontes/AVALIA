"""Testes dos PRÓPRIOS hooks de guarda (correção: hooks são código não testado
geram loop de tokens por falso positivo).

Invoca cada hook como subprocesso, alimentando JSON no stdin como o Claude Code faz,
e verifica decisões de allow/deny. Cobre casos positivos (deve bloquear) e negativos
(não pode bloquear → senão vira loop de correção caro).

NB: aqui `subprocess` roda os HOOKS DO AVALIA — não o sistema-alvo. RNF-05 íntegro.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[2] / ".claude" / "hooks"
EXEC_GUARD = HOOKS / "guard_no_target_exec.py"
MODEL_GUARD = HOOKS / "guard_model_access.py"


def run_hook(hook: Path, tool_input: dict, tool_name: str = "Write") -> dict:
    payload = json.dumps({"tool_name": tool_name, "tool_input": tool_input})
    proc = subprocess.run(
        [sys.executable, str(hook)],
        input=payload, capture_output=True, text=True, timeout=30,
    )
    out = proc.stdout.strip()
    if not out:
        return {"decision": "allow", "stderr": proc.stderr}
    try:
        data = json.loads(out)
        dec = data.get("hookSpecificOutput", {}).get("permissionDecision", "allow")
        return {"decision": dec, "raw": data, "stderr": proc.stderr}
    except json.JSONDecodeError:
        return {"decision": "allow", "stderr": proc.stderr}


def w(path: str, content: str) -> dict:
    return {"file_path": path, "content": content}


# ---------- CC-H01: guard_no_target_exec ----------

def test_blocks_exec_in_src():
    r = run_hook(EXEC_GUARD, w("src/avalia/x.py", "def f():\n    exec(code)\n"))
    assert r["decision"] == "deny"
    assert "RNF-05" in r["raw"]["hookSpecificOutput"]["permissionDecisionReason"]


def test_blocks_importlib_in_src():
    r = run_hook(EXEC_GUARD, w("src/avalia/x.py", "import importlib\n"))
    assert r["decision"] == "deny"


def test_blocks_import_target_fixtures():
    r = run_hook(EXEC_GUARD, w("src/avalia/x.py", "from tests.fixtures import alvo\n"))
    assert r["decision"] == "deny"


def test_ignores_fixtures_dir():
    # fixtures = dado estático do alvo; pode conter exec sem ser violação do AVALIA
    r = run_hook(EXEC_GUARD, w("tests/fixtures/alvo/main.py", "exec('x')\n"))
    assert r["decision"] == "allow"


def test_ignores_non_src():
    r = run_hook(EXEC_GUARD, w("scripts/util.py", "exec('x')\n"))
    assert r["decision"] == "allow"


def test_subprocess_warns_not_blocks():
    r = run_hook(EXEC_GUARD, w("src/avalia/x.py", "import subprocess\n"))
    assert r["decision"] == "allow"
    assert "RNF-05" in r["stderr"]  # aviso emitido, mas não bloqueia


def test_clean_src_passes():
    r = run_hook(EXEC_GUARD, w("src/avalia/x.py", "import ast\n\ndef parse(s):\n    return ast.parse(s)\n"))
    assert r["decision"] == "allow"


# ---------- CC-H07: guard_model_access (RNF-06 + RNF-12) ----------

def test_blocks_hardcoded_model_slug():
    r = run_hook(MODEL_GUARD, w("src/avalia/judge.py", 'M = "claude-opus-4-20250514"\n'))
    assert r["decision"] == "deny"
    assert "RNF-06" in r["raw"]["hookSpecificOutput"]["permissionDecisionReason"]


def test_blocks_direct_client_instantiation():
    r = run_hook(MODEL_GUARD, w("src/avalia/judge.py", "c = ChatAnthropic(model=m)\n"))
    assert r["decision"] == "deny"
    assert "RNF-12" in r["raw"]["hookSpecificOutput"]["permissionDecisionReason"]


def test_allows_slug_in_docstring():
    # NÃO pode bloquear texto que descreve o default "Opus→Sonnet" / slug em docstring
    src = '"""Default: claude-opus then claude-sonnet."""\nx = 1\n'
    r = run_hook(MODEL_GUARD, w("src/avalia/judge.py", src))
    assert r["decision"] == "allow"


def test_exempts_gateway_module():
    r = run_hook(MODEL_GUARD, w("src/avalia/model_gateway/client.py", "c = ChatAnthropic(model=m)\n"))
    assert r["decision"] == "allow"


def test_allows_word_opus_in_prose_constant():
    # "opus"/"sonnet" como palavra solta não é slug → não bloqueia
    r = run_hook(MODEL_GUARD, w("src/avalia/judge.py", 'note = "fallback de opus para sonnet"\n'))
    assert r["decision"] == "allow"
