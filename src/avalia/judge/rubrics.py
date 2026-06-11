"""Rubricas versionadas dos juízes-LLM (RNF-01). O `id` da rubrica entra em cada `JudgeOpinion`.

Versionar a rubrica é o que torna o julgamento reproduzível por faixa entre execuções.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Rubric(BaseModel):
    """Critério de julgamento versionado."""

    model_config = ConfigDict(frozen=True)

    id: str
    text: str


_RUBRICS: dict[str, Rubric] = {
    "trajetoria/v1": Rubric(
        id="trajetoria/v1",
        text=(
            "Avalie a dimensão Trajetória: clareza das descrições de ferramentas e ausência "
            "de sobreposição ambígua (T1); coerência do roteamento, sem caminhos mortos (T2). "
            "Loops sem teto são tratados como fato determinístico, não como opinião."
        ),
    ),
    "custo/v1": Rubric(
        id="custo/v1",
        text=(
            "Avalie Custo e Eficiência: adequação do mix de modelos (caro só onde necessário, "
            "C1) e chamadas de modelo redundantes no fluxo principal (C3). Tetos/limites/cache "
            "são fatos determinísticos."
        ),
    ),
    "performance/v1": Rubric(
        id="performance/v1",
        text=(
            "Avalie Performance e Latência: serialização desnecessária onde caberia "
            "paralelização (P1). Timeouts e streaming são fatos determinísticos."
        ),
    ),
    "qualidade/v1": Rubric(
        id="qualidade/v1",
        text=(
            "Avalie Qualidade e Correção (comportamental): clareza dos prompts e presença de "
            "rubricas/critérios de qualidade (Q1). A existência de harness é fato determinístico; "
            "a correção real das saídas NÃO é avaliável na Fase 1."
        ),
    ),
    "assertividade/v1": Rubric(
        id="assertividade/v1",
        text=(
            "Avalie Assertividade (comportamental): os prompts pedem expressão de confiança/"
            "certeza (A1)? O comportamento real não é avaliável na Fase 1; só a prontidão."
        ),
    ),
    "alucinacao/v1": Rubric(
        id="alucinacao/v1",
        text=(
            "Avalie Alucinação/Fundamentação (comportamental): exigência de citação de fontes, "
            "grounding com atribuição de origem e instruções de abstenção sem base factual (H1). "
            "A taxa real de alucinação NÃO é medível na Fase 1."
        ),
    ),
    "robustez/v1": Rubric(
        id="robustez/v1",
        text=(
            "Avalie Robustez: significância do tratamento de erro (R1) e adequação dos guard-rails "
            "anti-injeção de prompt (R3). Retry, fallback de modelo e validação de entrada são "
            "fatos determinísticos."
        ),
    ),
}


def get_rubric(rubric_id: str) -> Rubric:
    try:
        return _RUBRICS[rubric_id]
    except KeyError as exc:
        raise KeyError(f"Rubrica desconhecida: {rubric_id!r}") from exc
