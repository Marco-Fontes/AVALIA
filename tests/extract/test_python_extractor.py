"""T-102/T-103 — testes do extrator Python (`ast`) e do construtor do TSM.

DoD: extrai cada categoria com símbolo correto; loop sem teto detectado; arquivo inválido
marcado unreadable sem quebrar; NADA executa/importa o alvo (só ast.parse).
Rastreabilidade: RF-14, RNF-07, RNF-05.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from avalia.extract.python_extractor import PythonExtractor
from avalia.extract.tsm_builder import build_tsm

pytestmark = pytest.mark.fast

_MULTI = """
from typing import TypedDict


class PipelineState(TypedDict):
    q: str


PLANNER_PROMPT = "Você é o planejador."
SOLVER_PROMPT = "Você é o executor."


def solver_agent(state):
    while True:
        state = step(state)


def step(state):
    return state


def build(graph):
    graph.add_edge("planner", "solver")
"""

_BOUNDED = """
def loop_ok():
    total = 0
    for i in range(10):
        total += i
    return total
"""


def test_extracts_loop_without_cap():
    r = PythonExtractor().extract({"alvo/main.py": _MULTI})
    loops = [loop for loop in r.loops if not loop.has_cap]
    assert len(loops) == 1
    assert loops[0].kind == "while"
    assert loops[0].evidence.symbol.startswith("solver_agent")
    assert loops[0].evidence.file_path == "alvo/main.py"


def test_for_range_is_capped():
    r = PythonExtractor().extract({"alvo/x.py": _BOUNDED})
    assert r.loops and all(loop.has_cap for loop in r.loops)


def test_extracts_prompts_edges_state():
    r = PythonExtractor().extract({"alvo/main.py": _MULTI})
    assert len(r.prompts) >= 2  # dois prompts distintos
    assert any(e.source == "planner" and e.target == "solver" for e in r.edges)
    assert any(s.kind == "typed_dict" for s in r.shared_state)


def test_evidence_has_symbol_not_only_line():
    r = PythonExtractor().extract({"alvo/main.py": _MULTI})
    for prompt in r.prompts:
        assert prompt.evidence.symbol  # nunca vazio (regra inviolável 5)


def test_invalid_file_marked_unreadable_without_crash():
    r = PythonExtractor().extract({"alvo/bad.py": "def f(:\n  pass"})
    assert r.unreadable_files == ["alvo/bad.py"]


def test_build_tsm_merges_and_is_immutable():
    tsm = build_tsm({"alvo/main.py": _MULTI, "README.md": "# não-python"})
    assert "alvo/main.py" in tsm.coverage.fully_analyzed
    assert "README.md" in tsm.coverage.sampled  # best-effort (sem extrator)
    assert any(not loop.has_cap for loop in tsm.loops)
    with pytest.raises(ValidationError):
        tsm.loops = []  # frozen
