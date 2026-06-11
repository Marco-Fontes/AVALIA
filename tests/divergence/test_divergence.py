"""T-401/T-402 — testes de detecção e reconciliação automática de divergência.

DoD: gatilho por faixas distintas OU confiança < piso (resolução #4); reconciliação convergente
→ resolvido (auto); persistente → None. Gateway mockado; nada executa o alvo.
"""

from __future__ import annotations

import pytest

from avalia.config.evaluator_config import EvaluatorConfig, RetryPolicy
from avalia.divergence import detect_candidates, reconcile_candidate
from avalia.domain.contracts import DimensionResult, DivergenceCandidate, JudgeOpinion, ResolvedBy
from avalia.domain.enums import Band, Confidence, Dimension
from avalia.extract.tsm_builder import build_tsm
from avalia.judge.framework import JudgeVerdict

pytestmark = pytest.mark.fast


def _op(band: Band, conf: Confidence = Confidence.ALTO) -> JudgeOpinion:
    return JudgeOpinion(
        angle="x", score=70, reasoning="r", confidence=conf, rubric_id="robustez/v1", band=band
    )


def _dr(opinions, confidence=Confidence.ALTO) -> DimensionResult:
    return DimensionResult(
        dimension=Dimension.ROBUSTEZ,
        applicable=True,
        score=70,
        confidence=confidence,
        reasoning="r",
        judge_opinions=opinions,
    )


def test_band_mismatch_triggers_candidate():
    dr = _dr([_op(Band.PRONTO), _op(Band.INSUFICIENTE)])
    cands = detect_candidates([dr], EvaluatorConfig())
    assert len(cands) == 1 and cands[0].threshold_hit == "band_mismatch"


def test_low_confidence_triggers_candidate():
    dr = _dr([_op(Band.PRONTO), _op(Band.PRONTO)], confidence=Confidence.BAIXO)
    cands = detect_candidates([dr], EvaluatorConfig())
    assert len(cands) == 1 and cands[0].threshold_hit == "low_confidence"


def test_single_opinion_no_candidate():
    dr = _dr([_op(Band.PRONTO)])
    assert detect_candidates([dr], EvaluatorConfig()) == []


def test_agreement_high_confidence_no_candidate():
    dr = _dr([_op(Band.PRONTO), _op(Band.PRONTO)], confidence=Confidence.ALTO)
    assert detect_candidates([dr], EvaluatorConfig()) == []


class _FixedGateway:
    """Devolve faixas roteirizadas para o re-julgamento de reconciliação."""

    def __init__(self, bands):
        self._bands = list(bands)

    def with_structured_output(self, node_type, role, schema):
        return self

    def invoke(self, messages):
        return JudgeVerdict(
            score=70, band=self._bands.pop(0), confidence=Confidence.ALTO, reasoning="r"
        )

    def retry_for(self, node_type):
        return RetryPolicy(max_attempts=1)


def _candidate() -> DivergenceCandidate:
    return DivergenceCandidate(
        dimension=Dimension.ROBUSTEZ,
        conflicting_positions=[_op(Band.PRONTO), _op(Band.INSUFICIENTE)],
        threshold_hit="band_mismatch",
    )


def test_reconcile_converges_resolves_auto():
    tsm = build_tsm({"main.py": 'PROMPT = "x"\n'})
    gw = _FixedGateway([Band.ADEQUADO_COM_RESSALVAS, Band.ADEQUADO_COM_RESSALVAS])
    record = reconcile_candidate(_candidate(), gateway=gw, tsm=tsm)
    assert record is not None
    assert record.resolved_by is ResolvedBy.AUTO
    assert "adequado_com_ressalvas" in record.resolution_note


def test_reconcile_persists_returns_none():
    tsm = build_tsm({"main.py": 'PROMPT = "x"\n'})
    gw = _FixedGateway([Band.PRONTO, Band.INSUFICIENTE])
    assert reconcile_candidate(_candidate(), gateway=gw, tsm=tsm) is None
