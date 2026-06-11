"""T-311/T-502/T-503 — agregação completa das 7 dimensões.

Order-independence do fan-in (T-311), exclusão por piso de confiança (T-502) e condições de
aprovação priorizadas por urgência (T-503).
"""

from __future__ import annotations

import pytest

from avalia.aggregate import aggregate
from avalia.classify import classify_target
from avalia.config.evaluator_config import EvaluatorConfig
from avalia.config.weight_profiles import load_weight_profiles
from avalia.domain.enums import Confidence, Dimension, Urgency, Verdict
from avalia.evaluators.registry import EVALUATORS
from avalia.extract.tsm_builder import build_tsm
from avalia.weights_select import select_weights

pytestmark = pytest.mark.fast

_LOOP = """
PLANNER_PROMPT = "Você é o planejador."
SOLVER_PROMPT = "Você é o executor."


def solver_agent(state):
    while True:
        state = step(state)


def step(state):
    return state


def build(g):
    g.add_edge("planner", "solver")
"""


def _results_and_profile():
    tsm = build_tsm({"main.py": _LOOP})
    classification = classify_target(tsm)
    profile = select_weights(classification, EvaluatorConfig(), load_weight_profiles()).profile
    results = [EVALUATORS[d](tsm, classification) for d in Dimension]
    return results, profile


def test_aggregate_is_order_independent():
    results, profile = _results_and_profile()
    cfg = EvaluatorConfig()
    a = aggregate(results, profile, cfg)
    b = aggregate(list(reversed(results)), profile, cfg)
    assert (a.score, a.verdict) == (b.score, b.verdict)
    assert [c.statement for c in a.approval_conditions] == [
        c.statement for c in b.approval_conditions
    ]


def test_seven_dimensions_aggregate_to_conditional():
    results, profile = _results_and_profile()
    assert len(results) == 7
    agg = aggregate(results, profile, EvaluatorConfig())
    assert agg.verdict is Verdict.APROVACAO_CONDICIONAL


def test_conditions_prioritized_critical_first():
    results, profile = _results_and_profile()
    agg = aggregate(results, profile, EvaluatorConfig())
    urgencies = [c.urgency for c in agg.approval_conditions]
    assert Urgency.CRITICO in urgencies
    assert urgencies == sorted(
        urgencies, key=lambda u: {Urgency.CRITICO: 0, Urgency.IMPORTANTE: 1, Urgency.SUGESTAO: 2}[u]
    )
    # condição crítica de loop sem teto presente e rastreável
    crit = next(c for c in agg.approval_conditions if c.urgency is Urgency.CRITICO)
    assert "teto de iteração" in crit.statement and crit.traces_to


def test_confidence_floor_excludes_multiple_low_conf():
    results, profile = _results_and_profile()
    lowered = [dr.model_copy(update={"confidence": Confidence.BAIXO}) for dr in results]
    cfg = EvaluatorConfig(confidence_floor=Confidence.MEDIO)
    agg = aggregate(lowered, profile, cfg)
    # todas as aplicáveis caíram abaixo do piso → todas excluídas
    applicable = {dr.dimension for dr in lowered if dr.applicable}
    assert set(agg.excluded_low_conf) == applicable
