"""T-802 — Budget short-circuit + laudo parcial (CA-13) e fallback esgotado (CB-10).

Tudo sobre fixtures/textos estáticos; o juiz é MOCKADO (sem modelo real). Nada executa o
alvo (RNF-05).
"""

from __future__ import annotations

import pytest

from avalia.config.evaluator_config import EvaluatorConfig, RetryPolicy
from avalia.domain.enums import Confidence, RunStatus
from avalia.domain.submission import Submission, TargetMetadata
from avalia.graph.build_graph import build_avalia_graph
from avalia.graph.state import BudgetState
from avalia.judge.framework import ModelUnavailableError

pytestmark = pytest.mark.fast

_META = TargetMetadata(target_id="alvo", version="v1")
_SRC = (
    "from langgraph.graph import StateGraph\n"
    "MODEL = 'claude-opus'\n"
    "SYSTEM_PROMPT = 'cite a fonte'\n"
    "def agent_a(state):\n    return state\n"
    "def build(g):\n    g.add_edge('agent_a', 'agent_b')\n"
)


def _run(files, *, config=None, gateway=None, budget=None) -> dict:
    graph = build_avalia_graph(gateway=gateway)
    inp: dict = {
        "submission": Submission(
            artifact_files=files, metadata=_META, config=config or EvaluatorConfig()
        )
    }
    if budget is not None:
        inp["budget"] = budget
    return graph.invoke(inp, config={"configurable": {"thread_id": "t"}})


def test_ca13_large_artifact_yields_honest_partial_report():
    files = {f"noise{i}.py": "x = 1\n" for i in range(12)}
    files["graph.py"] = _SRC
    result = _run(files, config=EvaluatorConfig(max_analyzed_files=2))
    assert result["status"] is RunStatus.PARTIAL
    report = result["report"]
    # cobertura declarada (integral vs. amostrado)
    assert report.metadata.coverage.sampled
    assert any(lim.startswith("Laudo PARCIAL") for lim in report.metadata.known_limitations)
    # confiança das dimensões reduzida pela parcialidade
    assert all(dr.confidence is not Confidence.ALTO for dr in report.dimensions if dr.applicable)


def test_budget_ceiling_short_circuits_to_deterministic_partial():
    # custo já acima do teto na entrada → desvia da fan-out de juízes (degradado), laudo parcial.
    result = _run(
        {"graph.py": _SRC},
        config=EvaluatorConfig(cost_ceiling=1.0),
        budget=BudgetState(accumulated_cost=5.0),
    )
    assert result["status"] is RunStatus.PARTIAL
    assert len(result["report"].dimensions) == 7  # todas avaliadas (deterministicamente)


class _ExhaustedStructured:
    def invoke(self, messages):
        raise ModelUnavailableError("modelo indisponível")


class _ExhaustedGateway:
    """Gateway cujo primário e fallback estão ambos indisponíveis (CB-10)."""

    def with_structured_output(self, node_type, role, schema):
        return _ExhaustedStructured()

    def retry_for(self, node_type):
        return RetryPolicy(max_attempts=1)


def test_cb10_exhausted_fallback_degrades_dimension_and_marks_partial():
    result = _run({"graph.py": _SRC}, gateway=_ExhaustedGateway())
    assert result["status"] is RunStatus.PARTIAL
    report = result["report"]
    # substituição/limitação DECLARADA (nunca silenciosa — RNF-12)
    subs = [s for dr in report.dimensions for s in dr.model_substitutions]
    assert subs and any("fallback de modelo esgotado" in s for s in subs)
    # dimensões que dependiam do juiz ficam com confiança baixa
    assert any(dr.confidence is Confidence.BAIXO for dr in report.dimensions)
