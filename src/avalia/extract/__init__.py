"""Extração estática do alvo (plan §3.1). Leitura por `ast`/tree-sitter — NUNCA execução.

O alvo é texto inerte (RNF-05/S-04). A interface `LanguageExtractor` é plugável por
linguagem (resolução #1); o M1 entrega apenas o extrator Python (`ast`).
"""

from __future__ import annotations
