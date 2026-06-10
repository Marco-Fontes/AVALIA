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
        input=payload,
        capture_output=True,
        text=True,
        timeout=30,
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


def test_allows_forbidden_literals_in_docstring():
    # AST-aware: mencionar importlib/runpy/exec/eval em docstring NÃO é execução.
    # Regressão: regex bruta bloqueava isso e travava python_extractor.py.
    src = (
        '"""Extrator estático.\n\n'
        "É PROIBIDO usar importlib/runpy/exec/eval para carregar o alvo.\n"
        '"""\nimport ast\n\n'
        "# este comentário cita importlib e runpy de propósito\n"
        "def parse(s):\n    return ast.parse(s)\n"
    )
    r = run_hook(EXEC_GUARD, w("src/avalia/extract/python_extractor.py", src))
    assert r["decision"] == "allow"


def test_allows_forbidden_literals_in_string_constant():
    # Literal de string que cita os termos (ex.: mensagem de erro) não é código.
    src = 'MSG = "não use exec(), eval() nem os.system() no alvo"\n'
    r = run_hook(EXEC_GUARD, w("src/avalia/x.py", src))
    assert r["decision"] == "allow"


def test_blocks_real_importlib_import_after_docstring_mention():
    # Docstring cita importlib (OK), mas um `import importlib` real continua bloqueado.
    src = '"""Não usar importlib aqui."""\nimport importlib\nmod = importlib.import_module(\'x\')\n'
    r = run_hook(EXEC_GUARD, w("src/avalia/x.py", src))
    assert r["decision"] == "deny"
    assert "importlib" in r["raw"]["hookSpecificOutput"]["permissionDecisionReason"]


def test_blocks_runpy_usage():
    r = run_hook(EXEC_GUARD, w("src/avalia/x.py", "import runpy\nrunpy.run_path('x')\n"))
    assert r["decision"] == "deny"


def test_blocks_os_system():
    r = run_hook(EXEC_GUARD, w("src/avalia/x.py", "import os\nos.system('ls')\n"))
    assert r["decision"] == "deny"


def test_blocks_compile_exec_mode():
    r = run_hook(EXEC_GUARD, w("src/avalia/x.py", "code = compile(s, 'f', 'exec')\n"))
    assert r["decision"] == "deny"


def test_regex_fallback_on_partial_edit():
    # Conteúdo que NÃO parseia (edição parcial) → fallback regex ainda bloqueia.
    r = run_hook(EXEC_GUARD, w("src/avalia/x.py", "def f(:\n    exec(code)\n"))
    assert r["decision"] == "deny"


def test_clean_src_passes():
    src = "import ast\n\ndef parse(s):\n    return ast.parse(s)\n"
    r = run_hook(EXEC_GUARD, w("src/avalia/x.py", src))
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
    # NÃO pode bloquear slug em docstring (texto que descreve o default Opus→Sonnet)
    src = '"""Default: claude-opus then claude-sonnet."""\nx = 1\n'
    r = run_hook(MODEL_GUARD, w("src/avalia/judge.py", src))
    assert r["decision"] == "allow"


def test_exempts_gateway_module():
    r = run_hook(
        MODEL_GUARD, w("src/avalia/model_gateway/client.py", "c = ChatAnthropic(model=m)\n")
    )
    assert r["decision"] == "allow"


def test_allows_word_opus_in_prose_constant():
    # "opus"/"sonnet" como palavra solta não é slug → não bloqueia
    r = run_hook(MODEL_GUARD, w("src/avalia/judge.py", 'note = "fallback de opus para sonnet"\n'))
    assert r["decision"] == "allow"
