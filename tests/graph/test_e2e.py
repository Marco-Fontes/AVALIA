"""T-801 — testes de integração ponta-a-ponta do grafo (fatia M1).

Valida CA-01 (erro sem laudo), CA-02 (borderline), CA-05 (reasoning), CA-09 (condição
rastreável). Fixtures são lidas como TEXTO (nunca importadas/executadas — RNF-05). O caminho
do juiz é exercitado com `ModelGateway` MOCKADO (sem modelo real).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from avalia.config.evaluator_config import RetryPolicy
from avalia.domain.enums import Band, Confidence, RunStatus, Topology, Verdict
from avalia.domain.submission import Submission, TargetMetadata
from avalia.graph.build_graph import build_avalia_graph
from avalia.judge.framework import JudgeVerdict

pytestmark = pytest.mark.fast

_FIX = Path(__file__).resolve().parents[1] / "fixtures"
_META = TargetMetadata(target_id="alvo", version="v1")


def _load(name: str) -> dict[str, str]:
    d = _FIX / name
    return {f.name: f.read_text(encoding="utf-8") for f in d.glob("*.py")}


def _run(sub: Submission, gateway=None) -> dict:
    graph = build_avalia_graph(gateway=gateway)
    return graph.invoke({"submission": sub}, config={"configurable": {"thread_id": "t"}})


def test_ca01_missing_source_errors_without_report():
    sub = Submission(artifact_files={"README.md": "# docs"}, metadata=_META)
    result = _run(sub)
    assert result["status"] is RunStatus.ERROR
    assert result.get("report") is None  # CA-01: nenhum laudo
    assert "código-fonte" in result["error_message"]


def test_ca02_single_agent_is_borderline_with_report():
    sub = Submission(artifact_files=_load("agente_unico"), metadata=_META)
    result = _run(sub)
    report = result["report"]
    assert report.header.classification.topology is Topology.AGENTE_UNICO_BORDERLINE
    assert report.header.classification.classification_conf is not None  # confiança explícita
    assert report.header.classification.caveats  # ressalva (RF-07)


def test_ca05_every_dimension_has_reasoning():
    sub = Submission(artifact_files=_load("agente_unico"), metadata=_META)
    report = _run(sub)["report"]
    assert report.dimensions
    assert all(dr.reasoning.strip() for dr in report.dimensions)


def test_ca09_loop_sem_teto_produces_traceable_condition():
    sub = Submission(artifact_files=_load("multiagente_loop_sem_teto"), metadata=_META)
    report = _run(sub)["report"]
    assert report.header.classification.topology is Topology.MULTIAGENTE
    assert report.header.verdict is Verdict.APROVACAO_CONDICIONAL
    assert report.approval_conditions
    cond = report.approval_conditions[0]
    assert "Adicionar teto de iteração no nó" in cond.statement
    # rastreável a um achado real do laudo (CA-09)
    identities = {f.identity for dr in report.dimensions for f in dr.findings}
    assert cond.traces_to in identities


# ---- caminho do juiz via gateway MOCKADO (RNF-12 plumbing ponta-a-ponta) ----


class _FakeStructured:
    def __init__(self, behavior):
        self._behavior = behavior

    def invoke(self, messages):
        return self._behavior()


class _FakeGateway:
    def with_structured_output(self, node_type, role, schema):
        return _FakeStructured(
            lambda: JudgeVerdict(
                score=72, band=Band.PRONTO, confidence=Confidence.MEDIO, reasoning="rota coerente"
            )
        )

    def retry_for(self, node_type):
        return RetryPolicy(max_attempts=2)


def test_judge_opinions_flow_through_all_dimensions_with_mock_gateway():
    # Com gateway injetado, os 7 nós de dimensão cabeiam o juiz (T-302) — sem modelo real.
    sub = Submission(artifact_files=_load("multiagente_loop_sem_teto"), metadata=_META)
    report = _run(sub, gateway=_FakeGateway())["report"]
    assert len(report.dimensions) == 7
    # toda dimensão recebeu opinião do juiz, com a rubrica versionada da sua dimensão
    for dr in report.dimensions:
        assert dr.judge_opinions, dr.dimension
        assert dr.judge_opinions[0].rubric_id.startswith(dr.dimension.value)


_RAG = """
from typing import TypedDict


class S(TypedDict):
    q: str


RETRIEVER_PROMPT = "Recupere documentos e cite a fonte de cada contexto recuperado."
ANSWER_PROMPT = "Responda usando apenas o contexto, com citação das fontes."


def build(g):
    g.add_edge("retriever", "answerer")
"""


def test_ca03_rag_profile_weights_hallucination_higher():
    from avalia.domain.enums import Dimension
    from avalia.domain.weights import WeightSource

    sub = Submission(artifact_files={"rag.py": _RAG}, metadata=_META)
    report = _run(sub)["report"]
    weights = report.header.effective_weights
    assert weights.source is WeightSource.INFERIDO  # perfil inferido pelo tipo (RAG)
    assert weights.weights[Dimension.ALUCINACAO] > 1.0 / 7  # > neutro (CA-03)
