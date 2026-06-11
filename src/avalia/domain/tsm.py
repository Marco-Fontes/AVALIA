"""T-103 — `TargetStaticModel` (TSM): fonte ÚNICA de fatos do alvo (plan §3.1/§4).

Estrutura normalizada e **agnóstica de linguagem** produzida pela extração estática. Cada
fato carrega `EvidenceRef` (arquivo + símbolo). O TSM é IMUTÁVEL após construção — todos os
avaliadores leem o mesmo objeto (paralelismo sem corrida). Nada aqui executa o alvo.

Rastreabilidade: RF-08, RF-12, RF-14, RNF-07; plan §3.1.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from avalia.domain.contracts import AnalysisCoverage, ReadabilityReport
from avalia.domain.evidence import EvidenceRef


class _Fact(BaseModel):
    """Base imutável de todo fato do TSM: sempre ancorado em evidência (símbolo)."""

    model_config = ConfigDict(frozen=True)

    evidence: EvidenceRef


class AgentNode(_Fact):
    """Papel/agente detectado (função/classe com prompt ou comportamento de agente)."""

    name: str
    role: str | None = None
    has_prompt: bool = False


class PromptRef(_Fact):
    """Prompt localizado (texto-fonte tratado como DADO não confiável a jusante)."""

    name: str
    text: str
    role: str | None = None  # system | user | tool | unknown


class ToolDef(_Fact):
    """Ferramenta exposta a um agente (função/decorador)."""

    name: str
    description: str | None = None
    params: list[str] = Field(default_factory=list)


class Edge(_Fact):
    """Aresta/roteamento entre nós do grafo do alvo."""

    source: str
    target: str
    condition: str | None = None


class LoopInfo(_Fact):
    """Loop detectado. `has_cap` = tem teto de iteração (range/contador/break)."""

    symbol: str
    kind: str  # for | while
    has_cap: bool
    cap_reason: str | None = None  # por que se considera (ou não) limitado


class ModelAssignment(_Fact):
    """Atribuição de modelo a um nó (ex.: `model=...` numa chamada)."""

    node: str
    model_expr: str  # expressão-fonte (pode referenciar config; não é julgada aqui)


class ConfigItem(_Fact):
    """Item de configuração declarado no artefato."""

    key: str
    value_expr: str


class ErrorHandling(_Fact):
    """Sinal de robustez detectado: try/except, retry, fallback, timeout, etc."""

    symbol: str
    # try_except | retry | fallback_modelo | timeout | streaming | cache | validacao_entrada
    kind: str


class SharedStateRef(_Fact):
    """Sinal de estado compartilhado entre passos (3º sinal de topologia — RF-04)."""

    name: str
    kind: str  # typed_dict | state_class | state_param


class TargetStaticModel(BaseModel):
    """Modelo estático unificado do alvo. Imutável; fonte única para os avaliadores."""

    model_config = ConfigDict(frozen=True)

    files: list[str] = Field(default_factory=list)
    agents: list[AgentNode] = Field(default_factory=list)
    prompts: list[PromptRef] = Field(default_factory=list)
    tools: list[ToolDef] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)
    loops: list[LoopInfo] = Field(default_factory=list)
    model_assignments: list[ModelAssignment] = Field(default_factory=list)
    configs: list[ConfigItem] = Field(default_factory=list)
    error_handling: list[ErrorHandling] = Field(default_factory=list)
    shared_state: list[SharedStateRef] = Field(default_factory=list)
    coverage: AnalysisCoverage = Field(default_factory=AnalysisCoverage)
    readability: ReadabilityReport = Field(default_factory=ReadabilityReport)
