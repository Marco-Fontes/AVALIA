"""T-403 — `ApprovalProvider` + implementações CLI e estática.

Abstrai a coleta da decisão humana sobre uma divergência. `CLIApprovalProvider` é interativa
(resolução #5); `StaticApprovalProvider` injeta decisões (testes). API-callback/UI ficam como
extensão da Fase 2, sem tocar o grafo.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Protocol

from avalia.domain.contracts import DivergenceCandidate, HumanDecision
from avalia.domain.enums import Band


class ApprovalProvider(Protocol):
    """Interface estável de coleta de decisão humana (interrupt/resume é detalhe do grafo)."""

    def decide(self, candidate: DivergenceCandidate) -> HumanDecision: ...


class StaticApprovalProvider:
    """Decisões pré-fornecidas por dimensão (testes/automação)."""

    def __init__(self, decisions: Iterable[HumanDecision]) -> None:
        self._by_dim = {d.dimension: d for d in decisions}

    def decide(self, candidate: DivergenceCandidate) -> HumanDecision:
        decision = self._by_dim.get(candidate.dimension)
        if decision is not None:
            return decision
        return HumanDecision(
            dimension=candidate.dimension,
            note="Sem decisão específica fornecida; divergência mantida como registrada.",
        )


class CLIApprovalProvider:
    """Coleta a decisão humana via CLI: apresenta as posições e lê faixa + nota."""

    def __init__(
        self,
        input_fn: Callable[[str], str] = input,
        output_fn: Callable[[str], None] = print,
    ) -> None:
        self._input = input_fn
        self._output = output_fn

    def decide(self, candidate: DivergenceCandidate) -> HumanDecision:
        self._output(
            f"\n— Divergência em '{candidate.dimension.value}' ({candidate.threshold_hit}) —"
        )
        for op in candidate.conflicting_positions:
            band = op.band.value if op.band else "?"
            self._output(f"  [{op.angle}] faixa={band} score={op.score}: {op.reasoning}")
        raw_band = self._input(
            "Faixa decidida (insuficiente/adequado_com_ressalvas/pronto, vazio = nenhuma): "
        ).strip()
        chosen = Band(raw_band) if raw_band in {b.value for b in Band} else None
        note = self._input("Justificativa: ").strip() or "Decisão humana registrada."
        return HumanDecision(dimension=candidate.dimension, chosen_band=chosen, note=note)
