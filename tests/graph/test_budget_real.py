"""T-805 / T-802 reforçado (v1.4, DQ-01) — orçamento aplicado sobre o consumo REAL reportado.

Antes da v1.4, `accumulated_cost` nunca era incrementado: o teto de custo não tinha efeito, e o
teste de CA-13 só passava porque INJETAVA o custo. Aqui o gasto vem do uso de tokens reportado
por um cliente de modelo falso (sem rede), e o teto é checado antes de cada chamada de juízo.
Relógios são falsos onde o tempo importa. Nada executa o alvo (RNF-05).

Rastreabilidade: RF-12, CA-13, RNF-12, spec v0.5 §4.2.8; plan v1.4 §3.3/§3.5.
"""

from __future__ import annotations

import time

import pytest

from avalia.cli import _build_parser, _make_config
from avalia.config.evaluator_config import (
    EvaluatorConfig,
    ModelPrice,
    NodeModelConfig,
    RetryPolicy,
)
from avalia.domain.enums import Band, Confidence, Dimension, RunStatus
from avalia.domain.evidence import EvidenceRef
from avalia.domain.submission import Submission, TargetMetadata
from avalia.graph.budget import BudgetMeter, RunRegistry, budget_usage, over_budget
from avalia.graph.build_graph import build_avalia_graph
from avalia.graph.state import BudgetState
from avalia.judge.framework import Judge, JudgeVerdict
from avalia.judge.rubrics import get_rubric
from avalia.model_gateway.gateway import DEFAULT_PRIMARY_MODEL, ModelGateway
from avalia.report.render import render_markdown

pytestmark = pytest.mark.fast

_SRC = (
    "from langgraph.graph import StateGraph\n"
    "SYSTEM_PROMPT = 'cite a fonte'\n"
    "def agent_a(state):\n    return state\n"
    "def build(g):\n    g.add_edge('agent_a', 'agent_b')\n"
)
_NO_WAIT = RetryPolicy(max_attempts=1, backoff_seconds=0.0)
_PRICE = ModelPrice(input_per_mtok=3.0, output_per_mtok=15.0)


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class _AIMessage:
    def __init__(self, tokens_in: int, tokens_out: int) -> None:
        self.usage_metadata = {"input_tokens": tokens_in, "output_tokens": tokens_out}


class _CountingClient:
    """Cliente falso: toda chamada responde um veredito e reporta 80+20 tokens."""

    calls = 0

    def with_structured_output(self, schema, include_raw: bool = False):
        return self

    def invoke(self, messages):
        type(self).calls += 1
        verdict = JudgeVerdict(
            score=70, band=Band.PRONTO, confidence=Confidence.ALTO, reasoning="ok"
        )
        return {"raw": _AIMessage(80, 20), "parsed": verdict, "parsing_error": None}


def _gateway() -> ModelGateway:
    cfg = EvaluatorConfig(
        node_models={f"juiz_{d.value}": NodeModelConfig(retry=_NO_WAIT) for d in Dimension}
    )
    return ModelGateway(cfg, client_factory=lambda ref: _CountingClient(), env={})


def _run(config: EvaluatorConfig, *, graph=None, thread: str = "t") -> dict:
    graph = graph or build_avalia_graph(gateway=_gateway())
    submission = Submission(
        artifact_files={"graph.py": _SRC},
        metadata=TargetMetadata(target_id="alvo", version="v1"),
        config=config,
    )
    return graph.invoke({"submission": submission}, config={"configurable": {"thread_id": thread}})


# ---------------------------- BudgetMeter ----------------------------


def test_meter_prices_known_models_and_flags_unpriced():
    meter = BudgetMeter(EvaluatorConfig(model_prices={"m-caro": _PRICE}))
    priced = meter.charge("m-caro", 1_000_000, 100_000)
    assert priced.cost == pytest.approx(3.0 + 1.5) and priced.unpriced_model is None
    unpriced = meter.charge("m-sem-preco", 10, 10)
    assert unpriced.cost is None and unpriced.unpriced_model == "m-sem-preco"
    snap = meter.snapshot()
    assert (snap.input_tokens, snap.output_tokens) == (1_000_010, 100_010)
    assert snap.unpriced_models == ("m-sem-preco",)


def test_meter_token_cost_and_time_ceilings():
    clock = _Clock()
    meter = BudgetMeter(EvaluatorConfig(token_ceiling=100, model_prices={"m": _PRICE}), clock=clock)
    assert meter.exceeded() is None
    meter.charge("m", 70, 30)
    assert meter.exceeded() and "tokens" in meter.exceeded()

    cost_meter = BudgetMeter(
        EvaluatorConfig(cost_ceiling=1.0, model_prices={"m": _PRICE}), clock=clock
    )
    cost_meter.charge("m", 400_000, 0)  # 1.20 em moeda
    assert "custo" in (cost_meter.exceeded() or "")

    time_meter = BudgetMeter(EvaluatorConfig(time_ceiling_s=5.0), clock=clock)
    clock.now += 6.0
    assert "tempo" in (time_meter.exceeded() or "")


def test_route_time_check_uses_wall_clock_anchor():
    # started_at é horário de parede (persistível no checkpoint; retomada em outro processo).
    state = {"budget": BudgetState(started_at=time.time() - 100)}
    assert "tempo" in (over_budget(state, EvaluatorConfig(time_ceiling_s=10)) or "")
    assert over_budget(state, EvaluatorConfig(time_ceiling_s=1000)) is None


