"""T-004 — Contratos compostos do domínio (plan §4). Pydantic v2.

Reúne os blocos do laudo: inventário, cobertura, legibilidade, classificação, achados,
checks/opiniões, resultado por dimensão, divergências, agregação, comparação histórica e o
`EvaluationReport` final (exige os blocos 4.2.1–4.2.8). Invariantes de contrato aqui:
- `DimensionResult` exige `reasoning` não-vazio e `confidence` (regra 6).
- dimensões comportamentais exigem `static_limitations` (RF-13/RNF-04, regra 7).
- `dynamic_metrics` é slot OPACO da Fase 2 — presente, default None, e None na Fase 1 (S-05).
- `Finding` deriva identidade estável e dimensão da taxonomia (RF-29, regra 4/5).

Rastreabilidade: RF-09, RF-10, RF-11, RF-14, RF-19, RF-25, RF-27, RF-29, RNF-02, RNF-03,
RNF-07, RNF-08, RNF-10, RNF-12; S-05; Seção 4 do plano.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from avalia.config.evaluator_config import EvaluatorConfig
from avalia.domain.enums import (
    BEHAVIORAL_DIMENSIONS,
    Band,
    CheckNature,
    Confidence,
    Dimension,
    Topology,
    Urgency,
    Verdict,
)
from avalia.domain.evidence import EvidenceRef
from avalia.domain.taxonomy import (
    FindingType,
    dimension_of,
    finding_identity,
    normalize_location,
)
from avalia.domain.weights import WeightProfile


class ResolvedBy(StrEnum):
    """Como uma divergência foi resolvida (RF-20, RF-24)."""

    AUTO = "auto"
    HUMANO = "humano"


# ----------------------------- indexação do artefato -----------------------------


class ComponentInventory(BaseModel):
    """Componentes presentes/ausentes na submissão (RF-01, RF-02)."""

    model_config = ConfigDict(frozen=True)

    present: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)


class ReadabilityReport(BaseModel):
    """Arquivos ilegíveis (ofuscado/compilado) e dimensões impactadas (RF-03, CB-02)."""

    model_config = ConfigDict(frozen=True)

    unreadable_files: list[EvidenceRef] = Field(default_factory=list)
    impacted_dims: list[Dimension] = Field(default_factory=list)


class AnalysisCoverage(BaseModel):
    """Cobertura de análise: integral vs. amostrado (RF-12, CB-05)."""

    model_config = ConfigDict(frozen=True)

    fully_analyzed: list[str] = Field(default_factory=list)
    sampled: list[str] = Field(default_factory=list)
    reason: str | None = None


class TargetClassification(BaseModel):
    """Topologia + tipo funcional + confiança própria (RF-04..08, RNF-03)."""

    model_config = ConfigDict(frozen=True)

    topology: Topology
    topology_signals: list[str] = Field(default_factory=list)
    system_type: str | None = None
    classification_conf: Confidence
    caveats: list[str] = Field(default_factory=list)


# ----------------------------- achados e julgamentos -----------------------------


class Recommendation(BaseModel):
    """Recomendação priorizável; pode rastrear a um achado (RF-27)."""

    model_config = ConfigDict(frozen=True)

    statement: str = Field(min_length=1)
    urgency: Urgency
    traces_to: str | None = None  # identidade de Finding


class Finding(BaseModel):
    """Achado com `FindingType` da taxonomia + evidência (símbolo). Identidade estável (RF-29).

    `dimension` e `identity` são DERIVADOS da taxonomia e da 1ª evidência — não podem ser
    inconsistentes com `finding_type` (regra inviolável 4/5).
    """

    model_config = ConfigDict(frozen=True)

    finding_type: FindingType
    urgency: Urgency
    statement: str = Field(min_length=1)
    reasoning: str = Field(min_length=1)  # RNF-02
    evidence: list[EvidenceRef] = Field(min_length=1)  # RF-14/RNF-07: sempre com evidência
    positive: bool = False

    @computed_field  # type: ignore[prop-decorator]
    @property
    def dimension(self) -> Dimension:
        return dimension_of(self.finding_type)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def identity(self) -> str:
        ref = self.evidence[0]
        loc = normalize_location(ref.file_path, ref.symbol)
        return finding_identity(self.dimension, self.finding_type, loc)


class CheckOutcome(BaseModel):
    """Resultado de um check (plan §3.2). Determinístico carrega `deterministic_hash` (RNF-01)."""

    model_config = ConfigDict(frozen=True)

    check_id: str = Field(min_length=1)
    nature: CheckNature
    passed: bool | None = None
    score_signal: float | None = None
    evidence: list[EvidenceRef] = Field(default_factory=list)
    deterministic_hash: str | None = None

    @model_validator(mode="after")
    def _deterministic_has_hash(self) -> CheckOutcome:
        if self.nature is CheckNature.DETERMINISTICO and not self.deterministic_hash:
            raise ValueError("Check determinístico exige `deterministic_hash` (RNF-01).")
        return self


class JudgeOpinion(BaseModel):
    """Opinião de um juiz-LLM (ângulo do painel). Rubrica versionada (RNF-01)."""

    model_config = ConfigDict(frozen=True)

    angle: str = Field(min_length=1)
    score: int = Field(ge=0, le=100)
    reasoning: str = Field(min_length=1)  # RNF-02
    confidence: Confidence
    rubric_id: str = Field(min_length=1)  # rubrica versionada (RNF-01)
    band: Band | None = None
    evidence: list[EvidenceRef] = Field(default_factory=list)


class DimensionResult(BaseModel):
    """Resultado completo de uma dimensão (RF-09..14). reasoning+confidence obrigatórios."""

    model_config = ConfigDict(frozen=True)

    dimension: Dimension
    applicable: bool = True
    score: int | None = None
    confidence: Confidence
    confidence_reason: str | None = None
    reasoning: str = Field(min_length=1)  # regra 6 / RNF-02
    findings: list[Finding] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)
    static_limitations: str | None = None  # RF-13 (comportamentais)
    check_outcomes: list[CheckOutcome] = Field(default_factory=list)
    judge_opinions: list[JudgeOpinion] = Field(default_factory=list)
    model_substitutions: list[str] = Field(default_factory=list)  # RNF-12: declaradas
    # Slot OPACO da Fase 2 (S-05): presente, default None, e None na Fase 1.
    dynamic_metrics: Mapping[str, Any] | None = None

    @model_validator(mode="after")
    def _contract_invariants(self) -> DimensionResult:
        if not self.reasoning.strip():
            raise ValueError(
                f"Dimensão '{self.dimension.value}' exige reasoning não-vazio (RNF-02/CA-05)."
            )
        if self.applicable:
            if self.score is None or not (0 <= self.score <= 100):
                raise ValueError(f"Dimensão aplicável '{self.dimension.value}' exige score 0–100.")
        elif self.score is not None:
            raise ValueError(f"Dimensão não aplicável '{self.dimension.value}' não deve ter score.")
        if self.dimension in BEHAVIORAL_DIMENSIONS and self.applicable:
            if not (self.static_limitations and self.static_limitations.strip()):
                raise ValueError(
                    f"Dimensão comportamental '{self.dimension.value}' exige "
                    "`static_limitations` (RF-13/RNF-04)."
                )
        bad = [f.finding_type.value for f in self.findings if f.dimension is not self.dimension]
        if bad:
            raise ValueError(
                f"Achados de outra dimensão em '{self.dimension.value}': {bad} (regra 4)."
            )
        if self.dynamic_metrics is not None:
            raise ValueError(
                "S-05: `dynamic_metrics` é slot opaco da Fase 2 — deve ser None na Fase 1."
            )
        return self


# ----------------------------- divergência e agregação -----------------------------


class DivergenceCandidate(BaseModel):
    """Divergência detectada, ANTES de resolvida (sem `resolved_by`) — T-401."""

    model_config = ConfigDict(frozen=True)

    dimension: Dimension
    conflicting_positions: list[JudgeOpinion] = Field(min_length=2)
    threshold_hit: str = Field(min_length=1)  # band_mismatch | low_confidence


class HumanDecision(BaseModel):
    """Decisão humana sobre uma divergência escalada (RF-24)."""

    model_config = ConfigDict(frozen=True)

    dimension: Dimension
    chosen_band: Band | None = None
    note: str = Field(min_length=1)


class DivergenceRecord(BaseModel):
    """Registro de divergência entre julgamentos da mesma dimensão (RF-20, 4.2.7)."""

    model_config = ConfigDict(frozen=True)

    dimension: Dimension
    conflicting_positions: list[JudgeOpinion] = Field(min_length=2)
    threshold_hit: str = Field(min_length=1)  # band_mismatch | low_confidence
    resolved_by: ResolvedBy
    resolution_note: str | None = None


class ApprovalCondition(BaseModel):
    """Condição de aprovação derivada de um achado (RF-19, CA-09)."""

    model_config = ConfigDict(frozen=True)

    statement: str = Field(min_length=1)
    urgency: Urgency
    traces_to: str = Field(min_length=1)  # identidade de Finding


class AggregateScore(BaseModel):
    """Score agregado + veredito + condições (RF-15..19, RF-22)."""

    model_config = ConfigDict(frozen=True)

    score: int = Field(ge=0, le=100)
    verdict: Verdict
    excluded_low_conf: list[Dimension] = Field(default_factory=list)
    approval_conditions: list[ApprovalCondition] = Field(default_factory=list)


class VersionComparison(BaseModel):
    """Comparação com a versão anterior do mesmo alvo (RF-28, RF-29)."""

    model_config = ConfigDict(frozen=True)

    prev_report_id: str = Field(min_length=1)
    deltas: dict[Dimension, int] = Field(default_factory=dict)
    regressions: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)
    resolved_findings: list[str] = Field(default_factory=list)
    persistent_findings: list[str] = Field(default_factory=list)
    new_findings: list[str] = Field(default_factory=list)


# ----------------------------- laudo final -----------------------------


class ReportHeader(BaseModel):
    """Bloco 4.2.1: classificação + perfil + veredito + confiança.

    `static_ceiling` (Frente 2): teto NOMINAL da prontidão estática da Fase 1 (~90). Aditivo,
    default 90 — não muda `score`/`verdict` nem as faixas (§4.2.6/RNF-04). Comunica que a faixa
    90–100 só é atingível com avaliação dinâmica (Fase 2): o score `83/100` não é "reprovado em
    17 pontos" — ~7 pontos são headroom reservado à Fase 2.
    """

    model_config = ConfigDict(frozen=True)

    classification: TargetClassification
    effective_weights: WeightProfile
    verdict: Verdict
    score: int = Field(ge=0, le=100)
    confidence: Confidence
    static_ceiling: int = Field(default=90, ge=0, le=100)


class ReportMetadata(BaseModel):
    """Bloco 4.2.8: config efetiva, inventário, cobertura, limitações (RNF-08, RNF-10)."""

    model_config = ConfigDict(frozen=True)

    effective_config: EvaluatorConfig
    inventory: ComponentInventory
    coverage: AnalysisCoverage
    readability: ReadabilityReport
    known_limitations: list[str] = Field(default_factory=list)
    model_substitutions: list[str] = Field(default_factory=list)  # RNF-12


class EvaluationReport(BaseModel):
    """Laudo final autocontido (RF-25, RNF-10). Exige os blocos 4.2.1–4.2.8."""

    model_config = ConfigDict(frozen=True)

    header: ReportHeader  # 4.2.1 + 4.2.6 (veredito)
    dimensions: list[DimensionResult] = Field(min_length=1)  # 4.2.2
    consolidated_recommendations: list[Recommendation] = Field(default_factory=list)  # 4.2.3
    approval_conditions: list[ApprovalCondition] = Field(default_factory=list)  # 4.2.4
    comparison: VersionComparison | None = None  # 4.2.5 (CB-06: opcional)
    divergences: list[DivergenceRecord] = Field(default_factory=list)  # 4.2.7
    metadata: ReportMetadata  # 4.2.8
