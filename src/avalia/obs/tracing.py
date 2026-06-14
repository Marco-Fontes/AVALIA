"""T-901 — Integração LangSmith opcional + montagem de callbacks (MS-10; plan §3.11).

LangSmith é dependência OPCIONAL (`[observability]`). A ausência **não pode quebrar** o import
nem a geração do laudo: `langsmith_callbacks` faz import GUARDADO e devolve `[]` quando o pacote
falta ou o tracing está desligado. `instrument_config` mescla os callbacks (coletor in-process +
LangSmith) no `config` do `graph.invoke(...)` — o grafo em si fica inalterado. NÃO executa o alvo.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from avalia.obs.spans import SpanCollector

_TRUTHY = {"1", "true", "yes", "on"}
ENV_TRACING = "AVALIA_TRACING"
ENV_LANGCHAIN = "LANGCHAIN_TRACING_V2"


def is_tracing_enabled(env: Mapping[str, str] | None = None) -> bool:
    """Tracing externo (LangSmith) ligado por env? (`AVALIA_TRACING` ou `LANGCHAIN_TRACING_V2`)."""
    e = env if env is not None else os.environ
    return any((e.get(k) or "").strip().lower() in _TRUTHY for k in (ENV_TRACING, ENV_LANGCHAIN))


def langsmith_callbacks(env: Mapping[str, str] | None = None) -> list[Any]:
    """Callbacks de exportação LangSmith, ou `[]` se desligado/ausente (NUNCA levanta)."""
    if not is_tracing_enabled(env):
        return []
    try:  # import GUARDADO: LangSmith é opcional (plan §3.11)
        from langchain_core.tracers.langchain import LangChainTracer

        return [LangChainTracer()]
    except Exception:  # noqa: BLE001 - ausência de observabilidade nunca bloqueia o laudo
        return []


def instrument_config(
    config: Mapping[str, Any] | None = None,
    *,
    env: Mapping[str, str] | None = None,
    collector: SpanCollector | None = None,
) -> dict[str, Any]:
    """Mescla callbacks (coletor in-process + LangSmith opcional) no config do `graph.invoke`."""
    merged: dict[str, Any] = dict(config or {})
    callbacks: list[Any] = list(merged.get("callbacks") or [])
    if collector is not None:
        callbacks.append(collector)
    callbacks.extend(langsmith_callbacks(env))
    if callbacks:
        merged["callbacks"] = callbacks
    return merged
