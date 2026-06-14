"""T-902 — Harness offline de meta-avaliação (MS-04/08/09; EC-10).

Compara os laudos do AVALIA aos rótulos humanos do dataset e calcula índices:
- **concordância de veredito por dimensão** (métrica primária, EC-10/MS-04);
- **concordância de classificação** topologia/tipo (MS-09);
- **calibração de confiança** — taxa de concordância por bucket de confiança (alto vs. baixo),
  validando que "alta concorda mais que baixa" (MS-08).

NÃO fixa limiar de "confiável": a calibração estatisticamente significativa depende de D-03
(dataset curado) e D-04 (primeiro lote) — declarado em `calibration_blocked_reason`. Job offline
sobre laudos já gerados; não altera o grafo, não executa o alvo (RNF-05).
"""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict, Field

from avalia.domain.contracts import EvaluationReport
from avalia.domain.enums import Confidence, Dimension
from avalia.metaeval.dataset import BenchmarkCase, BenchmarkDataset, band_of_score

CALIBRATION_BLOCKED_REASON = (
    "Calibração estatisticamente significativa e o limiar de 'confiável' dependem de D-03 "
    "(dataset curado por humanos) e D-04 (primeiro lote) — fora de escopo de código (EC-10)."
)


class CaseResult(BaseModel):
    """Resultado da comparação de um laudo com seu rótulo de referência."""

    model_config = ConfigDict(frozen=True)

    target_id: str
    dimension_agreement: dict[Dimension, bool] = Field(default_factory=dict)
    dimension_agreement_rate: float = Field(ge=0.0, le=1.0)
    topology_agreement: bool
    system_type_agreement: bool | None = None


class MetaEvalReport(BaseModel):
    """Índices de meta-avaliação (sem limiar — calibração diferida por D-03/D-04)."""

    model_config = ConfigDict(frozen=True)

    n_cases: int = Field(ge=0)
    per_case: list[CaseResult] = Field(default_factory=list)
    overall_dimension_agreement: float = Field(ge=0.0, le=1.0)
    overall_topology_agreement: float = Field(ge=0.0, le=1.0)
    high_conf_agreement: float | None = None
    low_conf_agreement: float | None = None
    n_high_conf: int = 0
    n_low_conf: int = 0
    calibration_blocked_reason: str = CALIBRATION_BLOCKED_REASON


def _by_dimension(report: EvaluationReport) -> dict[Dimension, object]:
    return {dr.dimension: dr for dr in report.dimensions}


def _agrees(dr: object, expected_band: object) -> bool:
    """O laudo concorda com a faixa rotulada para a dimensão?"""
    score = getattr(dr, "score", None)
    applicable = getattr(dr, "applicable", False)
    if dr is None or not applicable or score is None:
        return False
    return band_of_score(score) is expected_band


def dimension_agreement(report: EvaluationReport, case: BenchmarkCase) -> dict[Dimension, bool]:
    """Concordância de veredito por dimensão rotulada (MS-04, métrica primária)."""
    by_dim = _by_dimension(report)
    return {dim: _agrees(by_dim.get(dim), label) for dim, label in case.dimension_labels.items()}


def classification_agreement(
    report: EvaluationReport, case: BenchmarkCase
) -> tuple[bool, bool | None]:
    """Concordância de topologia e (se rotulado) de tipo (MS-09)."""
    cls = report.header.classification
    topo = cls.topology is case.expected_topology
    if case.expected_system_type is None:
        return topo, None
    return topo, cls.system_type == case.expected_system_type


def _rate(values: list[bool]) -> float:
    return sum(values) / len(values) if values else 0.0


def evaluate_dataset(
    reports_by_target: Mapping[str, EvaluationReport], dataset: BenchmarkDataset
) -> MetaEvalReport:
    """Calcula todos os índices comparando laudos ao dataset (job offline)."""
    per_case: list[CaseResult] = []
    all_dim_agreements: list[bool] = []
    topo_agreements: list[bool] = []
    # buckets de calibração: (confiança da dimensão, concordou?)
    conf_pairs: list[tuple[Confidence, bool]] = []

    for case in dataset.cases:
        report = reports_by_target.get(case.target_id)
        if report is None:  # sem laudo para o caso → fora da medição
            continue
        dim_agree = dimension_agreement(report, case)
        topo, sys_type = classification_agreement(report, case)
        per_case.append(
            CaseResult(
                target_id=case.target_id,
                dimension_agreement=dim_agree,
                dimension_agreement_rate=_rate(list(dim_agree.values())),
                topology_agreement=topo,
                system_type_agreement=sys_type,
            )
        )
        all_dim_agreements.extend(dim_agree.values())
        topo_agreements.append(topo)
        by_dim = _by_dimension(report)
        for dim, agreed in dim_agree.items():
            dr = by_dim.get(dim)
            conf = getattr(dr, "confidence", None)
            if isinstance(conf, Confidence):
                conf_pairs.append((conf, agreed))

    high = [a for c, a in conf_pairs if c is Confidence.ALTO]
    low = [a for c, a in conf_pairs if c is Confidence.BAIXO]
    return MetaEvalReport(
        n_cases=len(per_case),
        per_case=per_case,
        overall_dimension_agreement=_rate(all_dim_agreements),
        overall_topology_agreement=_rate(topo_agreements),
        high_conf_agreement=_rate(high) if high else None,
        low_conf_agreement=_rate(low) if low else None,
        n_high_conf=len(high),
        n_low_conf=len(low),
    )
