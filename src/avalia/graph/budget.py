"""T-802/T-805 — Orçamento de custo/tempo da avaliação (RF-12, CA-13, RNF-12; DQ-01).

Duas peças (plan v1.4 §3.3/§3.5):

- `BudgetMeter` — medidor EM MEMÓRIA de uma execução: acumula os tokens reportados por cada
  chamada de juízo (e o custo em moeda, quando há `model_prices`) e diz se algum teto foi
  atingido. Protegido por lock porque os 7 ramos do fan-out rodam em paralelo. O juiz o consulta
  ANTES de cada chamada — é onde o gasto acontece (antes da v1.4, `accumulated_cost` nunca era
  incrementado e o teto de custo não tinha efeito).
- `over_budget` — pré-checagem barata no roteamento (antes do fan-out), sobre o `BudgetState`.

`RunRegistry` guarda o medidor e o `JudgeCache` de cada execução (chave = `thread_id`): são
recriados na ingestão e liberados ao montar o laudo. Ficam fora do State/checkpoint (não são
serializáveis nem precisam ser: o `BudgetState` guarda o registro auditável do consumo).

Nada executa o alvo (RNF-05): só lê estado, config e o uso reportado pelo gateway.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from avalia.config.evaluator_config import EvaluatorConfig
from avalia.domain.contracts import BudgetUsage
from avalia.graph.state import AvaliaState, BudgetState
from avalia.judge.base import ChargeResult
from avalia.judge.framework import JudgeCache


def over_budget(state: AvaliaState, config: EvaluatorConfig) -> str | None:
    """Razão de estouro de teto (tokens, custo ou tempo) pelo `BudgetState`, ou None."""
    budget = state.get("budget")
    if budget is None:
        return None
    total_tokens = budget.input_tokens + budget.output_tokens
    if config.token_ceiling is not None and total_tokens >= config.token_ceiling:
        return f"tokens consumidos {total_tokens} ≥ teto {config.token_ceiling}"
    if config.cost_ceiling is not None and budget.accumulated_cost >= config.cost_ceiling:
        return f"custo acumulado {budget.accumulated_cost:.4f} ≥ teto {config.cost_ceiling}"
    if config.time_ceiling_s is not None:
        elapsed = time.time() - budget.started_at
        if elapsed >= config.time_ceiling_s:
            return f"tempo decorrido {elapsed:.2f}s ≥ teto {config.time_ceiling_s}s"
    return None


def budget_usage(budget: BudgetState | None, config: EvaluatorConfig) -> BudgetUsage:
    """`BudgetState` (registro do consumo) → bloco `budget_usage` do laudo (spec §4.2.8, DQ-01).

    Custo em moeda só é informado se TODO modelo usado tem preço em `model_prices`; senão fica
    `None` e o motivo é declarado (nunca um custo parcial apresentado como total)."""
    state = budget or BudgetState()
    cost: float | None = state.accumulated_cost
    reason: str | None = None
    if state.unpriced_models:
        cost = None
        reason = "sem preço configurado (model_prices) para: " + ", ".join(state.unpriced_models)
    return BudgetUsage(
        input_tokens=state.input_tokens,
        output_tokens=state.output_tokens,
        cost=cost,
        cost_unavailable_reason=reason,
        elapsed_s=round(max(0.0, time.time() - state.started_at), 3),
        token_ceiling=config.token_ceiling,
        cost_ceiling=config.cost_ceiling,
        time_ceiling_s=config.time_ceiling_s,
        degraded_dims=list(state.degraded_dims),
    )


@dataclass(frozen=True)
class UsageSnapshot:
    """Consumo acumulado num instante (tokens de entrada/saída, custo, modelos sem preço)."""

    input_tokens: int
    output_tokens: int
    cost: float
    unpriced_models: tuple[str, ...]

    def since(self, before: UsageSnapshot) -> UsageSnapshot:
        return UsageSnapshot(
            self.input_tokens - before.input_tokens,
            self.output_tokens - before.output_tokens,
            self.cost - before.cost,
            tuple(m for m in self.unpriced_models if m not in before.unpriced_models),
        )


class BudgetMeter:
    """Medidor de orçamento de UMA execução (thread-safe). Implementa o `UsageMeter` do juiz."""

    def __init__(
        self, config: EvaluatorConfig, *, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._config = config
        self._clock = clock
        self._started = clock()
        self._lock = threading.Lock()
        self._input = 0
        self._output = 0
        self._cost = 0.0
        self._unpriced: list[str] = []

    def charge(self, model: str | None, input_tokens: int, output_tokens: int) -> ChargeResult:
        """Contabiliza uma chamada bem-sucedida e devolve o custo dela (se precificável)."""
        price = self._config.model_prices.get(model) if model else None
        cost = price.cost(input_tokens, output_tokens) if price is not None else None
        unpriced = None if price is not None else (model or "<modelo desconhecido>")
        with self._lock:
            self._input += input_tokens
            self._output += output_tokens
            if cost is not None:
                self._cost += cost
            if unpriced is not None and unpriced not in self._unpriced:
                self._unpriced.append(unpriced)
        return ChargeResult(cost=cost, unpriced_model=unpriced)

    def snapshot(self) -> UsageSnapshot:
        """Consumo acumulado até agora (para medir o delta de um nó que roda sozinho)."""
        with self._lock:
            return UsageSnapshot(self._input, self._output, self._cost, tuple(self._unpriced))

    def exceeded(self) -> str | None:
        """Razão do teto atingido (tokens, custo, tempo), ou None se ainda há orçamento."""
        cfg = self._config
        with self._lock:
            tokens, cost = self._input + self._output, self._cost
        if cfg.token_ceiling is not None and tokens >= cfg.token_ceiling:
            return f"tokens consumidos {tokens} ≥ teto {cfg.token_ceiling}"
        if cfg.cost_ceiling is not None and cost >= cfg.cost_ceiling:
            return f"custo acumulado {cost:.4f} ≥ teto {cfg.cost_ceiling}"
        elapsed = self._clock() - self._started
        if cfg.time_ceiling_s is not None and elapsed >= cfg.time_ceiling_s:
            return f"tempo decorrido {elapsed:.2f}s ≥ teto {cfg.time_ceiling_s}s"
        return None


@dataclass(frozen=True)
class RunResources:
    """Recursos de uma execução do grafo: medidor de orçamento + cache de juízo (T3.2)."""

    meter: BudgetMeter
    cache: JudgeCache | None


class RunRegistry:
    """Recursos por execução (chave = `thread_id`), fora do checkpoint. Thread-safe."""

    def __init__(self, *, with_cache: bool) -> None:
        self._with_cache = with_cache
        self._lock = threading.Lock()
        self._runs: dict[str, RunResources] = {}

    def _new(self, config: EvaluatorConfig) -> RunResources:
        return RunResources(
            meter=BudgetMeter(config), cache=JudgeCache() if self._with_cache else None
        )

    def start(self, key: str, config: EvaluatorConfig) -> RunResources:
        """Nova execução (ingestão): recria medidor e cache — nada vaza entre avaliações."""
        with self._lock:
            self._runs[key] = self._new(config)
            return self._runs[key]

    def get(self, key: str, config: EvaluatorConfig) -> RunResources:
        """Recursos da execução; recria se ausentes (ex.: retomada de HITL em outro processo —
        o consumo anterior segue registrado no `BudgetState`, e o medidor recomeça do zero)."""
        with self._lock:
            if key not in self._runs:
                self._runs[key] = self._new(config)
            return self._runs[key]

    def finish(self, key: str) -> None:
        with self._lock:
            self._runs.pop(key, None)
