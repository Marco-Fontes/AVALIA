"""T-601/T-603/T-604 — teste-contrato do repositório de laudos.

Roda contra `InMemoryReportRepository` sempre; contra `PostgresReportRepository` apenas quando
`AVALIA_PG_DSN` está definido (CI sem Postgres → skip). Verifica save/latest_for, ordem por
recência, ausência → None e preservação do `findings_index`. Nada executa o alvo.
"""

from __future__ import annotations

import os
from uuid import uuid4

import pytest

from avalia.config.evaluator_config import EvaluatorConfig
from avalia.domain.contracts import (
    AnalysisCoverage,
    ComponentInventory,
    DimensionResult,
    EvaluationReport,
    ReadabilityReport,
    ReportHeader,
    ReportMetadata,
    TargetClassification,
)
from avalia.domain.enums import Confidence, Dimension, Topology, Verdict
from avalia.domain.submission import TargetMetadata
from avalia.domain.weights import WeightProfile, WeightSource
from avalia.persistence.repository import InMemoryReportRepository, make_record

pytestmark = pytest.mark.fast

_DSN = os.environ.get("AVALIA_PG_DSN")


@pytest.fixture(
    params=[
        "inmemory",
        pytest.param("postgres", marks=pytest.mark.skipif(not _DSN, reason="sem AVALIA_PG_DSN")),
    ]
)
def repo(request):
    if request.param == "inmemory":
        return InMemoryReportRepository()
    from avalia.persistence.postgres import PostgresReportRepository

    return PostgresReportRepository(_DSN)


def _report(score: int = 60) -> EvaluationReport:
    eq = 1.0 / 7
    header = ReportHeader(
        classification=TargetClassification(
            topology=Topology.MULTIAGENTE, classification_conf=Confidence.ALTO
        ),
        effective_weights=WeightProfile(
            source=WeightSource.FALLBACK_NEUTRO, weights=dict.fromkeys(Dimension, eq)
        ),
        verdict=Verdict.APROVACAO_CONDICIONAL,
        score=score,
        confidence=Confidence.ALTO,
    )
    metadata = ReportMetadata(
        effective_config=EvaluatorConfig(),
        inventory=ComponentInventory(present=["codigo_fonte"]),
        coverage=AnalysisCoverage(),
        readability=ReadabilityReport(),
    )
    dr = DimensionResult(
        dimension=Dimension.TRAJETORIA,
        score=score,
        confidence=Confidence.ALTO,
        reasoning="ok",
    )
    return EvaluationReport(header=header, dimensions=[dr], metadata=metadata)


def test_empty_repo_returns_none(repo):
    assert repo.latest_for(uuid4().hex) is None


def test_save_and_latest_roundtrip(repo):
    tid = uuid4().hex
    meta = TargetMetadata(target_id=tid, version="1")
    record = make_record(_report(60), meta)
    repo.save(record)
    got = repo.latest_for(tid)
    assert got is not None
    assert got.target_id == tid and got.score == 60
    assert got.report.header.verdict is Verdict.APROVACAO_CONDICIONAL  # round-trip do laudo


def test_latest_returns_most_recent(repo):
    tid = uuid4().hex
    repo.save(make_record(_report(50), TargetMetadata(target_id=tid, version="1")))
    repo.save(make_record(_report(80), TargetMetadata(target_id=tid, version="2")))
    latest = repo.latest_for(tid)
    assert latest is not None and latest.target_version == "2" and latest.score == 80


def test_findings_index_preserved(repo):
    tid = uuid4().hex
    record = make_record(_report(60), TargetMetadata(target_id=tid, version="1"))
    repo.save(record)
    got = repo.latest_for(tid)
    assert got is not None and got.findings_index == record.findings_index
