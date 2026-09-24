"""PR-7 (v1.4) — nenhum segredo do alvo fica no TSM (nem, portanto, no checkpoint ou no laudo).

A CHAVE continua visível (sinal de "há credencial configurada"); só o VALOR literal é mascarado.
Referências a variáveis de ambiente são mantidas (boa prática, não segredo). Nada executa o
alvo (RNF-05).
"""

from __future__ import annotations

import pytest

from avalia.extract.secrets import REDACTED, is_sensitive_key, redact_value
from avalia.extract.tsm_builder import build_tsm

pytestmark = pytest.mark.fast


@pytest.mark.parametrize(
    ("key", "sensitive"),
    [
        ("OPENAI_API_KEY", True),
        ("api_key", True),
        ("apiKey", True),
        ("llm.anthropic.api-key", True),
        ("DB_PASSWORD", True),
        ("access_token", True),
        ("AVALIA_PG_DSN", True),
        ("client_secret", True),
        ("max_tokens", False),  # limite de custo, não credencial
        ("model", False),
        ("timeout", False),
        ("keywords", False),
    ],
)
def test_sensitive_key_detection(key, sensitive):
    assert is_sensitive_key(key) is sensitive


def test_env_references_are_kept_and_url_passwords_masked():
    assert redact_value("API_KEY", 'os.environ["API_KEY"]') == 'os.environ["API_KEY"]'
    assert redact_value("api_key", "${OPENAI_API_KEY}") == "${OPENAI_API_KEY}"
    assert redact_value("DATABASE_URL", "postgresql://u:hunter2@db:5432/x") == (
        "postgresql://u:***@db:5432/x"
    )
    assert redact_value("api_key", "sk-123") == REDACTED


def test_no_secret_value_reaches_the_tsm_from_any_extractor():
    files = {
        "app/.env": "OPENAI_API_KEY=sk-SUPERSECRETO123\nDB_PASSWORD=hunter2\n",
        "app/settings.yaml": "llm:\n  api_key: sk-yaml-SECRET\n  model: claude-x\n",
        "app/agent.py": 'API_KEY = "sk-literal-SECRET"\nMAX_TOKENS = 1024\n',
    }
    tsm = build_tsm(files)
    dump = tsm.model_dump_json()
    for secret in ("sk-SUPERSECRETO123", "hunter2", "sk-yaml-SECRET", "sk-literal-SECRET"):
        assert secret not in dump
    keys = {c.key for c in tsm.configs}
    assert {"OPENAI_API_KEY", "DB_PASSWORD", "llm.api_key"} <= keys  # a chave segue visível
    values = {c.key: c.value_expr for c in tsm.configs}
    assert values["llm.model"] == "claude-x"  # não-sensível intacto (contradição de slug)
