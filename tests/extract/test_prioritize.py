"""T-105 — Priorização por sinal + amostragem (RF-12, CB-05, CA-13).

Verifica o ranking estável/determinístico e a amostragem acima do teto de cobertura.
"""

from __future__ import annotations

import pytest

from avalia.config.evaluator_config import EvaluatorConfig
from avalia.extract.prioritize import rank_files
from avalia.extract.tsm_builder import build_tsm

pytestmark = pytest.mark.fast

_GRAPH = "from langgraph.graph import StateGraph\ndef build(g):\n    g.add_edge('a', 'b')\n"
_PROMPT = "SYSTEM_PROMPT = 'instruções do agente'\n"
_NOISE = "x = 1\n"


def test_graph_file_ranks_above_noise():
    files = {"noise.py": _NOISE, "graph.py": _GRAPH, "prompts.py": _PROMPT}
    ranked = rank_files(files)
    assert ranked[0] == "graph.py"
    assert ranked.index("prompts.py") < ranked.index("noise.py")


def test_ranking_is_stable_and_deterministic():
    files = {f"f{i}.py": _NOISE for i in range(5)}
    assert rank_files(files) == rank_files(files)  # estável
    assert rank_files(files) == sorted(files)  # empate → ordem por caminho


def test_sampling_keeps_high_signal_and_declares_coverage():
    files = {f"noise{i}.py": _NOISE for i in range(8)}
    files["graph.py"] = _GRAPH
    tsm = build_tsm(files, EvaluatorConfig(max_analyzed_files=2))
    # CA-13/RF-12: acima do teto, só os de maior sinal são analisados a fundo; o resto é amostrado.
    assert "graph.py" in tsm.coverage.fully_analyzed
    assert len(tsm.coverage.fully_analyzed) == 2
    assert len(tsm.coverage.sampled) == 7
    assert tsm.coverage.reason and "amostrad" in tsm.coverage.reason
