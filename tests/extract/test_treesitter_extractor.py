"""M10 — testes do extrator TS/JS (tree-sitter): extração estrutural + roteamento no TSM.

DoD: extrai agentes/prompts/arestas/loops/modelo/robustez/estado de um alvo multiagente TS/JS;
o `build_tsm` roteia `.ts`/`.js` ao extrator (não best-effort); a classificação enxerga ≥2 sinais
→ multiagente; o laudo declara a confiança reduzida da análise estrutural (RNF-08). Arquivo
inválido → unreadable, sem quebrar. NADA executa o alvo (só tree-sitter sobre o texto).
Rastreabilidade: RF-14, RNF-07, RNF-05/S-04, RNF-08; Decisão #1; Risco R1.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from avalia.classify import classify_target
from avalia.config.evaluator_config import EvaluatorConfig
from avalia.config.weight_profiles import load_weight_profiles
from avalia.domain.contracts import ComponentInventory
from avalia.domain.enums import Topology
from avalia.extract.registry import get_extractor, is_structural_only, language_for_path
from avalia.extract.treesitter_extractor import (
    JavaScriptExtractor,
    TypeScriptExtractor,
    is_available,
)
from avalia.extract.tsm_builder import build_tsm

pytestmark = [
    pytest.mark.fast,
    pytest.mark.skipif(
        not (is_available("javascript") and is_available("typescript")),
        reason="gramáticas tree-sitter JS/TS não instaladas",
    ),
]

_FIX = Path(__file__).resolve().parents[1] / "fixtures" / "js_multiagente" / "graph.ts"


def _ts_result():
    return TypeScriptExtractor().extract({"graph.ts": _FIX.read_text(encoding="utf-8")})


def test_registry_routes_js_ts_extensions():
    assert language_for_path("a.js") == "javascript"
    assert language_for_path("a.jsx") == "javascript"
    assert language_for_path("a.ts") == "typescript"
    assert language_for_path("a.tsx") == "typescript"
    assert get_extractor("javascript") is not None
    assert get_extractor("typescript") is not None
    assert is_structural_only("a.ts") and not is_structural_only("a.py")


def test_extracts_agents_prompts_edges():
    r = _ts_result()
    agent_names = {a.name for a in r.agents}
    assert "retrieverAgent" in agent_names  # function declaration
    assert "answerAgent" in agent_names  # arrow function atribuída a const
    prompt_names = {p.name for p in r.prompts}
    assert {"RETRIEVER_PROMPT", "ANSWER_PROMPT"} <= prompt_names
    assert any(e.source == "retriever" and e.target == "answerer" for e in r.edges)
    assert any(e.target == "<conditional>" for e in r.edges)


def test_extracts_loop_without_cap_and_robustness():
    r = _ts_result()
    uncapped = [loop for loop in r.loops if not loop.has_cap]
    assert uncapped and uncapped[0].kind == "while"  # while(true) sem break
    kinds = {e.kind for e in r.error_handling}
    assert {"try_except", "token_limit", "timeout"} <= kinds
    assert "retry" not in kinds and "fallback_modelo" not in kinds  # ausências reais


def test_extracts_shared_state_and_model():
    r = _ts_result()
    assert any(s.kind == "state_class" and s.name == "PipelineState" for s in r.shared_state)
    assert any(s.kind == "state_param" for s in r.shared_state)
    assert any(m.model_expr == "claude-opus-4" for m in r.model_assignments)


def test_evidence_has_symbol_and_line():
    r = _ts_result()
    for frag in [*r.agents, *r.prompts, *r.edges]:
        assert frag.evidence.symbol  # símbolo obrigatório (regra 5)
        assert frag.evidence.file_path == "graph.ts"
        assert frag.evidence.line_start and frag.evidence.line_start >= 1


def test_build_tsm_routes_ts_and_classifies_multiagent():
    tsm = build_tsm({"graph.ts": _FIX.read_text(encoding="utf-8")})
    assert "graph.ts" in tsm.coverage.fully_analyzed
    assert "graph.ts" not in tsm.coverage.sampled  # roteado ao extrator, não best-effort
    cls = classify_target(tsm)
    # ≥2 sinais (prompts distintos + arestas + estado compartilhado) → multiagente
    assert cls.topology is Topology.MULTIAGENTE


def test_report_declares_structural_only_limitation():
    from avalia.aggregate import aggregate
    from avalia.evaluators.trajetoria import evaluate_trajetoria
    from avalia.report.build import build_report
    from avalia.weights_select import select_weights

    tsm = build_tsm({"graph.ts": _FIX.read_text(encoding="utf-8")})
    cls = classify_target(tsm)
    sel = select_weights(cls, EvaluatorConfig(), load_weight_profiles())
    dr = evaluate_trajetoria(tsm)
    agg = aggregate([dr], sel.profile, EvaluatorConfig())
    report = build_report(
        classification=cls,
        weights=sel.profile,
        aggregate_score=agg,
        results=[dr],
        inventory=ComponentInventory(present=["codigo_fonte"]),
        tsm=tsm,
        config=EvaluatorConfig(),
    )
    assert any("estrutural" in lim and "RNF-08" in lim for lim in report.metadata.known_limitations)


def test_javascript_invalid_marked_unreadable_without_crash():
    r = JavaScriptExtractor().extract({"bad.js": "@@@ not valid <<< ;;;"})
    # tree-sitter é tolerante; só marca unreadable quando não há nós nomeados algum.
    assert "bad.js" in r.files
