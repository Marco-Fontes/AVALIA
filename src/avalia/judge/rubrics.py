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
}


def get_rubric(rubric_id: str) -> Rubric:
    try:
        return _RUBRICS[rubric_id]
    except KeyError as exc:
        raise KeyError(f"Rubrica desconhecida: {rubric_id!r}") from exc
