"""Funções dos nós do grafo (T-201..204, T-308 wiring, T-501, T-701).

Cada nó lê/escreve o `AvaliaState` e delega à lógica pura (ingest/classify/weights/evaluators/
aggregate/report). Nada executa o alvo (RNF-05) — só lê o TSM e fala com modelos via gateway.
O juiz da Trajetória é injetado opcionalmente (M1 roda determinístico por padrão).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langgraph.types import interrupt

from avalia.aggregate import aggregate
from avalia.classify import classify_target
from avalia.compare import compare
from avalia.config.weight_profiles import load_weight_profiles
from avalia.divergence import detect_candidates, reconcile_candidate
from avalia.domain.contracts import (
    DimensionResult,
    DivergenceCandidate,
    DivergenceRecord,
    HumanDecision,
    ResolvedBy,
)
from avalia.domain.enums import Confidence, Dimension, RunStatus
from avalia.evaluators.registry import EVALUATORS
from avalia.extract.tsm_builder import build_tsm
from avalia.graph.budget import over_budget
from avalia.graph.state import AvaliaState, BudgetState
from avalia.ingest import ingest_validate
from avalia.judge.contributors import build_contribution
from avalia.judge.framework import GatewayLike, JudgeCache
from avalia.persistence.repository import ReportRepository, make_record
from avalia.report.build import build_report
from avalia.weights_select import select_weights


def n0_ingest(state: AvaliaState) -> dict[str, Any]:
    out = ingest_validate(state["submission"])
    # Inicializa o budget (âncora de tempo) já na entrada, salvo se o teste o injetou (RF-12).
    update: dict[str, Any] = {"inventory": out.inventory, "status": out.status}
    if state.get("budget") is None:
        update["budget"] = BudgetState()
    if out.error_message is not None:
        update["error_message"] = out.error_message
    return update


def n1_index(state: AvaliaState) -> dict[str, Any]:
    return {"tsm": build_tsm(state["submission"].artifact_files, state["submission"].config)}


def n2_classify(state: AvaliaState) -> dict[str, Any]:
    return {"classification": classify_target(state["tsm"])}


def n3_select_weights(state: AvaliaState) -> dict[str, Any]:
    sel = select_weights(
        state["classification"], state["submission"].config, load_weight_profiles()
    )
    return {"effective_weights": sel.profile, "applicable_dims": sel.applicable_dims}


def _degrade_for_exhausted_fallback(dr: DimensionResult) -> DimensionResult:
    """CB-10: fallback de modelo esgotado → dimensão degrada para o score determinístico-âncora,
    confiança forçada a baixo e substituição DECLARADA (RNF-12, nunca silenciosa)."""
    subs = list(
        dict.fromkeys(
            [*dr.model_substitutions, "fallback de modelo esgotado — juiz indisponível (RNF-12)"]
        )
    )
    return dr.model_copy(
        update={
            "confidence": Confidence.BAIXO,
            "confidence_reason": (
                "Fallback de modelo esgotado; dimensão degradada para checagem determinística "
                "(RNF-12/CB-10)."
            ),
            "model_substitutions": subs,
        }
    )


def make_dimension_node(
    dimension: Dimension,
    gateway: GatewayLike | None = None,
    cache: JudgeCache | None = None,
) -> Callable[[AvaliaState], dict[str, Any]]:
    """Nó de avaliação de uma dimensão (fan-out). Se `gateway`, cabeia o juiz (T-302)."""
    evaluator = EVALUATORS[dimension]

    def node(state: AvaliaState) -> dict[str, Any]:
        tsm = state["tsm"]
        classification = state["classification"]
        contribution = (
            build_contribution(gateway, dimension, tsm, cache=cache)
            if gateway is not None
            else None
        )
        result = evaluator(tsm, classification, contribution=contribution)
        update: dict[str, Any] = {}
        # CB-10: juiz esgotou o fallback de modelo → degrada a dimensão e sinaliza laudo parcial.
        if contribution is not None and contribution.partial:
            result = _degrade_for_exhausted_fallback(result)
            update["budget"] = BudgetState(
                partial=True,
                reasons=[f"fallback de modelo esgotado na dimensão {dimension.value} (CB-10)"],
            )
        # reducer operator.add concatena os 7 ramos no fan-in (ordenação estável em aggregate).
        update["dimension_results"] = [result]
        return update

    return node


def make_budget_degraded_node() -> Callable[[AvaliaState], dict[str, Any]]:
    """Caminho parcial (T-802/CA-13): teto de custo/tempo atingido → pula a fan-out de juízes e
    avalia as 7 dimensões só com os checks determinísticos (baratos), marcando laudo parcial."""

    def node(state: AvaliaState) -> dict[str, Any]:
        tsm = state["tsm"]
        classification = state["classification"]
        reason = over_budget(state, state["submission"].config) or "teto de orçamento atingido"
        results = [EVALUATORS[d](tsm, classification, contribution=None) for d in Dimension]
        return {
            "dimension_results": results,
            "budget": BudgetState(
                partial=True,
                reasons=[f"{reason} — fan-out de juízes ignorado; análise determinística (CA-13)"],
            ),
        }

    return node


def route_after_weights(state: AvaliaState) -> list[str] | str:
    """N3 → fan-out das 7 dimensões, ou caminho degradado se estourou o budget (T-802)."""
    if over_budget(state, state["submission"].config):
        return "budget_degraded"
    return [f"dim_{d.value}" for d in Dimension]


def make_detect_divergence_node(
    gateway: GatewayLike | None = None,
    cache: JudgeCache | None = None,
) -> Callable[[AvaliaState], dict[str, Any]]:
    """N4 fan-in: detecta divergências e tenta reconciliar automaticamente (T-401/T-402)."""

    def node(state: AvaliaState) -> dict[str, Any]:
        config = state["submission"].config
        candidates = detect_candidates(state["dimension_results"], config)
        resolved: list[DivergenceRecord] = []
        pending: list[DivergenceCandidate] = []
        for candidate in candidates:
            record = (
                reconcile_candidate(candidate, gateway=gateway, tsm=state["tsm"], cache=cache)
                if gateway is not None
                else None
            )
            if record is not None:
                resolved.append(record)
            else:
                pending.append(candidate)
        return {"divergences": resolved, "pending_divergences": pending}

    return node


def n4h_human_gate(state: AvaliaState) -> dict[str, Any]:
    """N4h: pausa (interrupt) em divergência persistente; retoma com a decisão humana (T-404)."""
    pending = list(state.get("pending_divergences", []))
    if not pending:
        return {}
    raw = interrupt({"pending": [c.model_dump(mode="json") for c in pending]})
    decisions = [HumanDecision.model_validate(d) for d in raw]
    by_dim = {d.dimension: d for d in decisions}
    records = [
        DivergenceRecord(
            dimension=c.dimension,
            conflicting_positions=c.conflicting_positions,
            threshold_hit=c.threshold_hit,
            resolved_by=ResolvedBy.HUMANO,
            resolution_note=(by_dim[c.dimension].note if c.dimension in by_dim else "Decidido."),
        )
        for c in pending
    ]
    return {
        "divergences": list(state.get("divergences", [])) + records,
        "human_decisions": decisions,
        "pending_divergences": [],
    }


def route_after_divergence(state: AvaliaState) -> str:
    """N4 → human_gate (divergência persistente) vs. seguir para a agregação."""
    return "human" if state.get("pending_divergences") else "aggregate"


def n5_aggregate(state: AvaliaState) -> dict[str, Any]:
    agg = aggregate(
        state["dimension_results"], state["effective_weights"], state["submission"].config
    )
    return {"aggregate": agg}


def make_compare_history_node(
    repository: ReportRepository | None = None,
) -> Callable[[AvaliaState], dict[str, Any]]:
    """N6: compara com a versão anterior do mesmo alvo, se houver (T-605/CB-06)."""

    def node(state: AvaliaState) -> dict[str, Any]:
        if repository is None:
            return {"comparison": None}
        prev = repository.latest_for(state["submission"].metadata.target_id)
        if prev is None:
            return {"comparison": None}
        index = sorted({f.identity for dr in state["dimension_results"] for f in dr.findings})
        return {"comparison": compare(state["dimension_results"], index, prev)}

    return node


def make_build_report_node(
    repository: ReportRepository | None = None,
) -> Callable[[AvaliaState], dict[str, Any]]:
    """N7: monta o laudo (com comparação) e o persiste no repositório (T-701/T-603)."""

    def node(state: AvaliaState) -> dict[str, Any]:
        comparison = state.get("comparison")
        no_history = repository is not None and comparison is None
        budget = state.get("budget")
        budget_reasons = list(budget.reasons) if budget else []
        budget_partial = bool(budget and budget.partial)
        partial = bool(budget_partial or state["tsm"].coverage.sampled)
        report = build_report(
            classification=state["classification"],
            weights=state["effective_weights"],
            aggregate_score=state["aggregate"],
            results=state["dimension_results"],
            inventory=state["inventory"],
            tsm=state["tsm"],
            config=state["submission"].config,
            divergences=list(state.get("divergences", [])),
            comparison=comparison,
            no_history_note=no_history,
            partial=partial,
            partial_reasons=budget_reasons,
            budget_partial=budget_partial,
        )
        if repository is not None:
            repository.save(make_record(report, state["submission"].metadata))
        return {"report": report, "status": RunStatus.PARTIAL if partial else RunStatus.OK}

    return node


def route_after_ingest(state: AvaliaState) -> str:
    """N0 → END(erro) sem laudo (CA-01) vs. seguir para a indexação."""
    return "error" if state.get("status") is RunStatus.ERROR else "continue"
