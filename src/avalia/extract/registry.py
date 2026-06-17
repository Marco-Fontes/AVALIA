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

__all__ = ["ConfigExtractor", "get_extractor", "language_for_path", "register"]

_REGISTRY: dict[str, LanguageExtractor] = {}
_EXT_TO_LANG = {".py": "python", **{ext: CONFIG_LANGUAGE for ext in CONFIG_EXTENSIONS}}


def register(extractor: LanguageExtractor) -> None:
    _REGISTRY[extractor.language] = extractor


def get_extractor(language: str) -> LanguageExtractor | None:
    return _REGISTRY.get(language)


def language_for_path(path: str) -> str | None:
    lower = path.lower()
    for ext, lang in _EXT_TO_LANG.items():
        if lower.endswith(ext):
            return lang
    return None


register(PythonExtractor())
register(ConfigExtractor())
