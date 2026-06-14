"""T-901 — Tracing não-bloqueante (MS-10): spans in-process + LangSmith opcional.

O grafo roda sobre texto estático; nada executa o alvo (RNF-05). LangSmith NÃO é exigido.
"""

from __future__ import annotations

import pytest

from avalia.domain.submission import Submission, TargetMetadata
from avalia.graph.build_graph import build_avalia_graph
from avalia.obs.spans import NodeSpan, SpanCollector
from avalia.obs.tracing import instrument_config, is_tracing_enabled, langsmith_callbacks

pytestmark = pytest.mark.fast

_META = TargetMetadata(target_id="alvo", version="v1")
_SRC = (
    "from langgraph.graph import StateGraph\n"
    "def agent_a(state):\n    return state\n"
    "def build(g):\n    g.add_edge('agent_a', 'agent_b')\n"
)


def _run(collector: SpanCollector | None = None, env=None) -> dict:
    graph = build_avalia_graph()
    cfg = instrument_config({"configurable": {"thread_id": "t"}}, env=env, collector=collector)
    sub = Submission(artifact_files={"graph.py": _SRC}, metadata=_META)
    return graph.invoke({"submission": sub}, config=cfg)


def test_tracing_disabled_yields_no_langsmith_callbacks():
    assert is_tracing_enabled({}) is False
    assert langsmith_callbacks({}) == []  # ausência/desligado nunca levanta (plan §3.11)


def test_report_is_generated_without_langsmith():
    # DoD MS-10: o laudo gera mesmo sem observabilidade configurada (não-bloqueante).
    result = _run(env={})
    assert result.get("report") is not None


def test_spancollector_records_per_node_latency():
    collector = SpanCollector()
    result = _run(collector=collector, env={})
    assert result.get("report") is not None  # tracing não interfere no laudo
    nodes = {s.node for s in collector.node_spans()}
    # spans aparecem por nó do grafo (latência sempre registrada)
    assert {"ingest", "classify", "build_report"} <= nodes
    assert any(n.startswith("dim_") for n in nodes)
    assert all(isinstance(s, NodeSpan) and s.duration_s >= 0.0 for s in collector.spans)


def test_instrument_config_merges_collector_callback():
    collector = SpanCollector()
    cfg = instrument_config({"configurable": {"x": 1}}, env={}, collector=collector)
    assert collector in cfg["callbacks"]
    assert cfg["configurable"] == {"x": 1}  # preserva o config original
