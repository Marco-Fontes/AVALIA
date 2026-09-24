"""Guarda T-008 (v1.4, DQ-03 / RNF-06): nenhuma constante de pontuação nos avaliadores.

Nota base e penalidades são parâmetros da avaliação (`ScoringConfig`), nunca constantes internas
(spec RNF-06). Esta guarda analisa a AST de `src/avalia/evaluators/` e falha se reaparecer uma
atribuição de módulo a nome `*_SCORE`/`*_PENALTY` (padrão que existia antes da v1.4).
Só LÊ o código do próprio AVALIA como texto; nada é importado nem executado (RNF-05).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.fast

_EVALUATORS = Path(__file__).resolve().parents[2] / "src" / "avalia" / "evaluators"
_FORBIDDEN = re.compile(r"(^|_)(SCORE|PENALTY|PENALTIES)$", re.IGNORECASE)


def _module_level_names(tree: ast.Module) -> list[str]:
    names: list[str] = []
    for node in tree.body:
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        names += [t.id for t in targets if isinstance(t, ast.Name)]
    return names


def test_no_module_level_scoring_constants_in_evaluators():
    files = sorted(_EVALUATORS.glob("*.py"))
    assert files, "diretório de avaliadores não encontrado"
    offenders = [
        f"{path.name}: {name}"
        for path in files
        for name in _module_level_names(ast.parse(path.read_text(encoding="utf-8")))
        if _FORBIDDEN.search(name)
    ]
    assert offenders == [], f"constantes de pontuação devem ir para ScoringConfig: {offenders}"


def test_guard_detects_the_old_pattern():
    old = "_BASE_SCORE = 90\n_CRITICAL_PENALTY = 22\nRUBRIC = 'x'\n"
    names = _module_level_names(ast.parse(old))
    assert [n for n in names if _FORBIDDEN.search(n)] == ["_BASE_SCORE", "_CRITICAL_PENALTY"]