def test_budget_usage_declares_unpriced_cost():
    usage = budget_usage(BudgetState(input_tokens=5, unpriced_models=["m"]), EvaluatorConfig())
    assert usage.cost is None and "model_prices" in (usage.cost_unavailable_reason or "")
    priced = budget_usage(BudgetState(input_tokens=5, accumulated_cost=0.25), EvaluatorConfig())
    assert priced.cost == 0.25 and priced.cost_unavailable_reason is None


# ---------------------------- Judge + meter ----------------------------


def test_judge_stops_before_next_angle_when_ceiling_hit_and_counts_tokens():
    judge = Judge(
        _gateway(),
        "juiz_trajetoria",
        meter=BudgetMeter(EvaluatorConfig(token_ceiling=100)),
    )
    contrib = judge.assess(
        dimension=Dimension.TRAJETORIA,
        rubric=get_rubric("trajetoria/v1"),
        instruction="Avalie.",
        angles=["defensor", "cetico"],
        target_content={"main.py": "x = 1"},
        evidence=[EvidenceRef(file_path="main.py", symbol="x", component_kind="module")],
    )
    assert len(contrib.opinions) == 1  # 1º ângulo gastou 100 tokens → 2º não chamou o modelo
    assert contrib.partial and contrib.partial_reason == "budget"
    assert "tokens" in (contrib.budget_detail or "")
    assert (contrib.input_tokens, contrib.output_tokens) == (80, 20)
    assert contrib.model_substitutions == []  # teto não é substituição de modelo


def test_judge_charges_priced_model_cost():
    meter = BudgetMeter(EvaluatorConfig(model_prices={DEFAULT_PRIMARY_MODEL: _PRICE}))
    contrib = Judge(_gateway(), "juiz_custo", meter=meter).assess(
        dimension=Dimension.CUSTO,
        rubric=get_rubric("custo/v1"),
        instruction="Avalie.",
        angles=["cetico"],
        target_content={"a": "b"},
        evidence=[],
    )
    assert contrib.cost == pytest.approx((80 * 3.0 + 20 * 15.0) / 1e6)
    assert contrib.unpriced_models == []


# ---------------------------- grafo ponta-a-ponta ----------------------------


def test_token_ceiling_from_real_usage_yields_partial_report():
    result = _run(EvaluatorConfig(token_ceiling=150))
    assert result["status"] is RunStatus.PARTIAL
    report = result["report"]
    usage = report.metadata.budget_usage
    assert usage is not None and usage.total_tokens >= 150  # consumo REAL, não injetado
    assert usage.total_tokens <= 7 * 2 * 100  # nunca passa do painel inteiro
    assert usage.degraded_dims  # quais dimensões foram cortadas é declarado
    degraded = [dr for dr in report.dimensions if dr.dimension in usage.degraded_dims]
    assert all(dr.confidence is Confidence.BAIXO for dr in degraded)
    assert all("Teto de orçamento" in (dr.confidence_reason or "") for dr in degraded)
    subs = {s for dr in report.dimensions for s in dr.model_substitutions}
    assert not any("fallback de modelo esgotado" in s for s in subs)  # causa correta
    assert any("teto de orçamento" in lim for lim in report.metadata.known_limitations)


def test_usage_without_prices_declares_cost_unavailable():
    report = _run(EvaluatorConfig())["report"]
    usage = report.metadata.budget_usage
    assert usage is not None and usage.total_tokens > 0 and usage.cost is None
    assert any("Custo em moeda não calculável" in lim for lim in report.metadata.known_limitations)
    assert "Consumo de orçamento" in render_markdown(report)


def test_usage_with_prices_reports_cost():
    config = EvaluatorConfig(model_prices={DEFAULT_PRIMARY_MODEL: _PRICE})
    usage = _run(config)["report"].metadata.budget_usage
    assert usage is not None and usage.cost is not None and usage.cost > 0
    assert usage.cost_unavailable_reason is None


def test_judge_cache_is_per_run_even_when_graph_is_reused():
    graph = build_avalia_graph(gateway=_gateway())
    _CountingClient.calls = 0
    _run(EvaluatorConfig(), graph=graph, thread="a")
    first = _CountingClient.calls
    _run(EvaluatorConfig(), graph=graph, thread="b")
    # Antes, o JudgeCache era do GRAFO: a avaliação "b" reusava os juízos de "a" (0 chamadas).
    # Agora é por execução: a 2ª avaliação chama o modelo de novo.
    assert first > 0 and _CountingClient.calls == 2 * first


def test_registry_restart_and_finish():
    registry = RunRegistry(with_cache=True)
    first = registry.start("t", EvaluatorConfig())
    assert registry.get("t", EvaluatorConfig()) is first
    second = registry.start("t", EvaluatorConfig())
    assert second is not first and second.cache is not first.cache
    registry.finish("t")
    assert registry.get("t", EvaluatorConfig()) is not second  # recriado sob demanda


# ---------------------------- CLI ----------------------------


def test_cli_ceiling_flags_reach_the_config():
    args = _build_parser().parse_args(
        ["alvo", "--token-ceiling", "5000", "--cost-ceiling", "0.5", "--time-ceiling", "90"]
    )
    config = _make_config(args)
    assert (config.token_ceiling, config.cost_ceiling, config.time_ceiling_s) == (5000, 0.5, 90)
