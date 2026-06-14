"""T-901 — Spans por nó (latência + tokens/custo) via callback LangChain (MS-10).

`SpanCollector` é um `BaseCallbackHandler` que registra um `NodeSpan` para cada nó do grafo
(latência) e para cada chamada de modelo (tokens/custo, quando há chamada real — com gateway
mockado nos testes não há). É **resiliente**: toda lógica em try/except, pois um erro de callback
JAMAIS pode derrubar a avaliação (não-bloqueante, plan §3.11). NÃO executa o alvo (RNF-05).
"""

from __future__ import annotations

import time
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from pydantic import BaseModel, ConfigDict, Field


class NodeSpan(BaseModel):
    """Span de execução de um nó (ou de uma chamada de modelo). Latência sempre presente."""

    model_config = ConfigDict(frozen=True)

    node: str
    kind: str = "node"  # node | llm
    duration_s: float = Field(ge=0.0)
    cost: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


def _node_name(metadata: dict[str, Any] | None, serialized: dict[str, Any] | None) -> str | None:
    """Nome do nó do LangGraph, se este run for um nó (senão None → ignorado)."""
    if metadata and metadata.get("langgraph_node"):
        return str(metadata["langgraph_node"])
    return None


class SpanCollector(BaseCallbackHandler):
    """Coletor in-process de spans. Sempre disponível (independe de LangSmith)."""

    def __init__(self) -> None:
        self.spans: list[NodeSpan] = []
        self._chain_starts: dict[UUID, tuple[str, float]] = {}
        self._llm_starts: dict[UUID, tuple[str, float]] = {}

    # ---- nós do grafo (latência) ----
    def on_chain_start(
        self,
        serialized: dict[str, Any] | None,
        inputs: Any,
        *,
        run_id: UUID,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        try:
            node = _node_name(metadata, serialized)
            if node is not None:
                self._chain_starts[run_id] = (node, time.monotonic())
        except Exception:  # noqa: BLE001 - callback nunca pode derrubar a avaliação
            pass

    def on_chain_end(self, outputs: Any, *, run_id: UUID, **kwargs: Any) -> None:
        try:
            entry = self._chain_starts.pop(run_id, None)
            if entry is not None:
                node, t0 = entry
                self.spans.append(
                    NodeSpan(node=node, kind="node", duration_s=time.monotonic() - t0)
                )
        except Exception:  # noqa: BLE001
            pass

    # ---- chamadas de modelo (tokens/custo, best-effort) ----
    def on_llm_start(
        self, serialized: dict[str, Any] | None, prompts: Any, *, run_id: UUID, **kwargs: Any
    ) -> None:
        try:
            name = (serialized or {}).get("name") or "<llm>"
            self._llm_starts[run_id] = (str(name), time.monotonic())
        except Exception:  # noqa: BLE001
            pass

    def on_llm_end(self, response: Any, *, run_id: UUID, **kwargs: Any) -> None:
        try:
            entry = self._llm_starts.pop(run_id, None)
            name, t0 = entry if entry is not None else ("<llm>", time.monotonic())
            usage = _usage_from(response)
            self.spans.append(
                NodeSpan(
                    node=name,
                    kind="llm",
                    duration_s=time.monotonic() - t0,
                    input_tokens=usage.get("input_tokens"),
                    output_tokens=usage.get("output_tokens"),
                )
            )
        except Exception:  # noqa: BLE001
            pass

    # ---- agregações de conveniência ----
    def node_spans(self) -> list[NodeSpan]:
        return [s for s in self.spans if s.kind == "node"]

    def total_tokens(self) -> int:
        return sum((s.input_tokens or 0) + (s.output_tokens or 0) for s in self.spans)


def _usage_from(response: Any) -> dict[str, int]:
    """Extrai tokens de um `LLMResult` (best-effort; formatos variam por provedor)."""
    out: dict[str, int] = {}
    try:
        llm_output = getattr(response, "llm_output", None) or {}
        usage = llm_output.get("token_usage") or llm_output.get("usage") or {}
        if usage.get("prompt_tokens") is not None:
            out["input_tokens"] = int(usage["prompt_tokens"])
        if usage.get("completion_tokens") is not None:
            out["output_tokens"] = int(usage["completion_tokens"])
    except Exception:  # noqa: BLE001
        pass
    return out
