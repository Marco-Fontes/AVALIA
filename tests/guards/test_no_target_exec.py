"""CC-T01 / T-1006 — Rede de regressão contínua do invariante RNF-05.

Varre src/**/*.py e falha se encontrar execução/importação de código do alvo.
Complementa o hook CC-H01 (que pega na escrita): este pega na regressão, em todo
marco. Em M0 (src/ vazio) o teste é skip — ainda não há o que varrer.

Rastreabilidade: RNF-05, S-04, T-1006.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"

FORBIDDEN_CALLS = {"exec", "eval", "__import__"}
FORBIDDEN_ATTR = {("os", "system")}


def _src_files() -> list[Path]:
    return list(SRC.rglob("*.py")) if SRC.exists() else []


@pytest.mark.skipif(
    not _src_files(), reason="M0: src/ ainda vazio (T-1006 ativa quando houver código)"
)
def test_no_target_execution_in_src() -> None:
    offenders: list[str] = []
    for f in _src_files():
        if "fixtures" in f.parts:  # dado estático do alvo
            continue
        tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = node.func
                if isinstance(fn, ast.Name) and fn.id in FORBIDDEN_CALLS:
                    offenders.append(f"{f}:{node.lineno} {fn.id}()")
                if isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name):
                    if (fn.value.id, fn.attr) in FORBIDDEN_ATTR:
                        offenders.append(f"{f}:{node.lineno} {fn.value.id}.{fn.attr}()")
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                mod = getattr(node, "module", "") or ""
                names = " ".join(a.name for a in node.names)
                if "importlib" in mod or "runpy" in mod or "importlib" in names or "runpy" in names:
                    offenders.append(f"{f}:{node.lineno} import {mod or names}")
                if mod.startswith("tests.fixtures"):
                    offenders.append(f"{f}:{node.lineno} import {mod} (alvo)")
    assert not offenders, "RNF-05 violado — o AVALIA não executa o alvo:\n" + "\n".join(offenders)
