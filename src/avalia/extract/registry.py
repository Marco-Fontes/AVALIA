"""T-101 — Registro de extratores por linguagem (seleção por extensão).

Resolve "python" no M1. Linguagem sem extrator registrado → `None` (o builder trata como
best-effort/baixa confiança, sem quebrar). Plugável: somar tree-sitter/TS é registrar outro
extrator, sem tocar o TSM (resolução #1).
"""

from __future__ import annotations

from avalia.extract.base import LanguageExtractor
from avalia.extract.python_extractor import PythonExtractor

_REGISTRY: dict[str, LanguageExtractor] = {}
_EXT_TO_LANG = {".py": "python"}


def register(extractor: LanguageExtractor) -> None:
    _REGISTRY[extractor.language] = extractor


def get_extractor(language: str) -> LanguageExtractor | None:
    return _REGISTRY.get(language)


def language_for_path(path: str) -> str | None:
    for ext, lang in _EXT_TO_LANG.items():
        if path.endswith(ext):
            return lang
    return None


register(PythonExtractor())
