"""Observabilidade do AVALIA (M6/E9, MS-10).

Tracing NÃO-BLOQUEANTE: o laudo gera mesmo sem LangSmith (plan §3.11). Expõe spans por nó
(latência sempre; tokens/custo quando há chamada real de modelo) e a integração opcional com
LangSmith. NADA aqui executa o alvo (RNF-05) — só observa o grafo de avaliação do AVALIA.
"""

from __future__ import annotations

from avalia.obs.spans import NodeSpan, SpanCollector
from avalia.obs.tracing import instrument_config, is_tracing_enabled, langsmith_callbacks

__all__ = [
    "NodeSpan",
    "SpanCollector",
    "instrument_config",
    "is_tracing_enabled",
    "langsmith_callbacks",
]
