"""T4.4 — calibração da confiança do laudo parcial.

Amostragem de 1 arquivo secundário NÃO derruba a confiança de dimensões intactas; só rebaixa
quando a fração amostrada é significativa (limiar configurável) ou quando a dimensão tem
evidência num arquivo amostrado. Rastreabilidade: RF-12; RNF-06.
"""

from __future__ import annotations

import pytest

from avalia.config.evaluator_config import EvaluatorConfig
from avalia.domain.contracts import (
    AnalysisCoverage,
    DimensionResult,
    Finding,
    ReadabilityReport,
)
from avalia.domain.enums import Confidence, Dimension, Urgency
from avalia.domain.evidence import EvidenceRef
from avalia.domain.taxonomy import FindingType
from avalia.domain.tsm import TargetStaticModel
from avalia.report.build import _apply_partial_confidence

pytestmark = pytest.mark.fast


def _tsm(fully: list[str], sampled: list[str]) -> TargetStaticModel:
    return TargetStaticModel(
        files=fully + sampled,
        coverage=AnalysisCoverage(fully_analyzed=fully, sampled=sampled),
        readability=ReadabilityReport(),
    )


def _clean_dim(dim: Dimension) -> DimensionResult:
    return DimensionResult(
        dimension=dim, applicable=True, score=80, confidence=Confidence.ALTO, reasoning="ok"
    )


def _dim_touching(dim: Dimension, file_path: str) -> DimensionResult:
    finding = Finding(
        finding_type=FindingType.SEM_RETRY,
        urgency=Urgency.IMPORTANTE,
        statement="sem retry",
        reasoning="lacuna",
        evidence=[EvidenceRef(file_path=file_path, symbol="<projeto>", component_kind="project")],
    )
    return DimensionResult(
        dimension=dim,
        applicable=True,
        score=80,
        confidence=Confidence.ALTO,
        reasoning="ok",
        findings=[finding],
    )


def test_minor_sampling_does_not_drop_untouched_dimension():
    tsm = _tsm(fully=["a.py", "b.py", "c.py", "d.py"], sampled=["e.py"])  # fração 1/5 = 0.2 < 0.25
    clean = _clean_dim(Dimension.CUSTO)
    out = _apply_partial_confidence([clean], tsm, EvaluatorConfig(), broad=False)
    assert out[0].confidence is Confidence.ALTO  # dimensão intacta mantém confiança


def test_dimension_with_evidence_in_sampled_file_is_reduced():
    tsm = _tsm(fully=["a.py", "b.py", "c.py", "d.py"], sampled=["e.py"])
    touch = _dim_touching(Dimension.ROBUSTEZ, "e.py")
    out = _apply_partial_confidence([touch], tsm, EvaluatorConfig(), broad=False)
    assert out[0].confidence is Confidence.MEDIO  # evidência em arquivo amostrado → rebaixa


def test_significant_sampling_reduces_all():
    tsm = _tsm(fully=["a.py"], sampled=["b.py", "c.py", "d.py", "e.py"])  # 4/5 = 0.8 ≥ 0.25
    clean = _clean_dim(Dimension.CUSTO)
    out = _apply_partial_confidence([clean], tsm, EvaluatorConfig(), broad=False)
    assert out[0].confidence is Confidence.MEDIO


def test_broad_partial_reduces_all_regardless_of_fraction():
    tsm = _tsm(fully=["a.py", "b.py", "c.py", "d.py"], sampled=["e.py"])
    clean = _clean_dim(Dimension.CUSTO)
    out = _apply_partial_confidence([clean], tsm, EvaluatorConfig(), broad=True)
    assert out[0].confidence is Confidence.MEDIO  # juízes pulados → degradação ampla
