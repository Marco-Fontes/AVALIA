"""T-605 — testes da comparação histórica (deltas + diff de achados por identidade).

Reusa a identidade estável de achado (RF-29). Suporta CA-15.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from avalia.compare import compare
from avalia.config.evaluator_config import EvaluatorConfig
from avalia.domain.contracts import (
    AnalysisCoverage,
    ComponentInventory,
    DimensionResult,
    EvaluationReport,
    Finding,
    ReadabilityReport,
    ReportHeader,
    ReportMetadata,
    TargetClassification,
)
from avalia.domain.enums import Confidence, Dimension, Topology, Urgency, Verdict
from avalia.domain.evidence import EvidenceRef
from avalia.domain.taxonomy import FindingType
from avalia.domain.weights import WeightProfile, WeightSource
from avalia.persistence.repository import EvaluationReportRecord, findings_index_of

pytestmark = pytest.mark.fast


def _finding(ft: FindingType, symbol: str) -> Finding:
    return Finding(
        finding_type=ft,
        urgency=Urgency.IMPORTANTE,
        statement="x",
        reasoning="y",
        evidence=[EvidenceRef(file_path="main.py", symbol=symbol, component_kind="loop")],
    )


def _dr(dimension: Dimension, score: int, findings=()) -> DimensionResult:
    return DimensionResult(
        dimension=dimension,
        score=score,
        confidence=Confidence.ALTO,
        reasoning="r",
        findings=list(findings),
    )


def _report(dims: list[DimensionResult]) -> EvaluationReport:
    eq = 1.0 / 7
    header = ReportHeader(
        classification=TargetClassification(
            topology=Topology.MULTIAGENTE, classification_conf=Confidence.ALTO
        ),
        effective_weights=WeightProfile(
            source=WeightSource.FALLBACK_NEUTRO, weights=dict.fromkeys(Dimension, eq)
        ),
        verdict=Verdict.APROVACAO_CONDICIONAL,
        score=dims[0].score or 0,
        confidence=Confidence.ALTO,
    )
    metadata = ReportMetadata(
        effective_config=EvaluatorConfig(),
        inventory=ComponentInventory(present=["codigo_fonte"]),
        coverage=AnalysisCoverage(),
        readability=ReadabilityReport(),
    )
    return EvaluationReport(header=header, dimensions=dims, metadata=metadata)


def _record(dims: list[DimensionResult]) -> EvaluationReportRecord:
    rep = _report(dims)
    return EvaluationReportRecord(
        report_id="prev-1",
        target_id="t",
        target_version="1",
        created_at=datetime.now(UTC),
        verdict=rep.header.verdict.value,
        score=rep.header.score,
        report=rep,
        findings_index=findings_index_of(rep),
    )


def _index(dims: list[DimensionResult]) -> list[str]:
    return sorted({f.identity for dr in dims for f in dr.findings})


def test_compare_reports_delta_resolved_persistent_new():
    loop = _finding(FindingType.LOOP_SEM_TETO, "solver")
    dead = _finding(FindingType.CAMINHO_MORTO, "router")
    prev = _record([_dr(Dimension.TRAJETORIA, 50, [loop, dead])])

    # v2: resolveu o loop, manteve o caminho morto, melhorou o score
    cur = [_dr(Dimension.TRAJETORIA, 75, [dead])]
    comp = compare(cur, _index(cur), prev)

    assert comp.prev_report_id == "prev-1"
    assert comp.deltas[Dimension.TRAJETORIA] == 25
    assert comp.improvements == ["trajetoria: +25"]
    assert loop.identity in comp.resolved_findings
    assert dead.identity in comp.persistent_findings
    assert comp.new_findings == []


def test_compare_reports_regression():
    prev = _record([_dr(Dimension.ROBUSTEZ, 80)])
    cur = [_dr(Dimension.ROBUSTEZ, 45)]
    comp = compare(cur, _index(cur), prev)
    assert comp.deltas[Dimension.ROBUSTEZ] == -35
    assert comp.regressions == ["robustez: -35"]
