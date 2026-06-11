"""Grafo de avaliação (LangGraph `StateGraph`) — plan §1.1/§5.

A análise nunca executa o alvo (RNF-05); o grafo só lê fatos do TSM e fala com modelos via
`ModelGateway`. M1 entrega a fatia N0→N1→N2→N3→[Trajetória]→N5→N7.
"""

from __future__ import annotations
