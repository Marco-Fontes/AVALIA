"""M7 / E10 — Suíte de aceite FECHADA: um teste explícito por CA-01..15 e CB-01..10.

Todos os testes são **black-box** sobre o grafo de avaliação (constroem o grafo, invocam e
asseguram sobre o `EvaluationReport`/status), espelhando o mapa caso→teste do plan §8. Reaproveitam
fixtures estáticas; juízes são MOCKADOS quando o caso exige divergência/fallback. NADA executa o
alvo (RNF-05/S-04) — inclusive CA-12 prova isso comportamentalmente.

Mapa caso→teste (resumo):
  CA-01 erro sem laudo · CA-02 borderline · CA-03 perfil RAG · CA-04 fallback neutro ·
  CA-05 reasoning · CA-06 confiança baixa s/ harness · CA-07 limitação comportamental ·
  CA-08 dimensão N/A + renormalização · CA-09 condição rastreável · CA-10 divergência auto ·
  CA-11 divergência → humano · CA-12 nunca executa o alvo · CA-13 laudo parcial ·
  CA-14 (ver test_reproducibility) · CA-15 comparação de versões.
  CB-01 opcionais ausentes · CB-02 ilegível · CB-03 não-multiagente · CB-04 divergência registrada ·
  CB-05 amostragem · CB-06 sem histórico · CB-07 pesos inválidos · CB-08 contradições ·
  CB-09 tipo não inferível · CB-10 fallback de modelo esgotado.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from avalia.config.evaluator_config import EvaluatorConfig, RetryPolicy
from avalia.domain.contracts import HumanDecision
from avalia.domain.enums import (
    Band,
    Confidence,
    Dimension,
    RunStatus,
    Topology,
    Verdict,
)
from avalia.domain.submission import Submission, TargetMetadata
from avalia.domain.taxonomy import FindingType
from avalia.domain.weights import WeightSource
from avalia.graph.build_graph import build_avalia_graph
from avalia.hitl.approval import StaticApprovalProvider
from avalia.hitl.runner import run_evaluation
from avalia.judge.framework import JudgeVerdict, ModelUnavailableError
from avalia.persistence.repository import InMemoryReportRepository

pytestmark = pytest.mark.fast

_FIX = Path(__file__).resolve().parents[1] / "fixtures"
_META = TargetMetadata(target_id="alvo", version="v1")


def _load(name: str) -> dict[str, str]:
    return {f.name: f.read_text(encoding="utf-8") for f in (_FIX / name).glob("*.py")}


def _run(files: dict[str, str], *, gateway=None, config=None, repo=None, tid="t") -> dict:
    graph = build_avalia_graph(gateway=gateway, repository=repo)
    sub = Submission(artifact_files=files, metadata=_META, config=config or EvaluatorConfig())
    return graph.invoke({"submission": sub}, config={"configurable": {"thread_id": tid}})


def _report(files: dict[str, str], **kw):
    return _run(files, **kw)["report"]


def _dim(report, dimension: Dimension):
    return next(dr for dr in report.dimensions if dr.dimension is dimension)


# --- alvos inline ---

_RAG = """
from typing import TypedDict


class S(TypedDict):
    q: str


RETRIEVER_PROMPT = "Recupere documentos e cite a fonte de cada contexto recuperado."
ANSWER_PROMPT = "Responda usando apenas o contexto, com citação das fontes."


def build(g):
    g.add_edge("retriever", "answerer")
"""

_FIXED_LOOP = """
from typing import TypedDict


class State(TypedDict):
    q: str


PLANNER_PROMPT = "Planeje a resposta."


def planner(state):
    return state


def worker(state):
    for _ in range(5):
        state = step(state)
    return state


def step(state):
    return state


def build(g):
    g.add_edge("planner", "worker")
"""

# Alvo cujo TOPO de módulo levantaria erro SE fosse executado — prova de não-execução (CA-12).
_BOMB = """
SYSTEM_PROMPT = "responda"


def agent_a(state):
    return state


def build(g):
    g.add_edge("agent_a", "agent_b")


