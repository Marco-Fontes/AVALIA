"""T-801 — testes de integração ponta-a-ponta do grafo (fatia M1).

Valida CA-01 (erro sem laudo), CA-02 (borderline), CA-05 (reasoning), CA-09 (condição
rastreável). Fixtures são lidas como TEXTO (nunca importadas/executadas — RNF-05). O caminho
do juiz é exercitado com `ModelGateway` MOCKADO (sem modelo real).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from avalia.config.evaluator_config import RetryPolicy
from avalia.domain.enums import Band, Confidence, Dimension, RunStatus, Topology, Verdict
from avalia.domain.submission import Submission, TargetMetadata
from avalia.graph.build_graph import build_avalia_graph
from avalia.judge.framework import Judge, JudgeVerdict
from avalia.judge.rubrics import get_rubric

pytestmark = pytest.mark.fast

_FIX = Path(__file__).resolve().parents[1] / "fixtures"
_META = TargetMetadata(target_id="alvo", version="v1")


def _load(name: str) -> dict[str, str]:
    d = _FIX / name
    return {f.name: f.read_text(encoding="utf-8") for f in d.glob("*.py")}


def _run(sub: Submission, contributor=None) -> dict:
    graph = build_avalia_graph(contributor=contributor)
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


def test_judge_opinions_flow_through_graph_with_mock_gateway():
    judge = Judge(_FakeGateway(), "juiz_trajetoria")

    def contribute(tsm):
        content = {p.evidence.file_path: p.text for p in tsm.prompts} or {"_": "(sem prompts)"}
        evidence = [p.evidence for p in tsm.prompts][:1]
        return judge.assess(
            dimension=Dimension.TRAJETORIA,
            rubric=get_rubric("trajetoria/v1"),
            instruction="Avalie a Trajetória.",
            angles=["cetico"],
            target_content=content,
            evidence=evidence,
        )

    sub = Submission(artifact_files=_load("multiagente_loop_sem_teto"), metadata=_META)
    report = _run(sub, contributor=contribute)["report"]
    trajetoria = next(dr for dr in report.dimensions if dr.dimension is Dimension.TRAJETORIA)
    assert trajetoria.judge_opinions  # opinião do juiz chegou ao laudo
    assert trajetoria.judge_opinions[0].rubric_id == "trajetoria/v1"
