"""T-002 — Enums atômicos do domínio.

Vocabulário fechado do laudo (plan.md §4). São a base de toda a Seção 4 do plano.
Rastreabilidade: RF-04, RF-05, RF-15, RF-18, RNF-03; base de RF-09..14.
"""

from __future__ import annotations

from enum import StrEnum


class Dimension(StrEnum):
    """As 7 dimensões avaliadas (plan §4)."""

    CUSTO = "custo"
    PERFORMANCE = "performance"
    QUALIDADE = "qualidade"
    ASSERTIVIDADE = "assertividade"
    ALUCINACAO = "alucinacao"
    TRAJETORIA = "trajetoria"
    ROBUSTEZ = "robustez"


# Dimensões comportamentais: exigem `static_limitations` no laudo (RF-13/RNF-04).
BEHAVIORAL_DIMENSIONS: frozenset[Dimension] = frozenset(
    {Dimension.QUALIDADE, Dimension.ASSERTIVIDADE, Dimension.ALUCINACAO}
)


class HarnessCategory(StrEnum):
    """Categorias de harness de produção para a CAMADA de cobertura (projeção sobre as 7
    dimensões; não substitui o motor). Subconjunto estaticamente avaliável do checklist de
    harness — excluídas desta fase: hooks/extensibilidade, interação humana e governança
    (sinal estático fino demais ou fora do escopo de análise de código). A numeração preserva
    a do checklist de origem para o time reconhecer (3,5,10,12,14 ainda sem check nesta fase)."""

    ORQUESTRACAO = "orquestracao"
    CONTEXTO = "contexto"
    MEMORIA = "memoria"
    FERRAMENTAS = "ferramentas"
    SKILLS = "skills"
    MULTIAGENTE = "multiagente"
    RESILIENCIA = "resiliencia"
    SAIDAS_VERIFICACAO = "saidas_verificacao"
    SEGURANCA = "seguranca"
    OBSERVABILIDADE = "observabilidade"
    AVALIACAO_CONTINUA = "avaliacao_continua"
    EXECUCAO_DURAVEL = "execucao_duravel"
    CICLO_DE_VIDA = "ciclo_de_vida"
    CUSTO_PERFORMANCE = "custo_performance"


class Confidence(StrEnum):
    """Confiança de um julgamento/classificação (RNF-03). Ordenável via `rank`."""

    BAIXO = "baixo"
    MEDIO = "medio"
    ALTO = "alto"

    @property
    def rank(self) -> int:
        return {"baixo": 0, "medio": 1, "alto": 2}[self.value]


class Topology(StrEnum):
    """Topologia detectada (RF-04). Sem recusa para agente único (CA-02)."""

    MULTIAGENTE = "multiagente"
    AGENTE_UNICO_BORDERLINE = "agente_unico_borderline"


class Verdict(StrEnum):
    """Veredito agregado por faixas (RF-18, plan §4.2.6)."""

    APROVADO = "aprovado"
    APROVACAO_CONDICIONAL = "aprovacao_condicional"
    REPROVADO = "reprovado"


class Band(StrEnum):
    """Faixa qualitativa de um julgamento (plan §4.2.6). Gatilho de divergência (#4)."""

    INSUFICIENTE = "insuficiente"
    ADEQUADO_COM_RESSALVAS = "adequado_com_ressalvas"
    PRONTO = "pronto"


class Urgency(StrEnum):
    """Urgência de um achado/recomendação (RF-19, RF-27)."""

    CRITICO = "critico"
    IMPORTANTE = "importante"
    SUGESTAO = "sugestao"


class CheckNature(StrEnum):
    """Natureza de um check de dimensão (plan §3.2)."""

    DETERMINISTICO = "deterministico"
    LLM_JUDGE = "llm_judge"
    HIBRIDO = "hibrido"


class RunStatus(StrEnum):
    """Estado da execução do grafo (plan §3.3)."""

    OK = "ok"
    PARTIAL = "partial"
    ERROR = "error"
    AWAITING_HUMAN = "awaiting_human"
