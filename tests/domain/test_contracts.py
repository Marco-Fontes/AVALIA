"""T-004 — testes de contrato dos blocos do laudo (Seção 4 do plano).

DoD: EvaluationReport exige blocos 4.2.1–4.2.8; DimensionResult exige reasoning não-vazio +
confidence (CA-05); comportamentais exigem static_limitations (CA-07/RF-13); dynamic_metrics
presente, default None, e None na Fase 1 (S-05). Identidade de achado derivada da taxonomia.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from avalia.config.evaluator_config import EvaluatorConfig
from avalia.domain.contracts import (
    AnalysisCoverage,
    CheckOutcome,
    ComponentInventory,
    DimensionResult,
    EvaluationReport,
    Finding,
    ReadabilityReport,
    ReportHeader,
    ReportMetadata,
    TargetClassification,
)
from avalia.domain.enums import (
    CheckNature,
    Confidence,
    Dimension,
    Topology,
    Urgency,
    Verdict,
)
from avalia.domain.evidence import EvidenceRef
from avalia.domain.taxonomy import FindingType, finding_identity, normalize_location
from avalia.domain.weights import WeightProfile, WeightSource

pytestmark = pytest.mark.fast


def _ev(symbol: str = "loop_principal") -> EvidenceRef:
    return EvidenceRef(file_path="alvo/main.py", symbol=symbol, component_kind="loop")


def _loop_finding() -> Finding:
    return Finding(
        finding_type=FindingType.LOOP_SEM_TETO,
        urgency=Urgency.CRITICO,
        statement="Loop sem teto no nó X.",
        reasoning="O while não tem condição de parada por iterações.",
        evidence=[_ev()],
    )


def _trajetoria_result() -> DimensionResult:
    return DimensionResult(
        dimension=Dimension.TRAJETORIA,
        applicable=True,
        score=60,
        confidence=Confidence.ALTO,
        reasoning="Loop sem teto detectado deterministicamente.",
        findings=[_loop_finding()],
    )


def _neutral_weights() -> WeightProfile:
    eq = 1.0 / 7
    return WeightProfile(
        source=WeightSource.FALLBACK_NEUTRO,
        weights=dict.fromkeys(Dimension, eq),
    )


def _header() -> ReportHeader:
    return ReportHeader(
        classification=TargetClassification(
            topology=Topology.MULTIAGENTE, classification_conf=Confidence.ALTO
        ),
        effective_weights=_neutral_weights(),
        verdict=Verdict.APROVACAO_CONDICIONAL,
        score=60,
        confidence=Confidence.ALTO,
    )


def _metadata() -> ReportMetadata:
    return ReportMetadata(
        effective_config=EvaluatorConfig(),
        inventory=ComponentInventory(present=["src"], missing=[]),
        coverage=AnalysisCoverage(fully_analyzed=["alvo/main.py"]),
        readability=ReadabilityReport(),
    )


def _minimal_report() -> EvaluationReport:
    return EvaluationReport(
        header=_header(), dimensions=[_trajetoria_result()], metadata=_metadata()
    )


def test_minimal_report_has_all_blocks():
    rep = _minimal_report()
    # 4.2.1, 4.2.2, 4.2.8 obrigatórios; 4.2.3/4/5/7 presentes (defaults)
    assert rep.header.verdict is Verdict.APROVACAO_CONDICIONAL  # 4.2.1/4.2.6
    assert rep.dimensions and rep.dimensions[0].dimension is Dimension.TRAJETORIA  # 4.2.2
    assert rep.consolidated_recommendations == []  # 4.2.3
    assert rep.approval_conditions == []  # 4.2.4
    assert rep.comparison is None  # 4.2.5 (CB-06)
    assert rep.divergences == []  # 4.2.7
    assert rep.metadata.effective_config is not None  # 4.2.8
    # round-trip Pydantic
    assert EvaluationReport.model_validate(rep.model_dump()) == rep


def test_report_requires_at_least_one_dimension():
    with pytest.raises(ValidationError):
        EvaluationReport(header=_header(), dimensions=[], metadata=_metadata())


def test_dimension_result_requires_nonempty_reasoning():
    with pytest.raises(ValidationError):
        DimensionResult(
            dimension=Dimension.TRAJETORIA,
            score=60,
            confidence=Confidence.ALTO,
            reasoning="   ",  # CA-05: reasoning não pode ser vazio
        )


def test_behavioral_dimension_requires_static_limitations():
    # CA-07 / RF-13: alucinação/qualidade/assertividade exigem static_limitations
    with pytest.raises(ValidationError, match="static_limitations"):
        DimensionResult(
            dimension=Dimension.ALUCINACAO,
            score=70,
            confidence=Confidence.MEDIO,
            reasoning="Sem citação obrigatória.",
        )


def test_behavioral_dimension_ok_with_static_limitations():
    dr = DimensionResult(
        dimension=Dimension.ALUCINACAO,
        score=70,
        confidence=Confidence.MEDIO,
        reasoning="Sem citação obrigatória.",
        static_limitations="Taxa real de alucinação não é medível na Fase 1 (CA-07).",
    )
    assert dr.static_limitations


def test_dynamic_metrics_is_opaque_none_in_phase1():
    with pytest.raises(ValidationError, match="S-05"):
        DimensionResult(
            dimension=Dimension.TRAJETORIA,
            score=60,
            confidence=Confidence.ALTO,
            reasoning="x",
            dynamic_metrics={"latency_ms": 12},  # proibido na Fase 1
        )


def test_applicable_requires_score_in_range():
    with pytest.raises(ValidationError):
        DimensionResult(
            dimension=Dimension.CUSTO,
            applicable=True,
            score=None,
            confidence=Confidence.ALTO,
            reasoning="x",
        )


def test_not_applicable_must_not_have_score():
    dr = DimensionResult(
        dimension=Dimension.PERFORMANCE,
        applicable=False,
        score=None,
        confidence=Confidence.BAIXO,
        reasoning="Não aplicável a este tipo de sistema.",
    )
    assert dr.score is None


def test_finding_identity_matches_taxonomy_helper():
    f = _loop_finding()
    expected = finding_identity(
        Dimension.TRAJETORIA,
        FindingType.LOOP_SEM_TETO,
        normalize_location("alvo/main.py", "loop_principal"),
    )
    assert f.dimension is Dimension.TRAJETORIA
    assert f.identity == expected


def test_dimension_result_rejects_foreign_finding():
    # achado de Robustez dentro de DimensionResult de Custo → erro (regra 4)
    foreign = Finding(
        finding_type=FindingType.SEM_RETRY,
        urgency=Urgency.IMPORTANTE,
        statement="x",
        reasoning="y",
        evidence=[_ev("chamada_api")],
    )
    with pytest.raises(ValidationError, match="regra 4"):
        DimensionResult(
            dimension=Dimension.CUSTO,
            score=50,
            confidence=Confidence.MEDIO,
            reasoning="z",
            findings=[foreign],
        )


def test_deterministic_check_requires_hash():
    with pytest.raises(ValidationError, match="deterministic_hash"):
        CheckOutcome(check_id="c2_token_limit", nature=CheckNature.DETERMINISTICO, passed=True)
