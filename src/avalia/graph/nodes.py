"""Funções dos nós do grafo (T-201..204, T-308 wiring, T-501, T-701).

Cada nó lê/escreve o `AvaliaState` e delega à lógica pura (ingest/classify/weights/evaluators/
aggregate/report). Nada executa o alvo (RNF-05) — só lê o TSM e fala com modelos via gateway.
O juiz da Trajetória é injetado opcionalmente (M1 roda determinístico por padrão).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from avalia.aggregate import aggregate
from avalia.classify import classify_target
from avalia.config.weight_profiles import load_weight_profiles
from avalia.domain.enums import RunStatus
from avalia.domain.tsm import TargetStaticModel
from avalia.evaluators.trajetoria import evaluate_trajetoria
from avalia.extract.tsm_builder import build_tsm
from avalia.graph.state import AvaliaState
from avalia.ingest import ingest_validate
from avalia.judge.base import JudgeContribution
from avalia.report.build import build_report
from avalia.weights_select import select_weights

# Contribuição do juiz para a Trajetória, dado o TSM (None = determinístico puro).
TrajetoriaContributor = Callable[[TargetStaticModel], JudgeContribution]


def n0_ingest(state: AvaliaState) -> dict[str, Any]:
    out = ingest_validate(state["submission"])
    update: dict[str, Any] = {"inventory": out.inventory, "status": out.status}
    if out.error_message is not None:
        update["error_message"] = out.error_message
    return update


def n1_index(state: AvaliaState) -> dict[str, Any]:
    return {"tsm": build_tsm(state["submission"].artifact_files)}


def n2_classify(state: AvaliaState) -> dict[str, Any]:
    return {"classification": classify_target(state["tsm"])}


def n3_select_weights(state: AvaliaState) -> dict[str, Any]:
    sel = select_weights(
        state["classification"], state["submission"].config, load_weight_profiles()
    )
    return {"effective_weights": sel.profile, "applicable_dims": sel.applicable_dims}


def make_trajetoria_node(
    contributor: TrajetoriaContributor | None = None,
) -> Callable[[AvaliaState], dict[str, Any]]:
    def node(state: AvaliaState) -> dict[str, Any]:
        tsm = state["tsm"]
        contribution = contributor(tsm) if contributor is not None else None
        # reducer operator.add concatena no fan-in (M2); aqui só a Trajetória escreve.
        return {"dimension_results": [evaluate_trajetoria(tsm, contribution)]}

    return node


def n5_aggregate(state: AvaliaState) -> dict[str, Any]:
    agg = aggregate(
        state["dimension_results"], state["effective_weights"], state["submission"].config
    )
    return {"aggregate": agg}


def n7_build_report(state: AvaliaState) -> dict[str, Any]:
    report = build_report(
        classification=state["classification"],
        weights=state["effective_weights"],
        aggregate_score=state["aggregate"],
        results=state["dimension_results"],
        inventory=state["inventory"],
        tsm=state["tsm"],
        config=state["submission"].config,
    )
    return {"report": report, "status": RunStatus.OK}


def route_after_ingest(state: AvaliaState) -> str:
    """N0 → END(erro) sem laudo (CA-01) vs. seguir para a indexação."""
    return "error" if state.get("status") is RunStatus.ERROR else "continue"
