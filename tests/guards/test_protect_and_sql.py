"""CC-T02 — testes dos hooks protect_secrets (CC-H02) e block_sql_destructive (CC-H06).

Hooks são código não testado → falso positivo vira loop de tokens caro; falso negativo
deixa passar segredo/SQL destrutivo. Cobre os dois lados (deve bloquear / não pode bloquear).

Marca `fast`: compõem o gate de Stop (quality_gate, CC-H05). Os segredos de teste são
montados por concatenação em runtime para NÃO existirem como literais no repositório
(senão o próprio protect_secrets bloquearia este arquivo). Nada aqui executa o alvo.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.fast

HOOKS = Path(__file__).resolve().parents[2] / ".claude" / "hooks"
SECRETS = HOOKS / "protect_secrets.py"
SQL = HOOKS / "block_sql_destructive.py"


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
        return {"decision": "allow"}


# ---------- CC-H02: protect_secrets ----------


def test_blocks_anthropic_key_literal():
    key = "sk-ant-" + "A1b2C3d4" * 6  # montado em runtime; não é literal no repo
    r = run_hook(SECRETS, {"file_path": "src/avalia/x.py", "content": f'K = "{key}"\n'})
    assert r["decision"] == "deny"


def test_blocks_aws_access_key_literal():
    key = "AKIA" + "ABCDEFGH12345678"
    r = run_hook(SECRETS, {"file_path": "src/avalia/x.py", "content": f'K = "{key}"\n'})
    assert r["decision"] == "deny"


def test_blocks_write_to_dotenv():
    r = run_hook(SECRETS, {"file_path": ".env", "content": "X=1\n"})
    assert r["decision"] == "deny"


def test_allows_env_example():
    r = run_hook(SECRETS, {"file_path": ".env.example", "content": "ANTHROPIC_API_KEY=\n"})
    assert r["decision"] == "allow"


def test_allows_env_var_read_without_literal():
    # Ler de variável de ambiente é o caminho CORRETO — não pode bloquear (RNF-06).
    src = 'import os\n\nkey = os.environ["ANTHROPIC_API_KEY"]\n'
    r = run_hook(SECRETS, {"file_path": "src/avalia/x.py", "content": src})
    assert r["decision"] == "allow"


# ---------- CC-H06: block_sql_destructive ----------


def cmd(c: str) -> dict:
    return {"command": c}


def test_blocks_drop_table():
    r = run_hook(SQL, cmd('psql -c "DROP TABLE reports;"'), tool_name="Bash")
    assert r["decision"] == "deny"


def test_blocks_truncate():
    r = run_hook(SQL, cmd("psql -c 'TRUNCATE reports'"), tool_name="Bash")
    assert r["decision"] == "deny"


def test_blocks_delete_without_where():
    r = run_hook(SQL, cmd('psql -c "DELETE FROM reports;"'), tool_name="Bash")
    assert r["decision"] == "deny"


def test_allows_delete_with_where():
    r = run_hook(SQL, cmd('psql -c "DELETE FROM reports WHERE id=1;"'), tool_name="Bash")
    assert r["decision"] == "allow"


def test_allows_alembic_upgrade():
    r = run_hook(SQL, cmd("alembic upgrade head"), tool_name="Bash")
    assert r["decision"] == "allow"


def test_blocks_alembic_downgrade_base():
    r = run_hook(SQL, cmd("alembic downgrade base"), tool_name="Bash")
    assert r["decision"] == "deny"
