"""T-101 / T1.2 — Registro de extratores por linguagem (seleção por extensão).

Resolve "python" e "config" (YAML/JSON/TOML/INI/`.env`). Linguagem sem extrator registrado →
`None` (o builder trata como best-effort/baixa confiança, sem quebrar). Plugável: somar
tree-sitter/TS é registrar outro extrator, sem tocar o TSM (resolução #1).
"""

from __future__ import annotations

from avalia.extract.base import LanguageExtractor
from avalia.extract.config_extractor import CONFIG_EXTENSIONS, ConfigExtractor
from avalia.extract.config_extractor import LANGUAGE as CONFIG_LANGUAGE
from avalia.extract.python_extractor import PythonExtractor
from avalia.extract.treesitter_extractor import (
    JavaScriptExtractor,
    TypeScriptExtractor,
    is_available,
)

__all__ = [
    "ConfigExtractor",
    "JavaScriptExtractor",
    "TypeScriptExtractor",
    "get_extractor",
    "is_structural_only",
    "language_for_path",
    "register",
]

# M10: TS/JS via tree-sitter. .tsx → typescript (best-effort; JSX gera ERROR tolerável).
_JS_EXTS = (".js", ".jsx", ".mjs", ".cjs")
_TS_EXTS = (".ts", ".tsx", ".mts", ".cts")

_REGISTRY: dict[str, LanguageExtractor] = {}
_EXT_TO_LANG = {
    ".py": "python",
    **{ext: CONFIG_LANGUAGE for ext in CONFIG_EXTENSIONS},
    **{ext: "javascript" for ext in _JS_EXTS},
    **{ext: "typescript" for ext in _TS_EXTS},
}


def register(extractor: LanguageExtractor) -> None:
    _REGISTRY[extractor.language] = extractor


def get_extractor(language: str) -> LanguageExtractor | None:
    return _REGISTRY.get(language)


# Linguagens analisadas SÓ estruturalmente (tree-sitter, sem inferência de tipos) → confiança
# reduzida declarada no laudo (RNF-08; plan §3.1). Python (ast) é first-class e não entra aqui.
STRUCTURAL_ONLY_LANGS = frozenset({"javascript", "typescript"})


def language_for_path(path: str) -> str | None:
    lower = path.lower()
    for ext, lang in _EXT_TO_LANG.items():
        if lower.endswith(ext):
            return lang
    return None


def is_structural_only(path: str) -> bool:
    """O arquivo é de uma linguagem analisada só estruturalmente (best-effort, M10)?"""
    return language_for_path(path) in STRUCTURAL_ONLY_LANGS


register(PythonExtractor())
register(ConfigExtractor())
# TS/JS só são registrados se a gramática tree-sitter estiver instalada; senão os arquivos
# caem em best-effort (sem quebrar o import — gramática é dependência declarada, não garantida).
if is_available("javascript"):
    register(JavaScriptExtractor())
if is_available("typescript"):
    register(TypeScriptExtractor())
