"""T-005 — `EvaluatorConfig` + validação (RNF-06, RNF-12, CB-07).

Pesos, limiares de faixa (default 50/75), piso de confiança, tetos de custo/tempo, e
**modelo por tipo de nó** (primário + fallback + back-end + retry). Tudo é DADO: trocar
modelo/provedor/limiar é só configuração (RNF-06). Pesos inválidos → erro descritivo
ANTES da análise (CB-07).

Os tipos de modelo (`Backend`, `ModelRef`, `RetryPolicy`, `NodeModelConfig`) vivem aqui
(camada de config, isenta do guard de modelo) e são consumidos pelo `ModelGateway` (T-007),
mantendo a dependência numa só direção (gateway → config). Os SLUGS-padrão (Opus→Sonnet)
NÃO moram aqui: são resolvidos pelo gateway a partir de env/defaults (RNF-06).

Rastreabilidade: RNF-06, CB-07, RF-18, RF-22, RNF-12; resoluções #2, #2b, #4.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from avalia.domain.enums import Confidence, Dimension, Verdict


class Backend(StrEnum):
    """Back-end de acesso a modelo (#2b). OpenRouter dá alcance cross-provider."""

    ANTHROPIC = "anthropic"
    OPENROUTER = "openrouter"


class ModelRef(BaseModel):
    """Referência concreta a um modelo — DADO de config (RNF-06)."""

    model_config = ConfigDict(frozen=True)

    backend: Backend = Backend.ANTHROPIC
    model: str = Field(min_length=1, description="Slug do modelo (config, nunca constante).")
    base_url: str | None = None
    temperature: float = Field(default=0.0, ge=0.0)  # RNF-01: juiz determinístico


class RetryPolicy(BaseModel):
    """Política de retry no mesmo modelo antes de escalar para fallback (RNF-12)."""

    model_config = ConfigDict(frozen=True)

    max_attempts: int = Field(default=2, ge=1)
    backoff_seconds: float = Field(default=1.0, ge=0.0)


class NodeModelConfig(BaseModel):
    """Config de modelo de um tipo de nó: primário + fallback + retry (RNF-12)."""

    model_config = ConfigDict(frozen=True)

    primary: ModelRef | None = None
    fallback: ModelRef | None = None
    retry: RetryPolicy = RetryPolicy()


class BandThresholds(BaseModel):
    """Limiares de faixa do veredito (RF-18, plan §4.2.6). Defaults 50/75."""

    model_config = ConfigDict(frozen=True)

    aprovacao_condicional_min: int = Field(default=50, ge=0, le=100)
    aprovado_min: int = Field(default=75, ge=0, le=100)

    @model_validator(mode="after")
    def _ordered(self) -> BandThresholds:
        if not (0 <= self.aprovacao_condicional_min <= self.aprovado_min <= 100):
            raise ValueError("Limiares devem satisfazer 0 ≤ condicional_min ≤ aprovado_min ≤ 100.")
        return self


class DivergenceConfig(BaseModel):
    """Gatilho de divergência (resolução #4): faixas distintas OU confiança < piso."""

    model_config = ConfigDict(frozen=True)

    trigger_on_band_mismatch: bool = True
    min_confidence: Confidence = Confidence.MEDIO


class EvaluatorConfig(BaseModel):
    """Configuração completa do avaliador (entrada, validada na ingestão — CB-07)."""

    model_config = ConfigDict(frozen=True)

    weights: dict[Dimension, float] | None = None
    thresholds: BandThresholds = BandThresholds()
    confidence_floor: Confidence | None = None
    cost_ceiling: float | None = Field(default=None, gt=0)
    time_ceiling_s: float | None = Field(default=None, gt=0)
    # Teto determinístico de cobertura na indexação (T-105/RF-12): acima dele, os arquivos de
    # menor sinal são amostrados (não analisados a fundo) e declarados em AnalysisCoverage.
    max_analyzed_files: int | None = Field(default=None, gt=0)
    node_models: dict[str, NodeModelConfig] = Field(default_factory=dict)
    divergence: DivergenceConfig = DivergenceConfig()

    @field_validator("weights")
    @classmethod
    def _validate_weights(cls, v: dict[Dimension, float] | None) -> dict[Dimension, float] | None:
        if v is None:
            return v
        if not v:
            raise ValueError("CB-07: 'weights' presente mas vazio.")
        bad = {d.value: w for d, w in v.items() if w < 0}
        if bad:
            raise ValueError(f"CB-07: pesos negativos não permitidos: {bad}.")
        if sum(v.values()) <= 0:
            raise ValueError("CB-07: a soma dos pesos deve ser positiva.")
        return v

    def verdict_for(self, score: int) -> Verdict:
        """Mapeia score 0–100 → veredito pelas faixas configuradas (RF-18)."""
        if score >= self.thresholds.aprovado_min:
            return Verdict.APROVADO
        if score >= self.thresholds.aprovacao_condicional_min:
            return Verdict.APROVACAO_CONDICIONAL
        return Verdict.REPROVADO
