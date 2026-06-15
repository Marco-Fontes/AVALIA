"""M7 / T-1005 — Reprodutibilidade (CA-14, RNF-01) em dois regimes.

Regime A (determinístico): o mesmo artefato ×N produz `deterministic_hash` BIT-IDÊNTICO em todo
`CheckOutcome`, vereditos por dimensão idênticos e o mesmo conjunto de achados críticos.
Regime B (juiz-LLM, mockado estável): vereditos estáveis POR FAIXA e o mesmo conjunto de achados
críticos (identidade composta), tolerando variação textual; nas dimensões ancoradas em fato
(ex.: Trajetória/loop sem teto) o veredito EXATO é estável.

Tudo black-box sobre o grafo; nada executa o alvo (RNF-05).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from avalia.config.evaluator_config import RetryPolicy
from avalia.domain.enums import Band, Confidence, Dimension
from avalia.domain.submission import Submission, TargetMetadata
from avalia.graph.build_graph import build_avalia_graph
from avalia.judge.framework import JudgeVerdict

pytestmark = pytest.mark.fast

_FIX = Path(__file__).resolve().parents[1] / "fixtures"
_META = TargetMetadata(target_id="alvo", version="v1")
_N = 3


def _load(name: str) -> dict[str, str]:
    return {f.name: f.read_text(encoding="utf-8") for f in (_FIX / name).glob("*.py")}


def _run(files: dict[str, str], gateway=None, tid="r") -> dict:
    graph = build_avalia_graph(gateway=gateway)
    return graph.invoke(
        {"submission": Submission(artifact_files=files, metadata=_META)},
        config={"configurable": {"thread_id": tid}},
    )


def _det_hashes(report) -> tuple[str, ...]:
    return tuple(
        sorted(
            co.deterministic_hash
            for dr in report.dimensions
            for co in dr.check_outcomes
            if co.deterministic_hash
        )
    )


def _verdicts(report) -> tuple[tuple[str, int | None], ...]:
    return tuple(sorted((dr.dimension.value, dr.score) for dr in report.dimensions))


def _critical_ids(report) -> frozenset[str]:
    return frozenset(
        f.identity for dr in report.dimensions for f in dr.findings if f.urgency.value == "critico"
    )


def _band(score: int | None) -> str:
    if score is None:
        return "na"
    return "pronto" if score >= 75 else "adequado" if score >= 50 else "insuficiente"


# ----------------------------- Regime A (determinístico) -----------------------------


def test_ca14_deterministic_regime_is_bit_identical():
    reports = [
        _run(_load("multiagente_loop_sem_teto"), tid=f"detA{i}")["report"] for i in range(_N)
    ]
    hashes = {_det_hashes(r) for r in reports}
    verdicts = {_verdicts(r) for r in reports}
    crit = {_critical_ids(r) for r in reports}
    assert len(hashes) == 1  # checks determinísticos bit-idênticos entre execuções
    assert len(verdicts) == 1  # vereditos por dimensão idênticos
    assert len(crit) == 1  # mesmos achados críticos


# ----------------------------- Regime B (juiz-LLM estável) -----------------------------


class _StableClient:
    def __init__(self, band: Band):
        self._band = band

    def invoke(self, messages):
        # texto VARIÁVEL (formulação muda), faixa/score ESTÁVEIS — reprodutibilidade estatística
        import uuid

        return JudgeVerdict(
            score=80, band=self._band, confidence=Confidence.MEDIO, reasoning=uuid.uuid4().hex
        )


class StableJudgeGateway:
    """Juiz que varia a redação mas mantém a faixa — testa RNF-01 regime estatístico."""

    def with_structured_output(self, node_type, role, schema):
        return _StableClient(Band.PRONTO)

    def retry_for(self, node_type):
        return RetryPolicy(max_attempts=2)


def test_ca14_judge_regime_is_band_stable_and_fact_anchored():
    gw = StableJudgeGateway()
    reports = [
        _run(_load("multiagente_loop_sem_teto"), gateway=gw, tid=f"detB{i}")["report"]
        for i in range(_N)
    ]
    # faixa por dimensão estável (tolera variação textual do juiz)
    bands = {
        tuple(sorted((dr.dimension.value, _band(dr.score)) for dr in r.dimensions)) for r in reports
    }
    assert len(bands) == 1
    # mesmo conjunto de achados críticos (identidade composta, não texto)
    assert len({_critical_ids(r) for r in reports}) == 1
    # ancoragem em fato: a Trajetória (loop sem teto) tem veredito EXATO estável
    traj_scores = {
        next(dr.score for dr in r.dimensions if dr.dimension is Dimension.TRAJETORIA)
        for r in reports
    }
    assert len(traj_scores) == 1
