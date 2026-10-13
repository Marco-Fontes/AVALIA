"""T-901 — Integração Langfuse opcional + montagem de callbacks (MS-10; plan §3.11).

Langfuse (gratuito/self-hostável) é dependência OPCIONAL (`[observability]`). A ausência **não
pode quebrar** o import nem a geração do laudo: `langfuse_callbacks` faz import GUARDADO e devolve
`[]` quando o pacote falta ou o tracing está desligado. `instrument_config` mescla os callbacks
(coletor in-process + Langfuse) no `config` do `graph.invoke(...)` — o grafo em si fica inalterado.
NÃO executa o alvo (RNF-05).

Config por ambiente: `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` e `LANGFUSE_BASE_URL` (host —
`https://cloud.langfuse.com` por padrão). O `CallbackHandler()` da v3 lê essas variáveis sozinho.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from avalia.obs.spans import SpanCollector

_TRUTHY = {"1", "true", "yes", "on"}
ENV_TRACING = "AVALIA_TRACING"
_LANGFUSE_KEYS = ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY")


def is_tracing_enabled(env: Mapping[str, str] | None = None) -> bool:
    """Tracing externo (Langfuse) ligado? Por `AVALIA_TRACING` OU pelas chaves Langfuse."""
    e = env if env is not None else os.environ
    if (e.get(ENV_TRACING) or "").strip().lower() in _TRUTHY:
        return True
    return all((e.get(k) or "").strip() for k in _LANGFUSE_KEYS)


def langfuse_callbacks(env: Mapping[str, str] | None = None) -> list[Any]:
    """Callbacks de exportação Langfuse, ou `[]` se desligado/ausente (NUNCA levanta)."""
    if not is_tracing_enabled(env):
        return []
    try:  # import GUARDADO: Langfuse é opcional (plan §3.11)
        from langfuse.langchain import CallbackHandler

        return [CallbackHandler()]  # v3: lê LANGFUSE_* do ambiente
    except Exception:  # noqa: BLE001 - ausência de observabilidade nunca bloqueia o laudo
        return []


def instrument_config(
    config: Mapping[str, Any] | None = None,
    *,
    env: Mapping[str, str] | None = None,
    collector: SpanCollector | None = None,
) -> dict[str, Any]:
    """Mescla callbacks (coletor in-process + Langfuse opcional) no config do `graph.invoke`."""
    merged: dict[str, Any] = dict(config or {})
    callbacks: list[Any] = list(merged.get("callbacks") or [])
    if collector is not None:
        callbacks.append(collector)
    callbacks.extend(langfuse_callbacks(env))
    if callbacks:
        merged["callbacks"] = callbacks
    return merged
