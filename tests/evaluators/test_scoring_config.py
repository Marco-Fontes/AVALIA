"""T-008 (v1.4, DQ-03) — parâmetros de pontuação vêm da config, não de constantes (RNF-06).

Os defaults reproduzem o cálculo anterior (bit-idêntico — ver também T-1005); mudar a config
muda a nota. Fixtures estáticas; nada executa o alvo (RNF-05).
"""

from __future__ import annotations

import pytest

from avalia.config.evaluator_config import EvaluatorConfig, ScoringConfig
from avalia.domain.enums import Dimension, Urgency
from avalia.domain.submission import Submission, TargetMetadata
from avalia.domain.taxonomy import FindingType
from avalia.evaluators.base import make_finding, project_anchor, score_from_findings
from avalia.evaluators.robustez import evaluate_robustez
from avalia.evaluators.trajetoria import evaluate_trajetoria
from avalia.extract.tsm_builder import build_tsm
from avalia.graph.build_graph import build_avalia_graph

pytestmark = pytest.mark.fast

_LOOP = "def agent(state):\n    while True:\n        state = step(state)\n"
_PLAIN = "def call():\n    return client.invoke('x')\n"


def _finding(urgency: Urgency):
    tsm = build_tsm({"a.py": _PLAIN})
    return make_finding(FindingType.SEM_RETRY, urgency, "s", "r", project_anchor(tsm))


def test_defaults_reproduce_previous_formula():
    findings = [_finding(Urgency.CRITICO), _finding(Urgency.IMPORTANTE), _finding(Urgency.SUGESTAO)]
    assert score_from_findings(findings) == 90 - 22 - 9 - 3  # cálculo anterior


def test_custom_penalties_change_the_score():
    scoring = ScoringConfig(base_score=80, important_penalty=20)
    assert score_from_findings([_finding(Urgency.IMPORTANTE)], scoring) == 60


def test_evaluator_uses_scoring_from_argument():
    tsm = build_tsm({"a.py": _PLAIN})
    default = evaluate_robustez(tsm)
    harsher = evaluate_robustez(tsm, scoring=ScoringConfig(important_penalty=30))
    assert default.findings  # há achados importantes (sem retry/fallback/timeout…)
    assert harsher.score is not None and default.score is not None
    assert harsher.score < default.score


def test_trajectory_parameters_are_configurable():
    tsm = build_tsm({"a.py": _LOOP})
    assert evaluate_trajetoria(tsm).score == 60  # 85 − 25 (defaults)
    custom = ScoringConfig(trajectory_base_score=85, trajectory_no_cap_penalty=50)
    assert evaluate_trajetoria(tsm, scoring=custom).score == 50  # piso da faixa condicional
    lower_floor = ScoringConfig(trajectory_no_cap_penalty=50, trajectory_no_cap_floor=30)
    assert evaluate_trajetoria(tsm, scoring=lower_floor).score == 35


def test_graph_passes_submission_scoring_to_evaluators():
    def run(config: EvaluatorConfig):
        graph = build_avalia_graph()
        sub = Submission(
            artifact_files={"a.py": _PLAIN},
            metadata=TargetMetadata(target_id="t", version="1"),
            config=config,
        )
        out = graph.invoke({"submission": sub}, config={"configurable": {"thread_id": "t"}})
        return {dr.dimension: dr.score for dr in out["report"].dimensions}

    default = run(EvaluatorConfig())
    harsher = run(EvaluatorConfig(scoring=ScoringConfig(important_penalty=30)))
    assert harsher[Dimension.ROBUSTEZ] < default[Dimension.ROBUSTEZ]


def test_scoring_values_are_validated():
    with pytest.raises(ValueError):
        ScoringConfig(base_score=120)
    with pytest.raises(ValueError):
        ScoringConfig(critical_penalty=-1)
