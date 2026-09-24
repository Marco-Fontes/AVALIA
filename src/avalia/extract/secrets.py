"""Mascaramento de segredos nos fatos de config do TSM (v1.4, PLANO-QUALIDADE PR-7).

O TSM guarda o VALOR de itens de config (`ConfigItem.value_expr` + `snippet` da evidência). Com o
checkpointer persistente (PostgresSaver, M11), um `.env` ou `api_key="sk-..."` do alvo iria parar
no banco. Aqui o valor de chaves sensíveis vira `<redacted>` — a CHAVE continua visível (a
detecção de "há api_key configurada" e de contradição de slug de modelo não depende do valor).

Referências a variáveis de ambiente (`os.environ[...]`, `getenv(...)`, `${VAR}`, `process.env`)
são mantidas: são sinal útil de boa prática, não segredo. Credenciais embutidas em URL
(`scheme://user:senha@host`) têm só a senha mascarada, em qualquer chave.

Leitura de TEXTO apenas; nada executa o alvo (RNF-05).
"""

from __future__ import annotations

import re

from avalia.domain.tsm import ConfigItem

REDACTED = "<redacted>"

# Palavras (após separar snake/camel/kebab) que marcam a chave como sensível. "tokens" (plural,
# ex.: max_tokens) NÃO está aqui de propósito: é limite de custo, não credencial.
_SENSITIVE_WORDS = frozenset(
    {
        "key",
        "apikey",
        "secret",
        "password",
        "passwd",
        "pwd",
        "token",
        "dsn",
        "credential",
        "credentials",
        "private",
    }
)
_ENV_REFERENCE = re.compile(r"os\.environ|getenv\s*\(|\$\{|process\.env|env\(", re.IGNORECASE)
_URL_CREDENTIALS = re.compile(r"(://[^:/@\s]+:)([^@\s]+)(@)")


def _words(key: str) -> list[str]:
    last = [seg for seg in re.split(r"[.\[\]]", key) if seg][-1:] or [key]
    snake = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", last[0])
    return [w for w in re.split(r"[^a-z0-9]+", snake.lower()) if w]


def is_sensitive_key(key: str) -> bool:
    """A chave (último segmento do caminho achatado) nomeia uma credencial?"""
    return any(word in _SENSITIVE_WORDS for word in _words(key))


def redact_value(key: str, value: str) -> str:
    """Valor seguro para guardar no TSM/checkpoint/laudo."""
    if is_sensitive_key(key) and value not in ("", "null") and not _ENV_REFERENCE.search(value):
        return REDACTED
    return _URL_CREDENTIALS.sub(r"\1***\3", value)


def redact_config(item: ConfigItem) -> ConfigItem:
    """Cópia do item com valor e trecho de evidência mascarados (identidade preservada)."""
    value = redact_value(item.key, item.value_expr)
    snippet = item.evidence.snippet
    safe_snippet = redact_value(item.key, snippet) if snippet is not None else None
    if value == item.value_expr and safe_snippet == snippet:
        return item
    return item.model_copy(
        update={
            "value_expr": value,
            "evidence": item.evidence.model_copy(update={"snippet": safe_snippet}),
        }
    )
