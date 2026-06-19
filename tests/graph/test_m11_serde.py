"""M11 — serde do checkpointer endurecido (HITL durável; atrito do M3).

Sob `LANGGRAPH_STRICT_MSGPACK=true` (que o LangGraph promete tornar padrão), tipos `avalia.*`
não-registrados seriam BLOQUEADOS na desserialização do checkpoint, quebrando interrupt/resume
(RF-24) — sobretudo com `PostgresSaver`. Estes testes provam que `avalia_checkpoint_serde()`
registra os tipos e faz roundtrip mesmo em modo estrito. Nada executa o alvo (RNF-05).
"""

from __future__ import annotations

import pytest

from avalia.domain.contracts import DivergenceCandidate, JudgeOpinion
from avalia.domain.enums import Band, Confidence, Dimension
from avalia.domain.submission import Submission, TargetMetadata
from avalia.extract.tsm_builder import build_tsm
from avalia.graph.serde import avalia_checkpoint_serde, avalia_checkpoint_types
from avalia.graph.state import BudgetState

pytestmark = pytest.mark.fast


@pytest.fixture(autouse=True)
def _strict(monkeypatch):
    # Liga AGORA o modo que será padrão no futuro: tipos não-registrados → bloqueados.
    monkeypatch.setenv("LANGGRAPH_STRICT_MSGPACK", "true")
    avalia_checkpoint_serde.cache_clear()  # reconstrói o serde sob o env do teste
    yield
    avalia_checkpoint_serde.cache_clear()


def _opinion() -> JudgeOpinion:
    return JudgeOpinion(
        angle="cetico",
        score=40,
        reasoning="r",
        confidence=Confidence.MEDIO,
        rubric_id="robustez/v1",
        band=Band.INSUFICIENTE,
        evidence=[],
    )


def test_registry_covers_core_state_types():
    names = {t.__name__ for t in avalia_checkpoint_types()}
    # representativos de cada camada que entra no estado/checkpoint
    assert {
        "Submission",
        "TargetStaticModel",
        "DimensionResult",
        "Confidence",
        "BudgetState",
    } <= names


@pytest.mark.parametrize("make", ["submission", "candidate", "tsm", "budget"])
def test_strict_mode_roundtrip_preserves_type(make):
    serde = avalia_checkpoint_serde()
    obj = {
        "submission": lambda: Submission(
            artifact_files={"a.py": "x = 1"}, metadata=TargetMetadata(target_id="t", version="1")
        ),
        "candidate": lambda: DivergenceCandidate(
            dimension=Dimension.ROBUSTEZ,
            conflicting_positions=[_opinion(), _opinion()],
            threshold_hit="band_mismatch",
        ),
        "tsm": lambda: build_tsm({"a.py": "X = 1\nwhile True:\n    pass\n"}),
        "budget": lambda: BudgetState(partial=True, reasons=["teto atingido"]),
    }[make]()
    back = serde.loads_typed(serde.dumps_typed(obj))
    assert type(back) is type(obj)  # não caiu para dict/raw (não foi bloqueado)
    assert back == obj
