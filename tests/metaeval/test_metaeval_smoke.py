"""T-1007 — Smoke do harness de meta-avaliação (MS-04/08/09).

Prova que o PIPELINE de medição roda ponta-a-ponta sobre um seed sintético: roda o grafo nas
fixtures, compara aos rótulos e confirma que os índices são CALCULADOS. NÃO assere limiar (a
calibração significativa é bloqueada por D-03/D-04). Fora do gate `-m fast` (não recebe a marca).
Nada executa o alvo (RNF-05).
"""

from __future__ import annotations

from pathlib import Path

from avalia.domain.enums import Band
from avalia.domain.submission import Submission, TargetMetadata
from avalia.graph.build_graph import build_avalia_graph
from avalia.metaeval.dataset import band_of_score, load_dataset
from avalia.metaeval.harness import CALIBRATION_BLOCKED_REASON, evaluate_dataset

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
_SEED = Path(__file__).resolve().parent / "fixtures" / "seed.yaml"


def _load_target(target_id: str) -> dict[str, str]:
    d = _FIXTURES / target_id
    return {f.name: f.read_text(encoding="utf-8") for f in d.glob("*.py")}


def test_band_of_score_maps_faixas():
    assert band_of_score(80) is Band.PRONTO
    assert band_of_score(60) is Band.ADEQUADO_COM_RESSALVAS
    assert band_of_score(40) is Band.INSUFICIENTE


def test_metaeval_pipeline_computes_indices_over_seed():
    dataset = load_dataset(_SEED)
    assert dataset.cases  # seed carregado

    reports = {}
    for case in dataset.cases:
        graph = build_avalia_graph()
        sub = Submission(
            artifact_files=_load_target(case.target_id),
            metadata=TargetMetadata(target_id=case.target_id, version="v1"),
        )
        reports[case.target_id] = graph.invoke(
            {"submission": sub}, config={"configurable": {"thread_id": case.target_id}}
        )["report"]

    report = evaluate_dataset(reports, dataset)

    # validação MECÂNICA do pipeline (não de limiar): índices presentes e em [0,1]
    assert report.n_cases == len(dataset.cases)
    assert 0.0 <= report.overall_dimension_agreement <= 1.0
    assert 0.0 <= report.overall_topology_agreement <= 1.0
    assert len(report.per_case) == len(dataset.cases)
    for case_result in report.per_case:
        assert 0.0 <= case_result.dimension_agreement_rate <= 1.0
        assert case_result.dimension_agreement  # ao menos uma dimensão rotulada comparada

    # buckets de calibração de confiança populados (MS-08) — alto e baixo
    assert report.n_high_conf > 0 and report.n_low_conf > 0
    assert report.high_conf_agreement is not None and report.low_conf_agreement is not None

    # calibração significativa permanece BLOQUEADA por dependência externa (D-03/D-04)
    assert report.calibration_blocked_reason == CALIBRATION_BLOCKED_REASON
    assert (
        "D-03" in report.calibration_blocked_reason and "D-04" in report.calibration_blocked_reason
    )
