"""Frente 2 — prontidão estática (teto ≈ 90) exibida honestamente.

DoD (PLANO-MELHORIAS §4):
- `static_ceiling` presente no contrato/JSON do laudo (default 90, configurável — RNF-06);
- render Markdown e resumo CLI anotam o teto da Fase 1;
- **nenhum** número de cálculo muda (score/veredito/faixas idênticos) — suíte de aceite intacta.
"""

from __future__ import annotations

import json

import pytest

from avalia.aggregate import aggregate
from avalia.classify import classify_target
from avalia.config.evaluator_config import EvaluatorConfig
from avalia.config.weight_profiles import load_weight_profiles
from avalia.domain.contracts import ComponentInventory, EvaluationReport
from avalia.evaluators.trajetoria import evaluate_trajetoria
from avalia.extract.tsm_builder import build_tsm
from avalia.report.build import build_report
from avalia.report.render import render_markdown
from avalia.weights_select import select_weights

pytestmark = pytest.mark.fast

_SRC = """
PLANNER_PROMPT = "Você é o planejador."
SOLVER_PROMPT = "Você é o executor."


def solver_agent(state):
    for _ in range(3):
        state = step(state)
    return state


def step(state):
    return state


def build(g):
    g.add_edge("planner", "solver")
"""


def _report(config: EvaluatorConfig) -> EvaluationReport:
    tsm = build_tsm({"main.py": _SRC})
    classification = classify_target(tsm)
    sel = select_weights(classification, config, load_weight_profiles())
    dr = evaluate_trajetoria(tsm)
    agg = aggregate([dr], sel.profile, config)
    return build_report(
        classification=classification,
        weights=sel.profile,
        aggregate_score=agg,
        results=[dr],
        inventory=ComponentInventory(present=["codigo_fonte", "metadados"]),
        tsm=tsm,
        config=config,
    )


def test_default_static_ceiling_is_90():
    report = _report(EvaluatorConfig())
    assert report.header.static_ceiling == 90


def test_static_ceiling_present_in_json_projection():
    report = _report(EvaluatorConfig())
    payload = json.loads(report.model_dump_json())
    assert payload["header"]["static_ceiling"] == 90


def test_static_ceiling_is_configurable():
    report = _report(EvaluatorConfig(static_ceiling=85))
    assert report.header.static_ceiling == 85


def test_markdown_annotates_static_readiness():
    md = render_markdown(_report(EvaluatorConfig()))
    assert "Prontidão estática" in md
    assert "Fase 2" in md
    assert "≈ **90**" in md


def test_static_ceiling_does_not_change_score_or_verdict():
    base = _report(EvaluatorConfig())
    lowered = _report(EvaluatorConfig(static_ceiling=50))
    # Mudar o teto EXIBIDO não toca o cálculo: score e veredito permanecem idênticos.
    assert base.header.score == lowered.header.score
    assert base.header.verdict == lowered.header.verdict
