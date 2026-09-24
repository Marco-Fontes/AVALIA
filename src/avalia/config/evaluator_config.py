"""T-005 — `EvaluatorConfig` + validação (RNF-06, RNF-12, CB-07).

Pesos, limiares de faixa (default 50/75), piso de confiança, tetos de custo/tempo, e
**modelo por tipo de nó** (primário + fallback + back-end + retry). Tudo é DADO: trocar
modelo/provedor/limiar é só configuração (RNF-06). Pesos inválidos → erro descritivo
ANTES da análise (CB-07).

Os tipos de modelo (`Backend`, `ModelRef`, `RetryPolicy`, `NodeModelConfig`) vivem aqui
(camada de config, isenta do guard de modelo) e são consumidos pelo `ModelGateway` (T-007),
mantendo a dependência numa só direção (gateway → config). Os SLUGS-padrão (Opus→Sonnet)
NÃO moram aqui: são resolvidos pelo gateway a partir de env/defaults (RNF-06).

v1.4 (DQ-03): os parâmetros de PONTUAÇÃO (nota base e penalidades por urgência) também são dado
(`ScoringConfig`), e o teto exibido de prontidão estática deriva deles.

Rastreabilidade: RNF-06, CB-07, RF-18, RF-22, RNF-12; resoluções #2, #2b, #4; DQ-03.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from avalia.domain.enums import Confidence, Dimension, Urgency, Verdict


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
    # T3.1 — controle de custo (RF-DIM-C2) e performance (RF-DIM-P2) das chamadas de JUÍZO do
    # próprio AVALIA: limite de tokens e timeout. DADO de config (RNF-06), sobrescrevível por env
    # no gateway. Aplica a correção apontada no dogfood (sem_limite_tokens/sem_timeout).
    max_tokens: int | None = Field(default=1024, gt=0)
    timeout_s: float | None = Field(default=60.0, gt=0)


class RetryPolicy(BaseModel):
    """Política de retry no mesmo modelo antes de escalar para fallback (RNF-12)."""

    model_config = ConfigDict(frozen=True)

    max_attempts: int = Field(default=2, ge=1)
    backoff_seconds: float = Field(default=1.0, ge=0.0)
    # v1.4 (plan §3.2c): teto da espera exponencial entre tentativas no mesmo modelo.
    max_backoff_seconds: float = Field(default=30.0, ge=0.0)

    def delay_for(self, retry_index: int) -> float:
        """Espera antes da retentativa `retry_index` (0 = 1ª): `backoff·2ⁿ`, limitada ao teto.
        Determinística (sem jitter) — não interfere na reprodutibilidade (RNF-01)."""
        return float(min(self.backoff_seconds * (2**retry_index), self.max_backoff_seconds))


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


class ModelPrice(BaseModel):
    """Preço de um modelo por milhão de tokens (v1.4, DQ-01). DADO de config (RNF-06): sem preço
    configurado, o custo em moeda é declarado como não calculável — nunca inventado."""

    model_config = ConfigDict(frozen=True)

    input_per_mtok: float = Field(ge=0.0)
    output_per_mtok: float = Field(ge=0.0)

    def cost(self, input_tokens: int, output_tokens: int) -> float:
        return (input_tokens * self.input_per_mtok + output_tokens * self.output_per_mtok) / 1e6


class ScoringConfig(BaseModel):
    """Parâmetros de pontuação das dimensões (v1.4, DQ-03, RNF-06; plan §3.2f).

    O score de cada dimensão é ancorado nos achados DETERMINÍSTICOS (regra 6): parte da nota base
    e desconta uma penalidade por achado, conforme a urgência. A Trajetória tem parâmetros próprios
    (loop sem teto rebaixa para a faixa condicional, com piso). Os defaults reproduzem exatamente
    o cálculo anterior — laudos com a config padrão são bit-idênticos.
    """

    model_config = ConfigDict(frozen=True)

    base_score: int = Field(default=90, ge=0, le=100)
    critical_penalty: int = Field(default=22, ge=0, le=100)
    important_penalty: int = Field(default=9, ge=0, le=100)
    suggestion_penalty: int = Field(default=3, ge=0, le=100)
    trajectory_base_score: int = Field(default=85, ge=0, le=100)
    trajectory_no_cap_penalty: int = Field(default=25, ge=0, le=100)
    trajectory_no_cap_floor: int = Field(default=50, ge=0, le=100)

    def penalty_for(self, urgency: Urgency) -> int:
        """Penalidade de um achado determinístico, pela urgência."""
        if urgency is Urgency.CRITICO:
            return self.critical_penalty
        if urgency is Urgency.IMPORTANTE:
            return self.important_penalty
        return self.suggestion_penalty

    @property
    def max_static_score(self) -> int:
        """Maior nota que o motor determinístico produz numa dimensão (teto da Fase 1)."""
        return max(self.base_score, self.trajectory_base_score)


# Instância padrão compartilhada (frozen) — default de argumento sem chamada na assinatura.
DEFAULT_SCORING = ScoringConfig()


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
    # Tetos de orçamento das chamadas de juízo (RF-12/CA-13; v1.4, DQ-01). `token_ceiling` (soma
    # de tokens de entrada+saída) é o teto principal, sempre aplicável. `cost_ceiling` é em MOEDA
    # e só é calculável com `model_prices` (slug do modelo → preço); sem preço, o laudo declara.
    token_ceiling: int | None = Field(default=None, gt=0)
    cost_ceiling: float | None = Field(default=None, gt=0)
    time_ceiling_s: float | None = Field(default=None, gt=0)
    model_prices: dict[str, ModelPrice] = Field(default_factory=dict)
    # Teto determinístico de cobertura na indexação (T-105/RF-12): acima dele, os arquivos de
    # menor sinal são amostrados (não analisados a fundo) e declarados em AnalysisCoverage.
    max_analyzed_files: int | None = Field(default=None, gt=0)
    # v1.4 (DQ-03): nota base e penalidades das dimensões (RNF-06).
    scoring: ScoringConfig = DEFAULT_SCORING
    # Teto NOMINAL da "prontidão estática" (Fase 1). Apenas EXIBIDO — não muda o cálculo nem as
    # faixas/veredito (PLANO-MELHORIAS §4 / decisão 2; RNF-04, §4.2.6). v1.4: por omissão DERIVA
    # de `scoring` (o motor determinístico não passa de `scoring.max_static_score`); valor
    # explícito é aceito, mas não pode ser menor que essa nota — senão o laudo exibiria um teto
    # que a própria nota ultrapassa. Use `effective_static_ceiling`.
    static_ceiling: int | None = Field(default=None, ge=0, le=100)
    # T4.4 — calibração do parcial: fração de arquivos amostrados a partir da qual o laudo parcial
    # rebaixa a confiança de TODAS as dimensões. Abaixo dela, só são rebaixadas as dimensões cujas
    # evidências caem em arquivos amostrados (amostragem de 1 arquivo secundário não derruba tudo).
    partial_significant_fraction: float = Field(default=0.25, ge=0.0, le=1.0)
    node_models: dict[str, NodeModelConfig] = Field(default_factory=dict)
    divergence: DivergenceConfig = DivergenceConfig()

    @model_validator(mode="after")
    def _ceiling_not_below_max_score(self) -> EvaluatorConfig:
        max_score = self.scoring.max_static_score
        if self.static_ceiling is not None and self.static_ceiling < max_score:
            raise ValueError(
                f"static_ceiling={self.static_ceiling} é menor que a nota máxima que o motor "
                f"estático produz ({max_score}, de `scoring`); o teto exibido seria falso."
            )
        return self

    @property
    def effective_static_ceiling(self) -> int:
        """Teto de prontidão estática exibido no laudo: explícito ou derivado de `scoring`."""
        if self.static_ceiling is not None:
            return self.static_ceiling
        return self.scoring.max_static_score

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