raise RuntimeError("EXECUTADO: o AVALIA jamais deve rodar o alvo (RNF-05)")
"""


# ----------------------------- juízes mockados -----------------------------


def _v(band: Band, conf: Confidence = Confidence.ALTO) -> JudgeVerdict:
    return JudgeVerdict(score=70, band=band, confidence=conf, reasoning="r")


class _ScriptedClient:
    def __init__(self, gw, node_type):
        self._gw, self._node_type = gw, node_type

    def invoke(self, messages):
        return self._gw.next_verdict(self._node_type)


class ScriptedGateway:
    """Fila de JudgeVerdict por node_type; `default` para os demais juízes (convergentes)."""

    def __init__(self, scripts, default):
        self._scripts = {k: list(v) for k, v in scripts.items()}
        self._default = default

    def with_structured_output(self, node_type, role, schema):
        return _ScriptedClient(self, node_type)

    def retry_for(self, node_type):
        return RetryPolicy(max_attempts=2)

    def next_verdict(self, node_type):
        q = self._scripts.get(node_type)
        return q.pop(0) if q else self._default


def _robustez_gateway(reconcile_bands: list[Band]) -> ScriptedGateway:
    script = {
        "juiz_robustez": [_v(Band.PRONTO), _v(Band.INSUFICIENTE), *[_v(b) for b in reconcile_bands]]
    }
    return ScriptedGateway(script, default=_v(Band.PRONTO))


class _ExhaustedClient:
    def invoke(self, messages):
        raise ModelUnavailableError("modelo indisponível")


class ExhaustedGateway:
    """Primário e fallback indisponíveis (CB-10)."""

    def with_structured_output(self, node_type, role, schema):
        return _ExhaustedClient()

    def retry_for(self, node_type):
        return RetryPolicy(max_attempts=1)


# ============================ Critérios de Aceite (CA) ============================


def test_ca01_missing_source_errors_without_report():
    result = _run({"README.md": "# docs"})
    assert result["status"] is RunStatus.ERROR
    assert result.get("report") is None
    assert "código-fonte" in result["error_message"]


def test_ca02_single_agent_borderline_with_caveat():
    report = _report(_load("agente_unico"))
    cls = report.header.classification
    assert cls.topology is Topology.AGENTE_UNICO_BORDERLINE
    assert cls.classification_conf is not None
    assert cls.caveats  # ressalva declarada (RF-07)


def test_ca03_rag_profile_weights_hallucination_above_neutral():
    report = _report({"rag.py": _RAG})
    w = report.header.effective_weights
    assert w.source is WeightSource.INFERIDO
    assert w.weights[Dimension.ALUCINACAO] > 1.0 / 7


def test_ca04_uninferable_type_falls_back_to_neutral():
    report = _report(_load("agente_unico"))
    assert report.header.effective_weights.source is WeightSource.FALLBACK_NEUTRO


def test_ca05_every_dimension_has_reasoning():
    report = _report(_load("multiagente_loop_sem_teto"))
    assert report.dimensions
    assert all(dr.reasoning.strip() for dr in report.dimensions)


def test_ca06_no_harness_lowers_quality_confidence():
    report = _report(_load("multiagente_loop_sem_teto"))  # sem arquivos de teste
    qual = _dim(report, Dimension.QUALIDADE)
    assert qual.confidence is Confidence.BAIXO
    assert "harness" in (qual.confidence_reason or "").lower()


def test_ca07_hallucination_declares_behavioral_limitation():
    report = _report(_load("multiagente_loop_sem_teto"))
    aluc = _dim(report, Dimension.ALUCINACAO)
    assert aluc.static_limitations and aluc.static_limitations.strip()


def test_ca08_inapplicable_dimension_excluded_no_artificial_low_score():
    report = _report(_load("agente_unico"))
    traj = _dim(report, Dimension.TRAJETORIA)
    assert traj.applicable is False and traj.score is None  # excluída, sem nota artificial
    assert 0 <= report.header.score <= 100


def test_ca09_loop_sem_teto_yields_traceable_condition():
    report = _report(_load("multiagente_loop_sem_teto"))
    assert report.header.verdict is Verdict.APROVACAO_CONDICIONAL
    assert report.approval_conditions
    cond = report.approval_conditions[0]
    assert "teto de iteração" in cond.statement
    identities = {f.identity for dr in report.dimensions for f in dr.findings}
    assert cond.traces_to in identities


def test_ca10_divergence_reconciled_automatically_no_hitl():
    gw = _robustez_gateway([Band.ADEQUADO_COM_RESSALVAS, Band.ADEQUADO_COM_RESSALVAS])
    result = _run(_load("multiagente_loop_sem_teto"), gateway=gw, tid="ca10")
    assert "__interrupt__" not in result
    div = [d for d in result["report"].divergences if d.dimension is Dimension.ROBUSTEZ]
    assert div and div[0].resolved_by.value == "auto"


def test_ca11_persistent_divergence_escalates_to_human():
    gw = _robustez_gateway([Band.PRONTO, Band.INSUFICIENTE])
    graph = build_avalia_graph(gateway=gw)
    provider = StaticApprovalProvider(
        [
            HumanDecision(
                dimension=Dimension.ROBUSTEZ,
                chosen_band=Band.INSUFICIENTE,
                note="mantenho a ressalva",
            )
        ]
    )
    result = run_evaluation(
        graph,
        {
            "submission": Submission(
                artifact_files=_load("multiagente_loop_sem_teto"), metadata=_META
            )
        },
        approval_provider=provider,
        thread_id="ca11",
    )
    div = [d for d in result["report"].divergences if d.dimension is Dimension.ROBUSTEZ]
    assert div and div[0].resolved_by.value == "humano"


def test_ca12_target_is_never_executed():
    # _BOMB levantaria RuntimeError no import; como o AVALIA só faz parse estático, o run conclui.
    report = _report({"bomb.py": _BOMB})
    assert report is not None  # nenhum RuntimeError → o alvo NÃO foi executado (RNF-05)
    assert report.header.score is not None


def test_ca13_large_artifact_yields_partial_report():
    files = {f"noise{i}.py": "x = 1\n" for i in range(12)}
    files["graph.py"] = _RAG
    result = _run(files, config=EvaluatorConfig(max_analyzed_files=2))
    assert result["status"] is RunStatus.PARTIAL
    report = result["report"]
    assert report.metadata.coverage.sampled
    assert any(lim.startswith("Laudo PARCIAL") for lim in report.metadata.known_limitations)


def test_ca15_version_comparison_lists_changes():
    repo = InMemoryReportRepository()
    _run(_load("multiagente_loop_sem_teto"), repo=repo, tid="v1")  # v1: loop sem teto
    report = _report({"fixed.py": _FIXED_LOOP}, repo=repo, tid="v2")  # v2: loop com teto
    cmp = report.comparison
    assert cmp is not None
    assert cmp.improvements or cmp.resolved_findings  # melhoria/achado resolvido detectado


# ============================ Casos de Borda (CB) ============================


def test_cb01_missing_optional_components_recorded_and_proceeds():
    result = _run(_load("multiagente_loop_sem_teto"))
    report = result["report"]
    assert result["status"] in (RunStatus.OK, RunStatus.PARTIAL)  # prossegue
    assert {"harness", "instrumentacao"} <= set(report.metadata.inventory.missing)
    assert _dim(report, Dimension.QUALIDADE).confidence is Confidence.BAIXO  # impacto declarado


def test_cb02_obfuscated_file_reduces_confidence():
    report = _report(_load("ofuscado"))
    assert report.metadata.readability.unreadable_files
    # dimensões impactadas pela ilegibilidade → confiança baixa (CB-02)
    assert all(dr.confidence is Confidence.BAIXO for dr in report.dimensions if dr.applicable)


def test_cb03_non_multiagent_is_not_refused():
    report = _report(_load("agente_unico"))
    assert report.header.classification.topology is Topology.AGENTE_UNICO_BORDERLINE
    assert not _dim(report, Dimension.TRAJETORIA).applicable  # inaplicável marcada, não recusada


def test_cb04_reconciled_divergence_is_recorded():
    gw = _robustez_gateway([Band.ADEQUADO_COM_RESSALVAS, Band.ADEQUADO_COM_RESSALVAS])
    report = _report(_load("multiagente_loop_sem_teto"), gateway=gw, tid="cb04")
    assert any(d.dimension is Dimension.ROBUSTEZ for d in report.divergences)


def test_cb05_sampling_declares_coverage():
    files = {f"noise{i}.py": "x = 1\n" for i in range(8)}
    files["graph.py"] = _RAG
    report = _report(files, config=EvaluatorConfig(max_analyzed_files=2))
    assert len(report.metadata.coverage.sampled) == 7
    assert report.metadata.coverage.fully_analyzed


def test_cb06_no_history_emits_note_without_comparison():
    repo = InMemoryReportRepository()
    report = _report(_load("multiagente_loop_sem_teto"), repo=repo, tid="solo")
    assert report.comparison is None
    assert any("cb-06" in lim.lower() for lim in report.metadata.known_limitations)


def test_cb07_invalid_weights_rejected_before_analysis():
    from pydantic import ValidationError

    with pytest.raises((ValidationError, ValueError)):
        EvaluatorConfig(weights={Dimension.CUSTO: -1.0})


def test_cb08_config_code_contradictions_become_findings():
    report = _report(_load("contradicao_config_codigo"))
    types = {f.finding_type for dr in report.dimensions for f in dr.findings}
    assert FindingType.CONTRADICAO_MODELO_CONFIG in types
    assert FindingType.CONTRADICAO_FLUXO_PROMPT in types


def test_cb09_uninferable_type_declares_neutral_fallback():
    report = _report(_load("agente_unico"))
    assert report.header.effective_weights.source is WeightSource.FALLBACK_NEUTRO
    assert report.header.classification.system_type is None


def test_cb10_exhausted_model_fallback_degrades_and_marks_partial():
    result = _run(_load("multiagente_loop_sem_teto"), gateway=ExhaustedGateway(), tid="cb10")
    assert result["status"] is RunStatus.PARTIAL
    report = result["report"]
    subs = [s for dr in report.dimensions for s in dr.model_substitutions]
    assert any("fallback de modelo esgotado" in s for s in subs)
    assert any(dr.confidence is Confidence.BAIXO for dr in report.dimensions)
