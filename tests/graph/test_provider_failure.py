"""CB-10 / T-1008 (DoD reforçado v1.4) — falha REAL do provedor não aborta a avaliação.

Reproduz o defeito da auditoria de 2026-09-22: um `RateLimitError` (429) do SDK propagava pelo
juiz e derrubava o grafo inteiro. Agora o `ModelGateway` real traduz a exceção, o juiz esgota
retry → fallback e o grafo emite laudo PARCIAL honesto. Cliente de modelo falso (sem rede);
nada executa o alvo (RNF-05).

Rastreabilidade: RNF-12, CB-10.
"""

from __future__ import annotations

import pytest

from avalia.config.evaluator_config import EvaluatorConfig, NodeModelConfig, RetryPolicy
from avalia.domain.enums import Dimension, RunStatus
from avalia.domain.submission import Submission, TargetMetadata
from avalia.graph.build_graph import build_avalia_graph
from avalia.model_gateway.gateway import ModelGateway

pytestmark = pytest.mark.fast

_SRC = (
    "from langgraph.graph import StateGraph\n"
    "SYSTEM_PROMPT = 'cite a fonte'\n"
    "def agent_a(state):\n    return state\n"
    "def build(g):\n    g.add_edge('agent_a', 'agent_b')\n"
)


class RateLimitError(Exception):
    status_code = 429


class _AlwaysRateLimited:
    def with_structured_output(self, schema, include_raw: bool = False):
        return self

    def invoke(self, messages):
        raise RateLimitError("rate_limit_error: 429")


def test_provider_rate_limit_everywhere_yields_partial_report_not_crash():
    no_wait = RetryPolicy(max_attempts=2, backoff_seconds=0.0)
    gw_config = EvaluatorConfig(
        node_models={f"juiz_{d.value}": NodeModelConfig(retry=no_wait) for d in Dimension}
    )
    gateway = ModelGateway(gw_config, client_factory=lambda ref: _AlwaysRateLimited(), env={})
    graph = build_avalia_graph(gateway=gateway)
    submission = Submission(
        artifact_files={"graph.py": _SRC},
        metadata=TargetMetadata(target_id="alvo", version="v1"),
        config=EvaluatorConfig(),
    )

    result = graph.invoke({"submission": submission}, config={"configurable": {"thread_id": "t"}})

    assert result["status"] is RunStatus.PARTIAL
    report = result["report"]
    assert len(report.dimensions) == 7
    subs = {s for dr in report.dimensions for s in dr.model_substitutions}
    assert any("fallback de modelo esgotado" in s for s in subs)  # declarado, nunca silencioso
