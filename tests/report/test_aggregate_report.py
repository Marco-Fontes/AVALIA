"""T-501/T-701/T-703 — agregação, condições de aprovação (CA-09) e renderização.

DoD: faixa condicional gera condição "adicionar teto…" rastreável (CA-09); laudo tem os
blocos; render MD/JSON fiéis; piso de confiança exclui (RF-22).
"""

from __future__ import annotations

import json

import pytest

from avalia.aggregate import aggregate
from avalia.classify import classify_target
from avalia.config.evaluator_config import EvaluatorConfig
from avalia.config.weight_profiles import load_weight_profiles
from avalia.domain.contracts import ComponentInventory, EvaluationReport
from avalia.domain.enums import Confidence, Verdict
from avalia.domain.taxonomy import FindingType
from avalia.evaluators.trajetoria import evaluate_trajetoria
from avalia.extract.tsm_builder import build_tsm
from avalia.report.build import build_report
from avalia.report.render import render_json, render_markdown
from avalia.weights_select import select_weights

pytestmark = pytest.mark.fast

_LOOP_SEM_TETO = """
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


def _pipeline(files: dict[str, str]):
    tsm = build_tsm(files)
    classification = classify_target(tsm)
    sel = select_weights(classification, EvaluatorConfig(), load_weight_profiles())
    dr = evaluate_trajetoria(tsm)
    agg = aggregate([dr], sel.profile, EvaluatorConfig())
    return tsm, classification, sel, dr, agg


def test_aggregate_condition_traces_to_finding():
    _tsm, _cls, _sel, dr, agg = _pipeline({"main.py": _LOOP_SEM_TETO})
    assert agg.verdict is Verdict.APROVACAO_CONDICIONAL  # faixa 50–74
    assert agg.approval_conditions
    cond = agg.approval_conditions[0]
    finding = next(f for f in dr.findings if f.finding_type is FindingType.LOOP_SEM_TETO)
    assert "Adicionar teto de iteração no nó" in cond.statement
    assert "solver_agent" in cond.statement
    assert cond.traces_to == finding.identity  # CA-09: rastreável ao achado


def test_build_report_has_blocks_and_renders():
    tsm, classification, sel, dr, agg = _pipeline({"main.py": _LOOP_SEM_TETO})
    report = build_report(
        classification=classification,
        weights=sel.profile,
        aggregate_score=agg,
        results=[dr],
        inventory=ComponentInventory(present=["codigo_fonte", "metadados"]),
        tsm=tsm,
        config=EvaluatorConfig(),
    )
    assert report.header.verdict is Verdict.APROVACAO_CONDICIONAL
    assert len(report.dimensions) == 1
    assert report.approval_conditions

    md = render_markdown(report)
    assert "Condições de aprovação" in md
    assert "Adicionar teto de iteração no nó" in md

    parsed = EvaluationReport.model_validate(json.loads(render_json(report)))
    assert parsed == report  # JSON fiel ao contrato


def test_confidence_floor_excludes_low_conf():
    tsm = build_tsm({"main.py": _LOOP_SEM_TETO})
    sel = select_weights(classify_target(tsm), EvaluatorConfig(), load_weight_profiles())
    dr = evaluate_trajetoria(tsm).model_copy(update={"confidence": Confidence.BAIXO})
    cfg = EvaluatorConfig(confidence_floor=Confidence.MEDIO)
    agg = aggregate([dr], sel.profile, cfg)
    assert dr.dimension in agg.excluded_low_conf
