"""T-403 — testes de `ApprovalProvider` (Static e CLI).

Interface estável de coleta de decisão humana (resolução #5). Nada executa o alvo.
"""

from __future__ import annotations

import pytest

from avalia.domain.contracts import DivergenceCandidate, HumanDecision, JudgeOpinion
from avalia.domain.enums import Band, Confidence, Dimension
from avalia.hitl.approval import CLIApprovalProvider, StaticApprovalProvider

pytestmark = pytest.mark.fast


def _op(band: Band) -> JudgeOpinion:
    return JudgeOpinion(
        angle="x",
        score=60,
        reasoning="r",
        confidence=Confidence.MEDIO,
        rubric_id="robustez/v1",
        band=band,
    )


def _candidate(dim: Dimension) -> DivergenceCandidate:
    return DivergenceCandidate(
        dimension=dim,
        conflicting_positions=[_op(Band.PRONTO), _op(Band.INSUFICIENTE)],
        threshold_hit="band_mismatch",
    )


def test_static_returns_given_decision_and_default():
    decision = HumanDecision(dimension=Dimension.ROBUSTEZ, note="manter a ressalva")
    provider = StaticApprovalProvider([decision])
    assert provider.decide(_candidate(Dimension.ROBUSTEZ)) is decision
    # dimensão sem decisão fornecida → default com nota não-vazia
    fallback = provider.decide(_candidate(Dimension.CUSTO))
    assert fallback.dimension is Dimension.CUSTO and fallback.note


def test_cli_provider_parses_band_and_note():
    answers = iter(["pronto", "concordo com o defensor"])
    outputs: list[str] = []
    provider = CLIApprovalProvider(input_fn=lambda _prompt: next(answers), output_fn=outputs.append)
    decision = provider.decide(_candidate(Dimension.ROBUSTEZ))
    assert decision.chosen_band is Band.PRONTO
    assert decision.note == "concordo com o defensor"
    assert any("Divergência" in line for line in outputs)  # apresentou o conflito


def test_cli_provider_empty_band_is_none():
    answers = iter(["", ""])
    provider = CLIApprovalProvider(
        input_fn=lambda _prompt: next(answers), output_fn=lambda _s: None
    )
    decision = provider.decide(_candidate(Dimension.ROBUSTEZ))
    assert decision.chosen_band is None and decision.note  # nota default não-vazia
