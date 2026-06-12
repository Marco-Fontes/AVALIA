"""T-803 — Streaming `astream_events` (plan §3.12).

Dirige a corrotina de streaming com `asyncio.run` (sem depender de plugin). O grafo roda sobre
texto estático; nada executa o alvo (RNF-05).
"""

from __future__ import annotations

import asyncio

import pytest

from avalia.domain.submission import Submission, TargetMetadata
from avalia.graph.build_graph import build_avalia_graph
from avalia.graph.streaming import ProgressEvent, stream_progress

pytestmark = pytest.mark.fast

_META = TargetMetadata(target_id="alvo", version="v1")
_SRC = (
    "from langgraph.graph import StateGraph\n"
    "def agent_a(state):\n    return state\n"
    "def build(g):\n    g.add_edge('agent_a', 'agent_b')\n"
)


def _collect() -> list[ProgressEvent]:
    async def main() -> list[ProgressEvent]:
        graph = build_avalia_graph()
        inp = {"submission": Submission(artifact_files={"graph.py": _SRC}, metadata=_META)}
        return [e async for e in stream_progress(graph, inp, {"configurable": {"thread_id": "t"}})]

    return asyncio.run(main())


def test_stream_emits_per_dimension_progress_and_terminal_node():
    events = _collect()
    assert events
    # progresso dimensão a dimensão: cada ramo do fan-out emite um node_end com score
    dim_scores = {
        e.node: e.score for e in events if e.node.startswith("dim_") and e.kind == "node_end"
    }
    assert len(dim_scores) == 7
    assert all(s is not None for s in dim_scores.values())
    # ciclo de vida: começo e fim de nós, terminando no build_report
    assert any(e.kind == "node_start" for e in events)
    assert any(e.node == "build_report" and e.kind == "node_end" for e in events)
