"""AVALIA — avaliador ESTÁTICO de sistemas multiagentes de IA (Fase 1).

O AVALIA é o avaliador; o sistema avaliado é o ALVO — apenas ENTRADA, nunca executado
(RNF-05 / S-04). Este pacote contém somente o código do próprio avaliador; toda inferência
vem de leitura estática (ast / tree-sitter) dos artefatos do alvo.
"""

from __future__ import annotations

__version__ = "0.0.0"
