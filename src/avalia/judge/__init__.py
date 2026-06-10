"""Juiz-LLM (plan §3.2/§3.6). Acesso a modelo só via `ModelGateway` (RNF-12).

Conteúdo do alvo é DADO não confiável: sempre delimitado, nunca tratado como instrução
(R8/T-310). temperature=0 e rubrica versionada (RNF-01).
"""

from __future__ import annotations
