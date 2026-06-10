"""T-002 — testes de enums atômicos e EvidenceRef.

DoD: tipos serializam/deserializam; EvidenceRef EXIGE símbolo (não só linha) — resolução #3.
Rastreabilidade: RF-14, RNF-07, RNF-03.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from avalia.domain.enums import (
    BEHAVIORAL_DIMENSIONS,
    Confidence,
    Dimension,
)
from avalia.domain.evidence import EvidenceRef

pytestmark = pytest.mark.fast


def test_dimension_roundtrip():
    assert Dimension("custo") is Dimension.CUSTO
    assert {d.value for d in Dimension} == {
        "custo",
        "performance",
        "qualidade",
        "assertividade",
        "alucinacao",
        "trajetoria",
        "robustez",
    }


def test_confidence_is_ordered():
    assert Confidence.BAIXO.rank < Confidence.MEDIO.rank < Confidence.ALTO.rank


def test_behavioral_dims_are_the_three_subjective():
    assert BEHAVIORAL_DIMENSIONS == frozenset(
        {Dimension.QUALIDADE, Dimension.ASSERTIVIDADE, Dimension.ALUCINACAO}
    )


def test_evidence_requires_symbol():
    # símbolo vazio → erro (linha sozinha não é evidência válida — regra inviolável 5)
    with pytest.raises(ValidationError):
        EvidenceRef(file_path="t/main.py", symbol="   ", component_kind="loop")


def test_evidence_serializes_without_lines():
    ref = EvidenceRef(file_path="t/main.py", symbol="run_agent", component_kind="agent")
    assert ref.line_start is None
    back = EvidenceRef.model_validate(ref.model_dump())
    assert back == ref  # frozen + igualdade estrutural


def test_evidence_is_frozen():
    ref = EvidenceRef(file_path="t/main.py", symbol="run_agent", component_kind="agent")
    with pytest.raises(ValidationError):
        ref.symbol = "outro"  # type: ignore[misc]
